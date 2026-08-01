from codecs import BOM_UTF8
from datetime import datetime, timezone
from io import BytesIO

import pandas
import pytest
import yaml
from admin_api.serializers.shop.orders import OrderAdminSerializer
from admin_api.test.helpers import OrdersAdminApi
from admin_api.views.shop.orders import OrderAdminViewSet
from core.const.shop_error_messages import NotRefundableErrorMessages
from freezegun import freeze_time
from model_bakery import baker
from rest_framework.fields import DateTimeField
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)
from rest_framework.test import APIClient
from shop.order.models import CustomerInfo, Order, OrderProductRelation
from shop.payment_history.models import PaymentHistory, PaymentHistoryStatus
from user.models import UserExt


@pytest.mark.parametrize("client_fixture", ["anon_client", "customer_client"])
@pytest.mark.django_db
def test_admin_list_rejects_non_superuser_client(request, client_fixture):
    response = OrdersAdminApi(http_client=request.getfixturevalue(client_fixture)).list()
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_list_returns_only_orders_with_payment_history_and_products(api_client, order_factory):
    completed_order = order_factory(status="completed")
    order_factory(status="empty")
    response = OrdersAdminApi(http_client=api_client).list()
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data],
    }


@pytest.mark.django_db
def test_admin_list_includes_free_completed_order(api_client, order_factory):
    order = order_factory(status="completed", product_price=0, imp_id=None)

    response = OrdersAdminApi(http_client=api_client).list()

    assert response.status_code == HTTP_200_OK
    row = response.json()["results"][0]
    assert row["id"] == str(order.id)
    assert row["current_status"] == PaymentHistoryStatus.completed
    assert row["current_paid_price"] == 0
    assert row["latest_imp_id"] is None
    assert row["payment_histories"][0]["price"] == 0
    assert row["payment_histories"][0]["imp_id"] is None


@pytest.mark.django_db
def test_admin_list_orders_by_first_paid_at_desc(api_client, order_factory):
    # 먼저 생성된 주문(= created_at 이 더 과거)이 더 최근에 결제되도록 구성.
    # 이렇게 해야 created_at 기본 정렬과 first_paid_at 정렬의 결과가 달라져 검증이 유효하다.
    older_order = order_factory(status="completed")
    newer_order = order_factory(status="completed")
    PaymentHistory.objects.filter(order=older_order).update(created_at=datetime(2026, 5, 2, tzinfo=timezone.utc))
    PaymentHistory.objects.filter(order=newer_order).update(created_at=datetime(2026, 5, 1, tzinfo=timezone.utc))

    response = OrdersAdminApi(http_client=api_client).list()

    assert response.status_code == HTTP_200_OK
    assert [row["id"] for row in response.json()["results"]] == [str(older_order.id), str(newer_order.id)]


@pytest.mark.django_db
def test_admin_list_filters_by_status_csv(api_client, order_factory):
    order_factory(status="completed")
    refunded_order = order_factory(status="refunded")
    response = OrdersAdminApi(http_client=api_client).list({"status": "refunded"})
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=refunded_order.id)).data],
    }


@pytest.mark.django_db
def test_admin_list_filters_by_product_id_distinct(api_client, ticket_product, order_factory):
    completed_order = order_factory(status="completed")
    response = OrdersAdminApi(http_client=api_client).list({"product_id": str(ticket_product.id)})
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data],
    }


@pytest.mark.django_db
def test_admin_list_filters_by_active_opr_category(api_client, ticket_product, order_factory):
    """`?category_id=` 가 active OPR 가 있는 주문만 매칭한다."""
    completed_order = order_factory(status="completed")
    response = OrdersAdminApi(http_client=api_client).list({"category_id": str(ticket_product.category_id)})
    assert response.status_code == HTTP_200_OK
    assert {row["id"] for row in response.json()["results"]} == {str(completed_order.id)}


@pytest.mark.django_db
def test_admin_list_filters_by_active_opr_category_group(api_client, ticket_product, order_factory):
    """`?category_group_id=` 가 active OPR 가 있는 주문만 매칭한다."""
    completed_order = order_factory(status="completed")
    response = OrdersAdminApi(http_client=api_client).list({"category_group_id": str(ticket_product.category.group_id)})
    assert response.status_code == HTTP_200_OK
    assert {row["id"] for row in response.json()["results"]} == {str(completed_order.id)}


