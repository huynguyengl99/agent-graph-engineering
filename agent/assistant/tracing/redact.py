"""Strip message bodies from spans on their way to a collector.

Off by default: a trace is worth having because it shows what the model was
actually sent, and the dashboard is the place people look. Turn it on when spans
leave for somewhere you do not control, because `gen_ai.input.messages` carries
the customer's own words - a ticket, verbatim, in a third party's database under
their retention.

Only the export path. The files on this machine keep everything.
"""

from collections.abc import Sequence
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

# What a prompt or a completion travels in. Everything the trace view is for -
# which node, how long, which model, what it decided, what it cost - is in other
# attributes and survives.
BODY_ATTRIBUTES = frozenset(
    {
        "final_result",
        "gen_ai.input.messages",
        "gen_ai.output.messages",
        "gen_ai.system_instructions",
        "gen_ai.tool.definitions",
        "model_request_parameters",
        "pydantic_ai.all_messages",
    }
)
PLACEHOLDER = "[redacted]"


def redacted_attributes(attributes: Any) -> dict[str, Any]:
    kept = {}
    for key, value in dict(attributes or {}).items():
        kept[key] = PLACEHOLDER if key in BODY_ATTRIBUTES else value
    return kept


class RedactingExporter(SpanExporter):
    """Wraps another exporter, replacing message bodies before they leave."""

    def __init__(self, inner: SpanExporter) -> None:
        self.inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self.inner.export([_without_bodies(span) for span in spans])

    def shutdown(self) -> None:
        self.inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self.inner.force_flush(timeout_millis)


def _without_bodies(span: ReadableSpan) -> ReadableSpan:
    return ReadableSpan(
        name=span.name,
        context=span.get_span_context(),
        parent=span.parent,
        resource=span.resource,
        attributes=redacted_attributes(span.attributes),
        events=span.events,
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )
