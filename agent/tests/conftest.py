"""Force the real provider path under test.

Without a key the agents fall back to `ScriptedModel`, which never makes an
HTTP call, so the respx mocks would match nothing. Setting a dummy key here
(before anything imports `triage.core.config`) keeps the tests exercising the
genuine OpenAI request/response pipeline, which is the point of mocking at the
HTTP layer rather than stubbing Pydantic AI.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-respx")
