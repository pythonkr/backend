import typing

from django.core.exceptions import FieldDoesNotExist
from django.db.models import Model
from django.db.models.manager import BaseManager
from rest_framework import serializers, settings
from rest_framework.utils import model_meta

if typing.TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise
else:
    StrOrPromise = str | typing.Callable[[], str]


class InstanceListSerializer(serializers.ListSerializer):
    error_messages: dict[str, StrOrPromise]
    allow_empty: bool
    max_length: int | None
    min_length: int | None
    default_error_messages: dict[str, StrOrPromise] = (  # type: ignore[misc]
        serializers.ListSerializer.default_error_messages
        | {"data_and_instance_not_equal_length": "The length of data and instance must be equal."}
    )

    def _validate_data(self, data: list[dict] | typing.Any) -> list[dict]:
        message: StrOrPromise
        if not isinstance(data, list):
            message = self.error_messages["not_a_list"].format(input_type=type(data).__name__)
            raise serializers.ValidationError(
                {settings.api_settings.NON_FIELD_ERRORS_KEY: [message]}, code="not_a_list"
            )

        if not self.allow_empty and not data:
            message = self.error_messages["empty"]
            raise serializers.ValidationError({settings.api_settings.NON_FIELD_ERRORS_KEY: [message]}, code="empty")

        if self.max_length is not None and len(data) > self.max_length:
            message = self.error_messages["max_length"].format(max_length=self.max_length)
            raise serializers.ValidationError(
                {settings.api_settings.NON_FIELD_ERRORS_KEY: [message]}, code="max_length"
            )

        if self.min_length is not None and len(data) < self.min_length:
            message = self.error_messages["min_length"].format(min_length=self.min_length)
            raise serializers.ValidationError(
                {settings.api_settings.NON_FIELD_ERRORS_KEY: [message]}, code="min_length"
            )

        if self.instance and len(data) != len(self.instance):
            message = self.error_messages["data_and_instance_not_equal_length"]
            raise serializers.ValidationError(
                {settings.api_settings.NON_FIELD_ERRORS_KEY: [message]}, code="not_equal_length"
            )

        return data

    def to_internal_value(self, data: list[dict]) -> list[dict]:
        assert isinstance(self.child, serializers.BaseSerializer)  # nosec: B101

        data = self._validate_data(data)
        ret, errors = [], []

        # self.instance 가 명시적으로 set 된 경우(예: instance=tags) length 가 _validate_data 에서 검증됨 →
        # id 미지정 시 위치 기반 매칭이 안전. parent 에서 fetch 한 경우는 length 검증 없으므로 위치 매칭 금지.
        has_explicit_instance = self.instance is not None
        child_instances = self.instance or (
            self.parent and self.parent.instance and getattr(self.parent.instance, self.source or self.field_name)
        )
        if isinstance(child_instances, BaseManager):
            child_instances = list(child_instances.all())

        for index, item in enumerate(data):
            try:
                self.child.initial_data = item
                self.child.context["index"] = index
                # 매 iteration 마다 초기화 — id 없는 항목은 create 모드로 검증.
                self.child.instance = None
                if child_instances and "id" in item:
                    target_instance = next((i for i in child_instances if str(i.id) == str(item["id"])), None)
                    if not target_instance:
                        raise serializers.ValidationError("유효하지 않은 ID입니다.", code="not_found")
                    self.child.instance = target_instance
                elif child_instances and has_explicit_instance:
                    self.child.instance = child_instances[index]
                validated = self.run_child_validation(item)
            except serializers.ValidationError as exc:
                errors.append(exc.detail)
            else:
                ret.append(validated)
                errors.append({})

        if any(errors):
            raise serializers.ValidationError(errors)

        return ret


