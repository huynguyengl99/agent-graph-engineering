"""Covers the topic's streaming path.

The graph tests call `ainvoke`, which never touches `astream`. A wrong
unpacking of the stream shape slipped through that gap and only showed up when
two live services talked to each other, so it gets its own test.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from assistant.messages.triage import TriageRequestMessage, TriageRequestPayload
from assistant.ws.topics import TriageTopic

from tests.helpers.contexts import ticket_context
from tests.helpers.events import Recorded, recording
from tests.helpers.openai_mock import mock_openai, tool_call


class DetachedTopic(TriageTopic):
    """Drives a run without a socket. Everything it and its graph emit is
    published on the topic, which the `events` fixture records."""

    def __init__(self) -> None:  # noqa: D107 - deliberately skips chanx init
        self.params = {"ticket_id": "t-1"}
        self.topic = "triage:t-1"


@pytest.fixture
def consumer() -> DetachedTopic:
    return DetachedTopic()


@pytest.fixture
def events() -> Iterator[Recorded]:
    with recording(TriageTopic) as recorded:
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
        tool_call("final_result_AnswerDirectly", {"reasoning": "Known answer."}),
        tool_call(
            "final_result",
            {"content": "Two charges means proration.", "requires_approval": False},
        ),
    ):
        await consumer._run_graph(
            ticket_context(
                ticket_id="t-1",
                title="Charged twice this month",
                description="My card shows two charges.",
            )
        )

    actions = events.actions()
    assert actions[0] == "classified"
    assert "decided" in actions
    assert "answer" in actions
    # The run ends parked at the approval gate, not at the answer.
    assert actions[-1] == "approval_required"
    assert events.last("approval_required").payload.draft == (
        "Two charges means proration."
    )


async def test_handler_reports_failure_instead_of_raising(
    consumer: DetachedTopic, monkeypatch: pytest.MonkeyPatch, events: Recorded
) -> None:
    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(consumer, "_run_graph", boom)

    await consumer.handle_triage_request(
        TriageRequestMessage(
            payload=TriageRequestPayload(ticket_id="t-1", title="x", description="y")
        )
    )

    assert events.actions() == ["triage_error"]
