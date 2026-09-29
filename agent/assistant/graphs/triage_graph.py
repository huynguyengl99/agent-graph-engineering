from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from assistant.agents import AgentConfig, AnswerAgent, ClassifierAgent, DecisionAgent
from assistant.agents.deps import TicketContext
from assistant.graphs.base import BaseGraph
from assistant.graphs.checkpointer import checkpointer
from assistant.graphs.delivery_graph import build_delivery_graph
from assistant.graphs.knowledge_graph import build_knowledge_graph
from assistant.graphs.states import TriageState
from assistant.guardrails import screen_input
from assistant.outputs.triage import Escalate, SearchKnowledgeBase, TicketAnswer
from assistant.tracing.nodes import Node


def _context_of(state: TriageState) -> TicketContext:
    """Re-validate after a checkpoint round-trip, which returns plain dicts."""
    context = state["context"]
    return context if isinstance(context, TicketContext) else TicketContext(**context)


def _answer_of(state: TriageState) -> TicketAnswer:
    """Re-validate after a checkpoint round-trip, which returns plain dicts."""
    answer = state["answer"]
    return (
        answer
        if isinstance(answer, TicketAnswer)
        else TicketAnswer.model_validate(answer)
    )


class TriageGraph(BaseGraph):
    """Works one ticket: file it, decide what to do, then answer or escalate.

    Retrieval and delivery are subgraphs, so this graph only holds the
    decisions. Adding a capability means a branch here and a graph of its own,
    not another `if` in a handler.
    """

    name = "triage"

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(config)
        self.classifier = ClassifierAgent(self.config)
        self.decider = DecisionAgent(self.config)
        self.answerer = AnswerAgent(self.config)

    async def classify(self, state: TriageState) -> TriageState:
        context = _context_of(state)
        # Recorded, not refused: see assistant/guardrails/input.py.
        attempts = screen_input(context.untrusted_text())
        return {
            "classification": await self.classifier.run(context.render(), context),
            "guardrail_findings": attempts.rendered(),
        }

    async def decide(self, state: TriageState) -> TriageState:
        context = _context_of(state)
        decision = await self.decider.run(context.render(), context)

        update: TriageState = {"decision": decision}
        if isinstance(decision, SearchKnowledgeBase):
            # The handoff into the subgraph: it searches for what the decider
            # asked for, not for the whole ticket.
            update["kb_query"] = decision.query
        return update


    async def escalate(self, state: TriageState) -> TriageState:
        decision = state["decision"]
        assert isinstance(decision, Escalate)
        return {
            "escalation_reason": decision.reason,
            "answer": TicketAnswer(
                content=(
                    "Thanks for reaching out. I am handing this to a specialist on "
                    f"our {decision.suggested_team} team, who will follow up here."
                ),
                requires_approval=False,
            ),
        }

    async def respond(self, state: TriageState) -> TriageState:
        context = _context_of(state)
        prompt = context.render()

        snippets = state.get("kb_snippets") or []
        if snippets:
            prompt += "\n\nKnowledge base articles:\n" + "\n\n".join(snippets)

        answer = await self.answerer.run(prompt, context)
        # Anything the customer will read goes through a human first.
        return {"answer": answer.model_copy(update={"requires_approval": True})}






    def route_decision(self, state: TriageState) -> str:
        match state["decision"]:
            case SearchKnowledgeBase():
                return "knowledge"
            case Escalate():
                return "escalate"
            case _:
                return "respond"

    def nodes(self) -> dict[str, Node]:
        """Only this graph's own steps. Subgraphs are added whole, in build()."""
        return {
            "classify": self.classify,
            "decide": self.decide,
            "escalate": self.escalate,
            "respond": self.respond,
        }

    def build(self) -> StateGraph[TriageState, None, TriageState, TriageState]:
        graph: StateGraph[TriageState, None, TriageState, TriageState] = StateGraph(
            TriageState
        )
        self.add_nodes(graph)

        # Compiled subgraphs go in as nodes. They share the keys they need with
        # this state, so nothing has to be mapped across the boundary.
        graph.add_node("knowledge", build_knowledge_graph(self.config))
        graph.add_node("delivery", build_delivery_graph(self.config))

        graph.add_edge(START, "classify")
        graph.add_edge("classify", "decide")
        graph.add_conditional_edges(
            "decide",
            self.route_decision,
            {"knowledge": "knowledge", "escalate": "escalate", "respond": "respond"},
        )
        graph.add_edge("knowledge", "respond")
        graph.add_edge("escalate", END)
        graph.add_edge("respond", "delivery")
        graph.add_edge("delivery", END)

        return graph


def build_triage_graph(
    config: AgentConfig | None = None,
    saver: BaseCheckpointSaver[str] | None = None,
) -> CompiledStateGraph[TriageState, None, TriageState, TriageState]:
    """Compile a run's graph. Cheap, and the topology never varies; what varies
    is which model each purpose resolves to."""
    return TriageGraph(config).compile(saver or checkpointer())

