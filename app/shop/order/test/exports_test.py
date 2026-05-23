import pytest
from rest_framework.fields import DateTimeField
from shop.order.exports import OrderExportSerializer, OrderProductExportSerializer
from shop.order.models import Order, OrderProductOptionRelation, OrderProductRelation
from shop.product.models import OptionGroup


@pytest.mark.django_db
def test_order_export_returns_dataframe_with_korean_renamed_columns(order_factory):
    completed_order = order_factory(status="completed")
    df = OrderExportSerializer(instance=Order.objects.filter(id=completed_order.id), many=True).export()
    assert df.to_dict(orient="records") == [
        {
            "주문 번호": str(completed_order.id),
            "주문 계정 이메일": completed_order.user.email,
            "고객명": "홍길동",
            "고객 전화번호": "01012345678",
            "고객 이메일": "customer@example.com",
            "고객 소속": None,
            "주문명": completed_order.name,
            "첫 결제 시간": DateTimeField().to_representation(completed_order.payment_histories.first().created_at),
            "첫 결제 금액": completed_order.first_paid_price,
            "현재 결제 금액": completed_order.current_paid_price,
            "현재 상태": "completed",
            "PortOne ID": "imp_test_completed",
        }
    ]


@pytest.mark.django_db
def test_order_export_returns_empty_dataframe_for_empty_queryset():
    # pandas 는 빈 data 에 대해 컬럼 없는 DataFrame 반환 — 행/열 모두 0.
    df = OrderExportSerializer(instance=Order.objects.none(), many=True).export()
    assert len(df) == 0
    assert df.empty


@pytest.mark.django_db
def test_order_product_export_flattens_options_as_dynamic_columns(product, order_factory):
    completed_order = order_factory(status="completed")
    size_group = OptionGroup.objects.create(product=product, name="사이즈")
    opr = completed_order.products.first()
    OrderProductOptionRelation.objects.create(
        order_product_relation=opr,
        product_option_group=size_group,
        product_option=size_group.options.create(name="M"),
    )
    OrderProductOptionRelation.objects.create(
        order_product_relation=opr,
        product_option_group=OptionGroup.objects.create(
            product=product,
            name="요청사항",
            is_custom_response=True,
            custom_response_pattern=r"^.*$",
        ),
        custom_response="배송 빠르게",
    )

    df = OrderProductExportSerializer(instance=OrderProductRelation.objects.filter(id=opr.id), many=True).export()
    # order_id / product_id 는 raw FK 라 UUID 그대로 노출 (DRF UUIDField 거치지 않음).
    assert df.to_dict(orient="records") == [
        {
            "주문 번호": completed_order.id,
            "상품 ID": product.id,
            "상품명": product.name,
            "상태": opr.status,
            "결제 금액": opr.price,
            "추가 기부액": opr.donation_price,
            "사이즈": "M",
            "요청사항": "배송 빠르게",
        }
    ]


@pytest.mark.django_db
def test_order_product_export_calling_export_on_child_raises_to_force_list_serializer():
    # 단건 OrderProductExportSerializer.export() 는 NotImplemented — `many=True` 강제하는 guard.
    with pytest.raises(NotImplementedError):
        OrderProductExportSerializer().export()


@pytest.mark.django_db
def test_order_export_calling_export_on_child_raises():
    with pytest.raises(NotImplementedError):
        OrderExportSerializer().export()