@pytest.mark.django_db
def test_admin_list_filters_by_active_opr_event(api_client, ticket_product, non_ticket_product, order_factory):
    """`?event_id=` 가 해당 이벤트 카테고리의 상품을 가진 주문만 매칭한다."""
    event = baker.make("event.Event", name="파이콘 한국 2026")
    ticket_product.category.event = event
    ticket_product.category.save()

    in_event_order = order_factory(status="completed")  # ticket_product → event 연결됨
    order_factory(status="completed", is_ticket=False)  # non_ticket_product → event 없음

    response = OrdersAdminApi(http_client=api_client).list({"event_id": str(event.id)})
    assert response.status_code == HTTP_200_OK
    assert {row["id"] for row in response.json()["results"]} == {str(in_event_order.id)}


@pytest.mark.django_db
def test_admin_retrieve_returns_nested_payload(api_client, order_factory):
    completed_order = order_factory(status="completed")
    response = OrdersAdminApi(http_client=api_client).retrieve(completed_order.id)
    assert response.status_code == HTTP_200_OK
    assert response.json() == OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data


@pytest.mark.django_db
def test_admin_refund_action_refunds_order(api_client, mock_portone_req_cancel_payment, order_factory):
    completed_order = order_factory(status="completed")
    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    completed_order.refresh_from_db()
    statuses = list(completed_order.products.values_list("status", flat=True))
    assert statuses == [OrderProductRelation.OrderProductStatus.refunded]
    assert completed_order.payment_histories.filter(status=PaymentHistoryStatus.refunded).exists()


@pytest.mark.django_db
def test_admin_refund_action_rejects_free_completed_order_without_portone_cancel(
    api_client, mock_portone_req_cancel_payment, order_factory
):
    order = order_factory(status="completed", product_price=0, imp_id=None)

    response = OrdersAdminApi(http_client=api_client).refund(order.id)

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert NotRefundableErrorMessages.ORDER_IMP_ID_NOT_EXIST in str(response.json())
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_admin_refund_product_action_does_partial_refund(
    api_client, ticket_product, mock_portone_req_cancel_payment, order_factory
):
    completed_order = order_factory(status="completed")
    target_opr = completed_order.products.first()
    OrderProductRelation.objects.create(
        order=completed_order,
        product=ticket_product,
        price=ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    response = OrdersAdminApi(http_client=api_client).refund_product(completed_order.id, target_opr.id)
    assert response.status_code == HTTP_204_NO_CONTENT
    target_opr.refresh_from_db()
    assert target_opr.status == OrderProductRelation.OrderProductStatus.refunded
    # OrderProductRefundSerializer 가 직접 OPR.save() 호출 — history_type='~' 기록 검증.
    assert target_opr.history.filter(history_type="~", status=OrderProductRelation.OrderProductStatus.refunded).exists()


@pytest.mark.django_db
def test_admin_refund_product_action_returns_404_for_unknown_rel(api_client, order_factory):
    completed_order = order_factory(status="completed")
    response = OrdersAdminApi(http_client=api_client).refund_product(
        completed_order.id, "00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_admin_refund_product_action_rejects_free_completed_opr_without_portone_cancel(
    api_client, mock_portone_req_cancel_payment, order_factory
):
    order = order_factory(status="completed", product_price=0, imp_id=None)
    opr = order.products.get()

    response = OrdersAdminApi(http_client=api_client).refund_product(order.id, opr.id)

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert NotRefundableErrorMessages.ORDER_NOT_REFUNDABLE in str(response.json())
    mock_portone_req_cancel_payment.assert_not_called()


@pytest.mark.django_db
def test_admin_refund_actions_document_validation_error_responses():
    response = APIClient().get("/api/schema/v1/")
    assert response.status_code == HTTP_200_OK

    schema = yaml.safe_load(response.content)
    total_refund_path = next(path for path in schema["paths"] if path.endswith("/admin-api/shop/order/{id}/refund/"))
    product_refund_path = next(
        path for path in schema["paths"] if path.endswith("/admin-api/shop/order/{id}/products/{rel_id}/refund/")
    )

    for path in (total_refund_path, product_refund_path):
        responses = schema["paths"][path]["post"]["responses"]
        assert "204" in responses
        assert responses["400"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ValidationErrorResponse",
        }


@pytest.mark.django_db
def test_admin_refund_allows_expired_window(api_client, mock_portone_req_cancel_payment, order_factory):
    completed_order = order_factory(status="completed")
    ticket_product = completed_order.products.first().product
    ticket_product.refundable_ends_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    ticket_product.save()

    response = OrdersAdminApi(http_client=api_client).refund(completed_order.id)
    assert response.status_code == HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_admin_import_template_returns_csv(api_client, ticket_product):
    response = OrdersAdminApi(http_client=api_client).import_template(product_id=str(ticket_product.id))
    assert response.status_code == HTTP_200_OK
    assert "text/csv" in response.headers["Content-Type"]
    # JSONRenderer 를 거치지 않은 그대로의 CSV 본문 + Excel 용 BOM 인지 확인.
    assert response.content.startswith(BOM_UTF8)
    assert response.content.decode("utf-8-sig").splitlines() == [
        "name,phone,email,organization,product_id,donation_price"
    ]


@pytest.mark.django_db
def test_admin_import_template_rejects_missing_product_id(api_client):
    response = OrdersAdminApi(http_client=api_client).import_template()
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_admin_import_template_returns_404_for_unknown_product(api_client):
    response = OrdersAdminApi(http_client=api_client).import_template(product_id="00000000-0000-0000-0000-000000000000")
    assert response.status_code == HTTP_404_NOT_FOUND


def _csv_bytes(raw: bytes) -> BytesIO:
    csv_file = BytesIO(raw)
    csv_file.name = "import.csv"
    return csv_file


def _csv_file(rows: str, encoding: str = "utf-8") -> BytesIO:
    return _csv_bytes(rows.encode(encoding))


@pytest.mark.django_db
def test_admin_import_csv_persists_paid_order_from_uploaded_row(api_client, customer_user, ticket_product):
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price\n"
            f"홍길동,010-1234-5678,{customer_user.email},,{ticket_product.id},0\n"
        )
    )
    assert response.status_code == HTTP_201_CREATED
    opr = OrderProductRelation.objects.get(product=ticket_product)
    assert opr.status == OrderProductRelation.OrderProductStatus.paid
    assert opr.order.user == customer_user
    # 빈 셀은 pandas NaN → 문자열 "nan" 이 아니라 빈 문자열로 저장돼야 한다.
    assert opr.order.customer_info.organization == ""


