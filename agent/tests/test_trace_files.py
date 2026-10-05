"""Spans on disk, and what is stripped on the way to a collector.

The two have opposite defaults on purpose: files keep everything because they
stay on this machine, and an export can be redacted because it does not.
"""

from pathlib import Path

import pytest
from assistant.tracing.files import TraceFiles
from assistant.tracing.nodes import STATE_IN, STATE_UPDATE
from assistant.tracing.redact import (
    BODY_ATTRIBUTES,
    PLACEHOLDER,
    redacted_attributes,
)
from assistant.tracing.store import SpanRecord, TraceStore


def record(span_id: str, name: str, parent: str | None = None) -> SpanRecord:
    return SpanRecord(
        span_id=span_id,
        parent_id=parent,
        name=name,
        start_ns=1_000,
        end_ns=2_000,
        attributes={"gen_ai.input.messages": "the customer wrote this"},
    )


@pytest.fixture
def files(tmp_path: Path) -> TraceFiles:
    return TraceFiles(tmp_path / "traces")


class TestFileStore:
    def test_nothing_is_written_until_there_is_a_span(self, files: TraceFiles) -> None:
        """Importing the agent should not leave a directory behind."""
        assert not files.directory.exists()
        assert files.runs() == []

    def test_a_run_is_one_file(self, files: TraceFiles) -> None:
        files.write("run-1", record("a", "node.support_classify"))
        files.write("run-1", record("b", "chat gpt-4o", parent="a"))
        files.write("run-2", record("c", "node.route"))

        assert sorted(files.runs()) == ["run-1", "run-2"]
        assert [s.name for s in files.spans("run-1")] == [
            "node.support_classify",
            "chat gpt-4o",
        ]

    def test_spans_round_trip_with_their_parents(self, files: TraceFiles) -> None:
        files.write("run-1", record("a", "node.support_classify"))
        files.write("run-1", record("b", "chat gpt-4o", parent="a"))

        [root, child] = files.spans("run-1")

        assert root.parent_id is None
        assert child.parent_id == "a"
        assert child.duration_ms == 0.0

    def test_a_torn_last_line_does_not_lose_the_rest(self, files: TraceFiles) -> None:
        """A killed process can leave half a line; the spans that finished are
        still worth reading."""
        files.write("run-1", record("a", "node.support_classify"))
        with files._path("run-1").open("a", encoding="utf-8") as handle:
            handle.write('{"span_id": "b", "nam')

        assert [s.name for s in files.spans("run-1")] == ["node.support_classify"]

    def test_an_unwritable_directory_does_not_fail_the_run(
        self, tmp_path: Path
    ) -> None:
        """Losing a trace must never take down the thing being traced."""
        blocked = tmp_path / "file-not-a-dir"
        blocked.write_text("")
        files = TraceFiles(blocked / "traces")

        files.write("run-1", record("a", "node.support_classify"))

        assert files.spans("run-1") == []

    def test_a_run_id_cannot_escape_the_directory(self, files: TraceFiles) -> None:
        files.write("../../etc/passwd", record("a", "node.support_classify"))

        written = list(files.directory.glob("*.jsonl"))
        assert [p.name for p in written] == ["passwd.jsonl"]

    def test_files_keep_the_message_bodies(self, files: TraceFiles) -> None:
        """Unredacted on purpose: they stay here, and seeing what the model was
        sent is the reason to keep a trace."""
        files.write("run-1", record("a", "chat gpt-4o"))

        [span] = files.spans("run-1")
        assert span.attributes["gen_ai.input.messages"] == "the customer wrote this"


class TestStoreBackedByFiles:
    def test_a_run_survives_losing_the_memory(self, files: TraceFiles) -> None:
        store = TraceStore(files=files)
        store.add("run-1", record("a", "node.support_classify"))

        store.clear()  # as a restart would

        assert [s["name"] for s in store.tree("run-1")] == ["node.support_classify"]
        assert store.runs() == ["run-1"]

    def test_memory_is_preferred_over_disk(self, files: TraceFiles) -> None:
        store = TraceStore(files=files)
        store.add("run-1", record("a", "node.support_classify"))

        assert len(store.spans("run-1")) == 1

    def test_without_files_a_restart_loses_the_run(self) -> None:
        store = TraceStore(files=None)
        store.add("run-1", record("a", "node.support_classify"))
        store.clear()

        assert store.tree("run-1") == []

    def test_clearing_memory_leaves_the_files_alone(self, files: TraceFiles) -> None:
        """A test clearing its own spans has no business deleting a run someone
        was looking at."""
        store = TraceStore(files=files)
        store.add("run-1", record("a", "node.support_classify"))

        store.clear()

        assert files.spans("run-1")


