from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from assistant.agents import AgentConfig
from assistant.agents.chat import ChatAgent, ChatRouterAgent
from assistant.conversations import history
from assistant.events import Emitter, silent
from assistant.graphs.base import BaseGraph
from assistant.graphs.checkpointer import checkpointer
from assistant.graphs.knowledge_graph import build_knowledge_graph
from assistant.graphs.states import ChatState, Update
from assistant.graphs.tool_graph import build_tool_graph
from assistant.messages.chat import ChatCompleteMessage, ChatCompletePayload
from assistant.outputs.chat import ConsultKnowledgeBase, RunTool
from assistant.tracing.nodes import Node


class ChatGraph(BaseGraph):
    """The rep-facing surface. Nothing here reaches a customer.

    It routes before it answers, and reaches for the knowledge base rather
    than recalling policy. That retrieval is the same compiled subgraph triage
    uses, which is what a subgraph is for: two parents, one loop.
    """

    name = "chat"

    def __init__(
        self, config: AgentConfig | None = None, emitter: Emitter = silent
    ) -> None:
        super().__init__(config, emitter)
        self.router = ChatRouterAgent(self.config)
        self.chat = ChatAgent(self.config)

    async def route(self, state: ChatState) -> Update:
        context = state.context
        # The router needs what came before to resolve "refund it", and it reads
        # the same history the answer will: not a summary of it.
        decision = await self.router.run(
            context.render(state.question),
            context,
            await history().load(context.conversation_id),
        )

        update: Update = {"route": decision}
        if isinstance(decision, ConsultKnowledgeBase):
            # Hand the subgraph what to search for, as triage does.
            update["kb_query"] = decision.query
        elif isinstance(decision, RunTool):
            # The tool subgraph plans against the rep's own words.
            update["request"] = state.question
        return update

    async def answer(self, state: ChatState) -> Update:
        context = state.context
        prompt = context.render(state.question)

        snippets = state.kb_snippets
        if snippets:
            prompt += "\n\nKnowledge base articles:\n" + "\n\n".join(snippets)

        if result := state.result:
            prompt += f"\n\nA tool was run and returned:\n{result}"
            if state.corrected:
                # Without this the model reads a corrected amount as an error
                # and tells the rep to make up the difference, which is the
                # reviewer's decision being undone by the summary of it.
                prompt += (
                    "\nA reviewer changed the arguments before approving. That "
                    "is the decision, not a mistake: report what ran."
                )
        elif state.cancelled:
            prompt += "\n\nThe action was cancelled by a reviewer. Say so plainly."
        elif error := state.tool_error:
            prompt += f"\n\nA tool failed:\n{error}"

        # LangGraph's custom stream channel: deltas leave the node as they are
        # produced rather than being returned in one block at the end.
        writer = get_stream_writer()

        parts: list[str] = []
        async for delta in self.chat.stream(
            prompt, context, await history().load(context.conversation_id)
        ):
            parts.append(delta)
            writer({"delta": delta})

        answer = "".join(parts)
        # Everything this turn saw, the model's own reply included, so the next
        # turn reads its actions as the calls they were rather than as prose.
        await history().replace(context.conversation_id, self.chat.messages)
        await self.emit(
            ChatCompleteMessage(
                payload=ChatCompletePayload(
                    conversation_id=context.conversation_id, content=answer
                )
            )
        )
        return {"answer": answer}

    def route_after_routing(self, state: ChatState) -> str:
        match state.route:
            case ConsultKnowledgeBase():
                return "knowledge"
            case RunTool():
                return "tool"
            case _:
                return "answer"

    def nodes(self) -> dict[str, Node]:
        return {"route": self.route, "answer": self.answer}

    def build(self) -> StateGraph[ChatState, None, ChatState, ChatState]:
        graph: StateGraph[ChatState, None, ChatState, ChatState] = StateGraph(ChatState)
        self.add_nodes(graph)

        # The same subgraph triage composes. It shares only kb_query and
        # kb_snippets with this state, so nothing has to be mapped across.
        graph.add_node("knowledge", build_knowledge_graph(self.config))
        # Holds the approval gate, so an interrupt here surfaces through chat.
        graph.add_node("tool", build_tool_graph(self.config))

        graph.add_edge(START, "route")
        graph.add_conditional_edges(
            "route",
            self.route_after_routing,
            {"knowledge": "knowledge", "tool": "tool", "answer": "answer"},
        )
        graph.add_edge("knowledge", "answer")
        graph.add_edge("tool", "answer")
        graph.add_edge("answer", END)

        return graph


def build_chat_graph(
    config: AgentConfig | None = None,
    saver: BaseCheckpointSaver[str] | None = None,
    emitter: Emitter = silent,
) -> CompiledStateGraph[ChatState, None, ChatState, ChatState]:
    return ChatGraph(config, emitter).compile(saver or checkpointer())
