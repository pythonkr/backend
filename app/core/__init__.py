from os import environ

from celery import Celery
from celery.signals import worker_process_init
from core.observability import configure_opentelemetry

environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

celery_app = Celery("pyconkr")
celery_app.config_from_object("django.conf:settings", namespace="CELERY")
celery_app.autodiscover_tasks()


@worker_process_init.connect
def _init_opentelemetry(**_kwargs):
    configure_opentelemetry(role="worker")
