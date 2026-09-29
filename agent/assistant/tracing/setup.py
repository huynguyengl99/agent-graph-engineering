"""Wire up OpenTelemetry once, at import.

Two exporters, both optional in the sense that neither needs an account:

- `TraceStoreExporter` always runs, so `/traces/{ticket_id}` works out of the box.
- An OTLP exporter is added when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, which is
  how you point this at Langfuse, Jaeger, or anything else speaking OTLP.

Pydantic AI emits its own spans for every model call, so once a graph node opens
a span the model calls nest underneath it automatically.
"""

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

from assistant.core.config import settings
from assistant.tracing.store import TraceStoreExporter

logger = structlog.get_logger(__name__)

_state: dict[str, bool] = {"configured": False}


def setup_tracing(force: bool = False) -> None:
    if _state["configured"] and not force:
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": "triage-agent"})
    )

    # Simple (not batched) so a span is queryable the moment the run ends.
    provider.add_span_processor(SimpleSpanProcessor(TraceStoreExporter()))

    if settings.otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=f"{settings.otlp_endpoint.rstrip('/')}/v1/traces",
                        headers=settings.otlp_headers,
                    )
                )
            )
        except ImportError:
            # The OTLP exporter is an extra. Losing it must not take the agent
            # down; the in-memory view still works.
            logger.warning(
                "otlp.exporter_missing",
                hint="install the 'tracing' extra to forward spans",
                endpoint=settings.otlp_endpoint,
            )

    trace.set_tracer_provider(provider)
    _state["configured"] = True


def tracer() -> trace.Tracer:
    return trace.get_tracer("triage")
