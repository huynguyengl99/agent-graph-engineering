"""A ticket is worked more than once, and the agent remembers none of it.

The backend holds the state each run ended with and sends it back, so what a
second run inherits is decided here rather than by a checkpointer. Two kinds
of request read that blob differently: a decision continues the run it came
from, a new question starts a new one.
"""

from typing import Any

from assistant.agents import AgentConfig, Context, ModelConfig, ModelPurpose
from assistant.conversations import dump_messages
from assistant.graphs.states import SupportState
from assistant.graphs.states.base import Resuming
from assistant.graphs.support_graph import SupportGraph
from assistant.messages.support import RunRequestPayload
from assistant.ws.topics import SupportTopic
from pydantic_ai.messages import ModelRequest, UserPromptPart

from tests.helpers.contexts import FLAGGED, flagged_ticket_context

TICKET = "aaaaaaaa-1111-2222-3333-444444444444"


def scripted() -> AgentConfig:
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


def context() -> Context:
    # Flagged, so the run still parks: this is about what a second run inherits
    # from the first, and the gate is how it gets somewhere to inherit from.
    return flagged_ticket_context(
        ticket_id=TICKET, title="Charged twice", description=f"Two charges. {FLAGGED}"
    )


class Detached(SupportTopic):
    """A topic without a socket, for the two methods that decide this."""

    def __init__(self) -> None:  # noqa: D107 - deliberately skips chanx init
        self.params = {"audience": "customer", "thread_id": TICKET}
        self.topic = f"support:customer:{TICKET}"


async def first_run() -> dict[str, Any]:
    """One run through the gate, and the state the backend would have stored."""
    graph = SupportGraph(scripted()).compile()
    parked = await graph.ainvoke(SupportState(context=context()))
    sent = await graph.ainvoke(
        SupportState.model_validate(
            {**parked, "resuming": Resuming.REPLY_APPROVAL, "approval_granted": True}
        )
    )
    return SupportState.model_validate(sent).model_dump(mode="json")


def ask(carried: dict[str, Any]) -> RunRequestPayload:
    # No ticket: the context is built from the backend's record and passed in
    # beside the payload, which is where the handler gets it from too.
    return RunRequestPayload(question="Any update?", state=carried)


async def test_a_second_question_starts_clean() -> None:
    finished = await first_run()
    assert finished["delivery_receipt"], "the first run should have sent"

    fresh = Detached()._turn(ask(finished), context())

    assert not fresh.delivery_receipt, "the new turn inherited the last reply"
    assert not fresh.approval_granted
    assert fresh.awaiting is Resuming.NOTHING


async def test_a_second_question_still_remembers_the_thread() -> None:
    """Clean is not blank: the one thing a turn inherits is the memory.

    A customer ticket is worked in a single pass and leaves none, so the blob
    here is a team thread's: what the last run wrote, coming back in.
    """
    remembered = dump_messages([ModelRequest(parts=[UserPromptPart("Refund it.")])])
    finished = {**await first_run(), "messages_json": remembered}

    fresh = Detached()._turn(ask(finished), context())

    assert fresh.messages_json == remembered


async def test_a_decision_keeps_everything_the_run_had() -> None:
    """The other half of the rule. A decision is the same run picked back up,
    so a cancelled call must not report a defaulted field as a success."""
    graph = SupportGraph(scripted()).compile()
    parked = SupportState.model_validate(
        await graph.ainvoke(SupportState(context=context()))
    ).model_dump(mode="json")

    resumed = Detached()._continue(
        parked, resuming=Resuming.REPLY_APPROVAL, approval_granted=True
    )

    assert resumed.answer == SupportState.model_validate(parked).answer
    assert resumed.approval_granted is True
