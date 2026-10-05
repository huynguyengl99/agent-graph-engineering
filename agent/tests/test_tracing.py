"""Tracing has to answer 'what happened to this one ticket', not 'list calls'."""

import pytest
from assistant.graphs.checkpointer import checkpointer
from assistant.graphs.support_graph import SupportGraph
from assistant.tracing import setup_tracing, trace_store
from langgraph.types import Command

from tests.helpers.contexts import ticket_context
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


def find(nodes: list[dict], name: str) -> dict:
    """The named span wherever it sits in the tree."""
    for node in nodes:
        if node["name"] == name:
            return node
        if found := find(node["children"], name):
            return found
    return {}


def names(nodes: list[dict]) -> list[str]:
    """Flatten the tree, depth first, preserving order."""
    flat: list[str] = []
    for node in nodes:
        flat.append(node["name"])
        flat.extend(names(node["children"]))
    return flat


async def run(ticket_id: str) -> str:
    """Returns the key the run was filed under: one run, one trace."""
    context = ticket_context(ticket_id=ticket_id, title="t", description="d")
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
        await (
            SupportGraph()
            .compile(checkpointer())
            .ainvoke({"context": context}, config=config(ticket_id))
        )
    return context.trace_key


async def test_trace_records_the_route_that_was_taken() -> None:
    run_key = await run("t-route")

    flat = names(trace_store.tree(run_key))

    assert "node.support_classify" in flat
    assert "node.support_decide" in flat
    # The retrieval subgraph appears by its own node name.
    assert "node.knowledge_search" in flat
    # The branch that was not taken leaves no span.
    assert "node.support_escalate" not in flat


async def test_model_calls_nest_under_the_node_that_made_them() -> None:
    """A flat list of completions is what the series complains about."""
    run_key = await run("t-nest")

    classify = find(trace_store.tree(run_key), "node.support_classify")

    assert classify["children"], "the model call should be a child of the node"
    assert any(AGENT_SPAN in child["name"] for child in classify["children"])


async def test_model_call_spans_carry_usage() -> None:
    """Pydantic AI's own attributes survive nesting under the node span."""
    run_key = await run("t-attrs")

    classify = find(trace_store.tree(run_key), "node.support_classify")
    runs = [c for c in classify["children"] if AGENT_SPAN in c["name"]]

    assert runs, f"no {AGENT_SPAN!r} span under the node"
    attributes = runs[0]["attributes"]
    assert attributes["gen_ai.aggregated_usage.input_tokens"] > 0
    assert "final_result" in attributes


async def test_traces_are_isolated_per_run() -> None:
    one = await run("t-one")
    two = await run("t-two")

    assert one != two, "two runs on one ticket are two traces"
    assert trace_store.tree(one)
    assert trace_store.tree(two)
    assert trace_store.tree("t-unknown") == []


async def test_resuming_after_approval_extends_the_same_ticket_trace() -> None:
    run_key = await run("t-resume")
    before = len(names(trace_store.tree(run_key)))

    await (
        SupportGraph()
        .compile(checkpointer())
        .ainvoke(Command(resume={"approved": True}), config=config("t-resume"))
    )

    flat = names(trace_store.tree(run_key))
    assert len(flat) > before
    # The irreversible step is visible in the same ticket's trace.
    assert "node.delivery_send" in flat


async def test_a_run_is_one_trace_not_one_per_node() -> None:
    """Compiling a graph is what gives the run its root, so no caller can leave
    it out."""
    run_key = await run("t-root")

    tree = trace_store.tree(run_key)

    assert len(tree) == 1, "a run should have exactly one root"
    assert tree[0]["name"] == "support run"
    children = [child["name"] for child in tree[0]["children"]]
    assert "node.support_classify" in children
    assert "node.support_decide" in children


async def test_a_streamed_run_is_one_trace_too() -> None:
    """Nodes run as the stream is consumed, not when `astream` is called."""
    with mock_openai(
        tool_call(
            "final_result",
            {"category": "billing", "priority": "medium", "reasoning": "Invoice."},
        ),
        tool_call(
            "final_result_SearchKnowledgeBase",
            {"query": "invoice", "reasoning": "Documented."},
        ),
        tool_call(
            "final_result", {"content": "Proration.", "requires_approval": False}
        ),
    ):
        context = ticket_context(ticket_id="t-stream", title="t", description="d")
        async for _ in (
            SupportGraph()
            .compile(checkpointer())
            .astream(
                {"context": context},
                config=config("t-stream"),
                stream_mode="updates",
            )
        ):
            pass

    tree = trace_store.tree(context.trace_key)

    assert [root["name"] for root in tree] == ["support run"]
    assert "node.support_classify" in names(tree)
