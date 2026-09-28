# Agent Graph Engineering - Agent Instructions

> Instructions for any coding agent working in this monorepo. Each project has its own `AGENTS.md` with detailed patterns and conventions.

## What this repo is

Companion repo for the **Agent Graph Engineering** blog series. The posts live in `~/Code/huynguyengl99/my-blog` under `src/content/posts/agent-graph-engineering/`. The demo app is a support ticket triage assistant built on LangGraph + Pydantic AI + chanx.

Because the repo is read alongside the posts, two rules override normal defaults:

1. **Every post gets a git tag** (`part-1-stack`, `part-2-agent`, ...). Never rewrite history behind a published tag.
2. **Code is didactic.** Prefer the clear version over the clever one. If a production system would do something more complex, that tradeoff belongs in the post, not in a code comment.

### Writing style for README and public docs

Public prose here follows the author's blog style:

- No em-dashes. Rephrase, or use a short hyphen if a dash is really needed.
- No manufactured engagement hooks ("What's your take?").
- Never add `Co-Authored-By` trailers or any AI attribution to commit messages.

### Known state (2026-09-19)

Inherited from an earlier schema-first reference project whose WebSocket layer had never run. Both sides have been rewritten against chanx 2.11.

**Working end to end:**

- Django backend: models, polymorphic `TicketEvent`, serializers, views, migrations, admin. `manage.py check` clean, `ruff` clean, 9 tests pass.
- Ticket WebSocket consumer on current chanx, routing via `chanx.channels.routing`, AsyncAPI at `/api/asyncapi/docs/` and `/api/asyncapi/schema/`.
- Agent service: FastAPI + LangGraph triage graph + Pydantic AI typed outputs, tool registry, approval interrupt. `ruff` clean, 31 tests pass. AsyncAPI at `/asyncapi.json`, rendered graph at `/graph.mermaid`.
- Schema-first codegen: `pnpm gen:all` produces Zodios clients, TS types, and WebSocket types from the running backend.

- Frontend: ticket list, event log, live progress, approval panel. `pnpm typecheck`, `pnpm lint`, `pnpm build` all clean.
- The full loop verified live across three processes: comment, classify, decide, park at approval, approve or reject, send, persist.

**Still not done:**

- Never run against a real provider. Verified end to end with `ScriptedModel`; the OpenAI path is covered only by respx mocks.
- Backend `mypy .` still reports 23 annotation gaps in inherited code.
- No automated browser test. The hook is covered by unit tests against a fake
  socket, and the full stack by a scripted WebSocket client, but nothing drives
  a real browser.
- Checkpointing is `InMemorySaver`, so a run parked at approval is lost if the agent restarts. Swapping in a Postgres saver is the only change needed.
- No evals yet.

### Tools

Tools live in `triage/tools/`, with the infrastructure in `triage/tools/core/`.
Add one with `@wrap_tool`:

```python
@wrap_tool(
    description="Look up a documented answer.",   # drives selection
    tags=("knowledge", "read-only"),
    requires_approval=False,                       # True for irreversible actions
    planner_hint="Prefer this over guessing.",     # steering, selection-time only
)
async def search_knowledge_base(query: str) -> list[Article]:
    """Docstring is the schema the *executing* model sees."""
```

Rules worth keeping:

- **Raise, never return an error string.** Raise a `ToolError` subclass; the
  wrapper converts it to a `ToolOutput` with a machine-readable `error_type`.
  Callers branch on `error_type`, never on error text.
- **`description` and `planner_hint` drive selection; the docstring does not.**
  The tool list the deciding model sees renders only `id: description [hint]`.
  Putting "use this, not that" in the docstring cannot prevent a wrong pick.
- **Non-`ToolError` exceptions propagate.** A `ZeroDivisionError` is a bug, not
  a handled failure, and must not be silently converted into a tool result.
- **Closed-set params should be `Literal`, not `str`**, so they render as a JSON
  schema enum and the model cannot invent a value.

Syncing the tool catalogue to the backend is deliberately out of scope: the
backend here does not own one.

### Approval flow

`respond` drafts, `await_approval` calls `interrupt()`, and only an approved run
reaches `send_reply`. Notes that cost time to rediscover:

- The thread id is the **ticket id**, so a decision arriving on a new socket
  still finds the paused run. The backend deliberately disconnects after
  `approval_required` and opens a fresh connection to resume.
- A resume reloads state through the serializer, which hands pydantic models
  back as **plain dicts**. `_answer_of()` re-validates at the boundary; do the
  same for any new model read after an interrupt.
- `allowed_msgpack_modules` takes `(module, qualname)` pairs, not module names.
  Getting it wrong only warns today but will start raising.
- The draft is persisted **only** on `ReplySentMessage`. An `AnswerMessage` with
  `requires_approval=True` is held in `pending_reply` and never written, so a
  rejected draft leaves no trace in the ticket log.

### Tracing

