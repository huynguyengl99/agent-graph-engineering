"""Reading and advancing a run's cursor, from async relay code."""

from channels.db import database_sync_to_async
from django.db import transaction

from helpdesk.core.models import AgentRunCursor


@database_sync_to_async
def last_handled(run_key: str) -> int:
    row = AgentRunCursor.objects.filter(run_key=run_key).values_list("seq", flat=True)
    return next(iter(row), 0)


def advance_sync(run_key: str, seq: int) -> None:
    """Move the cursor forward, never back.

    Synchronous so it can share a transaction with the write it records: advanced
    separately, a crash in between would replay an effect that already happened.
    """
    if not run_key or seq <= 0:
        return
    with transaction.atomic():
        cursor, _ = AgentRunCursor.objects.select_for_update().get_or_create(
            run_key=run_key
        )
        if seq > cursor.seq:
            cursor.seq = seq
            cursor.save(update_fields=["seq", "updated_at"])


advance = database_sync_to_async(advance_sync)
