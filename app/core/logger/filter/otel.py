from logging import Filter, LogRecord

from opentelemetry import trace


class OtelTraceContextFilter(Filter):
    def filter(self, record: LogRecord) -> bool:
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            record.otelTraceID = format(ctx.trace_id, "032x")
            record.otelSpanID = format(ctx.span_id, "016x")
        else:
            record.otelTraceID = "0"
            record.otelSpanID = "0"
        return True
