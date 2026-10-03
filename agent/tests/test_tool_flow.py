"""The tool gate as it reaches the browser.

`test_tool_graph` proves the graph parks and resumes; this proves the topic
turns that park into a message a UI can render, and turns the reviewer's reply
back into a resume on the same thread. The two halves broke independently
during development: the graph interrupt is nested inside a subgraph update, and
a completion sent while parked would have the client close the card early.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from assistant.messages.chat import (
    ToolDecisionMessage,
    ToolDecisionPayload,
)
from assistant.messages.support import RunRequestMessage, RunRequestPayload
from assistant.messages.triage import ModelOverrides
from assistant.tracing import setup_tracing, trace_store
from assistant.ws.topics import SupportTopic

from tests.helpers.events import Recorded, recording
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


class DetachedTopic(SupportTopic):
    """Drives a run without a socket. Token deltas still go to the one socket
    that is streaming, so they arrive here; every other event is broadcast and
    the `events` fixture captures it."""

    def __init__(self) -> None:  # noqa: D107 - deliberately skips chanx init
        self.sent: list[Any] = []
        self.params = {"audience": "team", "thread_id": CONVERSATION}
        self.topic = f"support:team:{CONVERSATION}"

    async def send_message(self, message: Any, **kwargs: Any) -> None:
        self.sent.append(message)

    @property
    def deltas(self) -> list[str]:
        return [m.payload.delta for m in self.sent if m.action == "chat_token"]


@pytest.fixture
def consumer() -> DetachedTopic:
    return DetachedTopic()


@pytest.fixture
def events() -> Iterator[Recorded]:
    with recording(SupportTopic) as recorded:
        yield recorded


def request() -> RunRequestMessage:
    return RunRequestMessage(
        payload=RunRequestPayload(
            conversation_id=CONVERSATION,
            question="Refund the duplicate charge for demo@example.com.",
            # Pin the provider so the mocked transport is the one in play.
            models=ModelOverrides(decision="openai:gpt-4o", answer="openai:gpt-4o"),
        )
    )


async def park(consumer: DetachedTopic) -> None:
    with mock_openai(ROUTE_TO_TOOL, PROPOSE_REFUND):
        await consumer.handle_run_request(request())


async def decide(
    consumer: DetachedTopic, *, approved: bool, arguments: dict[str, Any]
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
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        await park(consumer)

        assert "tool_approval" in events.actions()
        payload = events.last("tool_approval").payload
        assert payload.tool == "issue_refund"
        assert payload.arguments["amount"] == 29.0
        assert payload.description, "the card needs something to show"

    async def test_the_form_is_described_by_the_schema(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        """The UI builds the correction form from this and nothing else."""
        await park(consumer)

        schema = events.last("tool_approval").payload.arguments_schema
        assert set(schema["properties"]) == {"email", "amount", "reason"}
        assert schema["properties"]["amount"]["type"] == "number"
        # Descriptions come from the docstring, so a new tool is reviewable
        # without anyone writing UI copy for it.
        assert schema["properties"]["amount"]["description"]
        # `approved` is how the tool wrapper enforces the gate. Offering it on
        # the form would let a reviewer approve by filling in a field.
        assert "approved" not in schema["properties"]

    async def test_no_answer_is_sent_while_a_human_is_deciding(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        await park(consumer)

        assert "chat_complete" not in events.actions()
        assert consumer.deltas == []

    async def test_the_schema_field_does_not_shadow_a_model_attribute(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        """Called `schema`, this field warns in every generated client."""
        await park(consumer)

        wire = events.last("tool_approval").model_dump()
        assert "arguments_schema" in wire["payload"]
        assert "schema" not in wire["payload"]


class TestOneTurnDoesNotLeakIntoTheNext:
    """The thread is the conversation, so its state outlives a turn.

    Caught by the browser smoke: a refund ran, then the next call was
    cancelled, and the assistant cheerfully reported the *earlier* refund as
    though the cancelled one had gone through.
    """

    async def test_a_cancelled_call_is_not_reported_as_the_last_success(
        self, consumer: DetachedTopic
    ) -> None:
        await park(consumer)
        await decide(consumer, approved=True, arguments={})

        await park(consumer)
        recorder = await decide(consumer, approved=False, arguments={})

        # This turn's prompt, not the whole exchange: history legitimately holds
        # the earlier refund.
        assert "Refunded" not in recorder.last_user_prompt, (
            "the previous turn's result was still in state"
        )
        assert "cancelled" in recorder.last_user_prompt

    async def test_a_plain_question_does_not_inherit_a_tool_result(
        self, consumer: DetachedTopic
    ) -> None:
        await park(consumer)
        await decide(consumer, approved=True, arguments={})

        answer_directly = tool_call(
            "final_result_Answer", {"reasoning": "Already covered."}
        )
        with mock_openai(answer_directly, text_stream("Here you go.")) as recorder:
            await consumer.handle_run_request(request())

        assert "A tool was run" not in recorder.last_user_prompt


class TestMisnamedArguments:
    async def test_a_dropped_argument_is_named_for_the_reviewer(
        self, consumer: DetachedTopic, events: Recorded
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
            await consumer.handle_run_request(request())

        payload = events.last("tool_approval").payload
        assert payload.unknown_arguments == ["customer_email"]
        assert "customer_email" not in payload.arguments


class TestDeciding:
    async def test_approving_runs_the_tool_and_answers(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        await park(consumer)
        recorder = await decide(consumer, approved=True, arguments={})

        assert "Refunded \u00a329.00" in recorder.prompts
        assert events.actions()[-1] == "chat_complete"
        assert "refunded" in events.last("chat_complete").payload.content

    async def test_a_correction_is_what_runs(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
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
        assert events.actions()[-1] == "chat_complete"

    async def test_the_answer_is_told_a_person_changed_the_arguments(
        self, consumer: DetachedTopic
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
        self, consumer: DetachedTopic
    ) -> None:
        await park(consumer)
        recorder = await decide(consumer, approved=True, arguments={})

        assert "A reviewer changed the arguments" not in recorder.prompts

    async def test_cancelling_answers_without_running_anything(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        await park(consumer)
        recorder = await decide(consumer, approved=False, arguments={})

        assert "Refunded" not in recorder.prompts
        assert "cancelled" in recorder.prompts
        assert events.actions()[-1] == "chat_complete"

    async def test_a_decision_for_an_unknown_thread_reports_an_error(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        """Resuming a run that was never parked must not hang the socket."""
        await consumer.handle_tool_decision(
            ToolDecisionMessage(
                payload=ToolDecisionPayload(
                    conversation_id="c-nothing-here", approved=True
                )
            )
        )

        assert events.actions() == ["chat_error"]


class TestTheParkAndTheResumeAreOneRun:
    """The gate splits a turn across two WebSocket messages."""

    async def test_the_resume_joins_the_run_it_parked(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        setup_tracing()
        trace_store.clear()
        await park(consumer)
        [run] = trace_store.runs()

        await decide(consumer, approved=True, arguments={})

        assert trace_store.runs() == [run], "the resume opened a trace of its own"
        assert [root["name"] for root in trace_store.tree(run)] == [
            "support run",
            "support run resumed",
        ]


class TestTheTicketRecordsWhatRan:
    """A reviewer approved an action, so what is recorded is the action, not
    only the sentence written about it afterwards."""

    async def test_an_approved_call_is_reported(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        await park(consumer)

        await decide(consumer, approved=True, arguments={})

        ran = events.last("tool_ran").payload
        assert ran.tool == "issue_refund"
        assert ran.arguments["amount"] == 29.0
        assert ran.result
        assert not ran.cancelled

    async def test_a_cancelled_one_says_so(
        self, consumer: DetachedTopic, events: Recorded
    ) -> None:
        await park(consumer)

        await decide(consumer, approved=False, arguments={})

        ran = events.last("tool_ran").payload
        assert ran.cancelled
        assert not ran.result
