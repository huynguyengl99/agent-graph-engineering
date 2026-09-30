"""A ticket gets triaged more than once, on one checkpointer thread.

The thread id is the ticket, so a second comment resumes a thread that still
holds the previous run's answer, receipt and approval. Every other test uses a
fresh thread id and never sees it.
"""

from typing import Any

from assistant.agents import AgentConfig, ModelConfig, ModelPurpose, TicketContext
from assistant.graphs.checkpointer import memory_checkpointer
from assistant.graphs.triage_graph import build_triage_graph
from assistant.ws.consumer import FRESH_RUN
from langgraph.types import Command

TICKET = "aaaaaaaa-1111-2222-3333-444444444444"


def scripted() -> AgentConfig:
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


def context() -> TicketContext:
    return TicketContext(
        ticket_id=TICKET, title="Charged twice", description="Two charges."
    )


async def triage_once(graph: Any, config: dict[str, Any]) -> dict[str, Any]:
    await graph.ainvoke({"context": context(), **FRESH_RUN}, config=config)
    return dict(
        await graph.ainvoke(
            Command(resume={"approved": True, "content": None}), config=config
        )
    )


async def test_a_second_triage_starts_clean() -> None:
    graph = build_triage_graph(scripted(), memory_checkpointer())
    config = {"configurable": {"thread_id": TICKET}}

    first = await triage_once(graph, config)
    assert first["delivery_receipt"], "the first run should have sent"

    # A new comment arrives. Without the reset this run begins holding the
    # last one's receipt, which the consumer re-emits as a second send.
    second = await graph.ainvoke({"context": context(), **FRESH_RUN}, config=config)

    assert second.get("delivery_receipt") in ("", None)
    assert second.get("approval_granted") in (False, None)
    assert second["__interrupt__"], "it must stop at the gate again"


async def test_without_the_reset_the_old_receipt_leaks() -> None:
    """Names the bug, so nobody quietly drops FRESH_RUN later."""
    graph = build_triage_graph(scripted(), memory_checkpointer())
    config = {"configurable": {"thread_id": "leaky"}}

    await graph.ainvoke({"context": context(), **FRESH_RUN}, config=config)
    await graph.ainvoke(
        Command(resume={"approved": True, "content": None}), config=config
    )

    leaked = await graph.ainvoke({"context": context()}, config=config)

    assert leaked.get("delivery_receipt"), (
        "this is the behaviour FRESH_RUN exists to prevent; if it is now empty "
        "the carry-over is gone and FRESH_RUN can go with it"
    )
