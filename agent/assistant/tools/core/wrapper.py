"""The `@wrap_tool` decorator and the registry it populates.

A tool is a plain async function plus metadata. The decorator does three things:
registers it so it can be discovered rather than imported by hand, attaches the
metadata the planner reads, and converts raised `ToolError`s into a `Failed`
so a failing tool never takes down the graph.
"""

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from assistant.tools.core.errors import ApprovalRequiredError, ToolError
from assistant.tools.core.metadata import Failed, Succeeded, ToolMetadata, ToolOutcome
from assistant.tools.core.schema import arguments_schema

WrappedTool = Callable[..., Awaitable[ToolOutcome]]

_REGISTRY: dict[str, WrappedTool] = {}


def wrap_tool(
    *,
    id: str | None = None,
    description: str,
    tags: tuple[str, ...] = (),
    requires_approval: bool = False,
    timeout: float = 10.0,
    planner_hint: str | None = None,
) -> Callable[[Callable[..., Awaitable[object]]], WrappedTool]:
    """Register an async function as a tool.

    Args:
        id: Tool id; defaults to the function name.
        description: Drives selection. Keep it about *when* to use the tool.
        tags: Free-form grouping, used for filtering.
        requires_approval: The action is irreversible and needs a human first.
        timeout: Seconds before the call is abandoned.
        planner_hint: Extra steering shown only in the tool list.
    """

    def decorator(func: Callable[..., Awaitable[object]]) -> WrappedTool:
        tool_id = id or func.__name__
        if tool_id in _REGISTRY:
            raise ValueError(
                f"Tool id {tool_id!r} is already registered. Ids must be unique; "
                f"pass id=... to disambiguate."
            )

        metadata = ToolMetadata(
            id=tool_id,
            description=description,
            tags=tags,
            requires_approval=requires_approval,
            timeout=timeout,
            planner_hint=planner_hint,
            arguments=arguments_schema(func),
        )

        @wraps(func)
        async def wrapper(
            *args: Any, approved: bool = False, **kwargs: Any
        ) -> ToolOutcome:
            if metadata.requires_approval and not approved:
                error = ApprovalRequiredError(
                    f"{tool_id} needs human approval before it can run.",
                    user_message="This action is waiting for your approval.",
                )
                return _failure(error)

            try:
                result = await asyncio.wait_for(
                    func(*args, **kwargs), timeout=metadata.timeout
                )
            except ToolError as error:
                return _failure(error)
            except TimeoutError:
                return _failure(
                    ToolError(
                        f"{tool_id} timed out after {metadata.timeout}s.",
                        user_message="That took too long. Please try again.",
                    )
                )
            return Succeeded(result=result)

        wrapper.metadata = metadata  # type: ignore[attr-defined]
        _REGISTRY[tool_id] = wrapper
        return wrapper

    return decorator


def _failure(error: ToolError) -> Failed:
    return Failed(
        kind=error.error_type,
        error=error.message,
        user_error=error.user_message,
    )


def get_tool(tool_id: str) -> WrappedTool:
    if tool_id not in _REGISTRY:
        raise KeyError(f"Unknown tool {tool_id!r}. Registered: {sorted(_REGISTRY)}")
    return _REGISTRY[tool_id]


def all_tools() -> dict[str, WrappedTool]:
    return dict(_REGISTRY)


def metadata_for(tool_id: str) -> ToolMetadata:
    return get_tool(tool_id).metadata  # type: ignore[attr-defined]


def render_tool_list(tags: tuple[str, ...] = ()) -> str:
    """The `[Available Tools]` block a planning prompt embeds."""
    lines = []
    for tool in _REGISTRY.values():
        meta: ToolMetadata = tool.metadata  # type: ignore[attr-defined]
        if tags and not set(tags) & set(meta.tags):
            continue
        lines.append(meta.render())
    return "\n".join(sorted(lines))
