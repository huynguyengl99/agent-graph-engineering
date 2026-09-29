from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from assistant.agents import AgentConfig
from assistant.agents.chat import ChatAgent
from assistant.agents.deps import ChatContext
from assistant.graphs.base import BaseGraph
from assistant.graphs.checkpointer import checkpointer
from assistant.graphs.states import ChatState
from assistant.tracing.nodes import Node


def _context_of(state: ChatState) -> ChatContext:
    """Re-validate after a checkpoint round-trip, which returns plain dicts."""
    context = state["context"]
    return context if isinstance(context, ChatContext) else ChatContext(**context)


class ChatGraph(BaseGraph):
    """The rep-facing surface. Nothing here reaches a customer.

    One node today. It exists as a graph rather than a bare agent call because
    routing, planning, and retrieval land here next, and the streaming and
    checkpointing they need are already wired.
    """

    name = "chat"

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(config)
        self.chat = ChatAgent(self.config)

    async def answer(self, state: ChatState) -> ChatState:
        context = _context_of(state)
        # LangGraph's custom stream channel: deltas leave the node as they are
        # produced rather than being returned in one block at the end.
        writer = get_stream_writer()

        parts: list[str] = []
        async for delta in self.chat.stream(context.render(state["question"]), context):
            parts.append(delta)
            writer({"delta": delta})

        return {"answer": "".join(parts)}

    def nodes(self) -> dict[str, Node]:
        return {"answer": self.answer}

    def build(self) -> StateGraph[ChatState, None, ChatState, ChatState]:
        graph: StateGraph[ChatState, None, ChatState, ChatState] = StateGraph(ChatState)
        self.add_nodes(graph)
        graph.add_edge(START, "answer")
        graph.add_edge("answer", END)
        return graph


def build_chat_graph(
    config: AgentConfig | None = None,
    saver: BaseCheckpointSaver[str] | None = None,
) -> CompiledStateGraph[ChatState, None, ChatState, ChatState]:
    return ChatGraph(config).compile(saver or checkpointer())
