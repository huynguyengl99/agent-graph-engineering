"""The last look at agent prose before a customer sees it.

The agent screens the reply it writes, where it also knows its own prompt and
can tell when the model has been talked into reciting it. This is the other
half, and it runs here because here is where the audience is settled: a run's
lane can be chosen after the words exist, when a reviewer sends what the agent
writes next to the customer.

Narrow on purpose, and only ever applied to what the agent wrote. A customer
pasting something that looks like a key into their own ticket must still see
their own message.
"""

import re

# Credential shapes, as in the agent's own guard. Duplicated rather than
# shared: two services, and a rule this one must not be able to lose.
SECRETS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def withheld(text: str, *, ticket_id: str) -> list[str]:
    """What would stop this reaching the customer, empty when nothing does."""
    reasons = [kind for kind, pattern in SECRETS if pattern.search(text or "")]
    if any(found.lower() != ticket_id.lower() for found in UUID.findall(text or "")):
        reasons.append("cross_ticket_reference")
    return reasons
