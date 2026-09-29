"""The rep-facing chat surface.

Chat is where token streaming has to work: the answer leaves the node as it is
produced, not in one block when the node returns.
"""

from typing import Any

from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
from assistant.agents.deps import ChatContext, TicketContext
from assistant.graphs.chat_graph import ChatGraph

QUESTION = "What do I tell them about the double charge?"


def scripted() -> AgentConfig:
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


async def run(context: ChatContext) -> tuple[list[str], dict[str, Any]]:
    graph = ChatGraph(scripted()).build().compile()
    deltas: list[str] = []
    updates: dict[str, Any] = {}
    async for mode, chunk in graph.astream(
        {"context": context, "question": QUESTION},
        stream_mode=["updates", "custom"],
    ):
        if mode == "custom":
            deltas.append(chunk["delta"])
        else:
            updates.update(chunk)
    return deltas, updates


async def test_the_answer_arrives_as_deltas_not_one_block() -> None:
    deltas, updates = await run(ChatContext(conversation_id="c-1"))

    assert len(deltas) > 1, "a single delta means nothing is actually streaming"
    # What streamed and what was saved must be the same text.
    assert "".join(deltas) == updates["answer"]["answer"]


async def test_a_ticket_linked_conversation_sees_the_ticket() -> None:
    context = ChatContext(
        conversation_id="c-2",
        ticket=TicketContext(
            ticket_id="t-9",
            title="Charged twice this month",
            description="Two charges on my card.",
        ),
    )
    prompt = context.render(QUESTION)

    assert "Charged twice this month" in prompt
    deltas, _ = await run(context)
    assert deltas


async def test_a_standalone_conversation_needs_no_ticket() -> None:
    context = ChatContext(conversation_id="c-3")
    assert "ticket" not in context.render(QUESTION).lower()

    deltas, updates = await run(context)
    assert updates["answer"]["answer"]


async def test_history_is_carried_into_the_prompt() -> None:
    context = ChatContext(
        conversation_id="c-4",
        history=[("user", "Is this refundable?"), ("assistant", "Within 14 days.")],
    )
    prompt = context.render(QUESTION)

    assert "Within 14 days." in prompt
    assert prompt.index("Within 14 days.") < prompt.index(QUESTION)
