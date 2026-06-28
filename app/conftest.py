from core.util.thread_local import thread_local
from django.core.cache import cache
from django.test import override_settings
from pytest import fixture


@fixture(autouse=True)
def _clear_cache():
    # /api/schema 는 cache_page 로 LocMemCache 에 캐시되는데, 캐시는 DB 와 달리 테스트 간 롤백되지 않는다.
    # 먼저 실행된 테스트가 만든 스키마(예: SocialApp 없는 상태로 생성된 provider enum 누락분)가 누출되므로 매 테스트 격리.
    cache.clear()
    yield


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
