"""`core` is the generic half again: talking to the agent is its own app.

State only. `agent_runs.0001_initial` renames the table it leaves behind.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0002_drop_conversations")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="AgentRunCursor")],
            database_operations=[],
        ),
    ]
