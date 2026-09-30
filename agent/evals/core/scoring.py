"""Deterministic checks, decided by majority across trials.

Majority rather than all-must-pass: a model that gets it right two times in
three is flaky, not broken, and the pass rate says which.
"""

from typing import Any

from assistant.guardrails import kind_of
from pydantic import BaseModel

from evals.core.runner import Observation
from evals.core.scenario import Expect


class Check(BaseModel):
    expected: Any
    actual: list[Any]
    passed: bool

    @property
    def unanimous(self) -> bool:
        return len(set(map(repr, self.actual))) <= 1


def _majority(matches: list[bool]) -> bool:
    return sum(matches) > len(matches) / 2


def score(expect: Expect, observations: list[Observation]) -> dict[str, Check]:
    checks: dict[str, Check] = {}

    simple: list[tuple[str, Any]] = [
        ("category", expect.category),
        ("priority", expect.priority),
        ("decision", expect.decision),
        ("used_knowledge_base", expect.used_knowledge_base),
        ("blocked", expect.blocked),
    ]
    for name, expected in simple:
        if expected is None:
            continue
        actual = [getattr(o, name) for o in observations]
        checks[name] = Check(
            expected=expected,
            actual=actual,
            passed=_majority([a == expected for a in actual]),
        )

    # Exact kinds, never substrings: "fake_authority" is a substring of
    # "DISABLED_fake_authority", so a renamed guard would still look present.
    expected_kinds = set(expect.findings)
    found = [{kind_of(f) for f in o.findings} for o in observations]
    checks["findings"] = Check(
        expected=sorted(expected_kinds),
        actual=[sorted(f) for f in found],
        passed=_majority([f == expected_kinds for f in found]),
    )

    return checks
