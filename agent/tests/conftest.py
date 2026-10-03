"""Force the real provider path under test.

Without a key the agents fall back to `ScriptedModel`, which never makes an
HTTP call, so the respx mocks would match nothing. Setting a dummy key here
(before anything imports `assistant.core.config`) keeps the tests exercising the
genuine OpenAI request/response pipeline, which is the point of mocking at the
HTTP layer rather than stubbing Pydantic AI.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-respx")
# A test that calls `setup_tracing` would otherwise write its spans into the
# repo's trace directory, and the console would list `t-route` as a run.
os.environ["ASSISTANT_TRACE_DIR"] = ""


import pytest
from assistant.conversations import MemoryHistoryStore, install_history
from assistant.core.layers import LAYER_ALIAS
from assistant.graphs.checkpointer import install_checkpointer, memory_checkpointer
from assistant.runs import MemoryEventStore, install_run_events
from assistant.tools.core.ledger import MemoryLedger, install_ledger
from assistant.tracing import trace_store
from fast_channels.layers import InMemoryChannelLayer, register_channel_layer


@pytest.fixture(autouse=True)
def _per_test_state() -> None:
    """Fresh stores and a layer of this process's own, per test.

    The service uses Postgres and Redis; a unit test should not need either to
    prove that a run resumes. Each of these is a process-wide singleton, so one
    shared between tests leaks: a conversation's model history carried a previous
    test's tool call into the next one's prompt, which read as the graph leaking
    state when it was the fixture.
    """
    install_checkpointer(memory_checkpointer())
    install_ledger(MemoryLedger())
    install_run_events(MemoryEventStore())
    install_history(MemoryHistoryStore())
    register_channel_layer(LAYER_ALIAS, InMemoryChannelLayer())
    # These tests are about the in-memory ring; the file store has its own test
    # with its own directory.
    trace_store.use_files(None)
    trace_store.clear()
