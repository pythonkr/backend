import http

import pytest
from allauth.account.models import EmailAddress
from django.urls import reverse
from rest_framework.test import APIClient
from shop.order.models import Order
from user.models import UserExt
from user.models.merge import UserMergeHistory

LIST = "v1:admin-user-merge-list"
DETAIL = "v1:admin-user-merge-detail"
PREVIEW = "v1:admin-user-merge-preview"
REVERT = "v1:admin-user-merge-revert"


@pytest.fixture
def source_user(db) -> UserExt:
    return UserExt.objects.create_user(username="source", email="source@example.com")


@pytest.fixture
def target_user(db) -> UserExt:
    return UserExt.objects.create_user(username="target", email="target@example.com")


# ---- Auth -------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_list_rejected():
    response = APIClient().get(reverse(LIST))
    assert response.status_code in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)


@pytest.mark.django_db
def test_non_superuser_preview_rejected(customer_user, source_user, target_user):
    client = APIClient()
    client.force_authenticate(user=customer_user)
    response = client.post(reverse(PREVIEW), {"source": source_user.id, "target": target_user.id}, format="json")
    assert response.status_code == http.HTTPStatus.FORBIDDEN


# ---- Preview (savepoint 실행 후 롤백) ----------------------------------------


@pytest.mark.django_db
def test_preview_lists_actual_merge_objects(api_client, source_user, target_user):
    order = Order.objects.create(user=source_user, name="src-order")

    response = api_client.post(reverse(PREVIEW), {"source": source_user.id, "target": target_user.id}, format="json")
    assert response.status_code == http.HTTPStatus.OK, response.json()
    body = response.json()
    assert body["source"]["id"] == source_user.id
    assert body["target"]["id"] == target_user.id

    assert body["is_self_merge"] is False

    moved = next(m for m in body["merged_objects"] if m["target_id"] == str(order.id))
    assert moved["target_type_app"] == "shop"
    assert moved["target_type_resource"] == "order"
    assert moved["field_names"] == ["user"]
    assert body["source"]["is_active"] is False  # post-merge 상태 노출(source 비활성)


@pytest.mark.django_db
def test_preview_rolls_back_and_persists_nothing(api_client, source_user, target_user):
    Order.objects.create(user=source_user, name="src-order")

    api_client.post(reverse(PREVIEW), {"source": source_user.id, "target": target_user.id}, format="json")

    assert Order.objects.get(name="src-order").user_id == source_user.id
    assert not UserMergeHistory.objects.exists()
    source_user.refresh_from_db()
    assert source_user.is_active is True
    assert source_user.merged_to_id is None


@pytest.mark.django_db
def test_preview_same_account_rejected(api_client, source_user):
    response = api_client.post(reverse(PREVIEW), {"source": source_user.id, "target": source_user.id}, format="json")
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


# ---- Create (execute merge) -------------------------------------------------


@pytest.mark.django_db
def test_create_merges_and_repoints(api_client, superuser, source_user, target_user):
    order = Order.objects.create(user=source_user, name="src-order")

    response = api_client.post(reverse(LIST), {"source": source_user.id, "target": target_user.id}, format="json")
    assert response.status_code == http.HTTPStatus.CREATED, response.json()
    body = response.json()
    assert body["source"]["id"] == source_user.id
    assert body["target"]["id"] == target_user.id
    assert body["is_self_merge"] is False
    assert superuser.email in body["created_by"]  # StringRelatedField → str(UserExt)
    assert body["reverted_at"] is None

    # Order 는 라우트 컨벤션상 shop/order.
    [moved] = body["merged_objects"]
    assert moved["target_type_app"] == "shop"
    assert moved["target_type_resource"] == "order"
    assert moved["target_id"] == str(order.id)
    assert moved["field_names"] == ["user"]

    order.refresh_from_db()
    source_user.refresh_from_db()
    assert order.user_id == target_user.id
    assert source_user.is_active is False
    assert source_user.merged_to_id == target_user.id


@pytest.mark.django_db
def test_create_same_account_rejected(api_client, source_user):
    response = api_client.post(reverse(LIST), {"source": source_user.id, "target": source_user.id}, format="json")
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert UserMergeHistory.objects.count() == 0