class TestRedactingExports:
    def test_message_bodies_are_replaced(self) -> None:
        kept = redacted_attributes(
            {
                "gen_ai.input.messages": "the customer wrote this",
                "pydantic_ai.all_messages": "and this",
            }
        )

        assert set(kept.values()) == {PLACEHOLDER}

    def test_everything_the_view_needs_survives(self) -> None:
        """Which node, how long, which model, what it decided, what it cost."""
        kept = redacted_attributes(
            {
                "gen_ai.input.messages": "the customer wrote this",
                "model_name": "gpt-4o",
                "decision": "SearchKnowledgeBase",
                "gen_ai.usage.input_tokens": 120,
                "operation.cost": 0.0001,
            }
        )

        assert kept["model_name"] == "gpt-4o"
        assert kept["decision"] == "SearchKnowledgeBase"
        assert kept["gen_ai.usage.input_tokens"] == 120
        assert kept["gen_ai.input.messages"] == PLACEHOLDER

    def test_every_body_attribute_is_one_something_actually_sets(self) -> None:
        """A key that nothing emits is a redaction that does nothing, and reads
        like protection that is not there."""
        from_pydantic_ai = {
            "final_result",
            "gen_ai.input.messages",
            "gen_ai.output.messages",
            "gen_ai.system_instructions",
            "gen_ai.tool.definitions",
            "model_request_parameters",
            "pydantic_ai.all_messages",
        }
        # Taken from the tracer rather than spelled again, so renaming one there
        # fails here instead of quietly leaving a state body unredacted.
        ours = {STATE_IN, STATE_UPDATE}

        assert BODY_ATTRIBUTES == from_pydantic_ai | ours

    def test_a_state_body_does_not_leave(self) -> None:
        """A graph state holds the ticket and the draft, so it is as much a body
        as a prompt is."""
        redacted = redacted_attributes(
            {STATE_IN: '{"context": "..."}', STATE_UPDATE: '{"answer": "..."}'}
        )

        assert set(redacted.values()) == {"[redacted]"}

    def test_nothing_is_added_or_dropped(self) -> None:
        attributes = {"a": 1, "gen_ai.input.messages": "x"}

        assert set(redacted_attributes(attributes)) == set(attributes)


class TestRedactingExporterWiring:
    """The wrapper has to produce a span the OTLP exporter still accepts."""

    def test_a_wrapped_span_keeps_everything_but_its_bodies(self) -> None:
        from assistant.tracing.redact import RedactingExporter
        from assistant.tracing.setup import setup_tracing, tracer
        from opentelemetry.sdk.trace.export import SpanExportResult

        setup_tracing()
        exported: list[object] = []

        class Capturing:
            def export(self, spans: object) -> SpanExportResult:
                exported.extend(spans)  # type: ignore[arg-type]
                return SpanExportResult.SUCCESS

            def shutdown(self) -> None: ...

            def force_flush(self, timeout_millis: int = 30_000) -> bool:
                return True

        with tracer().start_as_current_span("node.support_classify") as span:
            span.set_attribute("gen_ai.input.messages", "the customer wrote this")
            span.set_attribute("model_name", "gpt-4o")
            finished = span

        RedactingExporter(Capturing()).export([finished])  # type: ignore[arg-type,list-item]

        [out] = exported
        attributes = dict(out.attributes or {})  # type: ignore[attr-defined]
        assert attributes["gen_ai.input.messages"] == PLACEHOLDER
        assert attributes["model_name"] == "gpt-4o"
        assert out.name == "node.support_classify"  # type: ignore[attr-defined]
        assert out.get_span_context().span_id == finished.get_span_context().span_id  # type: ignore[attr-defined]
