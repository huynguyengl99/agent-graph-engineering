"""What a scenario asserts, and how the golden set is loaded."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

Category = Literal["technical", "billing", "account", "general"]
Priority = Literal["low", "medium", "high", "urgent"]
Decision = Literal["AnswerDirectly", "SearchKnowledgeBase", "Escalate", "DraftReply"]


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


class Scenario(BaseModel):
    name: str
    title: str
    description: str
    history: list[str] = []
    expect: Expect


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
