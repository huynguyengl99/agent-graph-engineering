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
    """Answer from what is in front of you, with no lookup.

    Not for anything resting on documented policy, limits, billing rules or a
    published procedure: knowing roughly how it works is not the same as having
    read it, and that is what the knowledge base is for.

    Not for a message you were told to deliver either. What you write here goes
    to whoever asked, so answering "send them a note" with the note leaves the
    customer still waiting for it.
    """

    reasoning: str = Field(description="Why no lookup or human is needed.")


class SearchKnowledgeBase(BaseModel):
    """The answer likely exists in the knowledge base."""

    query: str = Field(description="Search terms. Plain words, not a question.")
    reasoning: str = Field(description="What the agent expects to find.")


class RunTool(BaseModel):
    """They are asking for something done, not explained.

    Sending the customer a message counts: a tool delivers it, and prose about
    it does not.
    """

    reasoning: str = Field(description="What they want done.")


class Escalate(BaseModel):
    """A person has to take this one."""

    reason: str = Field(description="Why a human is required.")
    suggested_team: Category


# Adding a capability means a member here and a branch in the graph, not another
# `if` in a handler.
#
# Which members are offered is the audience's: answering the team there is
# nobody to escalate to. Both may reach for a tool - the gate parks it on a
# person either way, so a customer asking for a refund proposes one rather than
# being told to wait for someone who will propose the same thing.
# Enforced by the schema rather than asked for in the prompt, because a branch
# the model cannot name is one it cannot take.
# In the prompt's order of precedence, and `Answer` last on purpose: a union
# member is an output tool the model picks from a list, and the first plausible
# one in that list wins more often than it should.
CustomerDecision = SearchKnowledgeBase | RunTool | Escalate | Answer
TeamDecision = SearchKnowledgeBase | RunTool | Answer

Decision = SearchKnowledgeBase | RunTool | Escalate | Answer


class TicketAnswer(BaseModel):
    """The final customer-facing text."""

    content: str
