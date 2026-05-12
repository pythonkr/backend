import typing

from core.const.shop_error_messages import CartNotOrderableErrorMessages
from rest_framework import serializers
from shop.order.models import Order, OrderProductRelation
from shop.payment_history.models import PaymentHistoryStatus
from user.models import UserExt


class CartOrderableCheckSerializer(serializers.Serializer):
    """
    장바구니가 주문 가능한지 확인합니다.
    아래 조건에 해당될 경우 주문 불가능합니다.
    - 이미 결제한 장바구니인 경우 주문 불가능
    - 장바구니 내에 이미 결제한 상품이 있는 경우 주문 불가능
    - 장바구니 내의 상품들 주문 금액 합계가 0원 미만이거나 100만원 이상인 경우 주문 불가능
    """

    cart = serializers.PrimaryKeyRelatedField(queryset=Order.objects.filter_has_no_payment_histories(), required=True)

    class Meta:
        fields = ("cart",)

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        super().__init__(*args, **kwargs)
        # 타인의 미결제 cart 로 결제 흐름 트리거를 방어 — request.user 의 cart 로만 lookup 한정.
        request = self.context.get("request")
        user = request.user if request is not None else None
        self.fields["cart"].queryset = (
            Order.objects.filter_has_no_payment_histories().filter(user=user)
            if isinstance(user, UserExt)
            else Order.objects.none()
        )

    def validate(self, data: dict) -> dict:
        cart: Order = data["cart"]

        # 이미 결제한 장바구니인 경우 주문 불가능
        if cart.current_status != PaymentHistoryStatus.pending or cart.payment_histories.exists():
            raise serializers.ValidationError(CartNotOrderableErrorMessages.ALREADY_ORDERED)

        # 장바구니 내에 이미 결제한 상품이 있는 경우 주문 불가능
        if cart.products.exclude(status=OrderProductRelation.OrderProductStatus.pending).exists():
            raise serializers.ValidationError(CartNotOrderableErrorMessages.CONTAINS_PAID_PRODUCT)

        # 장바구니 내의 상품들 주문 금액 합계가 0원 이하거나 100만원 이상인 경우 주문 불가능
        if cart.first_paid_price <= 0:
            raise serializers.ValidationError(CartNotOrderableErrorMessages.CART_PRICE_TOO_LOW)
        if cart.first_paid_price >= 1_000_000:
            raise serializers.ValidationError(CartNotOrderableErrorMessages.CART_PRICE_TOO_HIGH)

        return data
