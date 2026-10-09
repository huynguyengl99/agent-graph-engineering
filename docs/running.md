# Running it

Everything here is the long version of [Run it](../README.md#run-it) in the README.

## Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+ with [pnpm](https://pnpm.io/)
- Docker and Docker Compose (PostgreSQL + Redis)
- [just](https://github.com/casey/just) (`brew install just`)

## Setup

```bash
just setup           # env files, deps, Docker, migrations, generated clients, accounts
```

That gives each service the `.env` next to it, from its own `.env.example`, waits for Postgres to accept connections before migrating, and seeds two accounts, both with the password `demo-pass-123`:

| | |
| --- | --- |
| `demo@example.com` | staff. The console: the queue, internal notes, both gates, the assistant, graphs, traces. |
| `customer@example.com` | reports problems. The portal: their own tickets, and only the public half of each thread. |

They are deliberately two people. Sign in as one in a normal window and the other in a private one, and you can watch a run from both sides at once: the customer asks, the agent reasons and writes in front of them, and the console watches the same run from the other side. Flag it, by asking for a refund, and the reply waits for staff instead.

## Models

No API key is required. With `OPENAI_API_KEY` unset the agent uses a built-in scripted model: the graph, routing, approvals, streaming and UI behave exactly the same, only the reasoning is canned.

Set a real key in `agent/.env` for real answers. No step in the graph names a model, so which model serves which purpose is configuration: see `agent/.env.example` for the decision and answer slots and the providers they accept.

## Day to day

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

`just clean` is a different axis: it removes caches and generated clients, so it wants a `just gen` afterwards.

Or one per terminal, when you are working on that service and want its output in front of you:

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

## A walk through both lanes

With the two accounts in two windows:

1. As the customer, report a problem and add a message. The console shows the classification and routing decision as they happen.
2. As staff, watch it park at the gate. Edit the draft, then approve: your text is what gets sent, not the model's. Reload while it is parked, and the draft is still there, because it is persisted rather than held in the tab.
3. As staff, add an **internal note**. Nothing runs: it was not addressed to the agent. It is read the next time one does, and the answer prompt says to use what it means without quoting it.
4. In the same note box, ask for something irreversible, for example *"refund the duplicate 29.00 charge for demo@example.com"*. It parks on a card whose form is generated from the tool's schema. Correct the amount and approve: the corrected value is what runs. A customer can reach a tool the same way, and it parks on the team just the same.
5. Open **Traces**. One tree per run, model calls nested under the node that made them, and what it cost.

### Which lane does what

**The public lane is the customer's.** The agent drafts replies *to the customer*, and only the customer asking something starts a run of its own: a staff note is addressed to colleagues, and a staff reply has already answered. A draft is screened on its way out, and stops for a person when the machine has a reason to want one, which in practice means the ticket tried to talk to the model rather than describe a problem.

**The internal lane is the team's.** Notes to colleagues, questions to the assistant, its answers, its reasoning and the lookups it ran. Staff-only, so nothing there is gated on the way in. A note can be sent with **Send with agent reply**, which asks the assistant in the ticket it is already about, and what it writes back lands in the same lane unless somebody sends it onward through the gate.

There used to be a separate Assistant tab for that second lane: the same thread about the same ticket in a different window, with a **Send to ticket** button to carry an answer back. It is gone, because the ticket is where the work is.

## Regenerating clients after a contract change

```bash
just gen               # everything
just gen-frontend      # OpenAPI + AsyncAPI to TypeScript
just gen-agent-client  # agent AsyncAPI to Python client
```

Each generator reads a live schema, so it starts the service it reads from if that service is not already up.

## Checking out the state a post describes

Each part of the series is pinned to a tag:

```bash
git tag -l
git checkout interrupts
```

`main` is always the latest state, and will be ahead of whatever post you are reading.
