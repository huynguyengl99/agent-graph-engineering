"""One question answered is one trace; the conversation is where it belongs."""

from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
from assistant.agents.deps import ChatContext
from assistant.graphs.chat_graph import ChatGraph
from assistant.tracing import setup_tracing, trace_store


def scripted() -> AgentConfig:
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


async def ask(question: str, context: ChatContext) -> str:
    graph = ChatGraph(scripted()).compile()
    await graph.ainvoke(
        {"context": context, "question": question},
        config={"configurable": {"thread_id": context.conversation_id}},
    )
    return context.trace_key


async def test_each_turn_is_its_own_trace() -> None:
    setup_tracing()
    trace_store.clear()

    first = await ask("hello", ChatContext(conversation_id="conv-42"))
    second = await ask("and again", ChatContext(conversation_id="conv-42"))

    assert first != second
    for run in (first, second):
        assert [root["name"] for root in trace_store.tree(run)] == ["chat run"]


async def test_a_turn_says_which_conversation_it_was() -> None:
    setup_tracing()
    trace_store.clear()

    run = await ask("hello", ChatContext(conversation_id="conv-42"))

    assert trace_store.summary(run)["thread"] == "conv-42"
    assert "node.answer" in [
        child["name"] for child in trace_store.tree(run)[0]["children"]
    ]
