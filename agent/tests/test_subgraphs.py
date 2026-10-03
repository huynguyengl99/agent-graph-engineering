"""Composition: the parent adds compiled subgraphs as nodes.

The risky part is the approval gate. It now lives one level down, so a resume
has to reach an interrupt inside a subgraph and the run has to finish there.
"""

from typing import Any

from assistant.agents import (
    AgentConfig,
    Audience,
    Context,
    ModelConfig,
    ModelPurpose,
)
from assistant.graphs.checkpointer import memory_checkpointer
from assistant.graphs.delivery_graph import DeliveryGraph
from assistant.graphs.knowledge_graph import MAX_ATTEMPTS, KnowledgeGraph
from assistant.graphs.support_graph import SupportGraph, build_support_graph
from langgraph.types import Command

from tests.helpers.contexts import ticket_context

TICKET = "aaaaaaaa-1111-2222-3333-444444444444"


def scripted() -> AgentConfig:
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


def ticket(title: str, description: str) -> Context:
    return ticket_context(ticket_id=TICKET, title=title, description=description)


class TestKnowledgeSubgraph:
    async def test_a_hit_does_not_retry(self) -> None:
        graph = KnowledgeGraph(scripted()).build().compile()
        state = await graph.ainvoke(
            {"context": ticket("Charged twice", "My invoice shows two charges.")}
        )

        assert state["kb_attempts"] == 1
        assert state["kb_snippets"]

    async def test_a_miss_refines_and_searches_again(self) -> None:
        graph = KnowledgeGraph(scripted()).build().compile()
        state = await graph.ainvoke(
            {"context": ticket("Zzzz", "Qqqq wwww eeee"), "kb_query": "zzzz qqqq"}
        )

        assert state["kb_attempts"] == MAX_ATTEMPTS
        assert not state["kb_snippets"]

    async def test_the_loop_is_capped(self) -> None:
        """Looping on a model's guesses is how a miss becomes a bill."""
        graph = KnowledgeGraph(scripted()).build().compile()
        state = await graph.ainvoke(
            {"context": ticket("Zzzz", "Qqqq"), "kb_query": "zzzz"}
        )

        assert state["kb_attempts"] <= MAX_ATTEMPTS


class TestComposition:
    def test_the_parent_owns_only_its_own_steps(self) -> None:
        parent = SupportGraph().nodes()

        assert set(parent) == {
            "classify",
            "decide",
            "escalate",
            "report_tool",
            "respond",
        }
        # The gate is one level down, and there is no other route to it.
        assert "send_reply" in DeliveryGraph().nodes()

    def test_subgraphs_appear_as_nodes_in_the_parent(self) -> None:
        graph = SupportGraph().build().compile().get_graph()
        names = set(graph.nodes)

        assert {"knowledge", "delivery"} <= names

    def test_xray_expands_the_subgraphs(self) -> None:
        """Without xray the diagram shows two opaque boxes."""
        compiled = SupportGraph().build().compile()

        flat = compiled.get_graph().draw_mermaid()
        expanded = compiled.get_graph(xray=True).draw_mermaid()

        assert "await_approval" not in flat
        assert "await_approval" in expanded
        assert "refine" in expanded


class TestApprovalThroughASubgraph:
    """The gate moved down a level; resume still has to find it."""

    async def build(self) -> Any:
        return build_support_graph(scripted(), memory_checkpointer())

    async def test_a_run_parks_inside_the_delivery_subgraph(self) -> None:
        graph = await self.build()
        config = {"configurable": {"thread_id": "sub-park"}}

        state = await graph.ainvoke(
            {"context": ticket("Charged twice", "Two charges on my card.")},
            config=config,
        )

        assert state["__interrupt__"], "the run should be parked, not finished"
        assert state["__interrupt__"][0].value["kind"] == "reply_approval"
        assert not state.get("delivery_receipt")

    async def test_resume_reaches_the_interrupt_one_level_down(self) -> None:
        graph = await self.build()
        config = {"configurable": {"thread_id": "sub-resume"}}

        await graph.ainvoke(
            {"context": ticket("Charged twice", "Two charges on my card.")},
            config=config,
        )
        state = await graph.ainvoke(
            Command(resume={"approved": True, "content": None}), config=config
        )

        assert state["delivery_receipt"], "approving must reach send_reply"
        assert state["approval_granted"] is True

    async def test_rejecting_inside_the_subgraph_sends_nothing(self) -> None:
        graph = await self.build()
        config = {"configurable": {"thread_id": "sub-reject"}}

        await graph.ainvoke(
            {"context": ticket("Charged twice", "Two charges on my card.")},
            config=config,
        )
        state = await graph.ainvoke(
            Command(resume={"approved": False, "content": None}), config=config
        )

        assert not state.get("delivery_receipt")
        assert state["approval_granted"] is False

    async def test_an_edit_made_at_the_gate_is_what_gets_sent(self) -> None:
        graph = await self.build()
        config = {"configurable": {"thread_id": "sub-edit"}}

        await graph.ainvoke(
            {"context": ticket("Charged twice", "Two charges on my card.")},
            config=config,
        )
        state = await graph.ainvoke(
            Command(resume={"approved": True, "content": "Rewritten by a human."}),
            config=config,
        )

        assert state["answer"].content == "Rewritten by a human."
        assert state["delivery_receipt"]


class TestACheckpointThreadBelongsToOneRun:
    """Keyed on the ticket alone, a customer's run and the team's run about it
    shared a thread, and the next one died validating the other's state."""

    def test_the_two_audiences_never_share_one(self) -> None:
        for_customer = SupportGraph.thread_for(
            Context(thread_id="abc", audience=Audience.CUSTOMER)
        )
        for_team = SupportGraph.thread_for(
            Context(thread_id="abc", audience=Audience.TEAM)
        )

        assert for_customer != for_team

    def test_the_key_is_still_in_it(self) -> None:
        assert "abc" in SupportGraph.thread_for(Context(thread_id="abc"))
