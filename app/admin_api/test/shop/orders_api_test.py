from datetime import datetime, timezone
from io import BytesIO

import pandas
import pytest
from admin_api.serializers.shop.orders import OrderAdminSerializer
from admin_api.views.shop.orders import OrderAdminViewSet
from freezegun import freeze_time
from rest_framework.fields import DateTimeField
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)
from shop.order.models import CustomerInfo, Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from shop.test.helpers import OrdersAdminApi, valid_refund_totp


@pytest.mark.parametrize("client_fixture", ["anon_client", "customer_client"])
@pytest.mark.django_db
def test_admin_list_rejects_non_superuser_client(request, client_fixture):
    response = OrdersAdminApi(http_client=request.getfixturevalue(client_fixture)).list()
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_list_returns_only_orders_with_payment_history_and_products(api_client, completed_order, empty_cart):
    response = OrdersAdminApi(http_client=api_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data],
    }


@pytest.mark.django_db
def test_admin_list_filters_by_status_csv(api_client, completed_order, refunded_order):
    response = OrdersAdminApi(http_client=api_client).list({"status": "refunded"})
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=refunded_order.id)).data],
    }


@pytest.mark.django_db
def test_admin_list_filters_by_product_id_distinct(api_client, completed_order, product):
    # distinct=True 라 OPR 여러 개 매칭돼도 같은 order 한 번만 반환.
    response = OrdersAdminApi(http_client=api_client).list({"product_id": str(product.id)})
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data],
    }


@pytest.mark.django_db
def test_admin_retrieve_returns_nested_payload(api_client, completed_order):
    response = OrdersAdminApi(http_client=api_client).retrieve(completed_order.id)
    assert response.status_code == HTTP_200_OK
    assert response.json() == OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data


@pytest.mark.django_db
def test_admin_refund_action_refunds_order_with_valid_totp(
    api_client, completed_order, mock_portone_req_cancel_payment
):
    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id, totp=valid_refund_totp())
    assert response.status_code == HTTP_204_NO_CONTENT
    completed_order.refresh_from_db()
    statuses = list(completed_order.products.values_list("status", flat=True))
    assert statuses == [OrderProductRelation.OrderProductStatus.refunded]
    assert completed_order.payment_histories.filter(status=PaymentHistoryStatus.refunded).exists()


@pytest.mark.django_db
def test_admin_refund_action_rejects_invalid_totp(api_client, completed_order, mock_portone_req_cancel_payment):
    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id, totp="000000")
    assert response.status_code == HTTP_400_BAD_REQUEST
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_admin_refund_action_rejects_missing_totp(api_client, completed_order, mock_portone_req_cancel_payment):
    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id)
    assert response.status_code == HTTP_400_BAD_REQUEST
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_admin_refund_product_action_does_partial_refund(
    api_client, completed_order, product, mock_portone_req_cancel_payment
):
    target_opr = completed_order.products.first()
    OrderProductRelation.objects.create(
        order=completed_order, product=product, price=product.price, status=OrderProductRelation.OrderProductStatus.paid
    )
    response = OrdersAdminApi(http_client=api_client).refund_product(
        completed_order.id, target_opr.id, totp=valid_refund_totp()
    )
    assert response.status_code == HTTP_204_NO_CONTENT
    target_opr.refresh_from_db()
    assert target_opr.status == OrderProductRelation.OrderProductStatus.refunded
    # OrderProductRefundSerializer 가 직접 OPR.save() 호출 — history_type='~' 기록 검증.
    assert target_opr.history.filter(history_type="~", status=OrderProductRelation.OrderProductStatus.refunded).exists()


@pytest.mark.django_db
def test_admin_refund_product_action_returns_404_for_unknown_rel(api_client, completed_order):
    response = OrdersAdminApi(http_client=api_client).refund_product(
        completed_order.id, "00000000-0000-0000-0000-000000000000", totp=valid_refund_totp()
    )
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_admin_refund_allows_expired_window(api_client, completed_order, mock_portone_req_cancel_payment):
    # admin endpoint 는 check_refundable_date=False 로 expired 상품도 환불 가능.
    product = completed_order.products.first().product
    product.refundable_ends_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    product.save()

    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id, totp=valid_refund_totp())
    assert response.status_code == HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_admin_import_template_returns_csv(api_client, product):
    response = OrdersAdminApi(http_client=api_client).import_template(product_id=str(product.id))
    assert response.status_code == HTTP_200_OK
    assert "text/csv" in response.headers["Content-Type"]


@pytest.mark.django_db
def test_admin_import_template_rejects_missing_product_id(api_client):
    response = OrdersAdminApi(http_client=api_client).import_template()
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_admin_import_template_returns_404_for_unknown_product(api_client):
    response = OrdersAdminApi(http_client=api_client).import_template(product_id="00000000-0000-0000-0000-000000000000")
    assert response.status_code == HTTP_404_NOT_FOUND


def _csv_file(rows: str) -> BytesIO:
    csv_file = BytesIO(rows.encode("utf-8"))
    csv_file.name = "import.csv"
    return csv_file


@pytest.mark.django_db
def test_admin_import_csv_persists_paid_order_from_uploaded_row(api_client, customer_user, product):
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price\n"
            f"홍길동,010-1234-5678,{customer_user.email},,{product.id},0\n"
        )
    )
    assert response.status_code == HTTP_201_CREATED
    opr = OrderProductRelation.objects.get(product=product)
    assert opr.status == OrderProductRelation.OrderProductStatus.paid
    assert opr.order.user == customer_user