OpenTelemetry, set up in `triage/tracing/`. Every graph node opens a span tagged
with the ticket; Pydantic AI's own spans (`instrument=True`) nest underneath.

- `TraceStoreExporter` always runs so `/traces/{ticket_id}` works with no
  account. An OTLP exporter is added only when `OTEL_EXPORTER_OTLP_ENDPOINT` is
  set, and a missing OTLP extra warns rather than crashing the agent.
- **Spans finish innermost-first**, so a child is exported before the parent
  that names the ticket, and only the node span carries the ticket id. The
  exporter therefore keys on **trace id** and buffers orphans until the naming
  span arrives. Keying on parent id instead silently loses every model call.
- `setup_tracing()` is called from `triage/agents/triage_agents.py` at import,
  before any `Agent` is constructed. Later and the first model call has no
  provider to report to.

### Frontend tests

`web/src/test/fake-socket.ts` is injected through chanx-js's `socketFactory`
option, so the real client code (framing, routing, reconnect) runs unchanged and
nothing global is monkey-patched. `useTicketChat.test.tsx` covers the address
the generated descriptor produces, the frames the hook sends, and handler
routing per action.

These were mutation-checked when written: breaking the send action, unwiring the
approval handler, and corrupting the ticket_id param each failed exactly one
test. Keep that property when adding more.

### Things that will bite

- `TRIAGE_ON_COMMENT` gates the automatic trigger and is `False` in test settings. Without it, every consumer test would reach for a live agent on :8001 and pass or fail depending on whether one happens to be running.
- Agent tests set a dummy `OPENAI_API_KEY` in `tests/conftest.py`, otherwise the agents fall back to `ScriptedModel` and the respx mocks match nothing.
- `graph.astream(..., stream_mode="updates")` yields `{node_name: update}` per step, not a `(name, update)` tuple. The graph tests use `ainvoke` and cannot catch a mistake here; `tests/test_consumer_streaming.py` exists for that.
- `agent/pyproject.toml` sets `addopts = "-p no:django"`. The shared venv makes pytest-django importable, and it activates off `DJANGO_SETTINGS_MODULE` in the root `.env`.

### Generated clients

- **WebSocket**: `@chanx-js/codegen` turns the backend's AsyncAPI document into
  `web/src/generated/` (message types plus a channel descriptor), and
  `@chanx-js/client/react` consumes it. `useTicketChat` is a thin wrapper over
  `useChannel`, so `send()` only accepts declared actions and each handler's
  payload is narrowed by its action. The hand-rolled `generate-ws-types.ts` is
  gone; it silently emitted an empty file because it parsed the AsyncAPI 2.x
  shape while chanx emits 3.0.
- **REST**: `web/scripts/generate-{schemas,types}.ts` still hand-roll the
  OpenAPI side. Keep them dependency-light and free of imports from `src/`.
- The socket carries a **typed** `TicketEvent` union (`tickets/messages/events.py`),
  not `dict[str, Any]`. That is what puts a discriminated union in the AsyncAPI
  document, so the generated client narrows on `eventType` exactly as the REST
  client does. `lib/types.ts` re-exports that union as the app's single event
  type for both transports.

`@chanx-js/codegen` 0.1.2 has two rough edges worth remembering: it needs
prettier 3 resolvable (v2 makes it crash on `prettier.resolveConfig`, which is
why prettier is a direct devDependency here), and it emits an unused
`defineTopic` import when a schema has no topics, which trips `noUnusedLocals`.
The second one has to be stripped by hand after each regeneration until fixed.

### Pitfalls already hit (do not re-derive)

- `asgi.py` must read settings via `django.conf.settings`, not by importing `settings.base` directly, or test overrides are silently ignored.
- chanx accepts the socket *before* `post_authentication`, so rejecting there is a close, not a refused handshake.
- `CHANX["CAMELIZE"]` camelizes the wire as well as the AsyncAPI document, but
  only from chanx 2.11.4. Before that, `broadcast_message` skipped it while
  direct sends applied it, so the same message arrived as `eventType` or
  `event_type` depending on how it was sent. Hence the `>=2.11.4` floor: on an
  older chanx the generated client silently finds no fields on broadcasts.
- `broadcast_message` fan-out arrives *after* the handler's `complete` frame. In tests use `receive_all_messages(stop_action="group_complete")`, and note each broadcast ends with its *own* `group_complete`, so drain one fan-out per read.
- Because accept precedes `post_authentication`, `connect()` can return before `group_add` runs, and a broadcast in that window hits an empty group. Use `WebsocketTestCase.connect_ready()`, which pings to prove the consumer is live. This was an intermittent test failure, not a flake.
- `BaseClient.__init__` takes `base_url` positionally only.
- `helpdesk/test_utils/__init__.py` must not re-export the test-case classes; factories import `BaseModelFactory` from it and it closes an import cycle.
- drf-spectacular's discriminator hook is a POSTprocessing hook. Registered as preprocessing it is called with `endpoints=` and raises.
- The root venv needs `.python-version` = 3.13; on 3.14 langchain-core warns about pydantic v1.
- `rest_polymorphic` defaults the discriminator to the class name (`CommentEvent`); `to_resource_type` is overridden to return `get_event_type()` (`comment`) so it matches the OpenAPI mapping.

