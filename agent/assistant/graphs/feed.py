from assistant.agents.config import AgentConfig, ModelPurpose
from assistant.events import Emitter
from assistant.messages.support import AnswerMessage, AnswerPayload
from assistant.outputs.support import TicketAnswer


class AnswerFeed:
    """Emitting the settled answer, shared because three places settle on one:
    `respond`, `escalate`, and delivery when a draft is rejected."""

    emit: Emitter
    config: AgentConfig

    @property
    def answer_model(self) -> str:
        """What actually wrote the reply, for whoever records it."""
        return self.config.models[ModelPurpose.ANSWER].slug

    async def answered(self, ticket_id: str, answer: TicketAnswer) -> None:
        await self.emit(
            AnswerMessage(
                payload=AnswerPayload(
                    ticket_id=ticket_id,
                    content=answer.content,
                    requires_approval=answer.requires_approval,
                    model=self.answer_model,
                )
            )
        )
