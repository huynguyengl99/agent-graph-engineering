"""Tracing has to answer 'what happened to this one ticket', not 'list calls'."""

import pytest
from assistant.agents import TicketContext
from assistant.graphs.triage_graph import build_triage_graph
from assistant.tracing import run_span, setup_tracing, trace_store
from langgraph.types import Command

from tests.helpers.openai_mock import mock_openai, tool_call


@pytest.fixture(autouse=True)
def clean_store():
    # Without this the file only passes when some other test has installed a
    # tracer provider first, and `pytest tests/test_tracing.py` records nothing.
    setup_tracing()
    trace_store.clear()
    yield
    trace_store.clear()


# Pydantic AI 2.x renamed this span from "agent run"; per-call usage now sits
# on the "chat <model>" span beneath it, and the aggregate on this one.
AGENT_SPAN = "invoke_agent"


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
        tool_call(
            "final_result", {"content": "Proration.", "requires_approval": False}
        ),
    ):
        await build_triage_graph().ainvoke(
            {"context": TicketContext(ticket_id=ticket_id, title="t", description="d")},
            config=config(ticket_id),
        )


async def test_trace_records_the_route_that_was_taken() -> None:
    await run("t-route")

    flat = names(trace_store.tree("t-route"))

    assert "node.classify" in flat
    assert "node.decide" in flat
    # The retrieval subgraph appears by its own node name.
    assert "node.search" in flat
    # The branch that was not taken leaves no span.
    assert "node.escalate" not in flat


async def test_model_calls_nest_under_the_node_that_made_them() -> None:
    """A flat list of completions is what the series complains about."""
    await run("t-nest")

    tree = trace_store.tree("t-nest")
    classify = next(n for n in tree if n["name"] == "node.classify")

    assert classify["children"], "the model call should be a child of the node"
    assert any(AGENT_SPAN in child["name"] for child in classify["children"])


async def test_model_call_spans_carry_usage() -> None:
    """Pydantic AI's own attributes survive nesting under the node span."""
    await run("t-attrs")

    tree = trace_store.tree("t-attrs")
    classify = next(n for n in tree if n["name"] == "node.classify")
    runs = [c for c in classify["children"] if AGENT_SPAN in c["name"]]

    assert runs, f"no {AGENT_SPAN!r} span under the node"
    attributes = runs[0]["attributes"]
    assert attributes["gen_ai.aggregated_usage.input_tokens"] > 0
    assert "final_result" in attributes


async def test_traces_are_isolated_per_ticket() -> None:
    await run("t-one")
    await run("t-two")

    assert trace_store.tree("t-one")
    assert trace_store.tree("t-two")
    assert trace_store.tree("t-unknown") == []


async def test_resuming_after_approval_extends_the_same_ticket_trace() -> None:
    await run("t-resume")
    before = len(names(trace_store.tree("t-resume")))

    await build_triage_graph().ainvoke(
        Command(resume={"approved": True}), config=config("t-resume")
    )

    flat = names(trace_store.tree("t-resume"))
    assert len(flat) > before
    # The irreversible step is visible in the same ticket's trace.
    assert "node.send_reply" in flat


async def test_a_run_is_one_trace_not_one_per_node() -> None:
    """Without a root span every node opens its own trace, and a backend shows
    one ticket as a dozen unrelated entries: the flat list of model calls this
    project exists to complain about."""
    trace_store.clear()
    with run_span("triage", "t-root"):
        await run("t-root")

    tree = trace_store.tree("t-root")

    assert len(tree) == 1, "a run should have exactly one root"
    assert tree[0]["name"] == "triage run"
    children = [child["name"] for child in tree[0]["children"]]
    assert "node.classify" in children
    assert "node.decide" in children
