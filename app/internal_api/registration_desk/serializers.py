import re
import typing

from core.serializer.nested_model_serializer import InstanceListSerializer, NestedModelSerializer
from drf_spectacular.utils import extend_schema_field
from event.models import Event
from internal_api.models import RegistrationDeskConfig
from rest_framework import exceptions, serializers
from shop.order.models import (
    CustomerInfo,
    Order,
    OrderProductOptionRelation,
    OrderProductRelation,
    OrderProductRelationTag,
    TicketInfo,
)
from shop.order.serializers.validator import TicketInfoSerializer, validate_ticket_info_against_product
from shop.payment_history.models import PaymentHistory
from shop.product.models import Category, Option, OptionGroup, Product
from shop.serializers.refund import _REFUND_DATE_OVERRIDABLE_REASONS as REFUND_DATE_OVERRIDABLE_REASONS
from user.models import UserExt

OrderProductStatus = OrderProductRelation.OrderProductStatus

PossibleStatusFSM: dict[OrderProductStatus, set[OrderProductStatus]] = {
    OrderProductStatus.pending: set(),
    OrderProductStatus.paid: {OrderProductStatus.used},
    OrderProductStatus.used: {OrderProductStatus.paid},
    OrderProductStatus.refunded: set(),
}

TICKET_INFO_EDITABLE_STATUSES = frozenset({OrderProductStatus.paid, OrderProductStatus.used})
OPTION_EDITABLE_STATUSES = frozenset({OrderProductStatus.paid})
OUT_OF_SCOPE_MESSAGE = "오늘 등록 데스크 설정의 대상 카테고리가 아닙니다."


def desk_refund_reason(reason: str | None) -> str | None:
    """등록 데스크 환불은 `check_refundable_date=False` 라 일자 관련 사유는 실제로 막지 않는다."""
    return None if reason in REFUND_DATE_OVERRIDABLE_REASONS else reason


class RegistrationDeskTagDto(serializers.ModelSerializer):
    class Meta:
        fields = ("id", "code", "name", "priority")
        model = OrderProductRelationTag


class RegistrationDeskProductDto(serializers.ModelSerializer):
    class RegistrationDeskProductCategoryDto(serializers.ModelSerializer):
        class Meta:
            fields = ("id", "name")
            model = Category

    category = RegistrationDeskProductCategoryDto(read_only=True)

    class Meta:
        fields = ("id", "name", "price", "category")
        model = Product


class RegistrationDeskTicketInfoDto(TicketInfoSerializer):
    class Meta(TicketInfoSerializer.Meta):
        fields = ("name", "phone", "email", "organization")

    def get_attribute(self, instance: OrderProductRelation) -> TicketInfo | None:
        # 소프트 삭제된 참가자 정보를 None 으로 흡수. 쓰기는 실제 관계(`ticket_info`)로 들어간다.
        return instance.ticket_info_or_none


class RegistrationDeskOrderProductOptionDto(NestedModelSerializer):
    class RegistrationDeskOptionGroupDto(serializers.ModelSerializer):
        class Meta:
            fields = ("id", "name", "is_custom_response", "custom_response_pattern", "placeholder_mode")
            model = OptionGroup

    class RegistrationDeskOptionDto(serializers.ModelSerializer):
        class Meta:
            fields = ("id", "name", "additional_price")
            model = Option

    id = serializers.UUIDField(required=True)
    product_option_group = RegistrationDeskOptionGroupDto(read_only=True)
    product_option = RegistrationDeskOptionDto(allow_null=True, read_only=True)
    custom_response = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        fields = ("id", "product_option_group", "product_option", "custom_response")
        model = OrderProductOptionRelation
        list_serializer_class = InstanceListSerializer

    def validate_id(self, value: str) -> str:
        if value != typing.cast(OrderProductOptionRelation, self.instance).id:
            raise serializers.ValidationError("id must not be modified")
        return value

    def validate_custom_response(self, value: str | None) -> str | None:
        option_group: OptionGroup = typing.cast(OrderProductOptionRelation, self.instance).product_option_group
        if not option_group.is_custom_response:
            raise serializers.ValidationError("cannot set custom response to non-custom-response option group")
        if option_group.placeholder_mode == OptionGroup.PlaceholderMode.REQUIRED and not value:
            raise serializers.ValidationError("응답이 필수인 옵션입니다.")
        if value is None:
            return value
        if not option_group.custom_response_pattern:
            raise serializers.ValidationError("custom response pattern is not set, please contact the administrator")
        if not re.match(option_group.custom_response_pattern, value):
            raise serializers.ValidationError("custom response does not match the pattern")

        return value


