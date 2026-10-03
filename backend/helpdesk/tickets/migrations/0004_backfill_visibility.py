"""Existing rows predate the field and would all read as internal.

A requester's own comment and an agent reply were both visible to the customer
before this, so they are public; anything a staff member wrote stays internal,
which is the safer reading of an unlabelled note.
"""

from typing import Any

from django.db import migrations


def set_audience(apps: Any, schema_editor: Any) -> None:
    CommentEvent = apps.get_model("tickets", "CommentEvent")
    AIResponseEvent = apps.get_model("tickets", "AIResponseEvent")

    AIResponseEvent.objects.update(visibility="public")
    for comment in CommentEvent.objects.select_related("ticket"):
        if comment.created_by_id == comment.ticket.created_by_id:
            CommentEvent.objects.filter(pk=comment.pk).update(visibility="public")


class Migration(migrations.Migration):
    dependencies = [("tickets", "0003_ticketevent_visibility")]
    operations = [migrations.RunPython(set_audience, migrations.RunPython.noop)]
