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
        sent_from="a@b.c",
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


@pytest.mark.django_db
def test_save_sets_created_by_on_insert_via_constructor(other_user):
    # objects.create()가 아닌 생성자 + save() 경로에서도 created_by가 채워져야 함
    with patch("core.models.get_current_user", return_value=other_user):
        instance = EmailNotificationTemplate(
            code="t2",
            title="t2",
            sent_from="a@b.c",
            data='{"title":"x","from_":"f","send_to":"r","body":"b"}',
        )
        instance.save()
    instance.refresh_from_db()
    assert instance.created_by_id == other_user.id
    assert instance.updated_by_id == other_user.id


@pytest.mark.django_db
def test_save_preserves_created_by_on_update(system_user, other_user):
    # 다른 사용자가 수정해도 created_by(원작성자)는 보존되고 updated_by만 갱신
    with patch("core.models.get_current_user", return_value=system_user):
        instance = EmailNotificationTemplate(
            code="t_upd",
            title="t",
            sent_from="a@b.c",
            data='{"title":"x","from_":"f","send_to":"r","body":"b"}',
        )
        instance.save()
    with patch("core.models.get_current_user", return_value=other_user):
        instance.title = "changed"
        instance.save()
    instance.refresh_from_db()
    assert instance.created_by_id == system_user.id
    assert instance.updated_by_id == other_user.id


@pytest.mark.django_db
def test_save_overwrites_caller_created_by_on_insert(system_user, other_user):
    # insert 시 호출자가 명시한 created_by도 현재 사용자로 덮어씀 (감사 필드는 시스템 관리 — create()와 동일 의도)
    with patch("core.models.get_current_user", return_value=other_user):
        instance = EmailNotificationTemplate(
            code="t3",
            title="t3",
            sent_from="a@b.c",
            data='{"title":"x","from_":"f","send_to":"r","body":"b"}',
            created_by=system_user,
        )
        instance.save()
    instance.refresh_from_db()
    assert instance.created_by_id == other_user.id
    assert instance.updated_by_id == other_user.id


@pytest.mark.django_db
def test_create_overwrites_caller_provided_audit(system_user, other_user):
    # QuerySet.create()도 호출자 지정 audit 값을 현재 사용자로 덮어씀 (의도된 동작)
    with patch("core.models.get_current_user", return_value=other_user):
        instance = EmailNotificationTemplate.objects.create(
            code="t4",
            title="t4",
            sent_from="a@b.c",
            data='{"title":"x","from_":"f","send_to":"r","body":"b"}',
            created_by=system_user,
            updated_by=system_user,
        )
    instance.refresh_from_db()
    assert instance.created_by_id == other_user.id
    assert instance.updated_by_id == other_user.id


@pytest.mark.django_db
def test_bulk_create_fills_audit_from_current_user(other_user):
    with patch("core.models.get_current_user", return_value=other_user):
        EmailNotificationTemplate.objects.bulk_create(
            [
                EmailNotificationTemplate(code="bc1", title="bc1", sent_from="a@b.c", data="{}"),
                EmailNotificationTemplate(code="bc2", title="bc2", sent_from="a@b.c", data="{}"),
            ]
        )
    for instance in EmailNotificationTemplate.objects.filter(code__in=["bc1", "bc2"]):
        assert instance.created_by_id == other_user.id
        assert instance.updated_by_id == other_user.id


@pytest.mark.django_db
def test_bulk_create_respects_explicit_audit(system_user, other_user):
    # 호출자가 명시한 created_by/updated_by는 현재 사용자로 덮어쓰지 않음 (NHN 동기화 케이스)
    with patch("core.models.get_current_user", return_value=other_user):
        EmailNotificationTemplate.objects.bulk_create(
            [
                EmailNotificationTemplate(
                    code="bc3",
                    title="bc3",
                    sent_from="a@b.c",
                    data="{}",
                    created_by=system_user,
                    updated_by=system_user,
                ),
            ]
        )
    instance = EmailNotificationTemplate.objects.get(code="bc3")
    assert instance.created_by_id == system_user.id
    assert instance.updated_by_id == system_user.id
