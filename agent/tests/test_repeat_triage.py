"""A ticket gets triaged more than once, on one checkpointer thread.

The thread id is the ticket, so a second comment resumes a thread that still
holds the previous run's answer, receipt and approval. Every other test uses a
fresh thread id and never sees it.
"""

from typing import Any

from assistant.agents import AgentConfig, Context, ModelConfig, ModelPurpose
from assistant.graphs.checkpointer import memory_checkpointer
from assistant.graphs.states import SupportState
from assistant.graphs.support_graph import build_support_graph
from langgraph.types import Command

from tests.helpers.contexts import ticket_context

TICKET = "aaaaaaaa-1111-2222-3333-444444444444"


def scripted() -> AgentConfig:
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


def context() -> Context:
    return ticket_context(
        ticket_id=TICKET, title="Charged twice", description="Two charges."
    )


async def triage_once(graph: Any, config: dict[str, Any]) -> dict[str, Any]:
    await graph.ainvoke(SupportState(context=context()), config=config)
    return dict(
        await graph.ainvoke(
            Command(resume={"approved": True, "content": None}), config=config
        )
    )


async def test_a_second_triage_starts_clean() -> None:
    graph = build_support_graph(scripted(), memory_checkpointer())
    config = {"configurable": {"thread_id": TICKET}}

    first = await triage_once(graph, config)
    assert first["delivery_receipt"], "the first run should have sent"

    # A whole state defaults every field, which clears the last run's receipt.
    second = await graph.ainvoke(SupportState(context=context()), config=config)

    assert second.get("delivery_receipt") in ("", None)
    assert second.get("approval_granted") in (False, None)
    assert second["__interrupt__"], "it must stop at the gate again"


async def test_a_partial_update_leaks_the_old_receipt() -> None:
    """Names the bug, so nobody passes an update where a state belongs."""
    graph = build_support_graph(scripted(), memory_checkpointer())
    config = {"configurable": {"thread_id": "leaky"}}

    await graph.ainvoke(SupportState(context=context()), config=config)
    await graph.ainvoke(
        Command(resume={"approved": True, "content": None}), config=config
    )

    # Only the ticket, so every other channel keeps what the last run left.
    leaked = await graph.ainvoke({"context": context()}, config=config)

    assert leaked.get("delivery_receipt"), (
        "this is why a whole SupportState is passed rather than an update; if it "
        "is now empty the carry-over is gone and the reset can go with it"
    )
