"""Two graphs now, so spans can no longer be filed under "ticket"."""

from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
from assistant.agents.deps import ChatContext
from assistant.graphs.chat_graph import ChatGraph
from assistant.tracing import setup_tracing, trace_store


def scripted() -> AgentConfig:
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


async def test_a_chat_run_is_filed_under_its_conversation() -> None:
    setup_tracing()
    trace_store.clear()

    graph = ChatGraph(scripted()).build().compile()
    await graph.ainvoke(
        {"context": ChatContext(conversation_id="conv-42"), "question": "hello"}
    )

    assert "conv-42" in trace_store.runs()
    names = [span["name"] for span in trace_store.tree("conv-42")]
    assert "node.answer" in names
