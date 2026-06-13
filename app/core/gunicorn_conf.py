import os

from core.observability import configure_opentelemetry

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", "4"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))


def post_fork(server, worker):
    configure_opentelemetry(role="api")
