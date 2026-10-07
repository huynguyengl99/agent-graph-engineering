# Agent Graph Engineering

A production-grade reference implementation of an AI agent system whose flow is a **declared graph** rather than a chain of `if/else` on an intent classifier. Type-safe across every boundary, self-documenting, self-visualizing, observable, and controllable. Three services in one repository, running on a single LLM key, or none at all.

Every decision in it is explained by a twelve-post series, **[Agent Graph Engineering](https://huynguyengl99.github.io/posts/agent-graph-engineering/before-it-had-a-name/)**. The code is the artifact; the series is its documentation.

Use it as a reference for a system you already run, as the starting point for one you are about to build, or as a base to adapt for a client. It is shaped for production rather than for a notebook, and [what you still owe](#what-you-still-owe-before-production) before real users touch it is written down rather than glossed over.

> **Not graph RAG.** This is about the *execution* graph of an agent: state, nodes, edges, routing, interrupts, resumption. Knowledge graphs and graph RAG are retrieval techniques, where a graph is the data you query. Graph RAG could sit behind one node here as one tool among several. Same word, unrelated concept.

## Run it

```bash
just setup       # env files, deps, Docker, migrations, generated clients, seeded accounts
just up          # all three services in the background, waiting until each answers
```

Then open <http://localhost:5173>. Two accounts are seeded, both with the
password `demo-pass-123`: `demo@example.com` is staff and gets the console, the
gates, the graph viewer and the trace viewer; `customer@example.com` sees only
the public half of their own tickets. Sign in as one in a normal window and the
other in a private one to watch a run from both sides at once.

**No API key is needed.** With `OPENAI_API_KEY` unset, a built-in scripted model
drives the whole system and the graph, routing, approvals, streaming and UI all
behave the same. Set a real key in `agent/.env` for real answers. Full detail,
including the containerised path, is in [Quick start](#quick-start) below.

## Where this comes from

Not a greenfield sketch. This is distilled from a production system of five
services, out of roughly five years of building realtime infrastructure and AI
agent systems: about three years on one agent product and two on another, both
with real users and real incidents.

That provenance is the point, because what you inherit is the failure modes. The
parts of this repo that look over-careful are mostly the parts that broke first
somewhere else. A run claims its lane because two runs on one thread silently
overwrote each other and an approved reply vanished. Events are appended before
they are published, with a cursor, because a restart mid-run lost a reply that
no one was subscribed to hear. An approval resumes on a different socket than
the one that started it because that is what actually happens when a person
takes a while to click.

What it is not is a copy. The commercial system's domain, its scale concerns and
its branding are all absent on purpose. What is here is the architecture, re-cut
to a support desk small enough to read in an afternoon.

## What you get

| | How it actually works |
| --- | --- |
| **Type-safe across every boundary** | Pydantic AI gives typed tools, typed outputs and typed dependencies. DRF serializers generate OpenAPI, which generates Zodios clients. chanx consumers generate AsyncAPI, which generates both a TypeScript client and a Python one. Change a shape, run `just gen`, and the compiler names what broke. |
| **Flow as a declared graph** | LangGraph state, nodes and conditional edges. Adding a capability is a node and an edge, not another condition threaded through an existing chain. |
| **Self-visualizing** | The graph exports Mermaid and renders in the app, so the architecture picture is generated from the thing that actually runs and cannot go stale. |
| **Self-documenting** | OpenAPI and AsyncAPI are generated, never hand-maintained. Your WebSocket layer gets the contract your REST API has had for a decade. |
| **Observable, with the viewers included** | An OpenTelemetry span per graph node, with Pydantic AI's own spans nested underneath, plus per-run cost. A local trace store works with no account at all, and `/traces` renders a run as the chain of steps it was: node states, model calls, and which span attributes are worth showing. `/graphs` renders the graph itself. Point `ASSISTANT_TRACE_EXPORT` at any OTLP backend, Langfuse or Jaeger or Grafana, when you want one. |
| **Controllable** | Irreversible tool calls park for human approval, survive a reload, and resume on a different socket than the one that started the run. Guardrails screen the input edge and the output edge. Postgres checkpointing makes a crashed or parked run resumable instead of lost. |
| **Testable without spending** | The LLM is mocked at the HTTP layer, so the real pipeline runs: SSE parsing, tool-call assembly, streaming, validation. A scripted model runs the entire system with no API key, streaming included. Evals hit real providers when you ask for them. `just e2e` drives a real browser against real services. |
| **Deployable** | Multi-stage images on a frozen lockfile, granian serving ASGI because the channels are WebSockets, and production-safe settings as the default with `dev.py` the one that loosens them. |

## The application

A support desk where one ticket has two lanes and one agent serves both:

- **The public lane is the customer's.** A ticket arrives, the graph decides what to do with it - answer directly, search the knowledge base, run a tool, escalate - and they watch it being worked out and written, step by step.
- **The internal lane is the team's.** Notes to colleagues, questions to the assistant, its answers, and the lookups it ran with what they were handed. Staff-only, so nothing there is gated on the way in.

One rule falls out of that split: **the assistant answers; a person authorizes anything it cannot take back.** A refund, a message staff wrote, and a reply about a ticket the guards flagged all wait for someone. An ordinary question does not, because a desk whose assistant can never finish a sentence has no assistant.

The domain was chosen so that the graph earns its place (real routing, not a two-node demo), the approval machinery solves a real problem (an irreversible action), and you can run the whole thing with only an LLM key. No OAuth, no third-party signups. With no key at all it still runs end to end on a scripted model, streaming included.

## Architecture

```
┌────────────┐   REST + WS   ┌────────────┐   typed WS   ┌──────────────┐
│  Frontend  │ ────────────▶ │  Backend   │ ───────────▶ │    Agent     │
│  (React)   │               │  (Django)  │   AsyncAPI   │  (FastAPI)   │
└────────────┘               └────────────┘              └──────────────┘
                                   │                            │
                              business data              graphs, tools,
                             auth, tickets               checkpoints
```

| Service    | Stack                                             | Port |
| ---------- | ------------------------------------------------- | ---- |
| `backend/` | Django 5.2, DRF, Channels, chanx, PostgreSQL      | 8000 |
| `agent/`   | FastAPI, LangGraph, Pydantic AI, chanx            | 8001 |
| `web/`     | React 19, Vite, Zodios, chanx-js, Tailwind        | 5173 |

What each service owns, how they stay in sync, and the generated contracts between them: **[docs/architecture.md](docs/architecture.md)**.

## Following along with the series

Twelve posts, each pinned to a tag so you can check out the exact state being described:

| #   | Post                                              | Tag             |
| --- | ------------------------------------------------- | --------------- |
| 0   | I needed this before it had a name                 | -               |
| 1   | The stack, and why each piece is there            | `stack`         |
| 2   | Split the services: where the line goes           | `split`         |
| 3   | Types and contracts                               | `contracts`     |
| 4   | The agent: typed tools, outputs, dependencies     | `agent`         |
| 5   | Tools and guardrails                              | `tools`         |
| 6   | The graph: state, nodes, edges, routing           | `graph`         |
| 7   | Subgraphs, persistence, and interrupts            | `interrupts`    |
| 8   | Streaming                                         | `streaming`     |
| 9   | Observability: tracing, and what a run cost       | `observability` |
| 10  | Testing and evals                                 | `testing`       |
| 11  | Shipping it                                       | `deploy`        |

```bash
git checkout interrupts
```

`main` is always the latest state, and will be ahead of whatever post you are reading.

## Quick start

### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+ with [pnpm](https://pnpm.io/)
- Docker and Docker Compose (PostgreSQL + Redis)
- [just](https://github.com/casey/just) (`brew install just`)

No API key is required to run it. With `OPENAI_API_KEY` unset the agent uses a
built-in scripted model: the graph, routing, streaming, and UI behave exactly
the same, only the reasoning is canned. Set a real key to get real answers.

### Setup

```bash
just setup           # env files, deps, Docker, migrations, generated clients, accounts
```

`just setup` gives each service the `.env` next to it, from its own
`.env.example`, waits for Postgres to accept connections before migrating, and
seeds two accounts - both with the password `demo-pass-123`:

| | |
| --- | --- |
| `demo@example.com` | staff. The console: the queue, internal notes, both gates, the assistant, graphs, traces. |
| `customer@example.com` | reports problems. The portal: their own tickets, and only the public half of each thread. |

They are deliberately two people. Sign in as one in a normal window and the
other in a private one, and you can watch a run from both sides at once: the
customer asks, the agent reasons and writes in front of them, and the console
watches the same run from the other side. Flag it - ask for a refund - and the
reply waits for staff instead. Set `OPENAI_API_KEY` in `agent/.env` when you want
real answers.

### Run

```bash
just up          # all three, in the background, waiting until each answers
just status      # which are up
just logs a      # follow one of them (b backend, a agent, w web)
just down        # stop them and free the ports
```

Three ways to tidy up, in increasing order of violence:

| | |
| --- | --- |
| `just down` | stops the services. Postgres and Redis keep running. |
| `just infra-down` | stops those too. Data survives, so `just up` picks up where you left off. |
| `just reset` | throws the data away: database volumes, traces, eval runs. Re-migrates and re-seeds, so you end where `just setup` left you. Code and `.env` files are untouched. |

`just clean` is a different axis: it removes caches and generated clients, so it
wants a `just gen` afterwards.

Or one per terminal, when you are working on that service and want its output
in front of you:

```bash
just backend     # http://localhost:8000
just agent       # http://localhost:8001
just frontend    # http://localhost:5173
```

Backend endpoints:

- API: http://localhost:8000/api/
- Admin: http://localhost:8000/admin/
- Swagger UI: http://localhost:8000/api/schema/swg/
- AsyncAPI docs: http://localhost:8000/api/asyncapi/docs/

### Driving it

One surface, two lanes, and which lane a message is in decides everything about
it.

**The public lane is the customer's.** The agent drafts replies *to the
customer*, and only the customer asking something starts a run of its own - a
staff note is addressed to colleagues, and a staff reply has already answered.
A draft is screened on its way out, and stops for a person when the machine has a reason to want one - which in practice means the ticket tried to talk to the model rather than describe a problem.

**The internal lane is the team's.** Notes to colleagues, questions to the
assistant, its answers, its reasoning and the lookups it ran: staff-only, so
nothing there is gated on the way in. A note can be sent with **Send with agent
reply**, which asks the assistant in the ticket it is already about, and what it
writes back lands in the same lane unless somebody sends it onward through the
gate.

There used to be a separate Assistant tab for that second lane: the same thread
about the same ticket in a different window, with a **Send to ticket** button to
carry an answer back. It is gone, because the ticket is where the work is.

A walk through both, with the two accounts in two windows:

1. As the customer, report a problem and add a message. The console shows the
   classification and routing decision as they happen.
2. As staff, watch it park at the gate. Edit the draft, then approve: your text
   is what gets sent, not the model's. Reload while it is parked - the draft is
   persisted, not held in the tab.
3. As staff, add an **internal note**. Nothing runs: it was not addressed to the
   agent. It is read the next time one does, and the answer prompt says to use
   what it means without quoting it.
4. In the same note box, ask for something irreversible - *"refund the duplicate
   29.00 charge for demo@example.com"*. It parks on a card whose form is
   generated from the tool's schema. Correct the amount and approve: the
   corrected value is what runs. A customer can reach a tool the same way, and
   it parks on the team just the same.
5. Open **Traces**. One tree per run, model calls nested under the node that
   made them, and what it cost.

### Regenerate clients after a contract change

```bash
just gen               # everything
just gen-frontend      # OpenAPI + AsyncAPI to TypeScript
just gen-agent-client  # agent AsyncAPI to Python client
```

Each generator reads a live schema, so it starts the service it reads from if
that service is not already up.

## What works today

All of the following runs end to end with nothing mocked, and `just e2e` drives
it in a real browser against real services and real models:

- **One ticket, two audiences.** A customer's message is persisted, fanned out
  over the ticket channel, handed to the agent over a typed WebSocket, and the
  classification and decision stream back live. The same graph answers the team
  privately on the same ticket.
- **Who is answering is a state the ticket carries.** The agent by default, a
  person once the agent escalates or someone replies to the customer, and back
  again through a button that introduces the change to the customer in a
  person's own words.
- **Human gates where they are earned.** A tool call parks before it runs,
  always. A reply parks when the guards flagged the ticket it answers, which is
  rare and is the machine saying it is unsure rather than a rule that the agent
  may never speak. Both survive a reload, both resume on a different socket
  than the one that started the run, and a message arriving while one is parked
  waits its turn instead of overwriting the run behind it.
- **The agent reasons out loud, at every step that explains itself.** Structured
  output arrives in pieces, so filing the ticket, choosing what to do, picking
  the tool and re-searching each report their reasoning while it is written,
  then keep it on the ticket - for the team only, including on runs a customer
  started.
- **Nothing half-written reaches a customer.** A value the model could not fill
  is written `{{like this}}`, and the agent's prompt, the backend and the
  browser all refuse to publish text that still has one.
- Postgres checkpointing, at-most-once execution for irreversible tools,
  guardrails on both sides of the model, evals, and per-run tracing.

- **A customer can reach a tool too, and sees what it did.** Their request
  proposes one, a reviewer clears it like any other, and the call is recorded on
  their half of the ticket - the name and whether it ran, with the arguments and
  the result kept for the team.

## What you still owe before production

Calling something production-ready without this list would be dishonest. The
architecture is production-grade and the deployment is production-shaped, and
these are the things you have to add for your own environment. None of them is
deep work; all of them are real.

**Before you deploy at all**

- **Set `DJANGO_SECRET_KEY`.** The default is the placeholder
  `django-insecure-change-me`, deliberately, so a fresh clone runs. Also set
  `DJANGO_ALLOWED_HOSTS`, which defaults to empty, and `ASSISTANT_AGENT_TOKEN`,
  which is unset so a clone needs no configuration. Unset means the agent
  accepts every caller.
- **Add the TLS and HSTS settings.** There is no `SECURE_SSL_REDIRECT`,
  `SECURE_HSTS_SECONDS` or secure-cookie configuration, because they depend on
  whether something terminates TLS in front of you.
- **Add a non-root `USER` to the images,** and a healthcheck or readiness probe
  on the app services. The infrastructure containers have one; the three app
  containers do not.
- **Keep the agent off the public network.** Only the backend should reach it.
  The approval gate lives inside the graph, so anything that can open a socket
  on the agent can both propose a tool call and approve it. Network isolation is
  the primary control and the token is the second.

**Before you put real traffic through it**

- **Context budgeting.** The whole conversation is sent, so cost grows with
  thread length. There is no summarization or windowing.
- **Spend caps.** Cost is measured per run and reported, but nothing enforces a
  ceiling.
- **Provider rate limits and retries.** There is no backoff policy for a
  provider returning 429 or a transient 5xx.
- **A migration story.** Migrations exist and run, but nothing here addresses
  running them against a live database with traffic on it.

**Known gaps, left visible on purpose**

- **No automatic resume after a worker dies.** A run is driven by an in-process
  task. Graph state, the lane claim and the event cursor are all durable, so
  nothing is corrupted and nothing is lost, but a run whose process died waits
  for its claim to go stale and be taken over by the next message rather than
  being picked up on its own. A sweeper that finds stale claims with an
  unfinished checkpoint and resumes them is the missing piece.
- **`just e2e` is kept out of CI,** because it needs provider keys and spends
  money. CI runs the three mocked suites.
- **The opening-description run is started by the portal** when the thread
  mounts, because nothing posted that description as a message. A customer who
  files a ticket and never opens it waits for a person, and that run's progress
  is broadcast before anyone is subscribed to hear it. Starting it where the
  ticket is created is the fix, and the create path is a synchronous view with
  no event loop to detach a run onto.

## Documentation

| Page | What it covers |
|---|---|
| [Architecture](docs/architecture.md) | What each service owns, the agent's boundary, how the two stay in sync, the generated contracts |
| [Graphs and subgraphs](docs/graphs.md) | The one graph and its three subgraphs, which drafts stop for a person, forms from a schema |
| [Evals](docs/evals.md) | The golden set, the cascade judge, choosing the models, the guardrails |
| [Observability](docs/observability.md) | Per-run traces, what a span may carry, moving them to object storage |
| [Testing](docs/testing.md) | What each suite mocks, and the pass that mocks nothing |
| [Containers](docs/containers.md) | The three images, and what building them found |

## License

MIT
