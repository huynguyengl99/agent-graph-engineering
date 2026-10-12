"""The three ways a run is asked for, as tasks a worker picks up.

Thin on purpose: the work still lives in `tickets/services/support.py`. Why the
worker is configured the way it is, is in `docs/running.md`.
"""

import asyncio
from typing import Any

from celery import shared_task


@shared_task(name="agent_runs.run_ticket")
def run_ticket(
    ticket_id: str,
    *,
    question: str = "",
    visibility: str,
    user_id: Any = None,
) -> None:
    from helpdesk.tickets.services.support import run

    asyncio.run(
        run(ticket_id, question=question, visibility=visibility, user_id=user_id)
    )


@shared_task(name="agent_runs.resume_approval")
def resume_approval(
    ticket_id: str,
    *,
    approved: bool,
    content: str | None = None,
    user_id: Any = None,
) -> None:
    from helpdesk.accounts.services.preferences import model_overrides
    from helpdesk.tickets.services.support import submit_approval

    async def go() -> None:
        await submit_approval(
            ticket_id=ticket_id,
            approved=approved,
            content=content,
            # Resolved here so the queued message stays plain JSON.
            models=await model_overrides(user_id),
        )

    asyncio.run(go())


@shared_task(name="agent_runs.resume_tool_decision")
def resume_tool_decision(
    ticket_id: str,
    *,
    approved: bool,
    arguments: dict[str, Any],
    publish: bool,
) -> None:
    from helpdesk.tickets.services.support import decide_tool

    asyncio.run(
        decide_tool(ticket_id, approved=approved, arguments=arguments, publish=publish)
    )
