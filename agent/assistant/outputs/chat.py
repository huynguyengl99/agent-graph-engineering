from pydantic import BaseModel, Field


class AnswerFromContext(BaseModel):
    """Everything needed is already in the thread or the ticket."""

    reasoning: str = Field(description="Why no lookup is needed.")


class ConsultKnowledgeBase(BaseModel):
    """The help centre probably documents this."""

    query: str = Field(description="Search terms. Plain words, not a question.")
    reasoning: str = Field(description="What the assistant expects to find.")


class RunTool(BaseModel):
    """The rep is asking for something done, not explained."""

    reasoning: str = Field(description="What they want done.")


# What the rep's question needs before it can be answered. Adding a capability
# means a member here and a branch in the graph, not an `if` in a handler.
ChatRoute = AnswerFromContext | ConsultKnowledgeBase | RunTool
