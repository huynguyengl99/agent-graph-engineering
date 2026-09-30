from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from assistant.agents import AgentConfig
from assistant.agents.deps import TicketContext
from assistant.graphs.base import BaseGraph
from assistant.graphs.states import DeliveryState
from assistant.guardrails import screen_reply
from assistant.outputs.triage import TicketAnswer
from assistant.prompts import ANSWER_PROMPT
from assistant.tools.reply import send_reply_to_customer
from assistant.tracing.nodes import Node


def _context_of(state: DeliveryState) -> TicketContext:
    """Re-validate after a checkpoint round-trip, which returns plain dicts."""
    context = state["context"]
    return context if isinstance(context, TicketContext) else TicketContext(**context)


def _answer_of(state: DeliveryState) -> TicketAnswer:
    """Re-validate after a checkpoint round-trip, which returns plain dicts."""
    answer = state["answer"]
    return (
        answer
        if isinstance(answer, TicketAnswer)
        else TicketAnswer.model_validate(answer)
    )


class DeliveryGraph(BaseGraph):
    """The only path to a customer, and the only irreversible step.

    A subgraph because it is the same pipeline wherever a draft comes from,
    and because keeping the gate in one place is the point: there is no second
    route to `send_reply`.
    """

    name = "delivery"

    async def screen(self, state: DeliveryState) -> DeliveryState:
        """The machine check that runs before the human one.

        A reviewer should never be asked to approve something a regex could
        have caught, and a blocked draft never reaches the approval gate.
        """
        result = screen_reply(
            _answer_of(state).content,
            ticket_id=_context_of(state).ticket_id,
            instructions=ANSWER_PROMPT,
        )
        findings = list(state.get("guardrail_findings") or []) + result.rendered()
        return {"guardrail_findings": findings, "reply_blocked": result.blocked}

    async def await_approval(self, state: DeliveryState) -> DeliveryState:
        """Park the run until a human accepts, edits, or rejects the draft."""
        answer = _answer_of(state)
        # Findings ride the interrupt rather than the state: a subgraph's
        # writes only merge into the parent when it returns, and the reviewer
        # needs them now.
        decision = interrupt(
            {
                "kind": "reply_approval",
                "draft": answer.content,
                "findings": list(state.get("guardrail_findings") or []),
            }
        )

        approved = (
            bool(decision.get("approved"))
            if isinstance(decision, dict)
            else bool(decision)
        )
        if not approved:
            return {
                "approval_granted": False,
                "answer": answer.model_copy(
                    update={"content": "The draft reply was rejected by a reviewer."}
                ),
            }

        edited = decision.get("content") if isinstance(decision, dict) else None
        return {
            "approval_granted": True,
            "answer": answer.model_copy(update={"content": edited or answer.content}),
        }

    async def send_reply(self, state: DeliveryState) -> DeliveryState:
        """The irreversible step, reachable only once approval is granted."""
        answer = _answer_of(state)
        output = await send_reply_to_customer(
            _context_of(state).ticket_id, answer.content, approved=True
        )
        if not output.ok:
            return {"tool_error": output.user_error or output.error or ""}
        return {"delivery_receipt": str(output.result)}

    def route_after_screen(self, state: DeliveryState) -> str:
        return END if state.get("reply_blocked") else "await_approval"

    def route_after_approval(self, state: DeliveryState) -> str:
        return "send_reply" if state.get("approval_granted") else END

    def nodes(self) -> dict[str, Node]:
        return {
            "screen": self.screen,
            "await_approval": self.await_approval,
            "send_reply": self.send_reply,
        }

    def build(self) -> StateGraph[DeliveryState, None, DeliveryState, DeliveryState]:
        graph: StateGraph[DeliveryState, None, DeliveryState, DeliveryState] = (
            StateGraph(DeliveryState)
        )
        self.add_nodes(graph)

        graph.add_edge(START, "screen")
        graph.add_conditional_edges(
            "screen",
            self.route_after_screen,
            {"await_approval": "await_approval", END: END},
        )
        graph.add_conditional_edges(
            "await_approval",
            self.route_after_approval,
            {"send_reply": "send_reply", END: END},
        )
        graph.add_edge("send_reply", END)

        return graph


def build_delivery_graph(
    config: AgentConfig | None = None,
) -> CompiledStateGraph[DeliveryState, None, DeliveryState, DeliveryState]:
    """Compiled, so the parent can add it as a node directly.

    No checkpointer of its own: a subgraph shares the parent's, which is what
    lets a resume reach the interrupt inside it.
    """
    return DeliveryGraph(config).build().compile()