### Current chanx API (2.11.1)

Verified against the installed package and the working repos listed below.

Shared:

```python
from chanx.core.decorators import channel, ws_handler, event_handler
from chanx.messages.base import BaseMessage
```

Messages are pydantic models with a `Literal` discriminator, payloads are plain `BaseModel`:

```python
class StreamingMessage(BaseMessage):
    action: Literal["streaming"] = "streaming"
    payload: StreamingPayload
```

Handlers may return a message instead of sending it. `ws_handler` and `event_handler` both take `summary` / `description` / `output_type` / `tags`, which feed the generated AsyncAPI.

Django side:

```python
from chanx.channels.websocket import AsyncJsonWebsocketConsumer
from chanx.channels.routing import path, include   # routing.py / asgi.py
from channels.sessions import CookieMiddleware      # not chanx.middleware
```

FastAPI side:

```python
from chanx.fast_channels.websocket import AsyncJsonWebsocketConsumer, ReceiveEvent
from chanx.fast_channels import asyncapi_docs, asyncapi_spec_json, asyncapi_spec_yaml
from chanx.fast_channels.type_defs import AsyncAPIConfig
from chanx.core.topic import Topic
```

Channel layers are registered through `fast_channels.layers.register_channel_layer(alias, layer)`, and a consumer selects one with `channel_layer_alias`. Consumers expose `send_message`, `broadcast_message`, `send_event`, `broadcast_event`, `groups`, `extra_groups`, `passthrough_events`.

### Reference repos for exact API usage

- `~/Code/huynguyengl99/pydantic-ai-ws-agent` - FastAPI + chanx + Pydantic AI, current and working.
- `~/Code/huynguyengl99/chanx-django-tutorial` - Django + chanx consumers, routing, asgi.
- `~/Code/huynguyengl99/chanx` - the library itself.

## Quick Commands

```bash
# Install dependencies
cd web && pnpm install           # Node packages (frontend)
uv sync --all-packages --active  # Python packages (backend + agent)

# Run services (see project AGENTS.md for details)
just backend                     # Backend: http://localhost:8000
just agent                       # Agent: http://localhost:8001
just frontend                    # Frontend: http://localhost:5173

# Build & validate
just check                       # All checks (mypy + ruff + django check + typecheck)
just lint                        # Lint all workspaces
just test                        # Run backend tests
```

## Project Navigation

| Project  | Path       | Details                  |
| -------- | ---------- | ------------------------ |
| Backend  | `backend/` | See `backend/AGENTS.md`  |
| Frontend | `web/`     | See `web/AGENTS.md`      |
| Agent    | `agent/`   | See `agent/AGENTS.md`    |

## Git Workflow

### Branch Naming

- Feature: `feature/<description>`
- Bugfix: `fix/<description>`
- Refactor: `refactor/<description>`

### Commit Messages

Use conventional commits:

- `feat:` new feature
- `fix:` bug fix
- `refactor:` code restructuring
- `docs:` documentation
- `test:` test changes

## Common Workflows

### Managing UV Packages

This project uses UV workspaces. The root `pyproject.toml` manages both `backend` and `agent` as workspace members.

```bash
# Add a package to backend
cd backend && uv add django-cors-headers

# Add a package to agent
cd agent && uv add httpx

# Sync all packages
uv sync --all-packages --active
```

### Code Generation

Code generation is the core workflow of this project. Backend defines the API contract, and clients are auto-generated:

```bash
# Generate all (agent client + frontend types/schemas)
just gen

# Generate frontend only (requires backend running at :8000)
just gen-frontend

# Generate agent → backend client only (requires agent running at :8001)
just gen-agent-client
```

### Full Setup (First Time)

```bash
just setup    # install + infra-up + migrate + gen
```

## Environment Setup

- Copy `.env.example` to `.env` and configure
- Docker Compose provides PostgreSQL and Redis

**IMPORTANT**: Never commit `.env` files with secrets.

## Warnings & Gotchas

1. **Dual package managers**: Use `pnpm` for Node.js project (`web/`), `uv` for Python projects (`backend/`, `agent/`)
2. **UV workspace**: Root `pyproject.toml` manages both `backend` and `agent` as workspace members
3. **Project-specific details**: See each project's AGENTS.md for code style, testing, generated files, and specific gotchas
4. **Code generation requires running services**: `just gen-frontend` needs backend at `:8000`, `just gen-agent-client` needs agent at `:8001`
5. **Never run `migrate` automatically**: Never run migrations unless the user explicitly asks. Running `makemigrations` to create migration files is OK.
6. **No venv activation**: The user already has the virtualenv activated. Never run `source .venv/bin/activate` or similar.