class RegistrationDeskOrderProductFieldsMixin(serializers.Serializer):
    """주문 검색과 주문 상품 조회가 공통으로 내려주는 읽기 전용 필드."""

    scancode_token = serializers.CharField(read_only=True)
    is_ticket = serializers.BooleanField(source="product.category.is_ticket", read_only=True)
    not_refundable_reason = serializers.SerializerMethodField()
    product = RegistrationDeskProductDto(read_only=True)
    tags = RegistrationDeskTagDto(many=True, read_only=True)

    @staticmethod
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_not_refundable_reason(obj: OrderProductRelation) -> str | None:
        return desk_refund_reason(obj.not_refundable_reason)


class RegistrationDeskOrderProductDto(RegistrationDeskOrderProductFieldsMixin, NestedModelSerializer):
    id = serializers.UUIDField(required=True)
    price = serializers.IntegerField(read_only=True)
    donation_price = serializers.IntegerField(read_only=True)
    status = serializers.ChoiceField(choices=OrderProductStatus.choices, required=False)

    options = RegistrationDeskOrderProductOptionDto(many=True, required=False)
    ticket_info = RegistrationDeskTicketInfoDto(required=False)

    class Meta:
        fields = (
            "id",
            "scancode_token",
            "is_ticket",
            "price",
            "donation_price",
            "status",
            "not_refundable_reason",
            "product",
            "options",
            "tags",
            "ticket_info",
        )
        model = OrderProductRelation
        list_serializer_class = InstanceListSerializer

    def validate_status(self, value: OrderProductStatus) -> OrderProductStatus:
        current_status = typing.cast(OrderProductRelation, self.instance).status
        if value == current_status:
            return value
        if value not in PossibleStatusFSM[typing.cast(OrderProductStatus, current_status)]:
            raise serializers.ValidationError("해당 상태로 변경할 수 없습니다.")
        return value

    def validate(self, attrs: dict) -> dict:
        instance = typing.cast(OrderProductRelation, self.instance)
        if "ticket_info" in attrs:
            if instance.status not in TICKET_INFO_EDITABLE_STATUSES:
                msg = "결제 완료 또는 사용 상태에서만 참가자 정보를 수정할 수 있습니다."
                raise serializers.ValidationError({"ticket_info": msg})
            validate_ticket_info_against_product(instance.product, attrs["ticket_info"])
        if "options" in attrs and instance.status not in OPTION_EDITABLE_STATUSES:
            raise serializers.ValidationError({"options": "결제 완료 상태에서만 옵션을 수정할 수 있습니다."})
        return attrs

    def update(self, instance: OrderProductRelation, validated_data: dict) -> OrderProductRelation:
        # 부모의 nested 처리는 미존재 시 생성을 못 한다.
        ticket_info_data = validated_data.pop("ticket_info", None)
        instance = typing.cast(OrderProductRelation, super().update(instance, validated_data))
        if ticket_info_data is not None:
            self._sync_ticket_info(instance, ticket_info_data)
        return instance

    @staticmethod
    def _sync_ticket_info(instance: OrderProductRelation, data: dict) -> None:
        # OneToOne 이라 소프트 삭제된 row 가 있으면 새로 만들 수 없다.
        ticket_info = TicketInfo.objects.filter(order_product_relation=instance).first() or TicketInfo(
            order_product_relation=instance
        )
        for field, value in data.items():
            setattr(ticket_info, field, value)
        ticket_info.deleted_at = ticket_info.deleted_by = None
        ticket_info.save()
        # 캐시된 이전 값이 응답에 새어 나가지 않도록 갱신.
        instance.ticket_info = ticket_info


