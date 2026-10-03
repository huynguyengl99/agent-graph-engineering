from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from assistant.agents import AgentConfig
from assistant.agents.deps import Context
from assistant.agents.refiner import RefinerAgent
from assistant.events import Emitter, silent
from assistant.graphs.base import BaseGraph
from assistant.graphs.states import KnowledgeState, Update
from assistant.tools.core import Failed, Succeeded
from assistant.tools.knowledge_base import search_knowledge_base
from assistant.tracing.nodes import Node

# One retry. A second empty result means the article does not exist, and
# looping on a model's guesses is how you turn a miss into a bill.
MAX_ATTEMPTS = 2


def _searchable(context: Context) -> str:
    """Raw text to search when no query was asked for. Unfenced on purpose: the
    fence boilerplate matches articles."""
    return context.untrusted_text()


def _described(context: Context) -> str:
    """Fenced context for the refiner, which reads it as data."""
    return context.ticket.render() if context.ticket else ""


class KnowledgeGraph(BaseGraph):
    """Search, and if nothing comes back, search again with better terms.

    A subgraph rather than a node because it loops, and because the parent has
    no business knowing how many attempts it took: only `kb_snippets` crosses
    back out.
    """

    name = "knowledge"

    def __init__(
        self, config: AgentConfig | None = None, emitter: Emitter = silent
    ) -> None:
        super().__init__(config, emitter)
        self.refiner = RefinerAgent(self.config)

    async def search(self, state: KnowledgeState) -> Update:
        query = state.kb_query or _searchable(state.context)
        attempts = state.kb_attempts + 1

        match await search_knowledge_base(query):
            case Succeeded(result=articles):
                snippets = [article.render() for article in articles]
            case Failed():
                # A failure reads as a miss; the loop already handles finding
                # nothing.
                snippets = []

        return {"kb_snippets": snippets, "kb_attempts": attempts}

    async def refine(self, state: KnowledgeState) -> Update:
        """Ask for broader terms. Only reached when the last search was empty."""
        refined = await self.reason(
            "refine",
            self.refiner,
            f"{_described(state.context)}\n\nThese terms found nothing: "
            f"{state.kb_query or '(the ticket text)'}",
            state.context,
        )
        # A model that returns nothing usable must not restart the same search.
        return {"kb_query": refined.query}

    def route_after_search(self, state: KnowledgeState) -> str:
        if state.kb_snippets or state.kb_attempts >= MAX_ATTEMPTS:
            return END
        return "refine"

    def nodes(self) -> dict[str, Node]:
        return {"search": self.search, "refine": self.refine}

    def build(self) -> StateGraph[KnowledgeState, None, KnowledgeState, KnowledgeState]:
        graph: StateGraph[KnowledgeState, None, KnowledgeState, KnowledgeState] = (
            StateGraph(KnowledgeState)
        )
        self.add_nodes(graph)

        graph.add_edge(START, "search")
        graph.add_conditional_edges(
            "search", self.route_after_search, {"refine": "refine", END: END}
        )
        graph.add_edge("refine", "search")

        return graph


def build_knowledge_graph(
    config: AgentConfig | None = None,
    emitter: Emitter = silent,
) -> CompiledStateGraph[KnowledgeState, None, KnowledgeState, KnowledgeState]:
    """Compiled, so the parent can add it as a node directly. The emitter comes
    with it: a subgraph that explains itself needs somewhere to say it."""
    return KnowledgeGraph(config, emitter).build().compile()
