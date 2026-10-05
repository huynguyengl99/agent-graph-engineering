from assistant.agents import Audience, Context
from assistant.graphs.states import SupportState
from assistant.graphs.support_graph import SupportGraph, build_support_graph
from assistant.outputs.support import Escalate, RunTool, SearchKnowledgeBase

from tests.helpers.contexts import ticket_context
from tests.helpers.openai_mock import mock_openai, tool_call

CLASSIFY = tool_call(
    "final_result",
    {
        "category": "billing",
        "priority": "medium",
        "reasoning": "Asks about an invoice.",
    },
)


def config(thread_id: str) -> dict:
    """The graph is checkpointed, so every run needs a thread to live on."""
    return {"configurable": {"thread_id": thread_id}}


def ticket(**overrides: str) -> Context:
    defaults = {
        "ticket_id": "t-1",
        "title": "Why was I charged twice?",
        "description": "My card shows two charges this month.",
    }
    return ticket_context(**{**defaults, **overrides})


async def test_knowledge_base_branch_grounds_the_answer() -> None:
    thread = "kb-branch"
    with mock_openai(
        CLASSIFY,
        tool_call(
            "final_result_SearchKnowledgeBase",
            {"query": "invoice proration billing", "reasoning": "Documented policy."},
        ),
        tool_call(
            "final_result",
            {
                "content": "Per [kb-002], the extra line is proration.",
                "requires_approval": False,
            },
        ),
    ) as route:
        state = await build_support_graph().ainvoke(
            {"context": ticket()}, config=config(thread)
        )

    assert route.call_count == 3
    assert isinstance(state["decision"], SearchKnowledgeBase)
    # The retrieval step ran and fed the answer agent.
    assert state["kb_snippets"]
    assert any("kb-002" in snippet for snippet in state["kb_snippets"])


async def test_customer_facing_answers_always_require_approval() -> None:
    thread = "approval"
    with mock_openai(
        CLASSIFY,
        tool_call("final_result_Answer", {"reasoning": "Simple question."}),
        tool_call(
            "final_result",
            # The model says no approval needed; the graph overrides it.
            {
                "content": "You can reset it from the sign-in page.",
                "requires_approval": False,
            },
        ),
    ):
        state = await build_support_graph().ainvoke(
            {"context": ticket()}, config=config(thread)
        )

    assert state["answer"].requires_approval is True


async def test_escalation_skips_the_answer_agent() -> None:
    thread = "escalation"
    with mock_openai(
        CLASSIFY,
        tool_call(
            "final_result_Escalate",
            {"reason": "Needs a refund decision.", "suggested_team": "billing"},
        ),
    ) as route:
        state = await build_support_graph().ainvoke(
            {"context": ticket()}, config=config(thread)
        )

    # Two calls, not three: escalation terminates before synthesis.
    assert route.call_count == 2
    assert isinstance(state["decision"], Escalate)
    assert state["escalation_reason"] == "Needs a refund decision."
    assert state["answer"].requires_approval is False


async def test_classification_is_typed_not_parsed() -> None:
    thread = "classify"
    with mock_openai(
        CLASSIFY,
        tool_call(
            "final_result_Escalate", {"reason": "x", "suggested_team": "billing"}
        ),
    ):
        state = await build_support_graph().ainvoke(
            {"context": ticket()}, config=config(thread)
        )

    classification = state["classification"]
    assert classification.category == "billing"
    assert classification.priority == "medium"


async def test_the_thread_reaches_the_prompt() -> None:
    """A triage run is one pass with no message history, so what was already
    said has to be in the prompt or the agent answers the ticket twice."""
    context = ticket_context(history=["I was charged twice.", "Any update?"])

    assert "Any update?" in context.render(with_history=True)


class TestWhatEachAudienceIsOffered:
    """One decider for two audiences, so the branches that do not apply to one
    of them have to be closed rather than merely discouraged."""

    def test_a_customer_run_reaches_the_gate_too(self) -> None:
        """The gate parks on a person either way, so a customer asking for a
        refund proposes one rather than waiting for someone to propose the same
        thing."""
        graph = SupportGraph()
        state = SupportState(
            context=Context(thread_id="t", audience=Audience.CUSTOMER),
            decision=RunTool(reasoning="Refund it."),
        )

        assert graph.route_decision(state) == "tool"

    def test_the_team_gets_the_gate(self) -> None:
        graph = SupportGraph()
        state = SupportState(
            context=Context(thread_id="c", audience=Audience.TEAM),
            decision=RunTool(reasoning="Refund it."),
        )

        assert graph.route_decision(state) == "tool"

    def test_the_team_is_never_escalated_to_itself(self) -> None:
        graph = SupportGraph()
        state = SupportState(
            context=Context(thread_id="c", audience=Audience.TEAM),
            decision=Escalate(reason="Needs a person.", suggested_team="billing"),
        )

        assert graph.route_decision(state) == "respond"


class TestWhatCountsAsAToolCall:
    """The decider routes to the tool branch; the planner decides whether there
    is anything to run. Those are two answers, and only the second one is the
    tool call."""

    def test_a_planner_that_found_nothing_reports_nothing(self) -> None:
        """It used to file a tool call with no tool in it, which reached the
        customer as a box saying RAN about nothing at all."""
        graph = SupportGraph()
        state = SupportState(context=Context(thread_id="t", audience=Audience.CUSTOMER))

        assert graph.route_after_tool(state) == "respond"

    def test_a_tool_that_ran_is_reported(self) -> None:
        graph = SupportGraph()
        state = SupportState(
            context=Context(thread_id="t", audience=Audience.CUSTOMER),
            tool="issue_refund",
            result="refund_1 issued",
        )

        assert graph.route_after_tool(state) == "report_tool"

    def test_a_tool_that_failed_is_reported_too(self) -> None:
        """A reviewer cancelling it, or the call erroring, is still something
        that happened to the ticket."""
        graph = SupportGraph()
        state = SupportState(
            context=Context(thread_id="t", audience=Audience.CUSTOMER),
            tool="issue_refund",
            cancelled=True,
        )

        assert graph.route_after_tool(state) == "report_tool"
