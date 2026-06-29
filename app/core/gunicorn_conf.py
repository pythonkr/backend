import os

from core.observability import configure_opentelemetry

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", "4"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "100"))


def post_fork(server, worker):
    configure_opentelemetry(role="api")
