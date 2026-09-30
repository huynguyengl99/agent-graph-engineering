# Triage Agent - Agent Instructions

**IMPORTANT**: When the user corrects you about a convention, pattern, structure, coding style, or gotcha — update this AGENTS.md to capture it so the lesson persists across sessions.

## Project Structure

```
agent/
├── triage/
│   ├── main.py                  # FastAPI app entry point
│   ├── apps/
│   │   └── agent/               # Agent implementation
│   │       ├── consumer.py      # WebSocket consumer (chanx fast-channels)
│   │       ├── service.py       # Agent business logic
│   │       └── messages.py      # Message definitions
│   └── core/
│       └── config.py            # Settings via environs
├── pyproject.toml               # Dependencies (uv)
├── pyrightconfig.json           # Pyright config
└── ruff.toml                    # Linter config (in pyproject.toml)
```

## Quick Commands

```bash
# Install dependencies
uv sync

# Development server
just agent
# Or directly:
cd agent && uv run uvicorn triage.main:app --port 8001 --reload

# Linting & type checking
cd agent && uv run ruff check .      # Ruff linter
cd agent && pyright                   # Pyright type checker
```

## Code Style

- Follow PEP 8 with 100 char line length (Ruff/Black formatting)
- Use type hints on all function signatures, models, services, etc.
- **HARD CONSTRAINT - Imports at top of file**: Always place imports at the top of the file, never inline inside functions. The only exceptions are:
  - Inside `if TYPE_CHECKING:` blocks (for type-only imports)
  - When Python/server startup actually fails due to circular imports (very rare)
- **Async-first**: Use `async/await` for all I/O operations
- Use Pydantic models for data validation
- Only run linting/formatting/typechecking at the end of a feature implementation or bug fix, not after every small change. Stay calm and batch it.

## AI Development

### Agent Service

The agent uses **pydantic-ai** for AI agent framework with OpenAI as the LLM provider. It communicates with the Django backend via WebSocket using **chanx fast-channels**.

### WebSocket Communication

- Uses **chanx fast-channels** for WebSocket consumers
- AsyncAPI schema auto-generated for type-safe message contracts
- Backend generates a Python WebSocket client from this schema

### Adding New Agent Capabilities

1. Define message types in `triage/apps/agent/messages.py`
2. Implement logic in `triage/apps/agent/service.py`
3. Handle WebSocket messages in `triage/apps/agent/consumer.py`
4. Backend regenerates client: `just gen-agent-client`

## Warnings & Gotchas

1. **Async everywhere**: All I/O must be async - use `async/await`
2. **Backend sync required**: After API changes, backend runs `just gen-agent-client` to update the client
3. **PydanticAI**: Uses pydantic-ai for structured AI agent interactions
4. **No venv activation**: The user already has the virtualenv activated. Never run `source .venv/bin/activate` or similar.

## Guardrails

`assistant/guardrails/` holds two guards with different jobs:

- **Input** (`input.py`): every customer-written field is fenced by
  `TicketContext.render()` so the model has a stated data/instruction boundary.
  Injection shapes are *recorded, never blocked* - a desk that refuses tickets
  containing "ignore" is broken, and a warning everyone learns to skip is worse
  than none.
- **Output** (`output.py`): runs as the `screen` graph node, between the drafted
  answer and the human approval gate. Leaked credentials, another ticket's id,
  or the prompt recited back all block the draft before a reviewer sees it.

Findings reach the UI on `approval_required.findings`, or as `reply_blocked`.

## Evals

The golden set lives in `evals/scenarios/*.yaml`, one file per concern.

```
just evals                        # everything, on evals/configs/openai.json
just evals guardrail              # names matching "guardrail"
just evals --config claude        # the same set on a different model set
just evals-compare scripted openai_gpt-4o
```

Model sets live in `evals/configs/*.json`. The judge stays on one model across
configs on purpose - judging Claude with Claude is not a comparison.

`trials: 1` means one bad sample fails a scenario; three consecutive runs came
back 12/12 but individual runs have come back 11/12. Raise `trials` when a
result has to be trustworthy - scoring is a majority vote, and the cost scales
with it.

