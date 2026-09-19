"""Tracing has to answer 'what happened to this one ticket', not 'list calls'."""

import pytest
from langgraph.types import Command
from triage.agents.triage_agents import TicketContext
from triage.graphs.triage_graph import triage_graph
from triage.tracing import trace_store

from tests.helpers.openai_mock import mock_openai, tool_call


@pytest.fixture(autouse=True)
def clean_store():
    trace_store.clear()
    yield
    trace_store.clear()


def config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def names(nodes: list[dict]) -> list[str]:
    """Flatten the tree, depth first, preserving order."""
    flat: list[str] = []
    for node in nodes:
        flat.append(node["name"])
        flat.extend(names(node["children"]))
    return flat


async def run(ticket_id: str) -> None:
    with mock_openai(
        tool_call(
            "final_result",
            {"category": "billing", "priority": "medium", "reasoning": "Invoice."},
        ),
        tool_call(
            "final_result_SearchKnowledgeBase",
            {"query": "invoice billing refund", "reasoning": "Documented."},
        ),
        tool_call("final_result", {"content": "Proration.", "requires_approval": False}),
    ):
        await triage_graph.ainvoke(
            {"context": TicketContext(ticket_id=ticket_id, title="t", description="d")},
            config=config(ticket_id),
        )


async def test_trace_records_the_route_that_was_taken() -> None:
    await run("t-route")

    flat = names(trace_store.tree("t-route"))

    assert "node.classify" in flat
    assert "node.decide" in flat
    assert "node.search_kb" in flat
    # The branch that was not taken leaves no span.
    assert "node.escalate" not in flat


async def test_model_calls_nest_under_the_node_that_made_them() -> None:
    """A flat list of completions is what the series complains about."""
    await run("t-nest")

    tree = trace_store.tree("t-nest")
    classify = next(n for n in tree if n["name"] == "node.classify")

    assert classify["children"], "the model call should be a child of the node"
    assert any("agent run" in child["name"] for child in classify["children"])


async def test_node_attributes_explain_the_decision() -> None:
    await run("t-attrs")

    tree = trace_store.tree("t-attrs")
    decide = next(n for n in tree if n["name"] == "node.decide")
    search = next(n for n in tree if n["name"] == "node.search_kb")

    assert decide["attributes"]["triage.decision"] == "SearchKnowledgeBase"
    assert search["attributes"]["triage.query"] == "invoice billing refund"


async def test_traces_are_isolated_per_ticket() -> None:
    await run("t-one")
    await run("t-two")

    assert trace_store.tree("t-one")
    assert trace_store.tree("t-two")
    assert trace_store.tree("t-unknown") == []


async def test_resuming_after_approval_extends_the_same_ticket_trace() -> None:
    await run("t-resume")
    before = len(names(trace_store.tree("t-resume")))

    await triage_graph.ainvoke(
        Command(resume={"approved": True}), config=config("t-resume")
    )

    flat = names(trace_store.tree("t-resume"))
    assert len(flat) > before
    # The irreversible step is visible in the same ticket's trace.
    assert "node.send_reply" in flat