@pytest.mark.django_db
def test_admin_import_csv_rejects_blank_required_cell(api_client, customer_user, ticket_product):
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price\n"
            f",010-1234-5678,{customer_user.email},,{ticket_product.id},0\n"
        )
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert [error["attr"] for error in response.json()["errors"]] == ["0.name"]
    assert not OrderProductRelation.objects.exists()


@pytest.mark.django_db
def test_admin_import_csv_skips_option_group_with_blank_cell(api_client, customer_user, ticket_product, option_group):
    option_group.options.create(name="M", additional_price=0)
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price,사이즈\n"
            f"홍길동,010-1234-5678,{customer_user.email},,{ticket_product.id},0,\n"
        )
    )
    assert response.status_code == HTTP_201_CREATED
    assert OrderProductRelation.objects.get(product=ticket_product).options.count() == 0


@pytest.mark.django_db
def test_admin_import_csv_accepts_template_output_verbatim(api_client, customer_user, ticket_product):
    """템플릿 → 작성 → 업로드 왕복. BOM 이 첫 컬럼명(name)에 섞여 들어가지 않아야 한다."""
    template = OrdersAdminApi(http_client=api_client).import_template(product_id=str(ticket_product.id))
    filled_csv = (
        template.content.decode("utf-8") + f"홍길동,010-1234-5678,{customer_user.email},,{ticket_product.id},0\n"
    )

    response = OrdersAdminApi(http_client=api_client).import_csv(csv_file=_csv_file(filled_csv))

    assert response.status_code == HTTP_201_CREATED
    assert OrderProductRelation.objects.filter(product=ticket_product).exists()


@pytest.mark.django_db
def test_admin_import_csv_accepts_cp949_encoded_file(api_client, customer_user, ticket_product):
    """한국어 Windows Excel 이 저장하는 CP949 파일도 읽어야 한다."""
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price\n"
            f"홍길동,010-1234-5678,{customer_user.email},파이콘,{ticket_product.id},0\n",
            encoding="cp949",
        )
    )
    assert response.status_code == HTTP_201_CREATED
    assert CustomerInfo.objects.get(order__products__product=ticket_product).name == "홍길동"


