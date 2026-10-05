"""One question answered is one trace; the conversation is where it belongs."""

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
