"""What the support agent chooses, and what it produces.

Two unions used to answer the same question for two audiences: "answer it",
"look it up", "do something", "hand it over". They are one union now, and the
audience decides which members the prompt offers.
"""

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["technical", "billing", "account", "general"]
Priority = Literal["low", "medium", "high", "urgent"]


class Classification(BaseModel):
    """How the ticket is filed. Drives SLA and queue, not routing."""

    category: Category
    priority: Priority
    reasoning: str = Field(description="One sentence justifying category and priority.")


class Answer(BaseModel):
    """Everything needed is already in the thread or the ticket."""

    reasoning: str = Field(description="Why no lookup or human is needed.")


class SearchKnowledgeBase(BaseModel):
    """The answer likely exists in the knowledge base."""

    query: str = Field(description="Search terms. Plain words, not a question.")
    reasoning: str = Field(description="What the agent expects to find.")


class RunTool(BaseModel):
    """They are asking for something done, not explained."""

    reasoning: str = Field(description="What they want done.")


class Escalate(BaseModel):
    """A person has to take this one."""

    reason: str = Field(description="Why a human is required.")
    suggested_team: Category


# Adding a capability means a member here and a branch in the graph, not another
# `if` in a handler.
#
# Which members are offered is the audience's: answering the customer there are
# no tools to reach for, and answering the team there is nobody to escalate to.
# Enforced by the schema rather than asked for in the prompt, because a branch
# the model cannot name is one it cannot take.
CustomerDecision = Answer | SearchKnowledgeBase | Escalate
TeamDecision = Answer | SearchKnowledgeBase | RunTool

Decision = Answer | SearchKnowledgeBase | RunTool | Escalate


class TicketAnswer(BaseModel):
    """The final customer-facing text."""

    content: str
    requires_approval: bool = Field(
        default=False,
        description="True when the text would be sent to the customer.",
    )
