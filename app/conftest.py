from core.util.thread_local import thread_local
from django.test import override_settings
from pytest import fixture


@fixture(autouse=True)
def _celery_eager():
    with override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=False):
        yield


@fixture(autouse=True)
def _isolate_thread_local():
    # ThreadLocalMiddleware 가 thread_local.current_request 를 정리하지 않아, 이전 테스트(롤백)의 user 가
    # get_current_user() 로 노출돼 created_by FK violation 유발. 양쪽으로 정리.
    if hasattr(thread_local, "current_request"):
        del thread_local.current_request
    yield
    if hasattr(thread_local, "current_request"):
        del thread_local.current_request