@pytest.mark.django_db
def test_admin_import_csv_rejects_missing_file(api_client):
    response = OrdersAdminApi(http_client=api_client).import_csv()
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_admin_import_csv_returns_400_for_invalid_rows_without_persisting(api_client, product):
    # email 매칭되는 user 부재 → 모든 row validate 실패 → atomic rollback.
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price\n"
            f"홍길동,010-1234-5678,nobody@example.com,,{product.id},0\n"
        )
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert not OrderProductRelation.objects.exists()


@pytest.mark.parametrize("include_refunded", [False, True])
@freeze_time(datetime(2026, 5, 23, 15, 30, 45, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_admin_export_returns_xlsx_filtering_refunded_per_include_flag(
    api_client, customer_user, refunded_order, product, include_refunded
):
    response = OrdersAdminApi(http_client=api_client).export(
        {"product_ids": [str(product.id)], "include_refunded": include_refunded}
    )
    assert response.status_code == HTTP_200_OK
    assert response.headers["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # `datetime.datetime.now()` 는 naive — freezegun UTC 시각 그대로 사용 (timezone 변환 없음).
    assert response.headers["Content-Disposition"] == "attachment; filename=order_export_2026-05-23_15-30-45.xlsx"

    df_dict = pandas.read_excel(
        BytesIO(b"".join(response.streaming_content)),
        sheet_name=None,
        # index_col=0 → write 시 추가된 pandas index 컬럼 제거. na_filter=False → 빈 셀을 NaN 대신 "" 로
        # 읽어 None vs NaN 비교 문제 회피. dtype 강제 → leading-zero 가진 string 이 int 로 추론되는 것 방지.
        index_col=0,
        na_filter=False,
        dtype={"고객 전화번호": str, "PortOne ID": str},
    )
    assert set(df_dict.keys()) == {"주문", "주문상품"}

    if not include_refunded:
        # REFUNDABLE_STATUSES 만 통과 → refunded order 는 제외 → 양쪽 시트 모두 empty.
        assert df_dict["주문"].to_dict(orient="records") == []
        assert df_dict["주문상품"].to_dict(orient="records") == []
        return

    opr = refunded_order.products.first()
    assert df_dict["주문"].to_dict(orient="records") == [
        {
            "주문 번호": str(refunded_order.id),
            "주문 계정 이메일": customer_user.email,
            "고객명": "홍길동",
            "고객 전화번호": "01012345678",
            "고객 이메일": "customer@example.com",
            # CustomerInfo.organization=None 이 XLSX 빈 셀로 저장 → na_filter=False 로 "" 로 환원.
            "고객 소속": "",
            "주문명": refunded_order.name,
            # DateTimeField 직렬화 결과 (ISO 8601 + tz offset) 가 XLSX 에 string 으로 저장됨.
            "첫 결제 시간": DateTimeField().to_representation(refunded_order.first_payment_history.created_at),
            "첫 결제 금액": refunded_order.first_paid_price,
            "현재 결제 금액": 0,
            "현재 상태": "refunded",
            "PortOne ID": "imp_test_completed",
        }
    ]
    assert df_dict["주문상품"].to_dict(orient="records") == [
        {
            "주문 번호": str(refunded_order.id),
            "상품 ID": str(product.id),
            "상품명": product.name,
            "상태": "refunded",
            "결제 금액": opr.price,
            "추가 기부액": opr.donation_price,
        }
    ]


@pytest.mark.parametrize("payload", [{}, {"product_ids": []}])
@pytest.mark.django_db
def test_admin_export_rejects_missing_or_empty_product_ids(api_client, payload):
    response = OrdersAdminApi(http_client=api_client).export(payload)
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_admin_partial_update_modifies_existing_customer_info(api_client, completed_order):
    response = OrdersAdminApi(http_client=api_client).update(
        completed_order.id,
        {"customer_info": {"name": "수정", "phone": "01099998888", "email": "new@x.com", "organization": "Z"}},
    )
    assert response.status_code == HTTP_200_OK
    assert list(
        CustomerInfo.objects.filter(order=completed_order).values("name", "phone", "email", "organization")
    ) == [{"name": "수정", "phone": "01099998888", "email": "new@x.com", "organization": "Z"}]


@pytest.mark.django_db
def test_admin_partial_update_creates_customer_info_when_missing(api_client, completed_order):
    CustomerInfo.objects.filter(order=completed_order).hard_delete()
    response = OrdersAdminApi(http_client=api_client).update(
        completed_order.id,
        {"customer_info": {"name": "신규", "phone": "01000000000", "email": "n@x.com", "organization": ""}},
    )
    assert response.status_code == HTTP_200_OK
    assert CustomerInfo.objects.filter(order=completed_order, name="신규", email="n@x.com").exists()


@pytest.mark.django_db
def test_admin_list_filters_by_user_id(api_client, completed_order, customer_user, other_user, product):
    other_order = Order.objects.create(user=other_user, name="other")
    OrderProductRelation.objects.create(
        order=other_order, product=product, price=product.price, status=OrderProductRelation.OrderProductStatus.paid
    )
    PaymentHistory.objects.create(
        order=other_order, imp_id="imp_o", status=PaymentHistoryStatus.completed, price=product.price
    )

    response = OrdersAdminApi(http_client=api_client).list({"user_id": str(customer_user.id)})
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data],
    }
