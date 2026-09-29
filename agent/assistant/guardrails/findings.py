from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    # Recorded and shown, but the run continues.
    NOTICE = "notice"
    # Stops the draft before a human is asked to approve it.
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    severity: Severity
    detail: str

    def render(self) -> str:
        return f"{self.severity}:{self.kind}: {self.detail}"


def kind_of(rendered: str) -> str:
    """The kind back out of a rendered finding.

    State carries findings as strings, because that is what goes on the wire,
    but anything asserting on them needs the exact kind. Substring matching
    here is how an eval suite silently passes against a renamed guard.
    """
    _, _, rest = rendered.partition(":")
    kind, _, _ = rest.partition(":")
    return kind.strip()


@dataclass(frozen=True, slots=True)
class Screening:
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.severity is Severity.BLOCK for f in self.findings)

    def rendered(self) -> list[str]:
        return [f.render() for f in self.findings]
