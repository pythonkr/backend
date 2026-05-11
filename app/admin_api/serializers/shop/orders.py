from contextlib import suppress
from typing import Any
from urllib.parse import urljoin

from admin_api.serializers.notification import HISTORY_ADMIN_SERIALIZER_BY_CHANNEL
from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.read_only_serializer import ReadOnlyModelSerializer
from core.serializer.skip_none_list_serializer import SkipNoneListSerializer
from django.conf import settings
from django.urls import NoReverseMatch
from notification.channels import NotificationChannel
from notification.models.base import Recipient
from rest_framework import serializers
from shop.order.models import CustomerInfo, Order, OrderProductOptionRelation, OrderProductRelation
from shop.payment_history.models import PaymentHistory
from shop.product.models import Product
from user.models import UserExt

CUSTOMER_INFO_RECIPIENT_ATTR_BY_CHANNEL = {
    NotificationChannel.EMAIL: "email",
    NotificationChannel.NHN_CLOUD_SMS: "phone",
    NotificationChannel.NHN_CLOUD_KAKAO_ALIMTALK: "phone",
}


class OrderAdminSerializer(
    ReadOnlyModelSerializer,
    BaseAbstractSerializer,
    JsonSchemaSerializer,
    serializers.ModelSerializer,
):
    class SimpleUserSerializer(serializers.ModelSerializer):
        class Meta:
            model = UserExt
            read_only_fields = fields = ("id", "username", "email", "unique_id")

    class SimpleCustomerInfoSerializer(serializers.ModelSerializer):
        class Meta:
            model = CustomerInfo
            read_only_fields = fields = ("name", "phone", "email", "organization")

    class SimplePaymentHistorySerializer(serializers.ModelSerializer):
        class Meta:
            model = PaymentHistory
            read_only_fields = fields = ("id", "imp_id", "status", "price", "created_at")

    class SimpleOrderProductRelationSerializer(serializers.ModelSerializer):
        class SimpleProductSerializer(serializers.ModelSerializer):
            class Meta:
                model = Product
                read_only_fields = fields = ("id", "name_ko", "name_en", "price")

        class SimpleOrderProductOptionRelationSerializer(serializers.ModelSerializer):
            option_group_name_ko = serializers.CharField(source="product_option_group.name_ko", read_only=True)
            option_group_name_en = serializers.CharField(source="product_option_group.name_en", read_only=True)
            option_name_ko = serializers.CharField(source="product_option.name_ko", read_only=True, allow_null=True)
            option_name_en = serializers.CharField(source="product_option.name_en", read_only=True, allow_null=True)

            class Meta:
                model = OrderProductOptionRelation
                read_only_fields = fields = (
                    "id",
                    "option_group_name_ko",
                    "option_group_name_en",
                    "option_name_ko",
                    "option_name_en",
                    "custom_response",
                )

        product = SimpleProductSerializer(read_only=True)
        options = SimpleOrderProductOptionRelationSerializer(many=True, read_only=True)

        class Meta:
            model = OrderProductRelation
            fields = ("id", "product", "status", "price", "donation_price", "options")
            read_only_fields = ("id", "product", "price", "donation_price", "options")

    user = SimpleUserSerializer(read_only=True)
    customer_info = SimpleCustomerInfoSerializer(read_only=True)
    products = SimpleOrderProductRelationSerializer(many=True, read_only=True)
    payment_histories = SimplePaymentHistorySerializer(many=True, read_only=True)
    first_paid_price = serializers.IntegerField(read_only=True)
    current_paid_price = serializers.IntegerField(read_only=True)
    current_status = serializers.CharField(read_only=True)
    first_paid_at = serializers.DateTimeField(read_only=True)
    latest_imp_id = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = COMMON_ADMIN_FIELDS + (
            "name_ko",
            "name_en",
            "user",
            "customer_info",
            "products",
            "payment_histories",
            "first_paid_price",
            "current_paid_price",
            "current_status",
            "first_paid_at",
            "latest_imp_id",
        )


class OrderExportRequestSerializer(JsonSchemaSerializer, serializers.Serializer):
    product_ids = serializers.ListField(child=serializers.UUIDField(), required=True, min_length=1)
    include_refunded = serializers.BooleanField(default=False)


