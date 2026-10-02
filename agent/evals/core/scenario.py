"""What a scenario asserts, and how the golden set is loaded."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

Category = Literal["technical", "billing", "account", "general"]
Priority = Literal["low", "medium", "high", "urgent"]
Decision = Literal["AnswerDirectly", "SearchKnowledgeBase", "Escalate", "DraftReply"]
Route = Literal["AnswerFromContext", "ConsultKnowledgeBase", "RunTool"]


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

    # Chat scenarios. `route` is the rep-facing router's choice; `tool` is what
    # the planner named; `parked` is whether the run stopped for a human.
    route: Route | None = None
    tool: str | None = None
    parked: bool | None = None


class Scenario(BaseModel):
    """A ticket for triage, or a rep's question for chat.

    One golden set rather than two: the two graphs fail in the same ways and a
    reader comparing runs wants one table.
    """

    name: str
    kind: Literal["triage", "chat"] = "triage"
    # Triage: the ticket. Chat: unset, and `question` carries the rep's words.
    title: str = ""
    description: str = ""
    question: str = ""
    # Chat only: the ticket the rep has open, if any.
    ticket: str = ""
    history: list[str] = []
    expect: Expect

    @model_validator(mode="after")
    def _needs_its_own_input(self) -> "Scenario":
        if self.kind == "triage" and not (self.title and self.description):
            raise ValueError(
                f"{self.name}: a triage scenario needs title and description"
            )
        if self.kind == "chat" and not self.question:
            raise ValueError(f"{self.name}: a chat scenario needs a question")
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
