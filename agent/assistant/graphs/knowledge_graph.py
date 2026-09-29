from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from assistant.agents import AgentConfig
from assistant.agents.deps import TicketContext
from assistant.agents.refiner import RefinerAgent
from assistant.graphs.base import BaseGraph
from assistant.graphs.states import KnowledgeState
from assistant.tools.knowledge_base import search_knowledge_base
from assistant.tracing.nodes import Node

# One retry. A second empty result means the article does not exist, and
# looping on a model's guesses is how you turn a miss into a bill.
MAX_ATTEMPTS = 2


def _context_of(state: KnowledgeState) -> TicketContext:
    """Re-validate after a checkpoint round-trip, which returns plain dicts."""
    context = state["context"]
    return context if isinstance(context, TicketContext) else TicketContext(**context)


class KnowledgeGraph(BaseGraph):
    """Search, and if nothing comes back, search again with better terms.

    A subgraph rather than a node because it loops, and because the parent has
    no business knowing how many attempts it took: only `kb_snippets` crosses
    back out.
    """

    name = "knowledge"

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(config)
        self.refiner = RefinerAgent(self.config)

    async def search(self, state: KnowledgeState) -> KnowledgeState:
        # The raw ticket text, not render(): that one is fenced, and the fence
        # boilerplate ("instructions", "customer", "data") matches articles.
        query = state.get("kb_query") or _context_of(state).untrusted_text()
        attempts = state.get("kb_attempts", 0) + 1

        output = await search_knowledge_base(query)
        if not output.ok:
            return {"kb_snippets": [], "kb_attempts": attempts}

        return {
            "kb_snippets": [article.render() for article in output.result],
            "kb_attempts": attempts,
        }

    async def refine(self, state: KnowledgeState) -> KnowledgeState:
        """Ask for broader terms. Only reached when the last search was empty."""
        context = _context_of(state)
        refined = await self.refiner.run(
            f"{context.render()}\n\nThese terms found nothing: "
            f"{state.get('kb_query') or '(the ticket text)'}",
            context,
        )
        # A model that returns nothing usable must not restart the same search.
        return {"kb_query": refined.query}

    def route_after_search(self, state: KnowledgeState) -> str:
        if state.get("kb_snippets"):
            return END
        if state.get("kb_attempts", 0) >= MAX_ATTEMPTS:
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
) -> CompiledStateGraph[KnowledgeState, None, KnowledgeState, KnowledgeState]:
    """Compiled, so the parent can add it as a node directly."""
    return KnowledgeGraph(config).build().compile()
