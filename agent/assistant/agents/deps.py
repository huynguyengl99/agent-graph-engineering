from dataclasses import dataclass, field


@dataclass
class TicketContext:
    """Everything an agent may read about the ticket it is working on."""

    ticket_id: str
    title: str
    description: str
    history: list[str] = field(default_factory=list)

    @property
    def trace_key(self) -> str:
        return self.ticket_id

    def render(self) -> str:
        parts = [f"Title: {self.title}", f"Description: {self.description}"]
        if self.history:
            parts.append("Conversation so far:")
            parts.extend(f"- {line}" for line in self.history)
        return "\n".join(parts)


@dataclass
class ChatContext:
    """What the assistant knows about the rep's conversation.

    The ticket is optional: a conversation may be opened about one, or be a
    general question with no ticket at all.
    """

    conversation_id: str
    history: list[tuple[str, str]] = field(default_factory=list)
    ticket: TicketContext | None = None

    @property
    def trace_key(self) -> str:
        return self.conversation_id

    def render(self, question: str) -> str:
        parts: list[str] = []
        if self.ticket is not None:
            parts.append("The agent is looking at this ticket:")
            parts.append(self.ticket.render())
        if self.history:
            parts.append("Earlier in this conversation:")
            parts.extend(f"{role}: {content}" for role, content in self.history)
        parts.append(f"Their question: {question}")
        return "\n\n".join(parts)
