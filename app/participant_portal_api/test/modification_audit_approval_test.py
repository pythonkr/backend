from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from core.util.django_orm import model_to_identifier
from core.util.thread_local import thread_local
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import override
from event.presentation.models import Presentation, PresentationSpeaker
from model_bakery import baker
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


def test_approve_presentation_audit_with_reordered_speakers(db, admin_client):
    """발표자 순서만 뒤집힌 채 저장된 과거 수정 요청도 승인할 수 있어야 한다."""
    presentation = baker.make(Presentation)
    speakers = baker.make(PresentationSpeaker, presentation=presentation, biography_ko="이전 소개", _quantity=2)
    audit = ModificationAudit.objects.create(
        instance_type=ContentType.objects.get_for_model(Presentation),
        instance_id=str(presentation.pk),
        original_data={model_to_identifier(presentation): {}},
        modification_data={
            model_to_identifier(presentation): {
                "speakers": [model_to_identifier(speaker) for speaker in reversed(speakers)]
            },
            model_to_identifier(speakers[0]): {"biography_ko": "새 소개"},
        },
    )

    response = admin_client.patch(APPROVE_URL.format(audit_id=audit.id), data={}, format="json")

    assert response.status_code == status.HTTP_200_OK, response.data
    speakers[0].refresh_from_db()
    assert speakers[0].biography_ko == "새 소개"
    assert set(presentation.speakers.values_list("id", flat=True)) == {speaker.pk for speaker in speakers}
