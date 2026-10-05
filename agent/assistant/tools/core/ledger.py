"""At-most-once execution for tools that cannot be undone.

A crash inside a node re-runs that node on resume: LangGraph only checkpoints
after a node returns, so a process killed mid-refund refunds again when it comes
back. Verified, not assumed.

`checkpoint_ns` is stable across that re-run, so thread plus namespace names one
logical execution and survives a restart in the same Postgres the checkpoints
use.

The honest limit: if the process dies between claiming and recording, nobody
knows whether the call went through. That is reported rather than guessed, so a
person checks - retrying risks a second refund and skipping risks none at all.
"""

import json
from dataclasses import dataclass
from typing import Any

import structlog
from langgraph.config import get_config

logger = structlog.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_executions (
    key         TEXT PRIMARY KEY,
    tool        TEXT NOT NULL,
    arguments   JSONB NOT NULL,
    result      TEXT,
    settled     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled_at  TIMESTAMPTZ
)
"""


@dataclass(frozen=True)
class Claim:
    """`fresh` means run it. Otherwise `result` is what the first attempt got,
    and a claim that is neither fresh nor settled is the unknown case."""

    fresh: bool
    settled: bool = False
    result: str | None = None

    @property
    def unknown(self) -> bool:
        return not self.fresh and not self.settled


def execution_key(tool: str) -> str | None:
    """None outside a graph run, where there is nothing to be idempotent about."""
    try:
        configurable = get_config().get("configurable") or {}
    except RuntimeError:
        return None

    thread = configurable.get("thread_id")
    namespace = configurable.get("checkpoint_ns")
    if not thread or not namespace:
        return None
    return f"{thread}:{namespace}:{tool}"


class ToolLedger:
    """Postgres-backed, so a claim outlives the process that made it."""

    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def setup(self) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(SCHEMA)

    async def claim(self, key: str, tool: str, arguments: dict[str, Any]) -> Claim:
        async with self.pool.connection() as conn:
            inserted = await conn.execute(
                "INSERT INTO tool_executions (key, tool, arguments) "
                "VALUES (%s, %s, %s) ON CONFLICT (key) DO NOTHING",
                (key, tool, json.dumps(arguments)),
            )
            if inserted.rowcount == 1:
                return Claim(fresh=True)

            existing = await conn.execute(
                "SELECT settled, result FROM tool_executions WHERE key = %s", (key,)
            )
            row = await existing.fetchone()

        settled, result = (row[0], row[1]) if row else (False, None)
        return Claim(fresh=False, settled=settled, result=result)

    async def settle(self, key: str, result: str) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE tool_executions SET result = %s, settled = TRUE, "
                "settled_at = now() WHERE key = %s",
                (result, key),
            )

    async def release(self, key: str) -> None:
        """A call that provably never reached the outside world, so the next
        attempt may try again."""
        async with self.pool.connection() as conn:
            await conn.execute("DELETE FROM tool_executions WHERE key = %s", (key,))


class MemoryLedger(ToolLedger):
    """For tests and for a deployment with no database, where a restart loses
    the paused run anyway."""

    def __init__(self) -> None:  # noqa: D107
        self.rows: dict[str, dict[str, Any]] = {}

    async def setup(self) -> None:
        return None

    async def claim(self, key: str, tool: str, arguments: dict[str, Any]) -> Claim:
        if key not in self.rows:
            self.rows[key] = {"tool": tool, "settled": False, "result": None}
            return Claim(fresh=True)
        row = self.rows[key]
        return Claim(fresh=False, settled=row["settled"], result=row["result"])

    async def settle(self, key: str, result: str) -> None:
        self.rows[key].update(settled=True, result=result)

    async def release(self, key: str) -> None:
        self.rows.pop(key, None)


@dataclass
class _Live:
    ledger: ToolLedger | None = None


_live = _Live()


async def setup_ledger(pool: Any | None) -> ToolLedger:
    _live.ledger = ToolLedger(pool) if pool is not None else MemoryLedger()
    await _live.ledger.setup()
    if pool is None:
        await logger.awarning(
            "ledger.in_memory",
            detail="a restart mid-tool could repeat an irreversible call",
        )
    return _live.ledger


def ledger() -> ToolLedger:
    if _live.ledger is None:
        _live.ledger = MemoryLedger()
    return _live.ledger


def install_ledger(new: ToolLedger) -> None:
    _live.ledger = new
