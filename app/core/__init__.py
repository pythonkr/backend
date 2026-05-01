from os import environ

from celery import Celery

environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

celery_app = Celery("pyconkr")
celery_app.config_from_object("django.conf:settings", namespace="CELERY")
celery_app.autodiscover_tasks()
