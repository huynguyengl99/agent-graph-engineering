"""Watching a step think must not cost the run.

`run_stream` validates the model's output and cannot ask it to correct a
mistake; `run` can. A planner that named the right tool and mis-shaped the
object around it took the whole graph down with
`UnexpectedModelBehavior: retries are not supported in run_stream()`, and the
gate the reviewer was waiting at never appeared.
"""

from typing import Any

import pytest
from assistant.agents import AgentConfig, Context
from assistant.agents.planner import ToolPlannerAgent
from assistant.outputs.tools import ToolProposal
from pydantic_ai import UnexpectedModelBehavior


class Stream:
    """Raises where pydantic-ai does: on entering the streamed run."""

    async def __aenter__(self) -> Any:
        raise UnexpectedModelBehavior(
            "Output validation failed during streaming, and retries are not "
            "supported in `run_stream()`"
        )

    async def __aexit__(self, *_exc: Any) -> None: ...


@pytest.fixture
def planner() -> Any:
    return ToolPlannerAgent(AgentConfig.resolve())


async def test_a_failed_stream_asks_again_without_it(
    planner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = ToolProposal(tool="issue_refund", arguments={}, reasoning="because")

    async def run(*_args: Any, **_kwargs: Any) -> Any:
        return proposal

    async def noop(_delta: str) -> None: ...

    monkeypatch.setattr(planner.agent, "run_stream", lambda *a, **k: Stream())
    monkeypatch.setattr(planner, "run", run)

    assert await planner.reason_aloud("refund it", Context(), on_delta=noop) is proposal


async def test_a_stream_that_validates_nothing_does_too(
    planner: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reached quietly rather than by an exception, and just as fatal: the node
    returned None and the graph routed on it."""
    proposal = ToolProposal(tool="issue_refund", arguments={}, reasoning="because")

    class Empty:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: Any) -> None: ...

        async def stream_output(self, **_kwargs: Any) -> Any:
            return
            yield  # pragma: no cover - an empty async generator

        def all_messages(self) -> list[Any]:
            return []

    async def run(*_args: Any, **_kwargs: Any) -> Any:
        return proposal

    monkeypatch.setattr(planner.agent, "run_stream", lambda *a, **k: Empty())
    monkeypatch.setattr(planner, "run", run)

    async def noop(_delta: str) -> None: ...

    assert await planner.reason_aloud("refund it", Context(), on_delta=noop) is proposal
