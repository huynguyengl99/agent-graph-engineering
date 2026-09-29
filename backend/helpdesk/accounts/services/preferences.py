"""A user's model choices, in the shape the agent's wire expects."""

from typing import Any

from channels.db import database_sync_to_async

from helpdesk.accounts.models import ModelPreference


def overrides_for(user_id: Any) -> dict[str, str]:
    """`{purpose: "provider:name"}` for the purposes this user has set.

    Absent purposes are simply missing, so the agent falls through to the
    deployment default rather than being handed a null to interpret.
    """
    if user_id is None:
        return {}
    return {
        preference.purpose: preference.model
        for preference in ModelPreference.objects.filter(user_id=user_id)
    }


model_overrides = database_sync_to_async(overrides_for)