@pytest.mark.django_db
def test_admin_import_csv_rejects_undecodable_file(api_client):
    """Excel '유니코드 텍스트'(UTF-16) 저장처럼 지원하지 않는 인코딩은 500 이 아니라 400."""
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_bytes("name,phone\n홍길동,010-1234-5678\n".encode("utf-16"))
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert [error["attr"] for error in response.json()["errors"]] == ["csv_file"]


@pytest.mark.django_db
def test_admin_import_csv_rejects_malformed_csv(api_client):
    """열 개수가 어긋난 CSV 도 500 이 아니라 400."""
    response = OrdersAdminApi(http_client=api_client).import_csv(csv_file=_csv_file("a,b,c\n1,2,3\n4,5,6,7,8\n"))
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert [error["attr"] for error in response.json()["errors"]] == ["csv_file"]


@pytest.mark.django_db
def test_admin_import_csv_rejects_missing_file(api_client):
    response = OrdersAdminApi(http_client=api_client).import_csv()
    assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_admin_import_csv_returns_400_for_invalid_rows_without_persisting(api_client, customer_user, ticket_product):
    # 전화번호 형식 불일치 → 모든 row validate 실패 → atomic rollback.
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price\n"
            f"홍길동,전화번호아님,{customer_user.email},,{ticket_product.id},0\n"
        )
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert not OrderProductRelation.objects.exists()
    assert response.json()["type"] == "validation_error"


@pytest.mark.django_db
def test_admin_import_csv_error_attr_identifies_the_failing_row(
    api_client, customer_user, ticket_product, option_group
):
    # 1행은 유효, 2행은 정의되지 않은 옵션값 → attr 의 행 인덱스로 실패한 행을 식별할 수 있어야 한다.
    option_group.options.create(name="M", additional_price=0)
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price,사이즈\n"
            f"홍길동,010-1234-5678,{customer_user.email},,{ticket_product.id},0,M\n"
            f"김철수,010-2222-3333,other@example.com,,{ticket_product.id},0,XXL\n"
        )
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert [error["attr"] for error in response.json()["errors"]] == ["1.non_field_errors"]
    # 유효한 1행도 저장되지 않는다 (전부 성공해야 저장).
    assert not OrderProductRelation.objects.exists()


@pytest.mark.django_db
def test_admin_import_csv_creates_missing_user_from_row_email(api_client, ticket_product):
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price\n"
            f"홍길동,010-1234-5678,nobody@example.com,,{ticket_product.id},0\n"
        )
    )
    assert response.status_code == HTTP_201_CREATED
    assert OrderProductRelation.objects.get(product=ticket_product).order.user.email == "nobody@example.com"


@pytest.mark.django_db
def test_admin_import_csv_rolls_back_created_users_when_a_later_row_fails(api_client, ticket_product, option_group):
    # 1행이 유저를 만들고 2행이 실패 → 라우트 atomic 으로 유저 생성까지 되돌아가야 한다.
    option_group.options.create(name="M", additional_price=0)
    response = OrdersAdminApi(http_client=api_client).import_csv(
        csv_file=_csv_file(
            "name,phone,email,organization,product_id,donation_price,사이즈\n"
            f"홍길동,010-1234-5678,first@example.com,,{ticket_product.id},0,M\n"
            f"김철수,010-2222-3333,second@example.com,,{ticket_product.id},0,XXL\n"
        )
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert not UserExt.objects.filter(email__in=["first@example.com", "second@example.com"]).exists()


@pytest.mark.parametrize("include_refunded", [False, True])
@freeze_time(datetime(2026, 5, 23, 15, 30, 45, tzinfo=timezone.utc))
@pytest.mark.django_db
def test_admin_export_returns_xlsx_filtering_refunded_per_include_flag(
    api_client, customer_user, ticket_product, include_refunded, order_factory
):
    refunded_order = order_factory(status="refunded")
    response = OrdersAdminApi(http_client=api_client).export(
        {"product_id": str(ticket_product.id), "include_refunded": include_refunded}
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
            "상품 ID": str(ticket_product.id),
            "상품명": ticket_product.name,
            "상태": "refunded",
            "결제 금액": opr.price,
            "추가 기부액": opr.donation_price,
        }
    ]


