from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

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

    async def delivery_screen(
        self, state: DeliveryState
    ) -> Command[Literal["delivery_approval", "delivery_send", "__end__"]]:
        """The machine check before the human one: a blocked draft never
        reaches the gate."""
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
            return Command(
                update={"guardrail_findings": findings, "reply_blocked": True},
                goto="__end__",
            )

        update = {"guardrail_findings": findings, "reply_blocked": False}
        waiting = self.needs_a_person(
            state.model_copy(update={"guardrail_findings": findings})
        )
        return Command(
            update=update, goto="delivery_approval" if waiting else "delivery_send"
        )

    async def delivery_approval(
        self, state: DeliveryState
    ) -> Command[Literal["delivery_send", "__end__"]]:
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
            return Command(
                update={"approval_granted": False, "answer": rejected},
                goto="__end__",
            )

        edited = decision.get("content") if isinstance(decision, dict) else None
        return Command(
            update={
                "approval_granted": True,
                "answer": answer.model_copy(
                    update={"content": edited or answer.content}
                ),
            },
            goto="delivery_send",
        )

    async def delivery_send(self, state: DeliveryState) -> Update:
        """The irreversible step."""
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
        """Whether a person reads this before the customer does.

        Output findings all block outright, so a finding surviving to here is
        the input screen's: something in the ticket addressed the model. A
        handover has already sent for a person, so it does not wait for one.
        """
        if state.escalation_reason:
            return False
        return state.answer.requires_approval or bool(state.guardrail_findings)

    # --- wiring -------------------------------------------------------------

    def nodes(self) -> dict[str, Node]:
        return {
            "delivery_screen": self.delivery_screen,
            "delivery_approval": self.delivery_approval,
            "delivery_send": self.delivery_send,
        }

    def build(self) -> StateGraph[DeliveryState, None, DeliveryState, DeliveryState]:
        graph: StateGraph[DeliveryState, None, DeliveryState, DeliveryState] = (
            StateGraph(DeliveryState)
        )
        self.add_nodes(graph)

        graph.add_edge(START, "delivery_screen")
        graph.add_edge("delivery_send", END)

        return graph
