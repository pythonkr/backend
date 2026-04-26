import pytest
from core.models import BaseAbstractModelQuerySet
from core.util.thread_local import thread_local
from notification.models import (
    EmailNotificationTemplate,
    NHNCloudKakaoAlimTalkNotificationTemplate,
    NHNCloudSMSNotificationTemplate,
)
from rest_framework.test import APIClient
from user.models import UserExt


@pytest.fixture(autouse=True)
def _isolate_thread_local():
    # ThreadLocalMiddleware가 thread_local.current_request를 정리하지 않아, 직전 테스트의 (롤백된) user를
    # get_current_user()가 반환하면서 FK violation이 발생. 양쪽으로 정리.
    if hasattr(thread_local, "current_request"):
        del thread_local.current_request
    yield
    if hasattr(thread_local, "current_request"):
        del thread_local.current_request


@pytest.fixture
def superuser(db) -> UserExt:
    return UserExt.objects.create_superuser(username="admin", email="admin@example.com", password="x")  # nosec B106


@pytest.fixture
def api_client(superuser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=superuser)
    return client


@pytest.fixture
def email_template(superuser) -> EmailNotificationTemplate:
    return EmailNotificationTemplate.objects.create(
        code="welcome",
        title="환영합니다",
        from_address="from@example.com",
        data='{"title":"Hi {{ name }}","from_":"f","send_to":"{{ recipient }}","body":"Hello {{ name }}"}',
        created_by=superuser,
        updated_by=superuser,
    )


@pytest.fixture
def sms_template(superuser) -> NHNCloudSMSNotificationTemplate:
    return NHNCloudSMSNotificationTemplate.objects.create(
        code="sms-welcome",
        title="SMS 환영",
        from_no="0212345678",
        data='{"body":"안녕 {{ name }}님"}',
        created_by=superuser,
        updated_by=superuser,
    )


@pytest.fixture
def kakao_template(superuser) -> NHNCloudKakaoAlimTalkNotificationTemplate:
    # NHN Cloud 측에서 동기화하는 모델이므로 일반 .create() 가 차단됨 — bulk_create로 우회.
    template = NHNCloudKakaoAlimTalkNotificationTemplate(
        code="kakao-welcome",
        title="알림톡 환영",
        sender_key="S1",
        data='{"templateContent":"안녕 #{name}","buttons":[]}',
        created_by=superuser,
        updated_by=superuser,
    )
    [created] = BaseAbstractModelQuerySet(model=NHNCloudKakaoAlimTalkNotificationTemplate).bulk_create([template])
    return created
