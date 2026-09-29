from dataclasses import dataclass, field


@dataclass
class TicketContext:
    """Everything an agent may read about the ticket it is working on."""

    ticket_id: str
    title: str
    description: str
    history: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts = [f"Title: {self.title}", f"Description: {self.description}"]
        if self.history:
            parts.append("Conversation so far:")
            parts.extend(f"- {line}" for line in self.history)
        return "\n".join(parts)
