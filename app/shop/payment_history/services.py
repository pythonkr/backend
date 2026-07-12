from __future__ import annotations

from types import SimpleNamespace

from core.const.shop_error_messages import FreeCheckoutErrorMessages
from django.db import transaction
from rest_framework import serializers
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation, SingleProductCart, TicketInfo
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus, is_legal_payment_status_transition
from shop.payment_history.tasks import send_payment_completed_notifications
from shop.product.models import Option, OptionGroup, Product, ProductTagRelation, Tag
from shop.serializers.cart_validation import (
    CartOrderableCheckSerializer,
    OrderableCheckSerializerMode,
    ProductOrderableCheckSerializer,
)

_LOCKED_OPTIONS_ATTR = "_locked_checkout_options"
_LOCKED_TICKET_INFO_ATTR = "_locked_checkout_ticket_info"
_MISSING = object()


def complete_free_checkout(cart_or_order: Order | SingleProductCart) -> Order:
    validation_mode = (
        OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT
        if isinstance(cart_or_order, SingleProductCart)
        else OrderableCheckSerializerMode.CHECKOUT_CART
    )

    with transaction.atomic():
        order = _lock_or_promote_order(cart_or_order)

        if order.prepared_price != 0:
            raise serializers.ValidationError(FreeCheckoutErrorMessages.PRICE_NOT_ZERO)
        if not is_legal_payment_status_transition(order.current_status, PaymentHistoryStatus.completed):
            raise serializers.ValidationError(FreeCheckoutErrorMessages.ILLEGAL_STATUS_TRANSITION)

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
        raise serializers.ValidationError(FreeCheckoutErrorMessages.TARGET_NOT_FOUND)

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
        # of=("self",) — 조인한 Product/Category 까지 잠그지 않도록 제한. Product 는 아래에서 id 순으로 잠근다.
        # (기본 FOR UPDATE 는 조인 테이블을 OPR.id 순으로 잠가, 상품을 공유하는 서로 다른 주문 간 락 순서가 엇갈려 데드락이 날 수 있음.)
        OrderProductRelation.objects.select_for_update(of=("self",))
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
    active_tag_ids = (
        ProductTagRelation.objects.filter_active().filter(product_id__in=product_ids).order_by().values("tag_id")
    )
    list(Tag.objects.select_for_update().filter_active().filter(id__in=active_tag_ids).order_by("id"))

    option_groups = list(
        OptionGroup.objects.select_for_update().filter_active().filter(product_id__in=product_ids).order_by("id")
    )
    option_group_ids = [option_group.id for option_group in option_groups]

    if option_group_ids:
        list(Option.objects.select_for_update().filter_active().filter(group_id__in=option_group_ids).order_by("id"))

    option_rels = list(
        OrderProductOptionRelation.objects.select_for_update()
        .filter_active()
        .filter(order_product_relation_id__in=product_rel_ids)
        .order_by("id")
    )
    ticket_infos = list(
        TicketInfo.objects.select_for_update()
        .filter_active()
        .filter(order_product_relation_id__in=product_rel_ids)
        .order_by("id")
    )

    option_rels_by_product_rel_id: dict[int, list[OrderProductOptionRelation]] = {}
    for option_rel in option_rels:
        option_rels_by_product_rel_id.setdefault(option_rel.order_product_relation_id, []).append(option_rel)

    ticket_infos_by_product_rel_id = {
        ticket_info.order_product_relation_id: ticket_info for ticket_info in ticket_infos
    }
    for product_rel in product_rels:
        setattr(product_rel, _LOCKED_OPTIONS_ATTR, option_rels_by_product_rel_id.get(product_rel.id, []))
        setattr(product_rel, _LOCKED_TICKET_INFO_ATTR, ticket_infos_by_product_rel_id.get(product_rel.id))

    return product_rels


def _build_product_validation_payload(
    product_rel: OrderProductRelation, validation_mode: OrderableCheckSerializerMode
) -> dict:
    option_rels = getattr(product_rel, _LOCKED_OPTIONS_ATTR, _MISSING)
    if option_rels is _MISSING:
        option_rels = product_rel.options.filter_active().order_by("id")

    payload = {
        "product": product_rel.product_id,
        "donation_price": product_rel.donation_price,
        "options": [
            {
                "product_option_group": option_rel.product_option_group_id,
                "product_option": option_rel.product_option_id,
                "custom_response": option_rel.custom_response,
            }
            for option_rel in option_rels
        ],
    }

    if (
        validation_mode == OrderableCheckSerializerMode.CHECKOUT_SINGLE_PRODUCT
        and product_rel.product.category.is_ticket
    ):
        ticket_info = getattr(product_rel, _LOCKED_TICKET_INFO_ATTR, _MISSING)
        if ticket_info is _MISSING:
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
