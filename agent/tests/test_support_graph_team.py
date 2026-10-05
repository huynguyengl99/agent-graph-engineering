"""The rep-facing chat surface.

Chat is where token streaming has to work: the answer leaves the node as it is
produced, not in one block when the node returns.
"""

from typing import Any

from assistant.agents import (
    AgentConfig,
    Context,
    ModelConfig,
    ModelPurpose,
    Ticket,
    Turn,
)
from assistant.graphs.support_graph import SupportGraph
from assistant.outputs.support import Answer, SearchKnowledgeBase

from tests.helpers.openai_mock import answer_stream, mock_openai, tool_call

QUESTION = "What do I tell them about the double charge?"


def scripted() -> AgentConfig:
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


async def run(context: Context) -> tuple[list[str], dict[str, Any]]:
    """The answer's deltas, caught where every subscriber catches them.

    They are published on the run's topic rather than written to the graph's
    stream, so a second tab sees the answer being typed. The decider's
    reasoning is published the same way and is a different thing being written,
    which is what the action tells them apart by.
    """
    deltas: list[str] = []

    async def emit(event: Any, *, replayable: bool = True) -> None:
        if event.action == "chat_token":
            deltas.append(event.payload.delta)

    graph = SupportGraph(scripted(), emit).build().compile()
    updates: dict[str, Any] = {}
    async for chunk in graph.astream(
        {"context": context, "question": QUESTION}, stream_mode="updates"
    ):
        updates.update(chunk)
    return deltas, updates


async def test_the_answer_arrives_as_deltas_not_one_block() -> None:
    deltas, updates = await run(Context(thread_id="c-1"))

    assert len(deltas) > 1, "a single delta means nothing is actually streaming"
    # What streamed and what was saved must be the same text.
    assert "".join(deltas) == updates["support_respond"]["answer"].content


async def test_a_ticket_linked_conversation_sees_the_ticket() -> None:
    context = Context(
        thread_id="c-2",
        ticket=Ticket(
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
    """Said rather than left out: with nothing about a ticket at all, the model
    assumes a customer is waiting and answers as though one had written in."""
    context = Context(thread_id="c-3")
    prompt = context.render(QUESTION)

    assert "BEGIN TICKET" not in prompt
    assert "No ticket is attached" in prompt

    deltas, updates = await run(context)
    assert updates["support_respond"]["answer"].content


async def test_history_is_not_flattened_into_the_prompt() -> None:
    """It reaches the model as its own message history instead.

    Repeating it here would send every earlier turn twice, and would turn a tool
    call the model made into a line of prose about it.
    """
    context = Context(
        thread_id="c-4",
        history=[
            Turn("user", "Is this refundable?"),
            Turn("assistant", "Within 14 days."),
        ],
    )
    prompt = context.render(QUESTION)

    assert "Within 14 days." not in prompt
    assert QUESTION in prompt


class TestRouting:
    """The chat surface looks things up rather than recalling policy.

    The scripted model resolves an unknown union to its first member, so the
    retrieval branch needs a real routing decision - mocked at the HTTP layer
    like every other one.
    """

    async def run_routed(self, route_call: dict[str, Any]) -> dict[str, Any]:
        with mock_openai(
            route_call,
            answer_stream("Per ", "[kb-003]", ", annual plans refund within 14 days."),
        ):
            config = AgentConfig(
                models=dict.fromkeys(
                    ModelPurpose, ModelConfig(provider="openai", name="gpt-4o")
                )
            )
            graph = SupportGraph(config).build().compile()
            return dict(
                await graph.ainvoke(
                    {
                        "context": Context(thread_id="c-route"),
                        "question": "What is our refund window on annual plans?",
                    }
                )
            )

    async def test_a_policy_question_goes_through_the_knowledge_base(self) -> None:
        state = await self.run_routed(
            tool_call(
                "final_result_SearchKnowledgeBase",
                {"query": "refund policy annual", "reasoning": "Documented."},
            )
        )

        assert isinstance(state["decision"], SearchKnowledgeBase)
        assert state["kb_snippets"], "the retrieval subgraph should have run"
        assert any("kb-003" in s for s in state["kb_snippets"])

    async def test_a_question_answerable_from_context_skips_retrieval(self) -> None:
        state = await self.run_routed(
            tool_call(
                "final_result_Answer",
                {"reasoning": "Already in the thread."},
            )
        )

        assert isinstance(state["decision"], Answer)
        assert not state.get("kb_snippets")


def test_the_retrieval_subgraph_has_two_parents() -> None:
    """Which is what makes it a subgraph rather than a node."""
    from assistant.graphs.support_graph import SupportGraph

    nodes = set(SupportGraph().build().compile().get_graph().nodes)

    assert "knowledge" in nodes
    assert "tool" in nodes


async def test_the_answer_is_grounded_in_what_retrieval_found() -> None:
    """Snippets have to reach the answering prompt, or the lookup was theatre."""
    seen: list[str] = []

    class Capturing(SupportGraph):
        async def support_respond(self, state: Any) -> Any:
            seen.append(str(state.kb_snippets))
            return await super().support_respond(state)

    with mock_openai(
        tool_call(
            "final_result_SearchKnowledgeBase",
            {"query": "refund policy annual", "reasoning": "Documented."},
        ),
        answer_stream("Per [kb-003]."),
    ):
        config = AgentConfig(
            models=dict.fromkeys(
                ModelPurpose, ModelConfig(provider="openai", name="gpt-4o")
            )
        )
        await (
            Capturing(config)
            .build()
            .compile()
            .ainvoke(
                {
                    "context": Context(thread_id="c-ground"),
                    "question": "What is our refund window?",
                }
            )
        )

    assert seen and "kb-003" in seen[0]
