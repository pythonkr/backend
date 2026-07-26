"""수정 심사 승인 시 변경 내역이 승인자의 언어와 무관하게 올바른 언어 컬럼에 반영되는지 검증한다."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from core.util.thread_local import thread_local
from django.core.files.base import ContentFile
from django.utils.translation import override
from file.models import PublicFile
from participant_portal_api.models import ModificationAudit
from participant_portal_api.serializers.user import UserPortalSerializer
from rest_framework import status
from rest_framework.test import APIClient
from user.models import UserExt

APPROVE_URL = "/v1/admin-api/participant_portal_api/modificationaudit/{audit_id}/approve/"


@contextmanager
def _acting_as(user: UserExt):
    """created_by 등은 thread-local 에서 실행자를 읽으므로, 요청자를 명시적으로 주입한다."""
    thread_local.current_request = SimpleNamespace(user=user)
    try:
        yield
    finally:
        if hasattr(thread_local, "current_request"):
            del thread_local.current_request


@pytest.fixture
def requester(db) -> UserExt:
    return UserExt.objects.create_user(
        username="requester", email="requester@example.com", nickname_ko="한글이름", nickname_en="EnglishName"
    )


@pytest.fixture
def superuser(db) -> UserExt:
    return UserExt.objects.create_superuser(username="admin", email="admin@example.com")


@pytest.fixture
def admin_client(superuser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=superuser)
    return client


def _request_profile_modification(requester: UserExt, payload: dict, language: str) -> ModificationAudit:
    """참가자 포탈에서 주어진 언어로 프로필 수정을 요청하고, 생성된 심사 건을 돌려준다."""
    with override(language), _acting_as(requester):
        serializer = UserPortalSerializer(instance=requester, data=payload, partial=True)
        assert serializer.is_valid(), serializer.errors
        serializer.save()

    return ModificationAudit.objects.get(status=ModificationAudit.Status.REQUESTED)


def test_approve_en_nickname_request_under_ko_locale_keeps_ko_nickname(requester, admin_client):
    """영문 UI 에서 영문 닉네임만 고친 요청을, 어드민이 한국어 로케일로 승인해도 한글 닉네임은 그대로여야 한다."""
    audit = _request_profile_modification(requester, {"nickname_en": "NewEnglish"}, language="en")

    response = admin_client.patch(
        APPROVE_URL.format(audit_id=audit.id), data={}, format="json", HTTP_ACCEPT_LANGUAGE="ko"
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    requester.refresh_from_db()
    assert requester.nickname_en == "NewEnglish"
    assert requester.nickname_ko == "한글이름"


def test_approve_ko_nickname_request_under_en_locale_keeps_en_nickname(requester, admin_client):
    """한국어 UI 에서 한글 닉네임만 고친 요청을, 어드민이 영문 로케일로 승인해도 영문 닉네임은 그대로여야 한다."""
    audit = _request_profile_modification(requester, {"nickname_ko": "새한글이름"}, language="ko")

    response = admin_client.patch(
        APPROVE_URL.format(audit_id=audit.id), data={}, format="json", HTTP_ACCEPT_LANGUAGE="en"
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    requester.refresh_from_db()
    assert requester.nickname_ko == "새한글이름"
    assert requester.nickname_en == "EnglishName"


@pytest.mark.parametrize("approval_language", ["ko", "en"], ids=["approved_in_ko", "approved_in_en"])
def test_approve_applies_requested_nickname_regardless_of_approval_locale(requester, admin_client, approval_language):
    """요청한 언어의 닉네임 변경 자체는 승인자의 로케일과 무관하게 반영되어야 한다."""
    audit = _request_profile_modification(requester, {"nickname_ko": "새한글이름"}, language="ko")

    response = admin_client.patch(
        APPROVE_URL.format(audit_id=audit.id),
        data={},
        format="json",
        HTTP_ACCEPT_LANGUAGE=approval_language,
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    requester.refresh_from_db()
    assert requester.nickname_ko == "새한글이름"


def test_approve_applies_non_translated_field(requester, admin_client):
    """번역 대상이 아닌 필드(프로필 이미지)는 기존대로 정상 반영되어야 한다."""
    with _acting_as(requester):
        image = PublicFile.objects.create(
            file=ContentFile(b"image-bytes", name="profile.png"), mimetype="image/png", hash="hash", size=11
        )

    audit = _request_profile_modification(requester, {"image": image.pk}, language="ko")

    response = admin_client.patch(
        APPROVE_URL.format(audit_id=audit.id), data={}, format="json", HTTP_ACCEPT_LANGUAGE="ko"
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    requester.refresh_from_db()
    assert requester.image_id == image.pk


def test_approve_marks_audit_as_approved(requester, admin_client):
    """승인이 끝나면 심사 상태가 approved 로 바뀌어야 한다."""
    audit = _request_profile_modification(requester, {"nickname_ko": "새한글이름"}, language="ko")

    response = admin_client.patch(APPROVE_URL.format(audit_id=audit.id), data={}, format="json")

    assert response.status_code == status.HTTP_200_OK, response.data
    assert response.data["status"] == ModificationAudit.Status.APPROVED
    audit.refresh_from_db()
    assert audit.status == ModificationAudit.Status.APPROVED
