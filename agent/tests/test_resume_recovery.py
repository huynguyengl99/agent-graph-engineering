"""A checkpoint that will not load used to wedge the ticket forever: every
retry failed identically, so the approval could never go through."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from psycopg import OperationalError


class _Saver:
    def __init__(self, raises: Exception | None = None) -> None:
        self.raises = raises
        self.deleted: list[str] = []

    async def aget_tuple(self, config: dict[str, Any]) -> None:
        if self.raises is not None:
            raise self.raises

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


@pytest.fixture
def topic() -> Any:
    from assistant.ws.topics.support import SupportTopic

    instance = object.__new__(SupportTopic)
    # thread_id is a property over the matched pattern params.
    instance.params = {"thread_id": "t-1", "audience": "customer"}  # type: ignore[attr-defined]
    # `topic` is the addressed name, used only for log context here.
    instance.topic = "support:customer:t-1"  # type: ignore[attr-defined]
    return instance


async def test_an_unreadable_checkpoint_is_discarded(topic: Any) -> None:
    saver = _Saver(raises=ValueError("msgpack: truncated"))
    with (
        patch("assistant.ws.topics.support.checkpointer", return_value=saver),
        patch("assistant.graphs.checkpointer._live") as live,
        patch.object(type(topic), "_fail", new=AsyncMock()) as failed,
        patch.object(type(topic), "_consume", new=AsyncMock()) as consumed,
    ):
        live.saver = saver
        await topic._resume(object(), None)

    assert saver.deleted == ["t-1"], "the wedged thread was not dropped"
    failed.assert_awaited_once()
    consumed.assert_not_awaited()


async def test_a_database_outage_does_not_delete_a_good_checkpoint(
    topic: Any,
) -> None:
    """The bug this guard could introduce is worse than the one it fixes."""
    saver = _Saver(raises=OperationalError("connection refused"))
    with (
        patch("assistant.ws.topics.support.checkpointer", return_value=saver),
        patch("assistant.graphs.checkpointer._live") as live,
        patch.object(type(topic), "_fail", new=AsyncMock()),
        patch.object(type(topic), "_consume", new=AsyncMock()),
    ):
        live.saver = saver
        await topic._resume(object(), None)

    assert saver.deleted == [], "a transient outage deleted a usable checkpoint"


async def test_a_readable_checkpoint_resumes_normally(topic: Any) -> None:
    saver = _Saver()
    with (
        patch("assistant.ws.topics.support.checkpointer", return_value=saver),
        patch.object(type(topic), "_graph", return_value=object()),
        patch.object(type(topic), "_consume", new=AsyncMock()) as consumed,
    ):
        await topic._resume(object(), None)

    assert saver.deleted == []
    consumed.assert_awaited_once()
