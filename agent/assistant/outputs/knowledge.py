from pydantic import BaseModel, Field


class RefinedQuery(BaseModel):
    """A second attempt at searching, after the first found nothing."""

    query: str = Field(description="Plain search terms, broader than the last attempt.")
    reasoning: str = Field(description="Why these terms should do better.")
