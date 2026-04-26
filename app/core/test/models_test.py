from unittest.mock import patch

import pytest
from notification.models import EmailNotificationTemplate
from user.models import UserExt


@pytest.fixture
def system_user(db):
    return UserExt.get_system_user()


@pytest.fixture
def other_user(db):
    return UserExt.objects.create(username="other", email="other@example.com")


@pytest.fixture
def template(system_user):
    return EmailNotificationTemplate.objects.create(
        code="t",
        title="t",
        from_address="a@b.c",
        data='{"title":"x","from_":"f","send_to":"r","body":"b"}',
        created_by=system_user,
        updated_by=system_user,
    )


# `BaseAbstractModelQuerySet.update()`가 호출자가 명시한 `updated_by[_id]`를 보존해야 함을 보장.
# 회귀 케이스: Django의 `bulk_update`는 FK 컬럼명(`updated_by_id`)을 사용해 `update()`를 호출하는데,
# 오버라이드가 무조건 `updated_by`를 추가하면 같은 컬럼이 두 번 SET되어 PostgreSQL이 거부함.


@pytest.mark.django_db
def test_queryset_update_auto_injects_updated_by_when_not_specified(template, other_user):
    # 호출자가 updated_by를 명시하지 않으면 `get_current_user()` 결과를 자동 주입
    with patch("core.models.get_current_user", return_value=other_user):
        EmailNotificationTemplate.objects.filter(pk=template.pk).update(title="new")
    template.refresh_from_db()
    assert template.title == "new"
    assert template.updated_by_id == other_user.id


@pytest.mark.django_db
def test_queryset_update_respects_explicit_updated_by_relation(template, other_user, system_user):
    # 명시한 updated_by가 자동 주입에 의해 덮어쓰이면 안 됨
    with patch("core.models.get_current_user", return_value=system_user):
        EmailNotificationTemplate.objects.filter(pk=template.pk).update(updated_by=other_user)
    template.refresh_from_db()
    assert template.updated_by_id == other_user.id


@pytest.mark.django_db
def test_queryset_update_respects_explicit_updated_by_id(template, other_user, system_user):
    # FK 컬럼명(`*_id`) 형태로 명시한 경우에도 자동 주입을 건너뛰어야 함 — bulk_update 경로
    with patch("core.models.get_current_user", return_value=system_user):
        EmailNotificationTemplate.objects.filter(pk=template.pk).update(updated_by_id=other_user.id)
    template.refresh_from_db()
    assert template.updated_by_id == other_user.id


@pytest.mark.django_db
def test_queryset_bulk_update_does_not_raise_duplicate_column(template, other_user):
    # bulk_update는 내부적으로 `update(updated_by_id=Case(...))`를 호출 → 자동 주입과 충돌하면 안 됨
    template.title = "bulked"
    template.updated_by = other_user
    EmailNotificationTemplate.objects.bulk_update([template], fields=["title", "updated_by"])

    template.refresh_from_db()
    assert template.title == "bulked"
    assert template.updated_by_id == other_user.id