def _export_order_ids(response) -> set[str]:
    """export XLSX 응답의 '주문' 시트에서 주문 번호 집합을 추출."""
    df = pandas.read_excel(BytesIO(b"".join(response.streaming_content)), sheet_name="주문", index_col=0, dtype=str)
    return set(df["주문 번호"].tolist()) if not df.empty else set()


@pytest.mark.django_db
def test_admin_export_without_filters_returns_all_purchased_orders(api_client, ticket_product, order_factory):
    """필터 없이 호출하면 결제 완료 주문 전체를 내보낸다 (기본 include_refunded=false → 환불 제외)."""
    completed_order = order_factory(status="completed")
    order_factory(status="refunded")  # include_refunded 기본 false → 제외
    response = OrdersAdminApi(http_client=api_client).export()
    assert response.status_code == HTTP_200_OK
    # streaming_content 는 1회성 iterator — 한 번만 읽어 비교 (== 비교가 환불 주문 제외도 함께 검증).
    assert _export_order_ids(response) == {str(completed_order.id)}


@pytest.mark.django_db
def test_admin_export_scopes_by_event_id(api_client, ticket_product, non_ticket_product, order_factory):
    """`?event_id=` 가 해당 이벤트 카테고리의 상품을 가진 주문만 내보낸다."""
    event = baker.make("event.Event", name="파이콘 한국 2026")
    ticket_product.category.event = event
    ticket_product.category.save()

    in_event_order = order_factory(status="completed")  # ticket_product (event 연결됨)
    order_factory(status="completed", is_ticket=False)  # non_ticket_product (event 없음)

    response = OrdersAdminApi(http_client=api_client).export({"event_id": str(event.id)})
    assert response.status_code == HTTP_200_OK
    assert _export_order_ids(response) == {str(in_event_order.id)}


@pytest.mark.django_db
def test_admin_export_scopes_by_category_group_id(api_client, ticket_product, non_ticket_product, order_factory):
    """`?category_group_id=` 가 해당 그룹 상품을 가진 주문만 내보낸다."""
    ticket_order = order_factory(status="completed")
    order_factory(status="completed", is_ticket=False)

    response = OrdersAdminApi(http_client=api_client).export(
        {"category_group_id": str(ticket_product.category.group_id)}
    )
    assert response.status_code == HTTP_200_OK
    assert _export_order_ids(response) == {str(ticket_order.id)}


@pytest.mark.django_db
def test_admin_partial_update_modifies_existing_customer_info(api_client, order_factory):
    completed_order = order_factory(status="completed")
    response = OrdersAdminApi(http_client=api_client).update(
        completed_order.id,
        {"customer_info": {"name": "수정", "phone": "01099998888", "email": "new@x.com", "organization": "Z"}},
    )
    assert response.status_code == HTTP_200_OK
    assert list(
        CustomerInfo.objects.filter(order=completed_order).values("name", "phone", "email", "organization")
    ) == [{"name": "수정", "phone": "01099998888", "email": "new@x.com", "organization": "Z"}]


@pytest.mark.django_db
def test_admin_partial_update_creates_customer_info_when_missing(api_client, order_factory):
    completed_order = order_factory(status="completed")
    CustomerInfo.objects.filter(order=completed_order).hard_delete()
    response = OrdersAdminApi(http_client=api_client).update(
        completed_order.id,
        {"customer_info": {"name": "신규", "phone": "01000000000", "email": "n@x.com", "organization": ""}},
    )
    assert response.status_code == HTTP_200_OK
    assert CustomerInfo.objects.filter(order=completed_order, name="신규", email="n@x.com").exists()


@pytest.mark.django_db
def test_admin_list_filters_by_user_id(api_client, customer_user, other_user, ticket_product, order_factory):
    completed_order = order_factory(status="completed")
    other_order = Order.objects.create(user=other_user, name="other")
    OrderProductRelation.objects.create(
        order=other_order,
        product=ticket_product,
        price=ticket_product.price,
        status=OrderProductRelation.OrderProductStatus.paid,
    )
    PaymentHistory.objects.create(
        order=other_order, imp_id="imp_o", status=PaymentHistoryStatus.completed, price=ticket_product.price
    )

    response = OrdersAdminApi(http_client=api_client).list({"user_id": str(customer_user.id)})
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [OrderAdminSerializer(instance=OrderAdminViewSet.queryset.get(id=completed_order.id)).data],
    }
