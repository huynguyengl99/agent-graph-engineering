"""Covers the consumer's streaming path.

The graph tests call `ainvoke`, which never touches `astream`. A wrong
unpacking of the stream shape slipped through that gap and only showed up when
two live services talked to each other, so it gets its own test.
"""

from typing import Any

import pytest
from assistant.agents import TicketContext
from assistant.ws.consumer import TriageConsumer
from assistant.ws.messages import TriageRequestMessage, TriageRequestPayload

from tests.helpers.openai_mock import mock_openai, tool_call


class RecordingConsumer(TriageConsumer):
    """Captures what would go on the wire, without a socket."""

    def __init__(self) -> None:  # noqa: D107 - deliberately skips chanx init
        self.sent: list[Any] = []

    async def send_message(self, message: Any, **kwargs: Any) -> None:
        self.sent.append(message)


@pytest.fixture
def consumer() -> RecordingConsumer:
    return RecordingConsumer()


async def test_every_graph_step_is_emitted_in_order(
    consumer: RecordingConsumer,
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
            TicketContext(
                ticket_id="t-1",
                title="Charged twice this month",
                description="My card shows two charges.",
            )
        )

    actions = [m.action for m in consumer.sent]
    assert actions[0] == "classified"
    assert "decided" in actions
    assert "answer" in actions
    # The run ends parked at the approval gate, not at the answer.
    assert actions[-1] == "approval_required"
    assert consumer.sent[-1].payload.draft == "Two charges means proration."


async def test_handler_reports_failure_instead_of_raising(
    consumer: RecordingConsumer, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(consumer, "_run_graph", boom)

    await consumer.handle_triage_request(
        TriageRequestMessage(
            payload=TriageRequestPayload(
                ticket_id="t-1", title="x", description="y"
            )
        )
    )

    assert [m.action for m in consumer.sent] == ["triage_error"]
