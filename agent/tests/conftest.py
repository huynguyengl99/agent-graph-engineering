"""Force the real provider path under test.

Without a key the agents fall back to `ScriptedModel`, which never makes an
HTTP call, so the respx mocks would match nothing. Setting a dummy key here
(before anything imports `assistant.core.config`) keeps the tests exercising the
genuine OpenAI request/response pipeline, which is the point of mocking at the
HTTP layer rather than stubbing Pydantic AI.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-respx")


import pytest
from assistant.graphs.checkpointer import install_checkpointer, memory_checkpointer


@pytest.fixture(autouse=True)
def _checkpointer() -> None:
    """A fresh in-memory saver per test.

    The service uses Postgres; a unit test should not need a database to prove
    that a run resumes, and a saver shared between tests leaks threads.
    """
    install_checkpointer(memory_checkpointer())
