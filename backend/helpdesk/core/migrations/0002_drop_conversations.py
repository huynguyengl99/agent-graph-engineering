"""The assistant's own tab is gone: a rep talks to it inside the ticket.

Deleting the app leaves its tables behind, because Django only drops what a
live app still declares. This drops them, guarded so a fresh database that
never had them migrates just as well.
"""

from django.db import migrations

TABLES = [
    "conversations_pendingapproval",
    "conversations_message",
    "conversations_conversation",
]


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=[f"DROP TABLE IF EXISTS {table} CASCADE" for table in TABLES],
            # Irreversible on purpose: the models are gone, so there is nothing
            # to recreate these from.
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
