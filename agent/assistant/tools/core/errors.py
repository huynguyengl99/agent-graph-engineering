"""Structured tool failures.

Tools signal failure by *raising* one of these, never by returning an error
string. `@wrap_tool` catches them and converts them into a `ToolOutput` carrying
a machine-readable `error_type`, so a failure never escapes into the graph and
the UI can react to the kind of failure rather than parsing prose.
"""


class ToolError(Exception):
    """Base for structured tool failures.

    `message` is LLM-facing and may carry technical detail. `user_message` is
    what a human sees; it defaults to the message when not given.
    """

    error_type = "tool_error"

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.user_message = user_message or message


class InvalidInputError(ToolError):
    """The caller passed something the tool cannot work with."""

    error_type = "invalid_input"


class NotFoundError(ToolError):
    error_type = "not_found"


class RateLimitedError(ToolError):
    error_type = "rate_limited"


class UpstreamServiceError(ToolError):
    """A dependency failed: 5xx, timeout, DNS, connection reset."""

    error_type = "upstream_error"


class ApprovalRequiredError(ToolError):
    """A tool marked `requires_approval` ran without an approved call.

    The interrupts work replaces this with a real pause-and-resume; until then
    it fails loudly rather than silently doing something irreversible.
    """

    error_type = "approval_required"
