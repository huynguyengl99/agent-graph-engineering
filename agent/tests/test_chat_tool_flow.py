"""The tool gate as it reaches the browser.

`test_tool_graph` proves the graph parks and resumes; this proves the consumer
turns that park into a message a UI can render, and turns the reviewer's reply
back into a resume on the same thread. The two halves broke independently
during development: the graph interrupt is nested inside a subgraph update, and
a completion sent while parked would have the client close the card early.
"""

from typing import Any

import pytest
from assistant.ws.chat_consumer import ChatConsumer
from assistant.ws.chat_messages import (
    ChatRequestMessage,
    ChatRequestPayload,
    ToolDecisionMessage,
    ToolDecisionPayload,
)
from assistant.ws.messages import ModelOverrides

from tests.helpers.openai_mock import Recorder, mock_openai, text_stream, tool_call

CONVERSATION = "c-tool"

ROUTE_TO_TOOL = tool_call(
    "final_result_RunTool", {"reasoning": "They want the refund issued."}
)
PROPOSE_REFUND = tool_call(
    "final_result_ToolProposal",
    {
        "tool": "issue_refund",
        "arguments": {
            "email": "demo@example.com",
            "amount": 29.0,
            "reason": "Duplicate charge",
        },
        "reasoning": "Charged twice for the same month.",
    },
)


class RecordingConsumer(ChatConsumer):
    """Captures what would go on the wire, without a socket."""

    def __init__(self) -> None:  # noqa: D107 - deliberately skips chanx init
        self.sent: list[Any] = []

    async def send_message(self, message: Any, **kwargs: Any) -> None:
        self.sent.append(message)

    @property
    def actions(self) -> list[str]:
        return [m.action for m in self.sent]

    def last(self, action: str) -> Any:
        return next(m for m in reversed(self.sent) if m.action == action)


@pytest.fixture
def consumer() -> RecordingConsumer:
    return RecordingConsumer()


def request() -> ChatRequestMessage:
    return ChatRequestMessage(
        payload=ChatRequestPayload(
            conversation_id=CONVERSATION,
            question="Refund the duplicate charge for demo@example.com.",
            # Pin the provider so the mocked transport is the one in play.
            models=ModelOverrides(decision="openai:gpt-4o", answer="openai:gpt-4o"),
        )
    )


async def park(consumer: RecordingConsumer) -> None:
    with mock_openai(ROUTE_TO_TOOL, PROPOSE_REFUND):
        await consumer.handle_chat_request(request())


async def decide(
    consumer: RecordingConsumer, *, approved: bool, arguments: dict[str, Any]
) -> Recorder:
    """Resume, and hand back what the answering model was told."""
    with mock_openai(text_stream("Done", " - ", "refunded.")) as recorder:
        await consumer.handle_tool_decision(
            ToolDecisionMessage(
                payload=ToolDecisionPayload(
                    conversation_id=CONVERSATION,
                    approved=approved,
                    arguments=arguments,
                )
            )
        )
    return recorder


class TestParking:
    async def test_the_proposal_reaches_the_client(
        self, consumer: RecordingConsumer
    ) -> None:
        await park(consumer)

        assert "tool_approval" in consumer.actions
        payload = consumer.last("tool_approval").payload
        assert payload.tool == "issue_refund"
        assert payload.arguments["amount"] == 29.0
        assert payload.description, "the card needs something to show"

    async def test_the_form_is_described_by_the_schema(
        self, consumer: RecordingConsumer
    ) -> None:
        """The UI builds the correction form from this and nothing else."""
        await park(consumer)

        schema = consumer.last("tool_approval").payload.arguments_schema
        assert set(schema["properties"]) == {"email", "amount", "reason"}
        assert schema["properties"]["amount"]["type"] == "number"
        # Descriptions come from the docstring, so a new tool is reviewable
        # without anyone writing UI copy for it.
        assert schema["properties"]["amount"]["description"]
        # `approved` is how the tool wrapper enforces the gate. Offering it on
        # the form would let a reviewer approve by filling in a field.
        assert "approved" not in schema["properties"]

    async def test_no_answer_is_sent_while_a_human_is_deciding(
        self, consumer: RecordingConsumer
    ) -> None:
        await park(consumer)

        assert "chat_complete" not in consumer.actions
        assert "chat_token" not in consumer.actions

    async def test_the_schema_field_does_not_shadow_a_model_attribute(
        self, consumer: RecordingConsumer
    ) -> None:
        """Called `schema`, this field warns in every generated client."""
        await park(consumer)

        wire = consumer.last("tool_approval").model_dump()
        assert "arguments_schema" in wire["payload"]
        assert "schema" not in wire["payload"]


