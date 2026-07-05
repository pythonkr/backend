import httpx
from core.external_apis.nhn_cloud.dooray import DoorayError, nhn_cloud_dooray_client
from django.urls import reverse
from rest_framework.test import APIClient
from user.models import UserExt

MASK = "*" * 12
ME_URL = reverse("v1:admin-user-me")


def _detail_url(pk) -> str:
    return reverse("v1:admin-user-detail", kwargs={"pk": pk})


def _me_returns(email: str):
    return lambda _token: {"name": "홍길동", "externalEmailAddress": email, "id": "member-1"}


def test_register_via_patch_validates_and_encrypts(api_client, superuser, monkeypatch):
    monkeypatch.setattr(nhn_cloud_dooray_client, "members_me", _me_returns(superuser.email))

    resp = api_client.patch(_detail_url(superuser.pk), {"dooray_api_key": "tok-123"}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["dooray_api_key"] == MASK  # 실토큰 대신 마스크
    assert UserExt.objects.get(pk=superuser.pk).dooray_api_key == "tok-123"  # DB 는 암호문, 필드가 복호화


def test_register_rejects_email_mismatch(api_client, superuser, monkeypatch):
    monkeypatch.setattr(nhn_cloud_dooray_client, "members_me", _me_returns("someone@dooray.com"))

    resp = api_client.patch(_detail_url(superuser.pk), {"dooray_api_key": "tok"}, format="json")

    assert resp.status_code == 400
    assert UserExt.objects.get(pk=superuser.pk).dooray_api_key is None


def test_register_rejects_invalid_token(api_client, superuser, monkeypatch):
    def _raise(_token):
        raise DoorayError(httpx.Response(401))

    monkeypatch.setattr(nhn_cloud_dooray_client, "members_me", _raise)

    resp = api_client.patch(_detail_url(superuser.pk), {"dooray_api_key": "bad"}, format="json")

    assert resp.status_code == 400


def test_cannot_register_on_other_users_record(api_client, superuser, monkeypatch, db):
    other = UserExt.objects.create_superuser(username="other", email="other@example.com", password="x")  # nosec B106
    monkeypatch.setattr(nhn_cloud_dooray_client, "members_me", _me_returns(superuser.email))

    resp = api_client.patch(_detail_url(other.pk), {"dooray_api_key": "tok"}, format="json")

    assert resp.status_code == 400  # 본인 레코드에만 허용
    assert UserExt.objects.get(pk=other.pk).dooray_api_key is None


def test_retrieve_other_user_masks_token_but_checks_connection(api_client, superuser, monkeypatch, db):
    other = UserExt.objects.create_superuser(username="other", email="o@example.com", password="x")  # nosec B106
    other.dooray_api_key = "secret"
    other.save(update_fields=["dooray_api_key"])
    monkeypatch.setattr(nhn_cloud_dooray_client, "members_me", _me_returns("o@example.com"))

    data = api_client.get(_detail_url(other.pk)).json()

    assert data["dooray_api_key"] == MASK  # 타인 실토큰 미노출
    # 상세는 해당 유저 토큰으로 라이브 검증 → 계정정보 노출(시크릿 아님, =연결됨 신호)
    assert data["dooray_account_info"]["externalEmailAddress"] == "o@example.com"


def test_owner_sees_real_token_on_retrieve_self(api_client, superuser, monkeypatch):
    superuser.dooray_api_key = "my-real-token"
    superuser.save(update_fields=["dooray_api_key"])
    monkeypatch.setattr(nhn_cloud_dooray_client, "members_me", _me_returns(superuser.email))

    data = api_client.get(_detail_url(superuser.pk)).json()

    assert data["dooray_api_key"] == "my-real-token"  # 본인 상세 → 실토큰
    assert data["dooray_account_info"]["name"] == "홍길동"


def test_me_masks_token_and_exposes_account_info(api_client, superuser, monkeypatch):
    before = api_client.get(ME_URL).json()
    assert before["dooray_api_key"] is None and before["dooray_account_info"] is None
    monkeypatch.setattr(nhn_cloud_dooray_client, "members_me", _me_returns(superuser.email))
    api_client.patch(_detail_url(superuser.pk), {"dooray_api_key": "tok"}, format="json")
    superuser.refresh_from_db()  # 실제 me 는 매 요청 DB 에서 유저를 새로 로드 (force_authenticate 는 객체 캐시)

    after = api_client.get(ME_URL).json()

    assert after["dooray_api_key"] == MASK  # mcp 는 토큰 미조회(마스킹)
    # me 는 라이브 검증(mcp gating 정확도) → 계정정보 존재 = 연결됨. list 만 예외.
    assert after["dooray_account_info"]["externalEmailAddress"] == superuser.email


def test_list_does_not_call_dooray(api_client, superuser):
    # members_me 를 mock 하지 않음 — list 가 라이브 호출하면 SocketBlockedError 로 실패한다.
    superuser.dooray_api_key = "tok"
    superuser.save(update_fields=["dooray_api_key"])

    resp = api_client.get(reverse("v1:admin-user-list"))

    assert resp.status_code == 200  # 라이브 호출 없음(SocketBlockedError 안 남)
    row = next(u for u in resp.json()["results"] if u["id"] == superuser.pk)
    assert row["dooray_account_info"] is None  # list 는 계정정보 미조회
    assert row["dooray_api_key"] == MASK


def test_clear_via_patch_empty_string(api_client, superuser):
    superuser.dooray_api_key = "tok"
    superuser.save(update_fields=["dooray_api_key"])

    resp = api_client.patch(_detail_url(superuser.pk), {"dooray_api_key": ""}, format="json")

    assert resp.status_code == 200
    assert UserExt.objects.get(pk=superuser.pk).dooray_api_key is None


def _forward_ok(*_args, **_kwargs):
    return httpx.Response(200, json={"header": {"isSuccessful": True, "resultCode": 0}, "result": []})


def _proxy_url(route: str) -> str:
    return reverse("v1:admin-dooray-proxy", kwargs={"route": route})


def test_proxy_requires_registered_token(api_client):
    assert api_client.get(_proxy_url("project/v1/projects")).status_code == 409


def test_proxy_rejects_disallowed_path(api_client, superuser):
    superuser.dooray_api_key = "tok-123"
    superuser.save(update_fields=["dooray_api_key"])
    # Messenger 는 allowlist 밖 → 403 (SSRF/스코프 가드).
    assert api_client.get(_proxy_url("messenger/v1/channels")).status_code == 403


def test_proxy_forwards_allowed_path(superuser, monkeypatch):
    monkeypatch.setattr(nhn_cloud_dooray_client, "forward", _forward_ok)
    superuser.dooray_api_key = "tok-123"
    superuser.save(update_fields=["dooray_api_key"])
    client = APIClient()
    client.force_authenticate(user=superuser)

    resp = client.get(_proxy_url("project/v1/projects"))

    assert resp.status_code == 200
    assert resp.json()["result"] == []


def test_proxy_passes_through_dooray_error(superuser, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise DoorayError(httpx.Response(404, json={"header": {"isSuccessful": False, "resultMessage": "없음"}}))

    monkeypatch.setattr(nhn_cloud_dooray_client, "forward", _raise)
    superuser.dooray_api_key = "tok-123"
    superuser.save(update_fields=["dooray_api_key"])
    client = APIClient()
    client.force_authenticate(user=superuser)

    resp = client.get(_proxy_url("project/v1/projects/x/posts/y"))

    assert resp.status_code == 404  # Dooray 오류 상태·본문 그대로 통과
    assert resp.json()["header"]["resultMessage"] == "없음"