Runs with no API key: the scripted model keeps the deterministic checks real,
and prose criteria are reported as *skipped* rather than scored, so a keyless
run never reads as if a model approved the answers.

Scoring is a majority vote across `trials`. Guardrail findings compare on exact
kinds, never substrings - see `tests/test_evals.py` for why.

Cost comes from the spans the tracer already collects
(`assistant/tracing/cost.py`), so it needs no plumbing through the agents. A
model with no price table reports its tokens with `priced: false` and names the
model, rather than a misleading $0.00.

Models the pinned release predates are priced from
`assistant/tracing/prices.py`, a hand-maintained table that goes stale by
design - check it against Anthropic's pricing page when a model moves.
genai-prices still wins wherever it knows the model; the local table is only a
fallback, and anything in neither is honestly `priced: false`.

**`genai-prices` is pinned exactly at 0.0.55.** 0.1.9 knows the newer Claude
models but silently zeroes pydantic-ai 1.63's token counts - every call still
reports, with `input=0` and `output=0`, so cost quietly becomes $0.00 instead
of failing. `tests/test_usage_reporting.py` guards it, and the OpenAI mock
carries the `*_tokens_details` objects a real response has, because without
them the parsing takes a different path and the bug does not reproduce.

## Model selection

Two axes, kept apart on purpose:

- **Which purpose a step runs under is system config.** A step names a
  `ModelPurpose` (`decision`, `answer`, `vision`), never a model, so no config
  can route classification onto the vision model or send the cheap one to
  write customer prose.
- **Which model fills a purpose is user config.** A `ModelPreference` row per
  user per purpose travels the wire as optional overrides and resolves
  user -> deployment default.

`ModelOverrides` on the wire has exactly one field per purpose, so a client
cannot reassign a step's purpose even if it wanted to. Overrides ride the
resume as well as the initial request; nothing after the approval gate calls
a model today, but that is a fact about the current graph, not a guarantee.

`build_model` goes through pydantic-ai's `infer_model("provider:name")`, so
adding a provider is config plus an API key, not code.

## Checkpointing

`assistant/graphs/checkpointer.py` opens one saver per process in the FastAPI
lifespan. Postgres by default; without `CHECKPOINT_DATABASE_URL` it falls back
to memory and says so loudly, because the failure is silent otherwise - a
deploy drops every reply waiting on a reviewer.

Tests install an in-memory saver via `install_checkpointer`, so proving a
resume needs no database.

## Graphs and subgraphs

`assistant/graphs/registry.py` is the list of every flow this service runs. A
graph missing from it is invisible to the docs endpoints, which is the intended
pressure.

| Graph | Kind | Why it is its own graph |
|---|---|---|
| `triage` | parent | works one ticket: classify, decide, answer or escalate |
| `chat` | parent | the rep's own thread; nothing customer-visible |
| `knowledge` | subgraph | it *loops* - search, refine, search again, capped at `MAX_ATTEMPTS` |
| `delivery` | subgraph | the only route to a customer, and the only irreversible step |

Subgraphs are compiled and added as nodes (`graph.add_node("knowledge", build_knowledge_graph(...))`).
They share only the keys they need with the parent state, so nothing has to be
mapped across the boundary; their private bookkeeping (`kb_attempts`) never
leaves.

Two things this changed that are easy to trip over:

- **A subgraph's writes reach the parent only when it returns.** The approval
  gate is inside `delivery`, so while a run is parked the parent cannot see
  `guardrail_findings` or `reply_blocked`. The reviewer's information travels
  on the interrupt payload instead, which is where it belongs anyway.
- **The parent seeds the subgraph.** `decide` writes `kb_query` from the
  decision, so retrieval searches for what the decider asked for rather than
  for the whole ticket.

## Diagrams

```
GET /graphs                        # every graph, and which are subgraphs
GET /graphs/{name}.mermaid         # xray=true by default, expands subgraphs
GET /graphs/{name}.mermaid?xray=false
```

Generated from the compiled graph, so the picture cannot disagree with the
code. The web UI renders them at `/graphs` (the agent is proxied at `/agent`
in development).
