"""Finished spans, in memory for this process and on disk for the next one.

The series' complaint about observability platforms is that they hand you a flat
list of model calls and leave you to reconstruct the flow. This collector keeps
the parent/child structure, grouped by ticket, so `GET /traces/{ticket_id}`
answers "what happened to this one message" directly.

Memory is the fast path for a run in flight; the files behind it are what make a
trace readable after a restart. Set an OTLP endpoint to send the same spans to a
collector as well.
"""

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from assistant.tracing.cost import RunCost, cost_of_span

MAX_RUNS = 50
RUN_ATTRIBUTE = "assistant.run_id"


@dataclass
class SpanRecord:
    span_id: str
    parent_id: str | None
    name: str
    start_ns: int
    end_ns: int
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return round((self.end_ns - self.start_ns) / 1_000_000, 2)


class TraceStore:
    """A bounded, per-run ring of spans, optionally backed by files.

    The ring keeps the process responsive without growing; the files are the
    durable copy, so a run from before the last restart still renders.
    """

    def __init__(self, max_runs: int = MAX_RUNS, files: Any = None) -> None:
        self._lock = Lock()
        self._by_ticket: OrderedDict[str, list[SpanRecord]] = OrderedDict()
        self._max_runs = max_runs
        self._files = files

    def use_files(self, files: Any) -> None:
        self._files = files

    def add(self, ticket_id: str, record: SpanRecord) -> None:
        with self._lock:
            spans = self._by_ticket.setdefault(ticket_id, [])
            spans.append(record)
            self._by_ticket.move_to_end(ticket_id)
            while len(self._by_ticket) > self._max_runs:
                self._by_ticket.popitem(last=False)

        if self._files is not None:
            self._files.write(ticket_id, record)

    def runs(self) -> list[str]:
        with self._lock:
            live = list(self._by_ticket)
        if self._files is None:
            return live

        # Files first, so the order is oldest to newest across both.
        stored = [run for run in self._files.runs() if run not in live]
        return stored + live

    def spans(self, ticket_id: str) -> list[SpanRecord]:
        with self._lock:
            held = list(self._by_ticket.get(ticket_id, []))
        if not held and self._files is not None:
            held = self._files.spans(ticket_id)
        return sorted(held, key=lambda s: s.start_ns)

    def tree(self, ticket_id: str) -> list[dict[str, Any]]:
        """Spans nested by parent, which is the view code cannot give you."""
        spans = self.spans(ticket_id)
        children: dict[str | None, list[SpanRecord]] = defaultdict(list)
        known = {span.span_id for span in spans}
        for span in spans:
            # A parent outside this ticket's set is treated as a root.
            parent = span.parent_id if span.parent_id in known else None
            children[parent].append(span)

        def build(parent: str | None) -> list[dict[str, Any]]:
            return [
                {
                    "name": span.name,
                    "duration_ms": span.duration_ms,
                    "attributes": span.attributes,
                    "children": build(span.span_id),
                }
                for span in children[parent]
            ]

        return build(None)

    def cost(self, run_id: str) -> RunCost:
        """Tokens and money for a whole run, summed over its model calls."""
        total = RunCost()
        for span in self.spans(run_id):
            if (call := cost_of_span(span.attributes)) is not None:
                total = total + call
        return total

    def clear(self) -> None:
        """Memory only. Files are data, and a test clearing its own spans has no
        business deleting a run someone was looking at."""
        with self._lock:
            self._by_ticket.clear()


trace_store = TraceStore()


class TraceStoreExporter(SpanExporter):
    """Files each finished span under the ticket it belongs to.

    Only the node span carries the ticket id; the model-call spans Pydantic AI
    creates underneath it do not. Spans also finish innermost-first, so a child
    is exported before the parent that names the ticket. Both are handled by
    keying on the trace id and buffering until the naming span shows up.
    """

    def __init__(self, store: TraceStore = trace_store) -> None:
        self._store = store
        self._run_by_trace: dict[str, str] = {}
        self._pending: dict[str, list[SpanRecord]] = defaultdict(list)

    def export(self, spans: tuple[ReadableSpan, ...]) -> SpanExportResult:  # type: ignore[override]
        for span in spans:
            context = span.get_span_context()
            if context is None:
                # A span with no context cannot be filed under a run.
                continue
            trace_id = format(context.trace_id, "032x")
            attributes = dict(span.attributes or {})

            record = SpanRecord(
                span_id=format(context.span_id, "016x"),
                parent_id=format(span.parent.span_id, "016x") if span.parent else None,
                name=span.name,
                start_ns=span.start_time or 0,
                end_ns=span.end_time or 0,
                attributes=attributes,
            )

            if ticket_id := attributes.get(RUN_ATTRIBUTE):
                self._run_by_trace[trace_id] = str(ticket_id)

            known = self._run_by_trace.get(trace_id)
            if known is None:
                self._pending[trace_id].append(record)
                continue

            for buffered in self._pending.pop(trace_id, []):
                self._store.add(known, buffered)
            self._store.add(known, record)

        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self._run_by_trace.clear()
        self._pending.clear()
