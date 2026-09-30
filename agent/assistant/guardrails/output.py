"""Guards on what leaves for a customer.

This runs before the human approval gate, not instead of it: a machine check
that a person never has to think about, ahead of the judgement call only a
person can make.
"""

from assistant.guardrails.findings import Finding, Screening, Severity
from assistant.guardrails.patterns import SECRET_PATTERNS, UUID_PATTERN


def screen_reply(draft: str, *, ticket_id: str, instructions: str = "") -> Screening:
    findings: list[Finding] = []

    for kind, pattern in SECRET_PATTERNS:
        if pattern.search(draft):
            findings.append(
                Finding(
                    kind=kind,
                    severity=Severity.BLOCK,
                    detail="the draft contains something shaped like a credential",
                )
            )

    # Any id that is not this ticket's belongs to someone else's.
    foreign = {
        found
        for found in UUID_PATTERN.findall(draft)
        if found.lower() != ticket_id.lower()
    }
    if foreign:
        findings.append(
            Finding(
                kind="cross_ticket_reference",
                severity=Severity.BLOCK,
                detail=f"the draft names {len(foreign)} id(s) from another record",
            )
        )

    if instructions and _leaks_instructions(draft, instructions):
        findings.append(
            Finding(
                kind="prompt_leak",
                severity=Severity.BLOCK,
                detail="the draft repeats its own instructions back",
            )
        )

    return Screening(findings=findings)


def _leaks_instructions(draft: str, instructions: str, window: int = 12) -> bool:
    """True when a long run of words from the instructions appears verbatim.

    Word runs rather than substrings: a short phrase overlapping by chance is
    not a leak, and a model that has been talked into reciting its prompt
    reproduces it in long stretches.
    """
    draft_words = draft.lower().split()
    prompt_words = instructions.lower().split()
    if len(draft_words) < window or len(prompt_words) < window:
        return False

    runs = {
        " ".join(prompt_words[i : i + window])
        for i in range(len(prompt_words) - window + 1)
    }
    return any(
        " ".join(draft_words[i : i + window]) in runs
        for i in range(len(draft_words) - window + 1)
    )