class TestOneTurnDoesNotLeakIntoTheNext:
    """The thread is the conversation, so its state outlives a turn.

    Caught by the browser smoke: a refund ran, then the next call was
    cancelled, and the assistant cheerfully reported the *earlier* refund as
    though the cancelled one had gone through.
    """

    async def test_a_cancelled_call_is_not_reported_as_the_last_success(
        self, consumer: RecordingConsumer
    ) -> None:
        await park(consumer)
        await decide(consumer, approved=True, arguments={})

        await park(consumer)
        recorder = await decide(consumer, approved=False, arguments={})

        assert "Refunded" not in recorder.prompts, (
            "the previous turn's result was still in state"
        )
        assert "cancelled" in recorder.prompts

    async def test_a_plain_question_does_not_inherit_a_tool_result(
        self, consumer: RecordingConsumer
    ) -> None:
        await park(consumer)
        await decide(consumer, approved=True, arguments={})

        answer_directly = tool_call(
            "final_result_AnswerFromContext", {"reasoning": "Already covered."}
        )
        with mock_openai(answer_directly, text_stream("Here you go.")) as recorder:
            await consumer.handle_chat_request(request())

        assert "A tool was run" not in recorder.prompts


class TestMisnamedArguments:
    async def test_a_dropped_argument_is_named_for_the_reviewer(
        self, consumer: RecordingConsumer
    ) -> None:
        """Otherwise the form shows a blank required field with no reason."""
        misnamed = tool_call(
            "final_result_ToolProposal",
            {
                "tool": "issue_refund",
                "arguments": {"customer_email": "demo@example.com", "amount": 29.0},
                "reasoning": "Charged twice.",
            },
        )
        with mock_openai(ROUTE_TO_TOOL, misnamed):
            await consumer.handle_chat_request(request())

        payload = consumer.last("tool_approval").payload
        assert payload.unknown_arguments == ["customer_email"]
        assert "customer_email" not in payload.arguments


class TestDeciding:
    async def test_approving_runs_the_tool_and_answers(
        self, consumer: RecordingConsumer
    ) -> None:
        await park(consumer)
        recorder = await decide(consumer, approved=True, arguments={})

        assert "Refunded \u00a329.00" in recorder.prompts
        assert consumer.actions[-1] == "chat_complete"
        assert "refunded" in consumer.last("chat_complete").payload.content

    async def test_a_correction_is_what_runs(self, consumer: RecordingConsumer) -> None:
        await park(consumer)
        recorder = await decide(
            consumer,
            approved=True,
            arguments={
                "email": "demo@example.com",
                "amount": 9.0,
                "reason": "Duplicate charge",
            },
        )

        # What the answering model was told is the only proof that the
        # corrected amount is the one that was charged.
        assert "Refunded \u00a39.00" in recorder.prompts
        assert "29" not in recorder.prompts, (
            "the proposed amount must not survive a correction"
        )
        assert consumer.actions[-1] == "chat_complete"

    async def test_the_answer_is_told_a_person_changed_the_arguments(
        self, consumer: RecordingConsumer
    ) -> None:
        """A live run answered a corrected £9 refund by telling the rep to
        refund the missing £20 - the reviewer's decision undone by the summary
        of it. The answer has to know the smaller number was deliberate."""
        await park(consumer)
        recorder = await decide(
            consumer,
            approved=True,
            arguments={
                "email": "demo@example.com",
                "amount": 9.0,
                "reason": "Duplicate charge",
            },
        )

        assert "A reviewer changed the arguments" in recorder.prompts

    async def test_an_untouched_approval_says_nothing_about_corrections(
        self, consumer: RecordingConsumer
    ) -> None:
        await park(consumer)
        recorder = await decide(consumer, approved=True, arguments={})

        assert "A reviewer changed the arguments" not in recorder.prompts

    async def test_cancelling_answers_without_running_anything(
        self, consumer: RecordingConsumer
    ) -> None:
        await park(consumer)
        recorder = await decide(consumer, approved=False, arguments={})

        assert "Refunded" not in recorder.prompts
        assert "cancelled" in recorder.prompts
        assert consumer.actions[-1] == "chat_complete"

    async def test_a_decision_for_an_unknown_thread_reports_an_error(
        self, consumer: RecordingConsumer
    ) -> None:
        """Resuming a run that was never parked must not hang the socket."""
        await consumer.handle_tool_decision(
            ToolDecisionMessage(
                payload=ToolDecisionPayload(
                    conversation_id="c-nothing-here", approved=True
                )
            )
        )

        assert consumer.actions == ["chat_error"]
