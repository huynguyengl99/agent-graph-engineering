"""The events a run has published, kept so a subscriber that missed them can ask.

A broadcast reaches whoever is listening at the time, so a restart mid-run leaves
the run recoverable and the record empty.
"""

import json
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS run_events (
    run_key    TEXT NOT NULL,
    seq        BIGINT NOT NULL,
    action     TEXT NOT NULL,
    event      JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_key, seq)
)
"""


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    action: str
    event: dict[str, Any]


class RunEventStore:
    """Postgres-backed, so what a run said outlives the process that said it."""

    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def setup(self) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(SCHEMA)

    async def append(self, run_key: str, action: str, event: dict[str, Any]) -> int:
        """Returns the sequence it was given, assigned by the database so two
        workers publishing for one run cannot pick the same number."""
        async with self.pool.connection() as conn:
            result = await conn.execute(
                "INSERT INTO run_events (run_key, seq, action, event) "
                "SELECT %s, COALESCE(MAX(seq), 0) + 1, %s, %s "
                "FROM run_events WHERE run_key = %s RETURNING seq",
                (run_key, action, json.dumps(event), run_key),
            )
            row = await result.fetchone()
        return int(row[0]) if row else 0

    async def since(self, run_key: str, after: int) -> list[StoredEvent]:
        async with self.pool.connection() as conn:
            result = await conn.execute(
                "SELECT seq, action, event FROM run_events "
                "WHERE run_key = %s AND seq > %s ORDER BY seq",
                (run_key, after),
            )
            rows = await result.fetchall()
        return [StoredEvent(seq=r[0], action=r[1], event=r[2]) for r in rows]


class MemoryEventStore(RunEventStore):
    """For tests and for a deployment with no database, where a restart loses what
    a run said - the gap this exists to close, so it is announced."""

    def __init__(self) -> None:  # noqa: D107
        self._events: dict[str, list[StoredEvent]] = {}

    async def setup(self) -> None:
        await logger.awarning(
            "runs.memory_store",
            detail="run events are in memory; a restart loses what a run said",
        )

    async def append(self, run_key: str, action: str, event: dict[str, Any]) -> int:
        stored = self._events.setdefault(run_key, [])
        seq = len(stored) + 1
        stored.append(StoredEvent(seq=seq, action=action, event=event))
        return seq

    async def since(self, run_key: str, after: int) -> list[StoredEvent]:
        return [e for e in self._events.get(run_key, []) if e.seq > after]


@dataclass
class _Live:
    store: RunEventStore | None = None


_live = _Live()


async def setup_run_events(pool: Any | None) -> RunEventStore:
    store: RunEventStore = RunEventStore(pool) if pool else MemoryEventStore()
    await store.setup()
    _live.store = store
    return store


def run_events() -> RunEventStore:
    if _live.store is None:
        _live.store = MemoryEventStore()
    return _live.store


def install_run_events(new: RunEventStore) -> None:
    _live.store = new
