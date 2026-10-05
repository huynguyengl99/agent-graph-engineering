"""Covers the topic's streaming path.

The graph tests call `ainvoke`, which never touches `astream`. A wrong
unpacking of the stream shape slipped through that gap and only showed up when
two live services talked to each other, so it gets its own test.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from assistant.messages.support import (
    RunRequestMessage,
    RunRequestPayload,
    TicketRef,
)
from assistant.ws.topics import SupportTopic

from tests.helpers.events import Recorded, recording
from tests.helpers.openai_mock import mock_openai, tool_call


class DetachedTopic(SupportTopic):
    """Drives a run without a socket. Everything it and its graph emit is
    published on the topic, which the `events` fixture records."""

    def __init__(self) -> None:  # noqa: D107 - deliberately skips chanx init
        self.params = {"audience": "customer", "thread_id": "t-1"}
        self.topic = "support:customer:t-1"
        self.sent: list[Any] = []

    async def send_message(self, message: Any, **kwargs: Any) -> None:
        """Reasoning deltas go to the asking socket; there is none here."""
        self.sent.append(message)


@pytest.fixture
def consumer() -> DetachedTopic:
    return DetachedTopic()


@pytest.fixture
def events() -> Iterator[Recorded]:
    with recording(SupportTopic) as recorded:
        yield recorded


async def test_every_graph_step_is_emitted_in_order(
    consumer: DetachedTopic, events: Recorded
) -> None:
    with mock_openai(
        tool_call(
            "final_result",
            {
                "category": "billing",
                "priority": "medium",
                "reasoning": "Invoice question.",
            },
        ),
        tool_call("final_result_Answer", {"reasoning": "Known answer."}),
        tool_call(
            "final_result",
            {"content": "Two charges means proration.", "requires_approval": False},
        ),
    ):
        await consumer.handle_run_request(
            RunRequestMessage(
                payload=RunRequestPayload(
                    ticket=TicketRef(
                        ticket_id="t-1",
                        title="Charged twice this month",
                        description="My card shows two charges.",
                    )
                )
            )
        )

    actions = events.actions()
    # A step explains itself while it decides, so the pieces of its reasoning
    # land before anything it settles on.
    assert actions[0] == "reasoning_delta"

    # The steps themselves, with the writing filtered out.
    settled = [a for a in actions if a != "reasoning_delta"]
    assert settled[:2] == ["reasoned", "classified"]
    assert "decided" in settled
    assert "answer" in settled
    # Nothing in this ticket asked for a person, so the run ends at the reply
    # rather than parked in front of one.
    assert settled[-1] == "reply_sent"
    assert events.last("answer").payload.content == "Two charges means proration."


async def test_handler_reports_failure_instead_of_raising(
    consumer: DetachedTopic, monkeypatch: pytest.MonkeyPatch, events: Recorded
) -> None:
    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(consumer, "_graph", boom)

    await consumer.handle_run_request(
        RunRequestMessage(
            payload=RunRequestPayload(
                ticket=TicketRef(
                    ticket_id="t-1",
                    title="x",
                    description="y",
                )
            )
        )
    )

    assert events.actions() == ["run_failed"]
