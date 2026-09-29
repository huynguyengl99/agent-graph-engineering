from typing import Any

import structlog
from chanx.core.decorators import channel, ws_handler
from chanx.fast_channels.websocket import AsyncJsonWebsocketConsumer
from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from assistant.agents import TicketContext
from assistant.agents.config import AgentConfig
from assistant.core.layers import LAYER_ALIAS
from assistant.graphs.states import TriageState
from assistant.graphs.triage_graph import build_triage_graph
from assistant.outputs.triage import TicketAnswer
from assistant.ws.messages import (
    AnswerMessage,
    AnswerPayload,
    ApprovalDecisionMessage,
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    ClassifiedMessage,
    ClassifiedPayload,
    DecidedMessage,
    DecidedPayload,
    ReplyBlockedMessage,
    ReplyBlockedPayload,
    ReplySentMessage,
    ReplySentPayload,
    TriageErrorMessage,
    TriageErrorPayload,
    TriageRequestMessage,
)

logger = structlog.get_logger(__name__)


def _slugs(overrides: Any) -> dict[str, str | None] | None:
    """A user's model choices as `{purpose: slug}`, or None when unset."""
    return overrides.model_dump() if overrides is not None else None


@channel(
    name="triage",
    description="Runs the ticket triage graph and streams its decisions back",
    tags=["agent", "triage"],
)
class TriageConsumer(AsyncJsonWebsocketConsumer):
    """The backend's single connection into the agent service."""

    channel_layer_alias = LAYER_ALIAS

    @ws_handler
    async def handle_ping(self, _message: PingMessage) -> PongMessage:
        return PongMessage()

    @ws_handler(
        summary="Triage a ticket",
        description=(
            "Runs the triage graph. Emits the classification and the routing "
            "decision as they happen, then the proposed answer."
        ),
        output_type=(
            ClassifiedMessage
            | DecidedMessage
            | AnswerMessage
            | ApprovalRequiredMessage
            | ReplySentMessage
            | ReplyBlockedMessage
            | TriageErrorMessage
        ),
    )
    async def handle_triage_request(self, message: TriageRequestMessage) -> None:
        payload = message.payload
        context = TicketContext(
            ticket_id=payload.ticket_id,
            title=payload.title,
            description=payload.description,
            history=payload.history,
        )

        try:
            await self._run_graph(
                context, AgentConfig.from_slugs(_slugs(payload.models))
            )
        except Exception:
            logger.exception("assistant.run_failed", ticket_id=payload.ticket_id)
            await self._fail(payload.ticket_id)

    @ws_handler(
        summary="Approve or reject a drafted reply",
        description="Resumes a run paused at the approval interrupt.",
        output_type=ReplySentMessage | AnswerMessage | TriageErrorMessage,
    )
    async def handle_approval_decision(self, message: ApprovalDecisionMessage) -> None:
        payload = message.payload
        try:
            await self._drive(
                payload.ticket_id,
                Command(
                    resume={
                        "approved": payload.approved,
                        "content": payload.content,
                    }
                ),
                AgentConfig.from_slugs(_slugs(payload.models)),
            )
        except Exception:
            logger.exception("assistant.resume_failed", ticket_id=payload.ticket_id)
            await self._fail(payload.ticket_id)

    async def _fail(self, ticket_id: str) -> None:
        await self.send_message(
            TriageErrorMessage(
                payload=TriageErrorPayload(
                    ticket_id=ticket_id,
                    message="The triage agent could not complete this ticket.",
                )
            )
        )

    async def _run_graph(
        self, context: TicketContext, agent_config: AgentConfig | None = None
    ) -> None:
        initial: TriageState = {"context": context}
        await self._drive(context.ticket_id, initial, agent_config)

    def _findings(self, update: object) -> list[str]:
        if isinstance(update, dict):
            return [str(f) for f in update.get("guardrail_findings") or []]
        return []

    async def _drive(
        self,
        ticket_id: str,
        payload: TriageState | Command[Any],
        agent_config: AgentConfig | None = None,
    ) -> None:
        """Stream one graph run, whether it is a fresh start or a resume.

        The thread id is the ticket, so a resume arriving on a different socket
        still finds the paused run.
        """
        config: RunnableConfig = {"configurable": {"thread_id": ticket_id}}

        # Built per run: the topology is fixed, but which model fills each
        # purpose comes from the requesting user.
        graph = build_triage_graph(agent_config or AgentConfig.resolve())

        # `stream_mode="updates"` yields one {node_name: update} dict per step,
        # not a (name, update) pair.
        # StateT is invariant in the astream signature, so a declared
        # `TriageState | Command` argument cannot satisfy it even though that is
        # exactly what the graph accepts.
        findings: list[str] = []
        async for step in graph.astream(
            payload,  # type: ignore[arg-type]
            config=config,
            stream_mode="updates",
        ):
            for node_name, update in step.items():
                if node_name == "__interrupt__":
                    await self._emit_interrupt(ticket_id, update, findings)
                    continue
                findings = self._findings(update) or findings
                if node_name == "screen":
                    await self._emit_screen(ticket_id, update, findings)
                await self._emit(ticket_id, node_name, update)

    async def _emit_screen(
        self, ticket_id: str, update: object, findings: list[str]
    ) -> None:
        """A blocked draft ends the run here, so say so: no interrupt follows."""
        if not isinstance(update, dict) or not update.get("reply_blocked"):
            return
        await self.send_message(
            ReplyBlockedMessage(
                payload=ReplyBlockedPayload(
                    ticket_id=ticket_id,
                    draft="",
                    findings=findings,
                )
            )
        )

    async def _emit_interrupt(
        self, ticket_id: str, update: object, findings: list[str]
    ) -> None:
        interrupts = update if isinstance(update, (list, tuple)) else [update]
        for item in interrupts:
            value = getattr(item, "value", item)
            if isinstance(value, dict) and value.get("kind") == "reply_approval":
                await self.send_message(
                    ApprovalRequiredMessage(
                        payload=ApprovalRequiredPayload(
                            ticket_id=ticket_id,
                            draft=str(value.get("draft", "")),
                            findings=[str(f) for f in value.get("findings") or []]
                            or findings,
                        )
                    )
                )

    async def _emit(self, ticket_id: str, node_name: str, update: object) -> None:
        if not isinstance(update, dict):
            return

        if (classification := update.get("classification")) is not None:
            await self.send_message(
                ClassifiedMessage(
                    payload=ClassifiedPayload(
                        ticket_id=ticket_id,
                        category=classification.category,
                        priority=classification.priority,
                        reasoning=classification.reasoning,
                    )
                )
            )

        if (decision := update.get("decision")) is not None:
            await self.send_message(
                DecidedMessage(
                    payload=DecidedPayload(
                        ticket_id=ticket_id,
                        decision=type(decision).__name__,
                        # The decision union spells its justification either
                        # `reasoning` or `reason` depending on the member.
                        reasoning=str(
                            getattr(decision, "reasoning", None)
                            or getattr(decision, "reason", "")
                        ),
                    )
                )
            )

        if (receipt := update.get("delivery_receipt")) is not None:
            await self.send_message(
                ReplySentMessage(
                    payload=ReplySentPayload(ticket_id=ticket_id, receipt=str(receipt))
                )
            )

        if (answer := update.get("answer")) is not None:
            # Resumed runs reload state through the serializer, which can hand
            # the model back as a plain dict.
            answer = (
                answer
                if isinstance(answer, TicketAnswer)
                else TicketAnswer.model_validate(answer)
            )
            await self.send_message(
                AnswerMessage(
                    payload=AnswerPayload(
                        ticket_id=ticket_id,
                        content=answer.content,
                        requires_approval=answer.requires_approval,
                    )
                )
            )