class NestedModelSerializer(serializers.ModelSerializer):
    list_serializer_class = InstanceListSerializer
    default_error_messages: dict[str, StrOrPromise] = (  # type: ignore[misc]
        serializers.ModelSerializer.default_error_messages | {"not_found": "The ID is not found."}
    )

    def _update_child_instance(self, serializer_obj: serializers.BaseSerializer, instance: Model, data: dict) -> None:
        child_serializer = serializer_obj.__class__(instance, data=data)
        child_serializer.is_valid(raise_exception=True)
        child_serializer.save()

    def _update_list_instances(self, field: serializers.ListSerializer, data: list[dict]) -> None:
        if (instances := getattr(self.instance, field.source or field.field_name)) and isinstance(
            instances, BaseManager
        ):
            instances = list(instances.all())

        instance_dict = {str(i.pk): i for i in instances}
        for datum in data:
            if child_instance := instance_dict.get(str(datum.get("id"))):
                self._update_child_instance(typing.cast(serializers.BaseSerializer, field.child), child_instance, datum)

    def update(self, instance: Model, validated_data: dict) -> Model:
        info: model_meta.FieldInfo = model_meta.get_field_info(instance.__class__)
        m2m_fields: list[tuple[str, typing.Any]] = []

        for field_name, value in validated_data.items():
            if (field := self.fields[field_name]).read_only:
                continue

            if isinstance(field, serializers.BaseSerializer):
                if isinstance(field, serializers.ListSerializer):
                    self._update_list_instances(field, value)
                elif instance := getattr(instance, field_name):
                    self._update_child_instance(field, instance, value)
            elif field_name in info.relations and info.relations[field_name].to_many:
                m2m_fields.append((field_name, value))
            else:
                setattr(instance, field_name, value)
        instance.save()

        for attr, value in m2m_fields:
            field_name = getattr(instance, attr)
            field_name.set(value)

        return instance


class NestedFieldSpec(typing.NamedTuple):
    related_manager_name: str  # parent 의 reverse manager 속성명 (예: "category_set", "options")
    child_model: type[Model]  # 자식 모델 클래스
    parent_fk_name: str  # 자식 모델에서 parent 를 가리키는 FK 필드명 (예: "group")


class NestedFieldModelSerializer(NestedModelSerializer):
    def __init_subclass__(cls, **kwargs: typing.Any) -> None:
        super().__init_subclass__(**kwargs)
        if (meta := getattr(cls, "Meta", None)) is None:
            return

        nested_fields = getattr(meta, "nested_fields", None)
        if not isinstance(nested_fields, dict):
            raise TypeError(f"{cls.__name__}.Meta must define `nested_fields: dict[str, NestedFieldSpec]`.")

        parent_model: type[Model] = meta.model
        for key, spec in nested_fields.items():
            if not hasattr(parent_model, spec.related_manager_name):
                raise TypeError(
                    f"{cls.__name__}.Meta.nested_fields[{key!r}]: "
                    f"{parent_model.__name__} has no attribute {spec.related_manager_name!r}."
                )
            try:
                spec.child_model._meta.get_field(spec.parent_fk_name)
            except FieldDoesNotExist as e:
                raise TypeError(
                    f"{cls.__name__}.Meta.nested_fields[{key!r}]: "
                    f"{spec.child_model.__name__} has no field {spec.parent_fk_name!r}."
                ) from e

    def create(self, validated_data: dict) -> Model:
        nested_data = {k: validated_data.pop(k, []) or [] for k in self.Meta.nested_fields}
        instance = super().create(validated_data)
        self._apply_nested_sync(instance, nested_data)
        return instance

    def update(self, instance: Model, validated_data: dict) -> Model:
        nested_data = {k: validated_data.pop(k, None) for k in self.Meta.nested_fields}
        instance = super().update(instance, validated_data)
        self._apply_nested_sync(instance, nested_data)
        return instance

    def _apply_nested_sync(self, instance: Model, nested_data: dict[str, list[dict] | None]) -> None:
        for key, children_data in nested_data.items():
            if children_data is None:
                continue
            spec = self.Meta.nested_fields[key]
            rel_mgr = getattr(instance, spec.related_manager_name)
            active_children_qs = rel_mgr.filter_active() if hasattr(rel_mgr, "filter_active") else rel_mgr.all()
            existing = {child.id: child for child in active_children_qs}
            provided_ids: set = set()

            for child_data in (dict(d) for d in children_data):
                child_id = child_data.pop("id", None)
                child_data.pop(spec.parent_fk_name, None)  # FK 는 parent 로 고정, 입력값 무시
                if child_id and (existing_child := existing.get(child_id)):
                    for k, v in child_data.items():
                        setattr(existing_child, k, v)
                    existing_child.save()
                    provided_ids.add(child_id)
                else:
                    spec.child_model.objects.create(**{spec.parent_fk_name: instance, **child_data})

            for child_id, child in existing.items():
                if child_id not in provided_ids:
                    child.delete()
