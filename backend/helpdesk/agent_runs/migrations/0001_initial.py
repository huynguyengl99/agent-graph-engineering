"""The cursor moved here from `core`, table and all.

`core` created it, so this adopts the existing table rather than making a
second one: the state operation gives this app the model, the database
operation renames what is already there.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("core", "0003_move_agent_run_cursor")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="AgentRunCursor",
                    fields=[
                        (
                            "run_key",
                            models.CharField(
                                max_length=255, primary_key=True, serialize=False
                            ),
                        ),
                        ("seq", models.BigIntegerField(default=0)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        "verbose_name": "agent run cursor",
                        "verbose_name_plural": "agent run cursors",
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE core_agentruncursor RENAME TO agent_runs_agentruncursor",
                    "ALTER TABLE agent_runs_agentruncursor RENAME TO core_agentruncursor",
                ),
            ],
        ),
    ]
