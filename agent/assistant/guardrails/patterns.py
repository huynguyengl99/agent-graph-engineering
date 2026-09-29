"""Signatures the guards look for.

Deliberately narrow. A broad keyword list would flag ordinary support tickets
("how do I ignore the previous setting?") and train everyone to skip the
warnings, which is worse than not having them.
"""

import re

# Attempts to address the model rather than describe a problem.
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "override_instructions",
        re.compile(
            r"\b(ignore|disregard|forget)\b[^.\n]{0,30}\b"
            r"(previous|prior|above|earlier|all)\b[^.\n]{0,20}\b"
            r"(instruction|prompt|rule|direction)s?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role_reassignment",
        re.compile(
            r"\byou\s+are\s+now\b|\bact\s+as\s+(if\s+you\s+are\s+)?an?\b|"
            r"\bnew\s+(system\s+)?(prompt|instruction)s?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"\b(reveal|repeat|print|show|output)\b[^.\n]{0,30}\b"
            r"(system\s+prompt|instructions|rules)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fake_authority",
        re.compile(
            r"\[?\s*(system|admin|developer)\s*(message|note|override)\s*\]?\s*:",
            re.IGNORECASE,
        ),
    ),
)

# Credential shapes that must never reach a customer.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
