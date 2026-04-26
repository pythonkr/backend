from unittest.mock import MagicMock, patch

import pytest
from core.models import BaseAbstractModelQuerySet
from notification.models import NHNCloudKakaoAlimTalkNotificationTemplate as Template
from user.models import UserExt


@pytest.fixture
def system_user(db):
    return UserExt.get_system_user()


@pytest.fixture
def mock_nhn_client():
    """NHN Cloud client 싱글톤을 mock으로 교체."""
    mock = MagicMock()
    mock.get_sender_list.return_value = {"senders": [{"senderKey": "S1"}]}
    with patch("notification.models.nhn_cloud_kakao_alimtalk.nhn_cloud_kakao_alimtalk_client", mock):
        yield mock


# ---- sync_with_nhn_cloud() --------------------------------------------------


@pytest.mark.django_db
def test_sync_creates_new_external_templates(mock_nhn_client):
    mock_nhn_client.list_templates.return_value = {
        "templateListResponse": {
            "templates": [
                {
                    "templateCode": "T1",
                    "templateName": "Hi",
                    "senderKey": "S1",
                    "templateContent": "안녕 #{name}",
                    "status": "TSC03",
                },
            ]
        }
    }

    Template.objects.sync_with_nhn_cloud()

    assert Template.objects.filter_active().count() == 1
    row = Template.objects.get(code="T1")
    assert row.title == "Hi"
    assert row.sender_key == "S1"


@pytest.mark.django_db
def test_sync_updates_changed_templates(system_user, mock_nhn_client):
    # Given: 기존 template
    existing = Template(
        code="X",
        title="OLD",
        sender_key="S1",
        description="",
        data='{"templateCode":"X","templateName":"OLD","senderKey":"S1","templateContent":"old","status":"TSC03"}',
        created_by=system_user,
        updated_by=system_user,
    )
    # 차단을 우회해서 시드. (sync 외부에서 직접 만드는 정상 경로는 없음)
    BaseAbstractModelQuerySet(model=Template).bulk_create([existing])

    mock_nhn_client.list_templates.return_value = {
        "templateListResponse": {
            "templates": [
                {
                    "templateCode": "X",
                    "templateName": "NEW",
                    "senderKey": "S1",
                    "templateContent": "changed",
                    "status": "TSC03",
                },
            ]
        }
    }

    Template.objects.sync_with_nhn_cloud()

    row = Template.objects.get(code="X")
    assert row.title == "NEW"
    assert "NEW" in row.data


@pytest.mark.django_db
def test_sync_soft_deletes_missing_templates(system_user, mock_nhn_client):
    BaseAbstractModelQuerySet(model=Template).bulk_create(
        [
            Template(
                code="GONE",
                title="g",
                sender_key="S1",
                description="",
                data="{}",
                created_by=system_user,
                updated_by=system_user,
            ),
        ]
    )

    # NHN Cloud 응답에서 사라짐 → soft delete 대상
    mock_nhn_client.list_templates.return_value = {"templateListResponse": {"templates": []}}
    Template.objects.sync_with_nhn_cloud()

    assert Template.objects.filter_active().count() == 0
    assert Template.objects.filter(code="GONE", deleted_at__isnull=False).exists()


@pytest.mark.django_db
def test_sync_ignores_unapproved_templates(mock_nhn_client):
    # TSC02(검수 중) 등 비승인 상태는 무시
    mock_nhn_client.list_templates.return_value = {
        "templateListResponse": {
            "templates": [
                {
                    "templateCode": "approved",
                    "templateName": "A",
                    "senderKey": "S1",
                    "templateContent": "x",
                    "status": "TSC03",
                },
                {
                    "templateCode": "pending",
                    "templateName": "P",
                    "senderKey": "S1",
                    "templateContent": "y",
                    "status": "TSC02",
                },
            ]
        }
    }

    Template.objects.sync_with_nhn_cloud()

    codes = set(Template.objects.filter_active().values_list("code", flat=True))
    assert codes == {"approved"}


# ---- 로컬 CUD 차단 ----------------------------------------------------------
# Kakao 템플릿은 NHN Cloud Console에서 관리하므로 로컬 CUD가 차단되어야 함.


@pytest.mark.django_db
def test_kakao_objects_create_blocked():
    with pytest.raises(NotImplementedError, match="NHN Cloud Console"):
        Template.objects.create(code="x", title="y", data="{}")


@pytest.mark.django_db
def test_kakao_objects_bulk_create_blocked():
    with pytest.raises(NotImplementedError, match="NHN Cloud Console"):
        Template.objects.bulk_create([Template(code="x", title="y", data="{}")])


@pytest.mark.django_db
def test_kakao_objects_update_blocked():
    with pytest.raises(NotImplementedError, match="NHN Cloud Console"):
        Template.objects.update(title="nope")


@pytest.mark.django_db
def test_kakao_objects_delete_blocked():
    with pytest.raises(NotImplementedError, match="NHN Cloud Console"):
        Template.objects.all().delete()


@pytest.mark.django_db
def test_kakao_objects_get_or_create_blocked():
    with pytest.raises(NotImplementedError, match="NHN Cloud Console"):
        Template.objects.get_or_create(code="x", defaults={"title": "y", "data": "{}"})


@pytest.mark.django_db
def test_kakao_instance_save_blocked():
    with pytest.raises(NotImplementedError, match="NHN Cloud Console"):
        Template(code="m", title="n", data="{}").save()


@pytest.mark.django_db
def test_kakao_instance_delete_blocked(system_user, mock_nhn_client):
    mock_nhn_client.list_templates.return_value = {
        "templateListResponse": {
            "templates": [
                {
                    "templateCode": "T1",
                    "templateName": "Hi",
                    "senderKey": "S1",
                    "templateContent": "x",
                    "status": "TSC03",
                },
            ]
        }
    }
    Template.objects.sync_with_nhn_cloud()
    row = Template.objects.first()
    with pytest.raises(NotImplementedError, match="NHN Cloud Console"):
        row.delete()
