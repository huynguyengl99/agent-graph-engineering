from assistant.events import Emitter
from assistant.messages.triage import AnswerMessage, AnswerPayload
from assistant.outputs.triage import TicketAnswer


class AnswerFeed:
    """Emitting the settled answer, shared because two graphs settle on one:
    triage's `respond` and `escalate`, and delivery when a draft is rejected."""

    emit: Emitter

    async def answered(self, ticket_id: str, answer: TicketAnswer) -> None:
        await self.emit(
            AnswerMessage(
                payload=AnswerPayload(
                    ticket_id=ticket_id,
                    content=answer.content,
                    requires_approval=answer.requires_approval,
                )
            )
        )