class RegistrationDeskOrderSerializer(NestedModelSerializer):
    class RegistrationDeskPaymentHistoryDto(serializers.ModelSerializer):
        class Meta:
            fields = ("status", "price", "created_at")
            model = PaymentHistory

    class RegistrationDeskUserDto(serializers.ModelSerializer):
        class Meta:
            fields = ("id", "username", "email", "unique_id")
            model = UserExt

    class RegistrationDeskCustomerInfoDto(serializers.ModelSerializer):
        class Meta:
            fields = ("name", "email", "phone", "organization")
            model = CustomerInfo

    id = serializers.UUIDField(read_only=True)
    # 데스크가 바꿀 수 있는 건 상품(체크인·참가자 정보·옵션)뿐 — 나머지가 열려 있으면 범위 검증을 우회한다.
    name = serializers.CharField(read_only=True)
    first_paid_price = serializers.IntegerField(read_only=True)
    first_paid_at = serializers.DateTimeField(read_only=True)
    current_paid_price = serializers.IntegerField(read_only=True)
    current_status = serializers.CharField(read_only=True)

    created_at = serializers.DateTimeField(read_only=True)
    not_fully_refundable_reason = serializers.SerializerMethodField()

    payment_histories = RegistrationDeskPaymentHistoryDto(many=True, read_only=True)
    products = RegistrationDeskOrderProductDto(many=True, required=False, source="active_products")
    user = RegistrationDeskUserDto(read_only=True)
    customer_info = RegistrationDeskCustomerInfoDto(read_only=True)

    class Meta:
        fields = (
            "id",
            "name",
            "first_paid_price",
            "first_paid_at",
            "current_paid_price",
            "current_status",
            "created_at",
            "not_fully_refundable_reason",
            "payment_histories",
            "products",
            "user",
            "customer_info",
        )
        model = Order

    @staticmethod
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_not_fully_refundable_reason(obj: Order) -> str | None:
        return desk_refund_reason(obj.not_fully_refundable_reason)

    def validate(self, attrs: dict) -> dict:
        config = self.context.get("desk_config")
        target_ids = [item["id"] for item in attrs.get("active_products", []) if item.get("id")]
        if config and target_ids and not config.covers(target_ids):
            raise exceptions.PermissionDenied(OUT_OF_SCOPE_MESSAGE)
        return attrs


class RegistrationDeskOrderProductSerializer(RegistrationDeskOrderProductFieldsMixin, serializers.ModelSerializer):
    class _OrderDto(serializers.ModelSerializer):
        current_status = serializers.CharField(read_only=True)
        first_paid_at = serializers.DateTimeField(read_only=True)

        class Meta:
            fields = ("id", "name", "current_status", "first_paid_at")
            model = Order

    options = RegistrationDeskOrderProductOptionDto(many=True, read_only=True)
    order = _OrderDto(read_only=True)
    ticket_info = RegistrationDeskTicketInfoDto(read_only=True)

    class Meta:
        fields = (
            "id",
            "short_id",
            "scancode_token",
            "is_ticket",
            "status",
            "price",
            "donation_price",
            "not_refundable_reason",
            "product",
            "options",
            "tags",
            "order",
            "ticket_info",
        )
        model = OrderProductRelation


class RegistrationDeskStatisticsSerializer(serializers.Serializer):
    registration_target_count = serializers.IntegerField()
    registered_count = serializers.IntegerField()
    waiting_count = serializers.IntegerField()


class RegistrationDeskSessionSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ("id", "unique_id", "username", "nickname", "email")
        model = UserExt


class RegistrationDeskConfigurationSerializer(serializers.ModelSerializer):
    class RegistrationDeskEventDto(serializers.ModelSerializer):
        logo_url = serializers.CharField(source="logo.file.url", read_only=True, allow_null=True)

        class Meta:
            fields = ("id", "name", "event_start_at", "event_end_at", "logo_url")
            model = Event

    event = RegistrationDeskEventDto(read_only=True)
    available_tags = serializers.SerializerMethodField()

    class Meta:
        fields = ("id", "name", "start_date", "end_date", "event", "available_tags")
        model = RegistrationDeskConfig

    @staticmethod
    @extend_schema_field(RegistrationDeskTagDto(many=True))
    def get_available_tags(obj: RegistrationDeskConfig) -> list[dict]:
        return RegistrationDeskTagDto(OrderProductRelationTag.objects.filter_active(), many=True).data
