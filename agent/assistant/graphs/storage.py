"""The database the agent owns, which is no longer where runs live.

A run that stops for a person ends, and the state it ended with goes back to
the backend, so nothing here persists execution state any more. What remains
is one pool, opened at startup, shared by the at-most-once ledger and the run
event log: the two things that genuinely have to outlive a run.
"""

from dataclasses import dataclass

import structlog
from psycopg_pool import AsyncConnectionPool

from assistant.core.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class _Live:
    """One pool per process, opened at startup and closed at shutdown."""

    pool: AsyncConnectionPool | None = None


_live = _Live()


async def setup_storage() -> None:
    """Open the pool. Called once, at startup."""
    if _live.pool is not None or not settings.storage_database_url:
        if not settings.storage_database_url:
            await logger.awarning(
                "storage.none",
                detail="the tool ledger and the event log need a database",
                fix="set STORAGE_DATABASE_URL",
            )
        return

    _live.pool = AsyncConnectionPool(
        conninfo=settings.storage_database_url,
        # psycopg's own min_size default is 4, so a smaller max would raise.
        min_size=min(4, settings.storage_pool_size),
        max_size=settings.storage_pool_size,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    await _live.pool.open()
    await logger.ainfo("storage.postgres", pool_size=settings.storage_pool_size)


async def close_storage() -> None:
    if _live.pool is not None:
        await _live.pool.close()
    _live.pool = None


def pool() -> AsyncConnectionPool | None:
    """Shared: one database, one pool, same lifecycle."""
    return _live.pool