@pytest.mark.django_db
def test_create_into_already_merged_target_rejected(api_client, source_user, target_user):
    other = UserExt.objects.create_user(username="other", email="other@example.com")
    UserMergeHistory.objects.create(source=target_user, target=other).merge()  # target 이 이미 병합됨
    EmailAddress.objects.create(user=target_user, email="again@example.com", verified=True, primary=True)  # 검증 통과용

    response = api_client.post(reverse(LIST), {"source": source_user.id, "target": target_user.id}, format="json")
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    # 실패한 병합 기록이 남으면 안 됨(atomic rollback).
    assert not UserMergeHistory.objects.filter(source=source_user).exists()


@pytest.mark.django_db
def test_create_enforces_self_mergeable(api_client, source_user, target_user):
    # 운영자 병합도 assert_self_mergeable 적용 — target 에 인증 이메일이 없으면 거부(운영자가 보고 설정 가능).
    EmailAddress.objects.filter(user=target_user).delete()
    response = api_client.post(reverse(LIST), {"source": source_user.id, "target": target_user.id}, format="json")
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert not UserMergeHistory.objects.filter(source=source_user).exists()


# ---- List / Retrieve --------------------------------------------------------


@pytest.mark.django_db
def test_list_and_retrieve(api_client, source_user, target_user):
    merge = UserMergeHistory.objects.create(source=source_user, target=target_user)
    merge.merge()

    response = api_client.get(reverse(LIST))
    assert response.status_code == http.HTTPStatus.OK
    rows = response.json()["results"]
    assert any(row["id"] == str(merge.id) for row in rows)

    response = api_client.get(reverse(DETAIL, kwargs={"pk": merge.id}))
    assert response.status_code == http.HTTPStatus.OK
    assert response.json()["source"]["id"] == source_user.id


@pytest.mark.django_db
def test_list_excludes_merged_objects_retrieve_includes(api_client, source_user, target_user):
    Order.objects.create(user=source_user, name="src-order")
    merge = UserMergeHistory.objects.create(source=source_user, target=target_user)
    merge.merge()

    [row] = api_client.get(reverse(LIST)).json()["results"]
    assert "merged_objects" not in row  # list 는 대량 가능성 때문에 제외

    detail = api_client.get(reverse(DETAIL, kwargs={"pk": merge.id})).json()
    assert len(detail["merged_objects"]) == 1


@pytest.mark.django_db
def test_list_filter_reverted(api_client, source_user, target_user):
    merge = UserMergeHistory.objects.create(source=source_user, target=target_user)
    merge.merge()

    assert api_client.get(reverse(LIST), {"reverted": "true"}).json()["results"] == []
    assert len(api_client.get(reverse(LIST), {"reverted": "false"}).json()["results"]) == 1


# ---- Revert -----------------------------------------------------------------


@pytest.mark.django_db
def test_revert_restores(api_client, source_user, target_user):
    order = Order.objects.create(user=source_user, name="src-order")
    merge = UserMergeHistory.objects.create(source=source_user, target=target_user)
    merge.merge()

    response = api_client.post(reverse(REVERT, kwargs={"pk": merge.id}))
    assert response.status_code == http.HTTPStatus.OK, response.json()
    body = response.json()
    assert body["reverted_at"] is not None  # 재조회 없이 in-place 갱신된 history 직렬화

    order.refresh_from_db()
    source_user.refresh_from_db()
    assert order.user_id == source_user.id
    assert source_user.is_active is True
    assert source_user.merged_to_id is None


@pytest.mark.django_db
def test_double_revert_rejected(api_client, source_user, target_user):
    merge = UserMergeHistory.objects.create(source=source_user, target=target_user)
    merge.merge()
    merge.unmerge()

    response = api_client.post(reverse(REVERT, kwargs={"pk": merge.id}))
    assert response.status_code == http.HTTPStatus.BAD_REQUEST


# ---- JSON Schema (form) -----------------------------------------------------


@pytest.mark.django_db
def test_json_schema_exposes_source_and_target(api_client):
    response = api_client.get(reverse(LIST) + "json-schema/")
    assert response.status_code == http.HTTPStatus.OK
    props = response.json()["schema"]["properties"]
    assert "source" in props and "target" in props
