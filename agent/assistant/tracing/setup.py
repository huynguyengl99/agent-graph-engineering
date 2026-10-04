"""Wire up OpenTelemetry once, at import.

`TraceStoreExporter` always runs, so `/traces/{run_id}` and a run's reported
cost work with no account and no configuration. Where spans go after that is
`ASSISTANT_TRACE_EXPORT`: files under `ASSISTANT_TRACE_DIR`, an OTLP collector
such as Langfuse or Jaeger, both, or neither.

Pydantic AI emits its own spans for every model call, so once a graph node opens
a span the model calls nest underneath it automatically.
"""

from pathlib import Path

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)
from pydantic_ai import Agent

from assistant.core.config import settings
from assistant.tracing.files import TraceFiles
from assistant.tracing.redact import RedactingExporter
from assistant.tracing.store import TraceStoreExporter, trace_store

logger = structlog.get_logger(__name__)

_state: dict[str, bool] = {"configured": False}


def setup_tracing(force: bool = False) -> None:
    if _state["configured"] and not force:
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": "triage-agent"})
    )

    if settings.trace_export.writes_files and settings.trace_dir:
        files = TraceFiles(Path(settings.trace_dir))
        trace_store.use_files(files)
        logger.info("tracing.files", directory=str(files.directory))

    # Simple (not batched) so a span is queryable the moment the run ends.
    provider.add_span_processor(SimpleSpanProcessor(TraceStoreExporter()))

    if (forwarder := otlp_processor()) is not None:
        provider.add_span_processor(forwarder)

    trace.set_tracer_provider(provider)

    # Set once for the process in pydantic-ai 2.x rather than per agent. This
    # is what nests model calls under the node span that made them.
    Agent.instrument_all(True)

    _state["configured"] = True


def otlp_processor() -> BatchSpanProcessor | None:
    """Forward spans to Langfuse, Jaeger, or any OTLP collector.

    Separate from `setup_tracing` because the global tracer provider can only
    be set once per process, so this is the part a test can exercise. The
    endpoint is guaranteed by the settings, which refuse a forwarding mode
    without one.
    """
    if not settings.trace_export.forwards:
        return None

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError:
        # The OTLP exporter is an extra. Losing it must not take the agent
        # down; the in-memory view still works.
        logger.warning(
            "otlp.exporter_missing",
            hint="install the 'tracing' extra to forward spans",
            endpoint=settings.otlp_endpoint,
        )
        return None

    exporter: SpanExporter = OTLPSpanExporter(
        endpoint=f"{settings.otlp_endpoint.rstrip('/')}/v1/traces",
        headers=settings.otlp_headers,
    )
    if settings.trace_redact_exports:
        exporter = RedactingExporter(exporter)
        logger.info("otlp.redacting", detail="message bodies are stripped on export")

    return BatchSpanProcessor(exporter)


def tracer() -> trace.Tracer:
    return trace.get_tracer("triage")
