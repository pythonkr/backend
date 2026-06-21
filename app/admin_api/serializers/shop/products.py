import re

from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.nested_model_serializer import (
    InstanceListSerializer,
    NestedFieldModelSerializer,
    NestedFieldSpec,
    NestedModelSerializer,
)
from core.util.timespan import TimeSpan
from document.models import IssuedDocument
from event.models import Event
from file.models import PublicFile
from rest_framework import serializers
from shop.order.models import OrderProductRelation
from shop.product.models import Category, CategoryGroup, Option, OptionGroup, Product, Tag


class CategoryGroupAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, NestedFieldModelSerializer):
    class CategoryAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, NestedModelSerializer):
        id = serializers.UUIDField(required=False, help_text="기존 Category 수정 시 PK 전달, 새로 추가 시 생략")
        event = serializers.PrimaryKeyRelatedField(
            queryset=Event.objects.filter_active(), allow_null=True, required=False
        )

        class Meta:
            model = Category
            fields = COMMON_ADMIN_FIELDS + ("group", "name", "priority", "is_ticket", "event")
            # group 은 NestedFieldSpec.parent_fk_name 으로 부모 인스턴스에서 주입되므로 입력 시 생략 가능.
            # validators=[] — auto UniqueTogetherValidator(group, name) 가 group 누락 시 required 로 막음.
            # DB unique constraint(uq__cat__grp_nm) 가 여전히 enforce.
            extra_kwargs = {"group": {"required": False}}
            validators: list = []
            list_serializer_class = InstanceListSerializer

        def validate(self, attrs: dict) -> dict:
            if self.instance is None:
                return attrs
            new_is_ticket = attrs.get("is_ticket", self.instance.is_ticket)
            if new_is_ticket != self.instance.is_ticket:
                self._validate_is_ticket_change(new_is_ticket=new_is_ticket)
            self._validate_issued_certificate_prerequisites(attrs)
            return attrs

        def _validate_is_ticket_change(self, *, new_is_ticket: bool) -> None:
            purchased = OrderProductRelation.objects.filter_active().filter(
                product__category=self.instance,
                status__in=OrderProductRelation.PURCHASED_STOCK_STATUS,
            )
            if new_is_ticket:
                if purchased.filter(ticket_info__isnull=True).exists():
                    msg = "참가자 정보가 없는 구매 건이 있어 티켓으로 전환할 수 없습니다."
                    raise serializers.ValidationError({"is_ticket": msg})
            elif purchased.filter(ticket_info__isnull=False).exists():
                msg = "참가자 정보가 수집된 티켓 구매 건이 있어 티켓 설정을 해제할 수 없습니다."
                raise serializers.ValidationError({"is_ticket": msg})

        def _validate_issued_certificate_prerequisites(self, attrs: dict) -> None:
            errors = {}
            if not attrs.get("is_ticket", self.instance.is_ticket):
                errors["is_ticket"] = "이미 발급된 참가확인서가 있어 is_ticket 을 해제할 수 없습니다."
            if not attrs.get("event", self.instance.event_id):
                errors["event"] = "이미 발급된 참가확인서가 있어 event 연결을 해제할 수 없습니다."
            if not errors:
                return
            if (
                OrderProductRelation.objects.filter_active()
                .filter(product__category=self.instance, issued_documents__in=IssuedDocument.objects.filter_active())
                .exists()
            ):
                raise serializers.ValidationError(errors)

    categories = CategoryAdminSerializer(many=True, required=False, source="category_set")
    category_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CategoryGroup
        fields = COMMON_ADMIN_FIELDS + ("name", "priority", "categories", "category_count")
        nested_fields = {
            "category_set": NestedFieldSpec(
                related_manager_name="category_set",
                child_model=Category,
                parent_fk_name="group",
            ),
        }


class CategoryReadAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    # 독립 카테고리 읽기/choices 용. CategoryGroupAdminSerializer 내부 nested CategoryAdminSerializer 와 이름 충돌 방지.
    group = serializers.PrimaryKeyRelatedField(queryset=CategoryGroup.objects.filter_active())
    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.filter_active(), allow_null=True, required=False)

    class Meta:
        model = Category
        fields = COMMON_ADMIN_FIELDS + ("group", "name", "priority", "is_ticket", "event")


class TagAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    leftover_stock = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Tag
        fields = COMMON_ADMIN_FIELDS + ("name_ko", "name_en", "stock", "max_quantity_per_user", "leftover_stock")


class OptionGroupAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, NestedFieldModelSerializer):
    class OptionAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, NestedModelSerializer):
        id = serializers.UUIDField(required=False, help_text="기존 Option 수정 시 PK 전달, 새로 추가 시 생략")
        leftover_stock = serializers.IntegerField(read_only=True, allow_null=True)

        class Meta:
            model = Option
            fields = COMMON_ADMIN_FIELDS + (
                "group",
                "priority",
                "name_ko",
                "name_en",
                "max_quantity_per_user",
                "additional_price",
                "stock",
                "leftover_stock",
            )
            # group 은 NestedFieldSpec.parent_fk_name 으로 부모 인스턴스에서 주입되므로 입력 시 생략 가능.
            extra_kwargs = {"group": {"required": False}}
            list_serializer_class = InstanceListSerializer

    options = OptionAdminSerializer(many=True, required=False)

    class Meta:
        model = OptionGroup
        fields = COMMON_ADMIN_FIELDS + (
            "product",
            "priority",
            "name_ko",
            "name_en",
            "min_quantity_per_product",
            "max_quantity_per_product",
            "max_quantity_per_user",
            "visible_starts_at",
            "visible_ends_at",
            "orderable_starts_at",
            "orderable_ends_at",
            "is_custom_response",
            "custom_response_pattern",
            "response_modifiable_ends_at",
            "options",
        )
        nested_fields = {
            "options": NestedFieldSpec(
                related_manager_name="options",
                child_model=Option,
                parent_fk_name="group",
            ),
        }

    def validate_custom_response_pattern(self, value: str | None) -> str | None:
        if value:
            try:
                re.compile(value)
            except re.error as exc:
                raise serializers.ValidationError(f"유효하지 않은 정규표현식입니다: {exc}") from exc
        return value

    def validate(self, attrs: dict) -> dict:
        # is_custom_response=True 면 패턴이 admin 계약 — 빈 답변 허용은 ".*", 비공란 강제는 ".+" 등으로 명시.
        is_custom_response = attrs.get("is_custom_response", getattr(self.instance, "is_custom_response", False))
        custom_response_pattern = attrs.get(
            "custom_response_pattern", getattr(self.instance, "custom_response_pattern", None)
        )
        if is_custom_response and not custom_response_pattern:
            raise serializers.ValidationError(
                {"custom_response_pattern": "is_custom_response=True 일 때 custom_response_pattern 은 필수입니다."}
            )

        if errors := self._validate_period(attrs):
            raise serializers.ValidationError(errors)
        return attrs

    # 메시지 템플릿 — visible / orderable 둘 다 같은 구조라 label 만 치환.
    _GROUP_PERIOD_LABELS = (("visible", "노출"), ("orderable", "판매"))

    def _validate_period(self, attrs: dict) -> dict[str, str]:
        merged = {**attrs}
        for field in (
            "visible_starts_at",
            "visible_ends_at",
            "orderable_starts_at",
            "orderable_ends_at",
            "min_quantity_per_product",
            "product",
        ):
            if self.instance is not None:
                merged.setdefault(field, getattr(self.instance, field, None))

        product: Product = merged["product"]
        min_qty = merged.get("min_quantity_per_product") or 0

        errors: dict[str, str] = {}
        for kind, label in self._GROUP_PERIOD_LABELS:
            span = TimeSpan(merged.get(f"{kind}_starts_at"), merged.get(f"{kind}_ends_at"))
            parent = getattr(product, f"{kind}_period")
            errors.update(self._check_group_span(span, parent, kind=kind, label=label))
            if min_qty >= 1:
                # 필수 옵션 그룹은 상품 기간과 동기되어야 한다 — 그룹 starts_at 이 늦거나 ends_at 이 일찍이면
                # 상품은 노출/판매되는데 필수 옵션을 채울 수 없는 죽은 구간이 생기므로 그룹 단위 윈도우 지정 금지.
                if span.starts_at is not None:
                    msg = f"필수 옵션 그룹의 {label} 시작은 별도로 지정할 수 없습니다 (상품 기준)."
                    errors[f"{kind}_starts_at"] = msg
                if span.ends_at is not None:
                    msg = f"필수 옵션 그룹의 {label} 종료는 별도로 지정할 수 없습니다 (상품 기준)."
                    errors[f"{kind}_ends_at"] = msg

        return errors

    @staticmethod
    def _check_group_span(span: TimeSpan, parent: TimeSpan, *, kind: str, label: str) -> dict[str, str]:
        # 그룹의 visible/orderable 윈도우 검증 — 자기 inverted + 상품 윈도우 안 포함 + 한 boundary fallback inverted.
        errors: dict[str, str] = {}
        if span.is_inverted:
            errors[f"{kind}_starts_at"] = f"옵션 그룹의 {label} 시작은 {label} 종료 이전이어야 합니다."
        if span.starts_before(parent):
            errors[f"{kind}_starts_at"] = f"옵션 그룹의 {label} 시작은 상품 {label} 시작 이후여야 합니다."
        if span.ends_after(parent):
            errors[f"{kind}_ends_at"] = f"옵션 그룹의 {label} 종료는 상품 {label} 종료 이전이어야 합니다."
        # 한 쪽 boundary 만 명시하면 model effective_*_period (None → product fallback) 가 inverted 될 수 있다.
        # 예: product=[2020,2099], group ends_at=2019 → effective=[2020,2019]. admin 이 잡는다.
        if span.ends_at and span.ends_at < parent.effective_starts_at:
            errors[f"{kind}_ends_at"] = f"옵션 그룹의 {label} 종료는 상품 {label} 시작 이후여야 합니다."
        if span.starts_at and span.starts_at > parent.effective_ends_at:
            errors[f"{kind}_starts_at"] = f"옵션 그룹의 {label} 시작은 상품 {label} 종료 이전이어야 합니다."
        return errors


class ProductAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    option_groups = OptionGroupAdminSerializer(many=True, read_only=True)
    tag_set = serializers.PrimaryKeyRelatedField(many=True, queryset=Tag.objects.filter_active(), required=False)
    tag_set_detail = TagAdminSerializer(many=True, read_only=True, source="tag_set")
    leftover_stock = serializers.IntegerField(read_only=True, allow_null=True)
    current_status = serializers.ChoiceField(choices=Product.CurrentStatus.choices, read_only=True)
    image = serializers.PrimaryKeyRelatedField(
        queryset=PublicFile.objects.filter_active(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Product
        fields = COMMON_ADMIN_FIELDS + (
            "name_ko",
            "name_en",
            "description_ko",
            "description_en",
            "image",
            "price",
            "stock",
            "max_quantity_per_user",
            "visible_starts_at",
            "visible_ends_at",
            "orderable_starts_at",
            "orderable_ends_at",
            "refundable_ends_at",
            "category",
            "priority",
            "donation_allowed",
            "donation_min_price",
            "donation_max_price",
            "option_groups",
            "tag_set",
            "tag_set_detail",
            "leftover_stock",
            "current_status",
        )

    def validate(self, attrs: dict) -> dict:
        if errors := self._validate_period(attrs):
            raise serializers.ValidationError(errors)
        return attrs

    def _validate_period(self, attrs: dict) -> dict[str, str]:
        """visible/orderable 윈도우 검증 — partial update 대비 merged 패턴."""
        merged = {**attrs}
        if self.instance is not None:
            for field in ("visible_starts_at", "visible_ends_at", "orderable_starts_at", "orderable_ends_at"):
                merged.setdefault(field, getattr(self.instance, field, None))

        visible = TimeSpan(merged.get("visible_starts_at"), merged.get("visible_ends_at"))
        orderable = TimeSpan(merged.get("orderable_starts_at"), merged.get("orderable_ends_at"))

        errors: dict[str, str] = {}
        if visible.is_inverted:
            errors["visible_starts_at"] = "노출 시작은 노출 종료 이전이어야 합니다."
        if orderable.is_inverted:
            errors["orderable_starts_at"] = "판매 시작은 판매 종료 이전이어야 합니다."
        if orderable.starts_before(visible):
            errors["orderable_starts_at"] = "판매 시작은 노출 시작 이후여야 합니다."
        if orderable.ends_after(visible):
            errors["orderable_ends_at"] = "판매 종료는 노출 종료 이전이어야 합니다."
        return errors
