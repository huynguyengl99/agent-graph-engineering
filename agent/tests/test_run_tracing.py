"""One question answered is one trace; the conversation is where it belongs."""

from typing import Any, cast

from assistant.agents import AgentConfig, Context, ModelConfig, ModelPurpose
from assistant.graphs.support_graph import SupportGraph
from assistant.tracing import setup_tracing, trace_store


def scripted() -> AgentConfig:
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


async def ask(question: str, context: Context) -> str:
    graph = SupportGraph(scripted()).compile()
    await graph.ainvoke(
        {"context": context, "question": question},
        config={"configurable": {"thread_id": context.thread_id}},
    )
    return context.trace_key


async def test_each_turn_is_its_own_trace() -> None:
    setup_tracing()
    trace_store.clear()

    first = await ask("hello", Context(thread_id="conv-42"))
    second = await ask("and again", Context(thread_id="conv-42"))

    assert first != second
    for run in (first, second):
        assert [root["name"] for root in trace_store.tree(run)] == ["support run"]


async def test_a_turn_says_which_conversation_it_was() -> None:
    setup_tracing()
    trace_store.clear()

    run = await ask("hello", Context(thread_id="conv-42"))

    assert trace_store.summary(run)["thread"] == "conv-42"
    assert "node.support_respond" in [
        child["name"] for child in trace_store.tree(run)[0]["children"]
    ]


async def test_the_conversation_is_its_turns_in_order() -> None:
    """One run tells you what the agent did; the thread tells you what it has
    been doing, which is the question somebody arrives with."""
    setup_tracing()
    trace_store.clear()

    # A fresh context per turn, because that is what a turn arrives with: the
    # run id is minted there, and it is what the span is filed under.
    first = await ask("hello", Context(thread_id="conv-42"))
    second = await ask("and again", Context(thread_id="conv-42"))
    other = await ask("different ticket", Context(thread_id="conv-43"))

    threads = trace_store.threads()

    assert threads["conv-42"] == [first, second]
    assert threads["conv-43"] == [other]


async def test_the_thread_endpoint_totals_the_conversation() -> None:
    """What a conversation cost is the sum of its turns, and nobody holding a
    thread id should have to fetch each run to add them up."""
    from assistant.main import thread_trace

    setup_tracing()
    trace_store.clear()

    await ask("hello", Context(thread_id="conv-44"))
    await ask("and again", Context(thread_id="conv-44"))

    body = await thread_trace("conv-44")
    runs = cast(list[dict[str, Any]], body["runs"])
    usage = cast(dict[str, Any], body["usage"])

    assert [run["thread"] for run in runs] == ["conv-44", "conv-44"]
    assert usage["calls"] == sum(run["calls"] for run in runs)
