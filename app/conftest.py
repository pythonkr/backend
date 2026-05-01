from django.test import override_settings
from pytest import fixture


@fixture(autouse=True)
def _celery_eager():
    with override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=False):
        yield
