"""The model's memory of a conversation, in Pydantic AI's own messages.

The backend's rows are the record a person reads. This is what the model was
actually told, which is a different thing: a tool call is a call here, not a
sentence about one.
"""

from dataclasses import dataclass
from typing import Any

import structlog
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

logger = structlog.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_history (
    conversation_id TEXT PRIMARY KEY,
    messages        JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _dump(messages: list[ModelMessage]) -> str:
    return ModelMessagesTypeAdapter.dump_json(messages).decode()


def _load(raw: Any) -> list[ModelMessage]:
    if not raw:
        return []
    return list(ModelMessagesTypeAdapter.validate_python(raw))


def as_messages(turns: list[tuple[str, str]]) -> list[ModelMessage]:
    """The backend's `(role, content)` rows as model messages. Lossy - a row
    cannot say which tool was called - so it only ever seeds."""
    messages: list[ModelMessage] = []
    for role, content in turns:
        if role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
        else:
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
    return messages


class HistoryStore:
    """Postgres-backed, so a conversation outlives the process that answered it."""

    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def setup(self) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(SCHEMA)

    async def load(self, conversation_id: str) -> list[ModelMessage]:
        async with self.pool.connection() as conn:
            result = await conn.execute(
                "SELECT messages FROM conversation_history WHERE conversation_id = %s",
                (conversation_id,),
            )
            row = await result.fetchone()
        return _load(row[0]) if row else []

    async def replace(self, conversation_id: str, messages: list[ModelMessage]) -> None:
        """The whole history, not an append: Pydantic AI hands back every message a
        run saw."""
        async with self.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO conversation_history (conversation_id, messages) "
                "VALUES (%s, %s) ON CONFLICT (conversation_id) DO UPDATE "
                "SET messages = EXCLUDED.messages, updated_at = now()",
                (conversation_id, _dump(messages)),
            )

    async def seed(self, conversation_id: str, turns: list[tuple[str, str]]) -> None:
        """Start from the backend's record, but only if there is nothing better."""
        if not turns or await self.load(conversation_id):
            return
        await self.replace(conversation_id, as_messages(turns))


class MemoryHistoryStore(HistoryStore):
    """For tests and for a deployment with no database."""

    def __init__(self) -> None:  # noqa: D107
        self._histories: dict[str, list[ModelMessage]] = {}

    async def setup(self) -> None:
        logger.warning(
            "conversations.memory_store",
            detail="model history is in memory; a restart forgets every conversation",
        )

    async def load(self, conversation_id: str) -> list[ModelMessage]:
        return list(self._histories.get(conversation_id, []))

    async def replace(self, conversation_id: str, messages: list[ModelMessage]) -> None:
        self._histories[conversation_id] = list(messages)


@dataclass
class _Live:
    store: HistoryStore | None = None


_live = _Live()


async def setup_history(pool: Any | None) -> HistoryStore:
    store: HistoryStore = HistoryStore(pool) if pool else MemoryHistoryStore()
    await store.setup()
    _live.store = store
    return store


def history() -> HistoryStore:
    if _live.store is None:
        _live.store = MemoryHistoryStore()
    return _live.store


def install_history(new: HistoryStore) -> None:
    _live.store = new
