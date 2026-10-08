# Agent Graph Engineering - Agent Instructions

> Instructions for any coding agent working in this monorepo. Each project has its own `AGENTS.md` with detailed patterns and conventions.

## What this repo is

A **production-grade reference implementation** of an AI agent system built as a declared graph on LangGraph + Pydantic AI + chanx: type-safe across every boundary, self-documenting, self-visualizing, observable and controllable. The application is a support helpdesk where one agent works a ticket for two audiences, the customer who reported it and the team answering it.

The code is the artifact. The **Agent Graph Engineering** series is its documentation, and lives in `~/Code/huynguyengl99/my-blog` under `src/content/posts/agent-graph-engineering/`.

That positioning matters when deciding what to build: people are meant to **adopt** this, not skim it. The README's "What you still owe before production" section is the honest boundary of the claim, and anything newly discovered that a real deployment would need belongs there rather than being quietly left out.

Because the repo is read alongside the posts, two rules override normal defaults:

1. **Every post gets a git tag**, named descriptively rather than by number, so inserting or splitting a post never renumbers the rest: `stack`, `split`, `interrupts`, `testing`. The README's table is the list. Never rewrite history behind a published tag.
2. **Production-grade guarantees, readable implementation.** The guarantees have to be real: typed boundaries, generated contracts, checkpointed runs, approval gates on irreversible actions, guardrails on both edges, tracing. Within that, prefer the clear version over the clever one, because a reference nobody can read is not a reference. Where a larger system would need something more complex, say so in the post rather than in a code comment. Never weaken a guarantee to make an example shorter.

### Writing style for README and public docs

Public prose here follows the author's blog style:

- No em-dashes. Rephrase, or use a short hyphen if a dash is really needed.
- US spelling: "visualize", "authorize", "organization", "behavior".
- No manufactured engagement hooks ("What's your take?").
- Never add `Co-Authored-By` trailers or any AI attribution to commit messages.

### Known state

Counts and snapshots rot, so this says where to look rather than what the
numbers are: `just check` runs every project's checks in parallel and `just test`
runs the three suites. `just e2e` drives a real browser against real services and
real models.

Inherited from an earlier schema-first reference project whose WebSocket layer
had never run; both sides were rewritten against current chanx.

What is deliberately not done is listed in the README under **"What you still
owe before production"**, which is the single place for it. Keep that list
current: it is what makes the production claim credible, so a gap found while
working here gets added there rather than mentioned in a commit message and
forgotten. The short version is no context budgeting, cost measured but not capped, no
TLS/HSTS settings, no non-root user or app healthchecks in the images, no
provider retry policy, no automatic resume after a worker dies, and `just e2e`
out of CI because it spends money.

**There is a trace viewer and a graph viewer**: `/traces` renders a run as its
chain of steps and `/graphs` renders the graph. An older copy of this file said
there was none, which was true once and then got repeated into the README. When
a capability lands, fix the claim here as part of landing it.

### Tools

Tools live in `assistant/tools/`, with the infrastructure in `assistant/tools/core/`.
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

`support_respond` drafts, `delivery_screen` decides whether a person is needed,
`delivery_approval` calls `interrupt()` when one is, and only then does a run
reach `delivery_send`. Notes that cost time to rediscover:

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

OpenTelemetry, set up in `assistant/tracing/`. Every graph node opens a span tagged
with the ticket; Pydantic AI's own spans (`instrument=True`) nest underneath.

- `TraceStoreExporter` always runs so `/traces/{run_id}` and a run's reported
  cost work with no account. The two durable sinks - files and an OTLP
  collector - are chosen by `ASSISTANT_TRACE_EXPORT`
  (`off|local|otlp|both`), and a missing OTLP extra warns rather than crashing
  the agent. A forwarding mode with no endpoint configured is refused at
  startup, because the alternative is a clean start that sends nothing.
- **Spans finish innermost-first**, so a child is exported before the parent
  that names the ticket, and only the node span carries the ticket id. The
  exporter therefore keys on **trace id** and buffers orphans until the naming
  span arrives. Keying on parent id instead silently loses every model call.
- `setup_tracing()` is called from `assistant/agents/` at import,
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

- `AGENT_ON_COMMENT` gates the automatic trigger and is `False` in test settings. Without it, every consumer test would reach for a live agent on :8001 and pass or fail depending on whether one happens to be running.
- Agent tests set a dummy `OPENAI_API_KEY` in `tests/conftest.py`, otherwise the agents fall back to `ScriptedModel` and the respx mocks match nothing.
- `graph.astream(..., stream_mode="updates")` yields `{node_name: update}` per step, not a `(name, update)` tuple. The graph tests use `ainvoke` and cannot catch a mistake here; `tests/test_consumer_streaming.py` exists for that.
- Each service reads the `.env` beside it (`backend/.env`, `agent/.env`, `web/.env`), never a shared one. environs resolves the nearest file walking up from the working directory, and every recipe runs a service from its own. A variable one service sets and another reads by accident is not a hypothetical: the backend's `DJANGO_SETTINGS_MODULE` used to reach the agent, where chanx reads it to pick an integration, and every topic broadcast would have failed.

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

### Current chanx API (2.11.5+)

Verified against the installed package and the working repos listed below.
A generated client sends the `headers` it was given from 2.11.5 on; before that
it accepted them and dropped them.

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

# Run services
just up                          # all three in the background, waiting for each
just status                      # which are up
just logs a                      # follow one (b backend, a agent, w web)
just down                        # stop them and free the ports
just backend                     # or one per terminal, to watch its output

# Build & validate
just check                       # every project's checks in parallel
just check ba                    # backend and agent only (-e w excludes web)
just fix                         # the same set, writing what it can
just test                        # backend, agent and web suites
just e2e                         # real browser, real models, spends tokens
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

- `just env` gives each service the `.env` next to it, from its own
  `.env.example`. There is no root `.env`.
- `ASSISTANT_AGENT_TOKEN` is the one value that has to agree across all three.
- Postgres and Redis come from `docker-compose.yml`, which owns their
  credentials; the services only hold connection strings.

**IMPORTANT**: Never commit `.env` files with secrets.

## Warnings & Gotchas

1. **Dual package managers**: Use `pnpm` for Node.js project (`web/`), `uv` for Python projects (`backend/`, `agent/`)
2. **UV workspace**: Root `pyproject.toml` manages both `backend` and `agent` as workspace members
3. **Project-specific details**: See each project's AGENTS.md for code style, testing, generated files, and specific gotchas
4. **Code generation requires running services**: `just gen-frontend` needs backend at `:8000`, `just gen-agent-client` needs agent at `:8001`
5. **Never run `migrate` automatically**: Never run migrations unless the user explicitly asks. Running `makemigrations` to create migration files is OK.
6. **No venv activation**: The user already has the virtualenv activated. Never run `source .venv/bin/activate` or similar.
