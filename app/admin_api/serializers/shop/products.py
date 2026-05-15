from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.nested_model_serializer import (
    InstanceListSerializer,
    NestedFieldModelSerializer,
    NestedFieldSpec,
    NestedModelSerializer,
)
from file.models import PublicFile
from rest_framework import serializers
from shop.product.models import Category, CategoryGroup, Option, OptionGroup, Product, Tag


class CategoryGroupAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, NestedFieldModelSerializer):
    class CategoryAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, NestedModelSerializer):
        id = serializers.UUIDField(required=False, help_text="기존 Category 수정 시 PK 전달, 새로 추가 시 생략")

        class Meta:
            model = Category
            fields = COMMON_ADMIN_FIELDS + ("group", "name", "priority")
            # group 은 NestedFieldSpec.parent_fk_name 으로 부모 인스턴스에서 주입되므로 입력 시 생략 가능.
            # validators=[] — auto UniqueTogetherValidator(group, name) 가 group 누락 시 required 로 막음.
            # DB unique constraint(uq__cat__grp_nm) 가 여전히 enforce.
            extra_kwargs = {"group": {"required": False}}
            validators: list = []
            list_serializer_class = InstanceListSerializer

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
        return attrs


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
            "hidden",
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
        merged = {**attrs}
        if self.instance is not None:
            for field in ("visible_starts_at", "visible_ends_at", "orderable_starts_at", "orderable_ends_at"):
                merged.setdefault(field, getattr(self.instance, field, None))

        v_start = merged.get("visible_starts_at")
        v_end = merged.get("visible_ends_at")
        o_start = merged.get("orderable_starts_at")
        o_end = merged.get("orderable_ends_at")

        errors: dict[str, str] = {}
        if v_start and o_start and o_start < v_start:
            errors["orderable_starts_at"] = "판매 시작은 노출 시작 이후여야 합니다."
        if v_end and o_end and o_end > v_end:
            errors["orderable_ends_at"] = "판매 종료는 노출 종료 이전이어야 합니다."

        if errors:
            raise serializers.ValidationError(errors)
        return attrs
