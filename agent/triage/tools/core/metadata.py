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

    def render(self) -> str:
        """One line, as shown to the deciding model."""
        line = f"{self.id}: {self.description}"
        return f"{line} [{self.planner_hint}]" if self.planner_hint else line


@dataclass
class ToolOutput:
    """A tool result, successful or not.

    `error` is LLM-facing; `user_error` is UI-facing. `error_type` is what the
    caller branches on, so recovery never depends on matching error text.
    """

    result: Any = None
    error: str | None = None
    user_error: str | None = None
    error_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error_type is None
