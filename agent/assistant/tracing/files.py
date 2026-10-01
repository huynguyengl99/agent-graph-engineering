"""Finished spans on disk, one file per run.

Traces are write-once, read-rarely, and always read by run, which is a file's
shape rather than a table's: no index to maintain, nothing to vacuum, and
expiry is a lifecycle rule on whatever holds the files. The production version
of this writes to object storage; the shape is the same.

Unredacted on purpose. These stay on the machine that produced them, and the
whole point of a trace is being able to see what the model was actually sent.
Redaction belongs on the way out, where spans leave for a collector.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog

from assistant.tracing.store import SpanRecord

logger = structlog.get_logger(__name__)


class TraceFiles:
    """One JSONL file per run, appended as spans finish.

    Appending rather than rewriting because a run's spans arrive over its
    lifetime, and a crash halfway should leave the spans that did finish.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, run_id: str) -> Path:
        # Runs are ids we generate, but a path is a path: never let one escape.
        return self.directory / f"{Path(run_id).name}.jsonl"

    def write(self, run_id: str, record: SpanRecord) -> None:
        try:
            # Created on first write, so importing the agent does not leave a
            # directory behind in a test run that traces nothing.
            self.directory.mkdir(parents=True, exist_ok=True)
            with self._path(run_id).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(record), default=str) + "\n")
        except OSError as error:
            # Losing a trace must never fail the run that produced it.
            logger.warning("trace_files.write_failed", run_id=run_id, error=str(error))

    def runs(self) -> list[str]:
        if not self.directory.exists():
            return []
        files = sorted(self.directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        return [path.stem for path in files]

    def spans(self, run_id: str) -> list[SpanRecord]:
        path = self._path(run_id)
        if not path.exists():
            return []

        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                raw: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                # A torn final line from a killed process; the rest is readable.
                continue
            records.append(
                SpanRecord(
                    span_id=raw["span_id"],
                    parent_id=raw.get("parent_id"),
                    name=raw["name"],
                    start_ns=int(raw["start_ns"]),
                    end_ns=int(raw["end_ns"]),
                    attributes=dict(raw.get("attributes") or {}),
                )
            )
        return records

    def clear(self) -> None:
        for path in self.directory.glob("*.jsonl"):
            path.unlink(missing_ok=True)
