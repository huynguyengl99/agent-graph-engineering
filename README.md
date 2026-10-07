# Agent Graph Engineering

Companion repository for the **[Agent Graph Engineering](https://huynguyengl99.github.io/posts/agent-graph-engineering/why-i-gave-up-on-if-else-ai-flows/)** blog series: building an observable, scalable, maintainable AI agent system with LangGraph, Pydantic AI, and chanx.

The series argues that your agent flow should be a **declared graph**, not a chain of `if/else` on an intent classifier. This repo is the working proof.

> **Not graph RAG.** This is about the *execution* graph of an agent: state, nodes, edges, routing, interrupts, resumption. Knowledge graphs and graph RAG are retrieval techniques, where a graph is the data you query. Graph RAG could sit behind one node here as one tool among several. Same word, unrelated concept.

## What it is

A support desk where one ticket has two lanes and one agent serves both:

- **The public lane is the customer's.** A ticket arrives, the graph decides what to do with it - answer directly, search the knowledge base, run a tool, escalate - and they watch it being worked out and written, step by step.
- **The internal lane is the team's.** Notes to colleagues, questions to the assistant, its answers, and the lookups it ran with what they were handed. Staff-only, so nothing there is gated on the way in.

One rule falls out of that split: **the assistant answers; a person authorises anything it cannot take back.** A refund, a message staff wrote, and a reply about a ticket the guards flagged all wait for someone. An ordinary question does not, because a desk whose assistant can never finish a sentence has no assistant.

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
| 0   | Why I gave up on if/else AI flows                 | -               |
| 1   | The stack, and why each piece is there            | `stack`         |
| 2   | Two services, one product                         | `split`         |
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

## Status

Work in progress, tracking the series as it publishes.

Working end to end, with nothing mocked in `just e2e`:

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

Not built yet: context budgeting for long threads, and spend caps - cost is
measured, not enforced.

One wart worth knowing about, since it is visible in the code: the run that
answers a ticket's opening description is started by the portal when the thread
mounts, because nothing posted that description as a message. So a customer who
files a ticket and never opens it waits for a person, and that run's progress
is broadcast before anyone is subscribed to hear it. Starting it where the
ticket is created is the fix, and the create path is a synchronous view with no
event loop to detach a run onto.

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
