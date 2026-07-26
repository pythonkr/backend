from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from core.util.thread_local import thread_local
from django.utils.translation import override
from participant_portal_api.models import ModificationAudit
from participant_portal_api.serializers.user import UserPortalSerializer
from rest_framework import status
from rest_framework.test import APIClient
from user.models import UserExt

APPROVE_URL = "/v1/admin-api/participant_portal_api/modificationaudit/{audit_id}/approve/"


@contextmanager
def _acting_as(user: UserExt):
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
    with override(language), _acting_as(requester):
        serializer = UserPortalSerializer(instance=requester, data=payload, partial=True)
        assert serializer.is_valid(), serializer.errors
        serializer.save()

    return ModificationAudit.objects.get(status=ModificationAudit.Status.REQUESTED)


def test_approve_en_nickname_request_under_ko_locale_keeps_ko_nickname(requester, admin_client):
    audit = _request_profile_modification(requester, {"nickname_en": "NewEnglish"}, language="en")

    response = admin_client.patch(
        APPROVE_URL.format(audit_id=audit.id), data={}, format="json", HTTP_ACCEPT_LANGUAGE="ko"
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    requester.refresh_from_db()
    assert requester.nickname_en == "NewEnglish"
    assert requester.nickname_ko == "한글이름"


def test_approve_ko_nickname_request_under_en_locale_keeps_en_nickname(requester, admin_client):
    audit = _request_profile_modification(requester, {"nickname_ko": "새한글이름"}, language="ko")

    response = admin_client.patch(
        APPROVE_URL.format(audit_id=audit.id), data={}, format="json", HTTP_ACCEPT_LANGUAGE="en"
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    requester.refresh_from_db()
    assert requester.nickname_ko == "새한글이름"
    assert requester.nickname_en == "EnglishName"
