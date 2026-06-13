import logging
import os
from typing import Literal

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

RoleType = Literal["api", "worker"]
logger = logging.getLogger(__name__)

_configured = False


def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _get_otlp_endpoint() -> str | None:
    return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")


def configure_opentelemetry(role: RoleType) -> None:
    global _configured
    if _configured or _flag("OTEL_SDK_DISABLED", False) or not _get_otlp_endpoint():
        return
    _configured = True

    try:
        resource = Resource.create(
            {
                "service.name": os.environ.get("OTEL_SERVICE_NAME", f"pyconkr-{role}"),
                "service.namespace": "pyconkr",
                "pyconkr.process_role": role,
                "service.version": os.environ.get("DEPLOYMENT_RELEASE_VERSION", "unknown"),
                "deployment.environment": os.environ.get("API_STAGE", "unknown"),
            }
        )

        if _flag("OTEL_TRACES_ENABLED", True):
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            trace.set_tracer_provider(provider)
        if _flag("OTEL_METRICS_ENABLED", True):
            metrics.set_meter_provider(
                MeterProvider(
                    resource=resource,
                    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
                )
            )
        DjangoInstrumentor().instrument()
        PsycopgInstrumentor().instrument()
        CeleryInstrumentor().instrument()
        RedisInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        RequestsInstrumentor().instrument()

        logger.info("OpenTelemetry configured (role=%s)", role)
    except Exception:
        logger.exception("OpenTelemetry 초기화 실패 — 계측 없이 계속 진행")
