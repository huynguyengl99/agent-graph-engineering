from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolMetadata:
    """What the planner and the UI need to know about a tool.

    `description` and `planner_hint` drive tool *selection*: they are what the
    deciding model sees in the available-tools list. The docstring is the schema
    the *executing* model sees once a tool has already been picked, so
    "use this one, not that one" steering belongs in `planner_hint`.
    """

    id: str
    description: str
    tags: tuple[str, ...] = ()
    requires_approval: bool = False
    timeout: float = 10.0
    planner_hint: str | None = None

    # JSON Schema for the arguments, derived from the signature. The planner
    # fills it and the reviewer's form is generated from it, so no tool needs
    # a hand-written form and neither can drift from the function.
    arguments: dict[str, Any] = field(default_factory=dict)

    def signature(self) -> str:
        """`name(arg: type, optional?: type)`, from the derived schema.

        Worth spelling out: shown only an id and a description, a planner
        invents argument names - `customer_email` for `email`, a `currency` the
        tool does not take - and every one of those lands on a reviewer as a
        blank required field to fill in by hand.
        """
        properties: dict[str, Any] = self.arguments.get("properties", {})
        required = set(self.arguments.get("required", []))

        parts = []
        for name, schema in properties.items():
            kind = schema.get("type") or "any"
            parts.append(f"{name}: {kind}" if name in required else f"{name}?: {kind}")
        return f"{self.id}({', '.join(parts)})"

    def render(self) -> str:
        """One line, as shown to the deciding model."""
        line = f"{self.signature()}: {self.description}"
        return f"{line} [{self.planner_hint}]" if self.planner_hint else line


@dataclass(frozen=True)
class Succeeded:
    """What the tool returned."""

    result: Any


@dataclass(frozen=True)
class Failed:
    """Why it did not work.

    `kind` is what a caller branches on, so recovery never depends on matching
    error text. `error` is LLM-facing and may carry technical detail; `user_error`
    is what a person reads, and `ToolError` guarantees both are present.
    """

    kind: str
    error: str
    user_error: str


# Two types rather than one with four optionals, which let `result` and `error`
# both be set, or neither.
ToolOutcome = Succeeded | Failed
