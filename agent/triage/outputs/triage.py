from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["technical", "billing", "account", "general"]
Priority = Literal["low", "medium", "high", "urgent"]


class Classification(BaseModel):
    """How the ticket is filed. Drives SLA and queue, not routing."""

    category: Category
    priority: Priority
    reasoning: str = Field(description="One sentence justifying category and priority.")


class AnswerDirectly(BaseModel):
    """The ticket can be answered from the agent's own knowledge."""

    reasoning: str = Field(description="Why no lookup or human is needed.")


class SearchKnowledgeBase(BaseModel):
    """The answer likely exists in the knowledge base."""

    query: str = Field(description="Search terms to look up.")
    reasoning: str = Field(description="What the agent expects to find.")


class Escalate(BaseModel):
    """A human has to take this one."""

    reason: str = Field(description="Why a human is required.")
    suggested_team: Category


class DraftReply(BaseModel):
    """Compose a customer-facing reply. Sending it requires human approval."""

    reasoning: str = Field(description="Why a reply is ready to be drafted.")


# The union the primary agent must choose from. Adding a capability means adding
# a member here and a routing branch in the graph, not another `if` in a handler.
TriageDecision = AnswerDirectly | SearchKnowledgeBase | Escalate | DraftReply


class TicketAnswer(BaseModel):
    """The final customer-facing text."""

    content: str
    requires_approval: bool = Field(
        default=False,
        description="True when the text would be sent to the customer.",
    )
