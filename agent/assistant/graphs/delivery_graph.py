from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from assistant.agents import AgentConfig
from assistant.events import Emitter, silent
from assistant.graphs.base import BaseGraph
from assistant.graphs.feed import AnswerFeed
from assistant.graphs.states import DeliveryState, Update
from assistant.guardrails import screen_reply
from assistant.messages.support import (
    ReplyBlockedMessage,
    ReplyBlockedPayload,
    ReplySentMessage,
    ReplySentPayload,
)
from assistant.prompts import ANSWER_PROMPT
from assistant.tools.core import Failed
from assistant.tools.reply import send_reply_to_customer
from assistant.tracing.nodes import Node


class DeliveryGraph(AnswerFeed, BaseGraph):
    """The only path to a customer, and the only irreversible step.

    A subgraph because it is the same pipeline wherever a draft comes from,
    and because keeping the gate in one place is the point: there is no second
    route to `send_reply`.

    The screen runs on every draft; the gate does not. Which drafts stop for a
    person is `needs_a_person`.
    """

    name = "delivery"

    async def screen(self, state: DeliveryState) -> Update:
        """The machine check that runs before the human one.

        A reviewer should never be asked to approve something a regex could
        have caught, and a blocked draft never reaches the approval gate.
        """
        answer = state.answer
        ticket_id = state.context.ticket_id
        result = screen_reply(
            answer.content, ticket_id=ticket_id, instructions=ANSWER_PROMPT
        )
        findings = list(state.guardrail_findings) + result.rendered()
        if result.blocked:
            # Nothing follows: say so here, because no interrupt will.
            await self.emit(
                ReplyBlockedMessage(
                    payload=ReplyBlockedPayload(
                        ticket_id=ticket_id, draft=answer.content, findings=findings
                    )
                )
            )
        return {"guardrail_findings": findings, "reply_blocked": result.blocked}

    async def await_approval(self, state: DeliveryState) -> Update:
        """Park the run until a human accepts, edits, or rejects the draft."""
        answer = state.answer
        # Findings ride the interrupt rather than the state: a subgraph's
        # writes only merge into the parent when it returns, and the reviewer
        # needs them now.
        decision = interrupt(
            {
                "kind": "reply_approval",
                "draft": answer.content,
                "findings": list(state.guardrail_findings),
            }
        )

        approved = (
            bool(decision.get("approved"))
            if isinstance(decision, dict)
            else bool(decision)
        )
        if not approved:
            rejected = answer.model_copy(
                update={"content": "The draft reply was rejected by a reviewer."}
            )
            await self.answered(state.context.ticket_id, rejected)
            return {"approval_granted": False, "answer": rejected}

        edited = decision.get("content") if isinstance(decision, dict) else None
        return {
            "approval_granted": True,
            "answer": answer.model_copy(update={"content": edited or answer.content}),
        }

    async def send_reply(self, state: DeliveryState) -> Update:
        """The irreversible step, reachable only once approval is granted."""
        answer = state.answer
        ticket_id = state.context.ticket_id
        outcome = await send_reply_to_customer(ticket_id, answer.content, approved=True)
        if isinstance(outcome, Failed):
            return {"tool_error": outcome.user_error}

        receipt = str(outcome.result)
        await self.emit(
            ReplySentMessage(
                payload=ReplySentPayload(ticket_id=ticket_id, receipt=receipt)
            )
        )
        return {"delivery_receipt": receipt}

    def needs_a_person(self, state: DeliveryState) -> bool:
        """Whether a human reads this one before the customer does.

        Not every reply, which is what it used to be: a desk whose assistant
        can never finish a sentence has no assistant, and the customer sat in
        front of an empty thread while the answer waited on a screen they
        cannot see.

        What is left here is the machine saying it is unsure. Everything the
        output screen finds is severe enough to stop the draft outright, so by
        this point a finding is the *input* screen's: something in the ticket
        addressed the model directly. That is worth a person's eyes on the
        reply, and it is rare.
        """
        return state.answer.requires_approval or bool(state.guardrail_findings)

    def route_after_screen(self, state: DeliveryState) -> str:
        if state.reply_blocked:
            return END
        return "await_approval" if self.needs_a_person(state) else "send_reply"

    def route_after_approval(self, state: DeliveryState) -> str:
        return "send_reply" if state.approval_granted else END

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
            {"await_approval": "await_approval", "send_reply": "send_reply", END: END},
        )
        graph.add_conditional_edges(
            "await_approval",
            self.route_after_approval,
            {"send_reply": "send_reply", END: END},
        )
        graph.add_edge("send_reply", END)

        return graph


def build_delivery_graph(
    config: AgentConfig | None = None, emitter: Emitter = silent
) -> CompiledStateGraph[DeliveryState, None, DeliveryState, DeliveryState]:
    """Compiled, so the parent can add it as a node directly.

    No checkpointer of its own: a subgraph shares the parent's, which is what
    lets a resume reach the interrupt inside it.
    """
    return DeliveryGraph(config, emitter).build().compile()
