"""Where a paused run lives between the interrupt and the human's answer.

This is not the business record. The backend's Postgres rows are what the
customer sees; this holds the *execution* state: which node runs next, the
channel values, the pending interrupt payload. Rebuilding that by hand would
mean reimplementing LangGraph's execution model, and resume is the only reason
the approval gate works at all.

In memory it survives a reconnect but not a restart, which means a deploy
silently drops every reply waiting on a reviewer. So Postgres is the default
and the in-memory saver is opt-in, announced loudly when it happens.
"""

from dataclasses import dataclass
from typing import Any, get_args

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg_pool import AsyncConnectionPool

from assistant.agents.deps import Context, Ticket, Turn
from assistant.core.config import settings
from assistant.outputs.chat import ChatRoute
from assistant.outputs.tools import ToolDecision
from assistant.outputs.triage import Classification, TicketAnswer, TriageDecision

logger = structlog.get_logger(__name__)

# Every model a graph state can hold. A missing one comes back as nothing rather
# than an error, so a router reads no route and takes its fallback branch.
# Derived from the unions, because listing it by hand is what went wrong.
CHECKPOINTED: tuple[Any, ...] = (
    Context,
    Ticket,
    Turn,
    Classification,
    TicketAnswer,
    *get_args(TriageDecision),
    *get_args(ChatRoute),
    *get_args(ToolDecision),
)

serde = JsonPlusSerializer(
    allowed_msgpack_modules=[
        (model.__module__, model.__name__) for model in CHECKPOINTED
    ]
)


@dataclass
class _Live:
    """One saver per process, opened at startup and closed at shutdown."""

    saver: BaseCheckpointSaver[str] | None = None
    pool: AsyncConnectionPool | None = None


_live = _Live()


async def setup_checkpointer() -> BaseCheckpointSaver[str]:
    """Open the pool and create the checkpoint tables. Called once, at startup."""
    if _live.saver is not None:
        return _live.saver

    if not settings.checkpoint_database_url:
        logger.warning(
            "checkpointer.in_memory",
            detail="paused approvals will not survive a restart",
            fix="set CHECKPOINT_DATABASE_URL",
        )
        _live.saver = InMemorySaver(serde=serde)
        return _live.saver

    _live.pool = AsyncConnectionPool(
        conninfo=settings.checkpoint_database_url,
        # psycopg's own min_size default is 4, so a smaller max would raise.
        min_size=min(4, settings.checkpoint_pool_size),
        max_size=settings.checkpoint_pool_size,
        open=False,
        # AsyncPostgresSaver issues DDL and expects no surrounding transaction.
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    await _live.pool.open()

    saver = AsyncPostgresSaver(_live.pool, serde=serde)  # type: ignore[arg-type]
    await saver.setup()
    _live.saver = saver
    logger.info("checkpointer.postgres", pool_size=settings.checkpoint_pool_size)
    return saver


async def close_checkpointer() -> None:
    if _live.pool is not None:
        await _live.pool.close()
    _live.saver, _live.pool = None, None


def checkpoint_pool() -> AsyncConnectionPool | None:
    """The ledger shares it: one database, one pool, same lifecycle."""
    return _live.pool


def checkpointer() -> BaseCheckpointSaver[str]:
    if _live.saver is None:
        raise RuntimeError("setup_checkpointer() must be awaited at startup")
    return _live.saver


def memory_checkpointer() -> BaseCheckpointSaver[str]:
    """For tests, which should not need a database to exercise a resume."""
    return InMemorySaver(serde=serde)


def install_checkpointer(saver: BaseCheckpointSaver[str]) -> None:
    """Set the process-wide saver directly, for tests and one-off scripts."""
    _live.saver = saver
