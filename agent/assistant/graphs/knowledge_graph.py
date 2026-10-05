"""Search the knowledge base, and search again if nothing came back."""

from typing import Literal

from langgraph.graph import START, StateGraph
from langgraph.types import Command

from assistant.agents import AgentConfig
from assistant.agents.deps import Context
from assistant.agents.refiner import RefinerAgent
from assistant.events import Emitter, silent
from assistant.graphs.base import BaseGraph
from assistant.graphs.limits import KB_MAX_ATTEMPTS
from assistant.graphs.states import KnowledgeState
from assistant.tools.core import Failed, Succeeded
from assistant.tools.knowledge_base import search_knowledge_base
from assistant.tracing.nodes import Node


def _searchable(context: Context) -> str:
    """Raw text to search when no query was asked for. Unfenced on purpose: the
    fence boilerplate matches articles."""
    return context.untrusted_text()


def _described(context: Context) -> str:
    """Fenced context for the refiner, which reads it as data."""
    return context.ticket.render() if context.ticket else ""


class KnowledgeGraph(BaseGraph):
    """Search, and if nothing comes back, search again with better terms.

    A subgraph because it loops: only `kb_snippets` crosses back out.
    """

    name = "knowledge"

    def __init__(
        self, config: AgentConfig | None = None, emitter: Emitter = silent
    ) -> None:
        super().__init__(config, emitter)
        self.refiner = RefinerAgent(self.config)

    # --- nodes, in the order a run meets them -------------------------------

    async def knowledge_search(
        self, state: KnowledgeState
    ) -> Command[Literal["knowledge_refine", "__end__"]]:
        """Search once; nothing found with attempts left means better terms."""
        query = state.kb_query or _searchable(state.context)
        attempts = state.kb_attempts + 1

        match await search_knowledge_base(query):
            case Succeeded(result=articles):
                snippets = [article.render() for article in articles]
            case Failed():
                # A failure reads as a miss; the loop already handles finding
                # nothing.
                snippets = []

        found = bool(snippets) or attempts >= KB_MAX_ATTEMPTS
        return Command(
            update={"kb_snippets": snippets, "kb_attempts": attempts},
            goto="__end__" if found else "knowledge_refine",
        )

    async def knowledge_refine(
        self, state: KnowledgeState
    ) -> Command[Literal["knowledge_search"]]:
        """Ask for broader terms. Only reached when the last search was empty."""
        refined = await self.run_aloud(
            "refine",
            self.refiner,
            f"{_described(state.context)}\n\nThese terms found nothing: "
            f"{state.kb_query or '(the ticket text)'}",
            state.context,
        )
        # A model that returns nothing usable must not restart the same search.
        return Command(update={"kb_query": refined.query}, goto="knowledge_search")

    # --- wiring -------------------------------------------------------------

    def nodes(self) -> dict[str, Node]:
        return {
            "knowledge_search": self.knowledge_search,
            "knowledge_refine": self.knowledge_refine,
        }

    def build(self) -> StateGraph[KnowledgeState, None, KnowledgeState, KnowledgeState]:
        graph: StateGraph[KnowledgeState, None, KnowledgeState, KnowledgeState] = (
            StateGraph(KnowledgeState)
        )
        self.add_nodes(graph)
        graph.add_edge(START, "knowledge_search")
        return graph
