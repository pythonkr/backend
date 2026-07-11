from __future__ import annotations

from django.db.models import TextChoices
from rest_framework import serializers


class Operation(TextChoices):
    CREATE = "create", "추가"
    UPDATE = "update", "수정"
    DELETE = "delete", "삭제"


class OperationListSerializer(serializers.ListSerializer):
    """`op` 필드로 항목별 추가/수정/삭제를 지시하는 부분반영 리스트.

    목록에 없는 항목은 건드리지 않으며, DRF 가 항목별 검증을 인덱스로 집계한다.
    child 는 `Meta.model` 을 가져야 한다(soft-delete `filter_active()` 전제).
    pk 는 서버가 소유한다 — create 는 서버가 pk 를 생성하고, update/delete 는 `id` 로 대상을 지정한다.
    실제 저장은 부모 직렬화기가 순서를 통제하며 `apply()` 를 호출한다.
    """

    def run_child_validation(self, data: dict) -> dict:
        if not isinstance(data, dict):
            raise serializers.ValidationError("객체 형식이어야 합니다.")

        op = data.get("op")
        if op not in Operation.values:
            raise serializers.ValidationError({"op": f"{list(Operation.values)} 중 하나여야 합니다."})

        pk = data.get("id")
        if op == Operation.CREATE:
            validated = dict(self.child.__class__(context=self.context).run_validation(data))
        else:
            if pk is None:
                raise serializers.ValidationError({"id": "update/delete 에는 id 가 필요합니다."})
            if not (instance := self.child.get_operation_queryset().filter(pk=pk).first()):
                raise serializers.ValidationError({"id": "존재하지 않는 항목입니다."})
            if op == Operation.DELETE:
                return {"op": Operation.DELETE.value, "id": instance.pk}
            validated = dict(
                self.child.__class__(instance=instance, partial=True, context=self.context).run_validation(data)
            )

        validated["op"] = op
        validated.setdefault("id", pk)
        return validated

    def apply(self, operations: list[dict], **create_defaults) -> list:
        model = self.child.Meta.model
        # name 과 attname(FK 의 `_id` 등) 을 모두 허용 — 도메인이 room_id 같은 attname 으로 값을 넘길 수 있다.
        model_fields = {n for f in model._meta.get_fields() for n in (f.name, getattr(f, "attname", f.name))}
        results = []
        for attrs in operations:
            op = attrs["op"]
            pk = attrs.get("id")
            fields = {key: value for key, value in attrs.items() if key != "id" and key in model_fields}
            if op == Operation.CREATE:
                results.append(model.objects.create(**create_defaults, **fields))
            elif op == Operation.UPDATE:
                instance = self.child.get_operation_queryset().get(pk=pk)
                for field, value in fields.items():
                    setattr(instance, field, value)
                instance.save()
                results.append(instance)
            else:
                instance = self.child.get_operation_queryset().get(pk=pk)
                instance.delete()
                results.append(instance)
        return results


class OperationSerializer(serializers.Serializer):
    """op 기반 부분반영 항목의 공통 필드(id·op)와 list_serializer_class 를 제공하는 믹스인.

    사용: `class Foo(OperationSerializer, serializers.ModelSerializer)` 로 ModelSerializer 와 함께 상속하고,
    `class Meta(OperationSerializer.Meta): model = ...; fields = OperationSerializer.Meta.fields + (...)`.

    - id: 이미 존재하는 항목의 pk. update/delete 대상 지정용(editable=False pk 는 기본 read-only 라 명시 선언).
    - op: 검증·분기는 OperationListSerializer 가 담당하고, 이 필드는 문서화(spectacular)·validated_data 포함용.

    create 항목을 같은 요청 안에서 참조해야 하는 링크 토큰(ref 등)은 도메인 하위 직렬화기에 직접 선언하고
    부모 직렬화기가 resolve 한다 — apply 는 모델 필드만 반영하므로 비모델 필드는 저장되지 않는다.
    """

    id = serializers.UUIDField(required=False)
    op = serializers.ChoiceField(choices=Operation.choices, write_only=True)

    def get_operation_queryset(self):
        return self.Meta.model.objects.filter_active()

    class Meta:
        fields = ("id", "op")
        list_serializer_class = OperationListSerializer
