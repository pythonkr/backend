from __future__ import annotations

from types import SimpleNamespace

from django.db import transaction
from rest_framework import serializers
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart, TicketInfo
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus, is_legal_payment_status_transition
from shop.payment_history.tasks import send_payment_completed_notifications
from shop.product.models import Option, OptionGroup, Product, Tag
from shop.serializers.cart_validation import (
    CartOrderableCheckSerializer,
    OrderableCheckSerializerMode,
    ProductOrderableCheckSerializer,
)

FREE_CHECKOUT_PRICE_ERROR = "무료 주문은 결제 준비 금액이 0원이어야 합니다."
FREE_CHECKOUT_TARGET_ERROR = "무료 주문 대상을 찾을 수 없습니다."
FREE_CHECKOUT_TRANSITION_ERROR = "이미 처리된 주문이거나 무료 완료로 전환할 수 없습니다."


def complete_free_checkout(cart_or_order: Order | SingleProductCart) -> Order:
    validation_mode = (
        OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT
        if isinstance(cart_or_order, SingleProductCart)
        else OrderableCheckSerializerMode.CHECKOUT_CART
    )

    with transaction.atomic():
        order = _lock_or_promote_order(cart_or_order)

        if order.prepared_price != 0:
            raise serializers.ValidationError(FREE_CHECKOUT_PRICE_ERROR)
        if not is_legal_payment_status_transition(order.current_status, PaymentHistoryStatus.completed):
            raise serializers.ValidationError(FREE_CHECKOUT_TRANSITION_ERROR)

        product_rels = lock_and_revalidate_checkout_order(order, validation_mode)

        for product_rel in product_rels:
            product_rel.status = OrderProductRelation.OrderProductStatus.paid
            product_rel.save(update_fields=["status"])

        PaymentHistory.objects.create(
            order=order,
            imp_id=None,
            status=PaymentHistoryStatus.completed,
            price=0,
        )
        transaction.on_commit(lambda: send_payment_completed_notifications.delay(str(order.id)))
        _clear_order_payment_cache(order)
        return order


def _lock_or_promote_order(cart_or_order: Order | SingleProductCart) -> Order:
    if isinstance(cart_or_order, SingleProductCart):
        if cart := SingleProductCart.objects.select_for_update().filter_active().filter(id=cart_or_order.id).first():
            return cart.to_order()
        if order := Order.objects.select_for_update().filter_active().filter(id=cart_or_order.id).first():
            return order
        raise serializers.ValidationError(FREE_CHECKOUT_TARGET_ERROR)

    return Order.objects.select_for_update().filter_active().get(id=cart_or_order.id)


def lock_and_revalidate_checkout_order(
    order: Order, validation_mode: OrderableCheckSerializerMode
) -> list[OrderProductRelation]:
    product_rels = _lock_order_allocation_rows(order)
    context = {"request": SimpleNamespace(user=order.user), "mode": validation_mode}

    ProductOrderableCheckSerializer(
        data=[_build_product_validation_payload(product_rel, validation_mode) for product_rel in product_rels],
        context=context,
        many=True,
    ).is_valid(raise_exception=True)

    if validation_mode == OrderableCheckSerializerMode.CHECKOUT_CART:
        CartOrderableCheckSerializer(data={"cart": order.id}, context=context).is_valid(raise_exception=True)

    return product_rels


def _lock_order_allocation_rows(order: Order) -> list[OrderProductRelation]:
    product_rels = list(
        OrderProductRelation.objects.select_for_update()
        .filter_active()
        .filter(order=order)
        .select_related("product", "product__category")
        .order_by("id")
    )
    product_rel_ids = [product_rel.id for product_rel in product_rels]
    product_ids = [product_rel.product_id for product_rel in product_rels]

    if not product_ids:
        return product_rels

    list(Product.objects.select_for_update().filter_active().filter(id__in=product_ids).order_by("id"))
    list(Tag.objects.select_for_update().filter_active().filter(products__product_id__in=product_ids).order_by("id"))

    option_groups = list(
        OptionGroup.objects.select_for_update().filter_active().filter(product_id__in=product_ids).order_by("id")
    )
    option_group_ids = [option_group.id for option_group in option_groups]

    if option_group_ids:
        list(Option.objects.select_for_update().filter_active().filter(group_id__in=option_group_ids).order_by("id"))

    list(
        OrderProductOptionRelation.objects.select_for_update()
        .filter_active()
        .filter(order_product_relation_id__in=product_rel_ids)
        .order_by("id")
    )
    list(TicketInfo.objects.select_for_update().filter_active().filter(order_product_relation_id__in=product_rel_ids))

    return product_rels


def _build_product_validation_payload(
    product_rel: OrderProductRelation, validation_mode: OrderableCheckSerializerMode
) -> dict:
    payload = {
        "product": product_rel.product_id,
        "donation_price": product_rel.donation_price,
        "options": [
            {
                "product_option_group": option_rel.product_option_group_id,
                "product_option": option_rel.product_option_id,
                "custom_response": option_rel.custom_response,
            }
            for option_rel in product_rel.options.filter_active().order_by("id")
        ],
    }

    if validation_mode == OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT and product_rel.product.category.is_ticket:
        ticket_info = getattr(product_rel, "ticket_info", None)
        if ticket_info:
            payload["ticket_info"] = {
                "name": ticket_info.name,
                "phone": ticket_info.phone,
                "email": ticket_info.email,
                "organization": ticket_info.organization or "",
                "contribution_message": ticket_info.contribution_message,
            }

    return payload


def _clear_order_payment_cache(order: Order) -> None:
    for attr in (
        "active_products",
        "active_payment_histories",
        "first_paid_price",
        "first_payment_history",
        "first_paid_at",
        "current_payment_history",
        "current_paid_price",
        "current_status",
        "latest_imp_id",
    ):
        order.__dict__.pop(attr, None)
