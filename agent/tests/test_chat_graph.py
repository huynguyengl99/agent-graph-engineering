"""The rep-facing chat surface.

Chat is where token streaming has to work: the answer leaves the node as it is
produced, not in one block when the node returns.
"""

from typing import Any

from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
from assistant.agents.deps import ChatContext, TicketContext
from assistant.graphs.chat_graph import ChatGraph
from assistant.outputs.chat import AnswerFromContext, ConsultKnowledgeBase

from tests.helpers.openai_mock import mock_openai, text_stream, tool_call

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


class TestRouting:
    """The chat surface looks things up rather than recalling policy.

    The scripted model resolves an unknown union to its first member, so the
    retrieval branch needs a real routing decision - mocked at the HTTP layer
    like every other one.
    """

    async def run_routed(self, route_call: dict[str, Any]) -> dict[str, Any]:
        with mock_openai(
            route_call,
            text_stream("Per ", "[kb-003]", ", annual plans refund within 14 days."),
        ):
            config = AgentConfig(
                models=dict.fromkeys(
                    ModelPurpose, ModelConfig(provider="openai", name="gpt-4o")
                )
            )
            graph = ChatGraph(config).build().compile()
            return dict(
                await graph.ainvoke(
                    {
                        "context": ChatContext(conversation_id="c-route"),
                        "question": "What is our refund window on annual plans?",
                    }
                )
            )

    async def test_a_policy_question_goes_through_the_knowledge_base(self) -> None:
        state = await self.run_routed(
            tool_call(
                "final_result_ConsultKnowledgeBase",
                {"query": "refund policy annual", "reasoning": "Documented."},
            )
        )

        assert isinstance(state["route"], ConsultKnowledgeBase)
        assert state["kb_snippets"], "the retrieval subgraph should have run"
        assert any("kb-003" in s for s in state["kb_snippets"])

    async def test_a_question_answerable_from_context_skips_retrieval(self) -> None:
        state = await self.run_routed(
            tool_call(
                "final_result_AnswerFromContext",
                {"reasoning": "Already in the thread."},
            )
        )

        assert isinstance(state["route"], AnswerFromContext)
        assert not state.get("kb_snippets")


def test_the_retrieval_subgraph_has_two_parents() -> None:
    """Which is what makes it a subgraph rather than a node."""
    from assistant.graphs.triage_graph import TriageGraph

    chat_nodes = set(ChatGraph().build().compile().get_graph().nodes)
    triage_nodes = set(TriageGraph().build().compile().get_graph().nodes)

    assert "knowledge" in chat_nodes
    assert "knowledge" in triage_nodes


async def test_the_answer_is_grounded_in_what_retrieval_found() -> None:
    """Snippets have to reach the answering prompt, or the lookup was theatre."""
    seen: list[str] = []

    class Capturing(ChatGraph):
        async def answer(self, state: Any) -> Any:
            seen.append(str(state.kb_snippets))
            return await super().answer(state)

    with mock_openai(
        tool_call(
            "final_result_ConsultKnowledgeBase",
            {"query": "refund policy annual", "reasoning": "Documented."},
        ),
        text_stream("Per [kb-003]."),
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
                    "context": ChatContext(conversation_id="c-ground"),
                    "question": "What is our refund window?",
                }
            )
        )

    assert seen and "kb-003" in seen[0]
