"""What a scenario asserts, and how the golden set is loaded."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

Category = Literal["technical", "billing", "account", "general"]
Priority = Literal["low", "medium", "high", "urgent"]
Decision = Literal["Answer", "SearchKnowledgeBase", "RunTool", "Escalate"]


class AnswerExpect(BaseModel):
    """Judged, not asserted. `criteria` costs a model call; the other two are free."""

    criteria: str | None = None
    must_contain: list[str] = []
    must_not_contain: list[str] = []


class Expect(BaseModel):
    category: Category | None = None
    priority: Priority | None = None
    decision: Decision | None = None
    used_knowledge_base: bool | None = None
    blocked: bool | None = None
    # Guardrail finding kinds that must appear, as a subset.
    findings: list[str] = []
    answer: AnswerExpect | None = None

    # `tool` is what the planner named; `parked` is whether the run stopped
    # for a human.
    tool: str | None = None
    parked: bool | None = None


class Scenario(BaseModel):
    """A ticket for triage, or a rep's question for chat. One golden set, because
    a reader comparing runs wants one table."""

    name: str
    # Who the run is answering, which decides what it may choose.
    audience: Literal["customer", "team"] = "customer"
    # A customer's run is the ticket. The team's is a question, with the ticket
    # they have open as context if there is one.
    title: str = ""
    description: str = ""
    question: str = ""
    ticket: str = ""
    history: list[str] = []
    # Unset means "every scenario answering the team".
    provider_required: bool | None = None
    expect: Expect

    @property
    def needs_provider(self) -> bool:
        """Whether the expectation means anything without a real model. The
        scripted one answers by keyword, so some of these pass by accident."""
        if self.provider_required is not None:
            return self.provider_required
        return self.audience == "team"

    @model_validator(mode="after")
    def _needs_its_own_input(self) -> "Scenario":
        if self.audience == "customer" and not (self.title and self.description):
            raise ValueError(
                f"{self.name}: a customer scenario needs title and description"
            )
        if self.audience == "team" and not self.question:
            raise ValueError(f"{self.name}: a team scenario needs a question")
        return self


def load_scenarios(directory: Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or []
        scenarios.extend(Scenario(**item) for item in raw)

    names = [s.name for s in scenarios]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        # Results are keyed by name, so a duplicate silently overwrites a result.
        raise ValueError(f"duplicate scenario names: {sorted(duplicates)}")
    return scenarios
