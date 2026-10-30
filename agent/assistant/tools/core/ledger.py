"""At-most-once execution for tools that cannot be undone.

A process killed mid-refund refunds again when the work comes back. The state
the backend holds is the one the run started from, so a redelivered decision
re-enters the graph and reaches the refund node a second time. Verified, not
assumed.

What makes two attempts the same call is the run they belong to. The run id is
minted when a turn arrives and comes back whole with a reviewer's decision, so
a redelivered decision claims the key its interrupted attempt made, while a
second refund somebody genuinely asked for is a new turn, a new id and a new
key. The claim is kept in the agent's own Postgres so it survives the restart.

The honest limit: if the process dies between claiming and recording, nobody
knows whether the call went through. That is reported rather than guessed, so a
person checks - retrying risks a second refund and skipping risks none at all.
"""

import json
from dataclasses import dataclass
from typing import Any

import structlog

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


def execution_key(run_id: str, tool: str) -> str | None:
    """None when a run has no id, where there is nothing to tie attempts to.

    Not `checkpoint_ns`, which names the position in the graph: stable across
    a retry, which is half of what a key needs, and identical for every turn
    on one thread, which is the other half wrong. A reviewer's second refund
    on a ticket would claim the first one's row and never run.
    """
    return f"{run_id}:{tool}" if run_id else None


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
