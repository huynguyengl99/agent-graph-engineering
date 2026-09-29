import asyncio

import pytest
from assistant.tools.core import (
    InvalidInputError,
    UpstreamServiceError,
    metadata_for,
    render_tool_list,
    wrap_tool,
)
from assistant.tools.core import wrapper as wrapper_module


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch):
    """Each test gets its own registry so ids do not collide across tests."""
    monkeypatch.setattr(wrapper_module, "_REGISTRY", {})


async def test_success_is_wrapped_in_a_tool_output() -> None:
    @wrap_tool(description="Adds numbers.")
    async def add(a: int, b: int) -> int:
        return a + b

    output = await add(2, 3)
    assert output.ok
    assert output.result == 5
    assert output.error_type is None


async def test_raised_tool_errors_become_structured_output() -> None:
    @wrap_tool(description="Always fails.")
    async def failing() -> None:
        raise UpstreamServiceError(
            "billing API returned 503",
            user_message="Billing is temporarily unavailable.",
        )

    output = await failing()

    # The graph sees data, never an exception.
    assert not output.ok
    assert output.error_type == "upstream_error"
    assert output.error == "billing API returned 503"
    assert output.user_error == "Billing is temporarily unavailable."


async def test_user_error_defaults_to_the_llm_message() -> None:
    @wrap_tool(description="Fails plainly.")
    async def failing() -> None:
        raise InvalidInputError("bad input")

    output = await failing()
    assert output.user_error == "bad input"


async def test_unexpected_exceptions_are_not_swallowed() -> None:
    """Only ToolError is a handled failure. A bug should still surface."""

    @wrap_tool(description="Has a bug.")
    async def buggy() -> None:
        raise ZeroDivisionError("genuine bug")

    with pytest.raises(ZeroDivisionError):
        await buggy()


async def test_approval_gated_tools_refuse_to_run_unapproved() -> None:
    ran = False

    @wrap_tool(description="Sends something.", requires_approval=True)
    async def dangerous() -> str:
        nonlocal ran
        ran = True
        return "sent"

    output = await dangerous()

    assert output.error_type == "approval_required"
    assert ran is False, "the body must not execute without approval"

    approved = await dangerous(approved=True)
    assert approved.ok and ran is True


async def test_timeout_is_reported_not_raised() -> None:
    @wrap_tool(description="Too slow.", timeout=0.01)
    async def slow() -> None:
        await asyncio.sleep(1)

    output = await slow()
    assert output.error_type == "tool_error"
    assert "timed out" in (output.error or "")


async def test_duplicate_ids_are_rejected_at_import_time() -> None:
    @wrap_tool(description="First.")
    async def dupe() -> None: ...

    with pytest.raises(ValueError, match="already registered"):

        @wrap_tool(id="dupe", description="Second.")
        async def other() -> None: ...


async def test_planner_list_shows_description_and_hint() -> None:
    @wrap_tool(
        description="Looks things up.",
        tags=("knowledge",),
        planner_hint="Prefer this over guessing.",
    )
    async def lookup() -> None: ...

    @wrap_tool(description="Unrelated.", tags=("other",))
    async def unrelated() -> None: ...

    rendered = render_tool_list(tags=("knowledge",))
    assert rendered == "lookup: Looks things up. [Prefer this over guessing.]"
    assert metadata_for("lookup").requires_approval is False
