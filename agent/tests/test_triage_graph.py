from assistant.agents import TicketContext
from assistant.graphs.triage_graph import triage_graph
from assistant.outputs.triage import Escalate, SearchKnowledgeBase

from tests.helpers.openai_mock import mock_openai, tool_call

CLASSIFY = tool_call(
    "final_result",
    {"category": "billing", "priority": "medium", "reasoning": "Asks about an invoice."},
)


def config(thread_id: str) -> dict:
    """The graph is checkpointed, so every run needs a thread to live on."""
    return {"configurable": {"thread_id": thread_id}}


def ticket(**overrides: str) -> TicketContext:
    defaults = {
        "ticket_id": "t-1",
        "title": "Why was I charged twice?",
        "description": "My card shows two charges this month.",
    }
    return TicketContext(**{**defaults, **overrides})


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
            {"content": "Per [kb-002], the extra line is proration.", "requires_approval": False},
        ),
    ) as route:
        state = await triage_graph.ainvoke({"context": ticket()}, config=config(thread))

    assert route.call_count == 3
    assert isinstance(state["decision"], SearchKnowledgeBase)
    # The retrieval step ran and fed the answer agent.
    assert state["kb_snippets"]
    assert any("kb-002" in snippet for snippet in state["kb_snippets"])


async def test_customer_facing_answers_always_require_approval() -> None:
    thread = "approval"
    with mock_openai(
        CLASSIFY,
        tool_call("final_result_AnswerDirectly", {"reasoning": "Simple question."}),
        tool_call(
            "final_result",
            # The model says no approval needed; the graph overrides it.
            {"content": "You can reset it from the sign-in page.", "requires_approval": False},
        ),
    ):
        state = await triage_graph.ainvoke({"context": ticket()}, config=config(thread))

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
        state = await triage_graph.ainvoke({"context": ticket()}, config=config(thread))

    # Two calls, not three: escalation terminates before synthesis.
    assert route.call_count == 2
    assert isinstance(state["decision"], Escalate)
    assert state["escalation_reason"] == "Needs a refund decision."
    assert state["answer"].requires_approval is False


async def test_classification_is_typed_not_parsed() -> None:
    thread = "classify"
    with mock_openai(
        CLASSIFY,
        tool_call("final_result_Escalate", {"reason": "x", "suggested_team": "billing"}),
    ):
        state = await triage_graph.ainvoke({"context": ticket()}, config=config(thread))

    classification = state["classification"]
    assert classification.category == "billing"
    assert classification.priority == "medium"
