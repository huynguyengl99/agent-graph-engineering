"""The human-in-the-loop gate: pause, then approve, reject, or edit."""

from assistant.agents import TicketContext
from assistant.graphs.triage_graph import triage_graph
from langgraph.types import Command

from tests.helpers.openai_mock import mock_openai, tool_call

DRAFT = "You were charged twice because of proration."


def config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def ticket() -> TicketContext:
    return TicketContext(
        ticket_id="t-1",
        title="Why was I charged twice?",
        description="My card shows two charges.",
    )


async def start(thread: str) -> dict:
    """Run until the graph parks at the approval interrupt."""
    with mock_openai(
        tool_call(
            "final_result",
            {"category": "billing", "priority": "medium", "reasoning": "Invoice."},
        ),
        tool_call("final_result_AnswerDirectly", {"reasoning": "Known answer."}),
        tool_call("final_result", {"content": DRAFT, "requires_approval": False}),
    ):
        return await triage_graph.ainvoke({"context": ticket()}, config=config(thread))


async def test_run_pauses_and_surfaces_the_draft() -> None:
    state = await start("pause")

    assert "__interrupt__" in state
    payload = state["__interrupt__"][0].value
    assert payload["kind"] == "reply_approval"
    assert payload["draft"] == DRAFT
    # Nothing was sent while the graph is parked.
    assert state.get("delivery_receipt") is None


async def test_approval_sends_the_reply() -> None:
    thread = "approve"
    await start(thread)

    state = await triage_graph.ainvoke(
        Command(resume={"approved": True}), config=config(thread)
    )

    assert state["approval_granted"] is True
    assert "Reply queued" in state["delivery_receipt"]


async def test_rejection_leaves_the_customer_untouched() -> None:
    thread = "reject"
    await start(thread)

    state = await triage_graph.ainvoke(
        Command(resume={"approved": False}), config=config(thread)
    )

    assert state["approval_granted"] is False
    # The irreversible node never ran.
    assert state.get("delivery_receipt") is None


async def test_reviewer_can_edit_before_sending() -> None:
    thread = "edit"
    await start(thread)
    edited = "Rewritten by a human reviewer."

    state = await triage_graph.ainvoke(
        Command(resume={"approved": True, "content": edited}),
        config=config(thread),
    )

    assert state["answer"].content == edited
    assert state["delivery_receipt"] is not None


async def test_resume_finds_the_run_without_replaying_the_llm() -> None:
    """The resume must not call the model again; state comes from the checkpoint."""
    thread = "no-replay"
    await start(thread)

    # No mock installed: any provider call here would raise.
    state = await triage_graph.ainvoke(
        Command(resume={"approved": True}), config=config(thread)
    )
    assert state["delivery_receipt"] is not None