class _OrderRecipientItemSerializer(serializers.Serializer):
    """Order → Recipient ({recipient, context}) 변환.

    customer_info / 첫 상품 / recipient 부재 시 None 반환. None-skip 의미를 가지므로
    반드시 `SkipNoneListSerializer` (Meta.list_serializer_class) 와 함께 `many=True` 로 사용 — 단독 사용 시 호출자가 None 처리 책임.
    """

    recipient = serializers.CharField()
    context = serializers.JSONField()

    class Meta:
        list_serializer_class = SkipNoneListSerializer

    def to_representation(self, order: Order) -> Recipient | None:
        channel: NotificationChannel = self.context["channel"]

        if not (customer_info := getattr(order, "customer_info", None)):
            return None
        if not (recipient := getattr(customer_info, CUSTOMER_INFO_RECIPIENT_ATTR_BY_CHANNEL[channel], "")):
            return None
        if not (order_product_rel := next(iter(order.products.all()), None)):
            return None

        ctx: dict[str, Any] = {
            o_rel.product_option_group.name: (
                o_rel.custom_response
                if o_rel.product_option_group.is_custom_response
                else (o_rel.product_option.name if o_rel.product_option else "")
            )
            for o_rel in order_product_rel.options.all()
        }
        with suppress(NoReverseMatch):
            # Order scancode viewset 미등록 (TODO.md). 미설정 시 missing_variables 로 보고.
            ctx["scancode_url"] = urljoin(settings.BACKEND_DOMAIN, order.scancode_path)

        return {"recipient": recipient, "context": ctx | self.context["context_override"]}


class OrderSendNotificationPreviewResponseSerializer(JsonSchemaSerializer, serializers.Serializer):
    class RecipientItemSerializer(JsonSchemaSerializer, serializers.Serializer):
        recipient = serializers.CharField()
        context = serializers.JSONField()
        missing_variables = serializers.ListField(child=serializers.CharField())

    template_variables = serializers.ListField(child=serializers.CharField())
    recipients = RecipientItemSerializer(many=True)


class OrderSendNotificationSerializer(JsonSchemaSerializer, serializers.Serializer):
    channel = serializers.ChoiceField(choices=NotificationChannel.choices)
    template_id = serializers.UUIDField()
    context_override = serializers.JSONField(required=False, default=dict)

    def validate_channel(self, value: str) -> NotificationChannel:
        return NotificationChannel(value)

    def validate(self, attrs: dict) -> dict:
        if not (t := attrs["channel"].template_class.objects.filter_active().filter(pk=attrs["template_id"]).first()):
            raise serializers.ValidationError({"template_id": "Template not found."})
        # validated_data 에 template_id (UUID) 와 template (instance) 가 공존.
        # downstream 은 template 만 사용; template_id 는 input round-trip 용으로 남김.
        return {**attrs, "template": t}

    def _build_recipient_items(self) -> list[Recipient]:
        return _OrderRecipientItemSerializer(instance=self.instance, many=True, context=self.validated_data).data

    def build_preview_response(self) -> OrderSendNotificationPreviewResponseSerializer:
        template_vars = self.validated_data["template"].template_variables
        return OrderSendNotificationPreviewResponseSerializer(
            instance={
                "template_variables": sorted(template_vars),
                "recipients": [
                    {**i, "missing_variables": sorted(template_vars - i["context"].keys())}
                    for i in self._build_recipient_items()
                ],
            },
        )

    def build_send_response(self) -> serializers.Serializer:
        if not (items := self._build_recipient_items()):
            raise serializers.ValidationError(
                "발송 대상이 없습니다 (filterset 결과 0건 또는 customer_info/첫 상품 부재)."
            )
        channel: NotificationChannel = self.validated_data["channel"]
        template = self.validated_data["template"]
        if invalid := [
            {**i, "missing_variables": missing}
            for i in items
            if (missing := sorted(template.template_variables - i["context"].keys()))
        ]:
            raise serializers.ValidationError({"missing_context_variables": invalid})

        # create_for_recipients (DB write) + history.send() (Celery dispatch on commit).
        history = channel.history_class.objects.create_for_recipients(template=template, recipients=items)
        history.send()
        history.refresh_from_db()
        return HISTORY_ADMIN_SERIALIZER_BY_CHANNEL[channel](instance=history)
