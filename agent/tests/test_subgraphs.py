"""Composition: the parent adds compiled subgraphs as nodes.

The risky part is the approval gate. It now lives one level down, so a resume
has to reach an interrupt inside a subgraph and the run has to finish there.
"""

from typing import Any

import pytest
from assistant.agents import (
    AgentConfig,
    Audience,
    Context,
    ModelConfig,
    ModelPurpose,
)
from assistant.graphs.delivery_graph import DeliveryGraph
from assistant.graphs.knowledge_graph import KnowledgeGraph
from assistant.graphs.limits import KB_MAX_ATTEMPTS
from assistant.graphs.states import (
    DeliveryState,
    KnowledgeState,
    SupportState,
    ToolState,
)
from assistant.graphs.states.base import ReplyRun
from assistant.graphs.support_graph import SupportGraph
from pydantic import BaseModel

from tests.helpers.contexts import FLAGGED, resume_with, ticket_context

TICKET = "aaaaaaaa-1111-2222-3333-444444444444"
# The gate is this class's subject, and only a flagged ticket reaches it now.
FLAGGED_DESCRIPTION = f"Two charges on my card. {FLAGGED}"


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

        assert state["kb_attempts"] == KB_MAX_ATTEMPTS
        assert not state["kb_snippets"]

    async def test_the_loop_is_capped(self) -> None:
        """Looping on a model's guesses is how a miss becomes a bill."""
        graph = KnowledgeGraph(scripted()).build().compile()
        state = await graph.ainvoke(
            {"context": ticket("Zzzz", "Qqqq"), "kb_query": "zzzz"}
        )

        assert state["kb_attempts"] <= KB_MAX_ATTEMPTS


class TestComposition:
    def test_the_parent_owns_only_its_own_steps(self) -> None:
        parent = SupportGraph().nodes()

        assert set(parent) == {
            "support_start",
            "support_classify",
            "support_decide",
            "support_escalate",
            "support_report_tool",
            "support_respond",
            "support_after_tool",
            "support_done",
        }
        # The gate is one level down, and there is no other route to it.
        assert "delivery_send" in DeliveryGraph().nodes()

    def test_subgraphs_appear_as_nodes_in_the_parent(self) -> None:
        graph = SupportGraph().build().compile().get_graph()
        names = set(graph.nodes)

        assert {"knowledge", "delivery"} <= names

    def test_xray_expands_the_subgraphs(self) -> None:
        """Without xray the diagram shows two opaque boxes."""
        compiled = SupportGraph().build().compile()

        flat = compiled.get_graph().draw_mermaid()
        expanded = compiled.get_graph(xray=True).draw_mermaid()

        assert "delivery_approval" not in flat
        assert "delivery_approval" in expanded
        assert "refine" in expanded


class TestApprovalThroughASubgraph:
    """The gate moved down a level; resume still has to find it.

    These tickets are flagged on the way in, which is what stops a reply for a
    person now that an ordinary one is sent by the agent.
    """

    async def build(self) -> Any:
        return SupportGraph(scripted()).compile()

    async def test_a_run_parks_inside_the_delivery_subgraph(self) -> None:
        graph = await self.build()
        config = {"configurable": {"thread_id": "sub-park"}}

        state = await graph.ainvoke(
            {"context": ticket("Charged twice", FLAGGED_DESCRIPTION)},
            config=config,
        )

        assert not state.get("delivery_receipt"), "it should have stopped, not sent"
        assert state["reply_run"] == "pending"
        assert not state.get("delivery_receipt")

    async def test_resume_reaches_the_interrupt_one_level_down(self) -> None:
        graph = await self.build()
        config = {"configurable": {"thread_id": "sub-resume"}}

        parked = await graph.ainvoke(
            {"context": ticket("Charged twice", FLAGGED_DESCRIPTION)},
            config=config,
        )
        state = await graph.ainvoke(
            resume_with(parked, reply_run=ReplyRun.APPROVED), config=config
        )

        assert state["delivery_receipt"], "approving must reach send_reply"
        assert state["reply_run"] == ReplyRun.SENT

    async def test_rejecting_inside_the_subgraph_sends_nothing(self) -> None:
        graph = await self.build()
        config = {"configurable": {"thread_id": "sub-reject"}}

        parked = await graph.ainvoke(
            {"context": ticket("Charged twice", FLAGGED_DESCRIPTION)},
            config=config,
        )
        state = await graph.ainvoke(
            resume_with(parked, reply_run=ReplyRun.REJECTED), config=config
        )

        assert not state.get("delivery_receipt")
        assert state["reply_run"] == ReplyRun.REJECTED

    async def test_an_edit_made_at_the_gate_is_what_gets_sent(self) -> None:
        graph = await self.build()
        config = {"configurable": {"thread_id": "sub-edit"}}

        parked = await graph.ainvoke(
            {"context": ticket("Charged twice", FLAGGED_DESCRIPTION)},
            config=config,
        )
        edited = "Rewritten by a human."
        state = await graph.ainvoke(
            resume_with(
                parked,
                reply_run=ReplyRun.APPROVED,
                answer={**parked["answer"].model_dump(), "content": edited},
            ),
            config=config,
        )

        assert state["answer"].content == edited
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


class TestTheParentCarriesWhatItsSubgraphsWrite:
    """A subgraph writing a key the parent does not have loses the write.

    Not an error, not a warning: LangGraph drops it, the run carries on, and
    the only symptom is a field that is mysteriously empty. Inheritance would
    make it impossible, at the price of the parent carrying every subgraph's
    private bookkeeping too, so this buys the same guarantee with a test.
    """

    @staticmethod
    def shared(state: type[BaseModel]) -> set[str]:
        """Fields a state gets from a mixin, which is what it shares upward.

        Anything declared on the class itself is its own business: a
        subgraph's attempt counter is not the parent's to know about.
        """
        return set(state.model_fields) - set(getattr(state, "__annotations__", {}))

    @pytest.mark.parametrize(
        ("child", "name"),
        [
            (KnowledgeState, "knowledge"),
            (ToolState, "tool"),
            (DeliveryState, "delivery"),
        ],
    )
    def test_every_shared_key_exists_on_the_parent(
        self, child: type[BaseModel], name: str
    ) -> None:
        missing = self.shared(child) - set(SupportState.model_fields)

        assert not missing, (
            f"the {name} subgraph writes {sorted(missing)}, which SupportState "
            "does not carry, so those writes would be dropped in silence"
        )

    def test_what_a_subgraph_keeps_to_itself_stays_there(self) -> None:
        """The other half, so the first test cannot be satisfied by giving the
        parent every field there is."""
        assert "kb_attempts" not in SupportState.model_fields
        assert "plan" not in SupportState.model_fields
