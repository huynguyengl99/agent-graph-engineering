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
just up          # everything, in the background, waiting until each answers
just status      # which are up
just logs a      # follow one of them (b backend, a agent, k worker, w web)
just down        # stop them and free the ports
```

`just up k` starts the Celery worker alone, which is what you want when you
are changing a task: `just down k && just up k` picks up your edit and the web
services keep running. The worker listens on nothing, so `just status` judges
it by whether its process is alive rather than by a health check.

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

The worker has no `just` recipe of its own because there is nothing to watch
but its log:

```bash
cd backend && uv run celery -A helpdesk.config worker --pool=threads -c 8 -Q agent_runs -l info
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

## The worker

Asking for a run does not run it. `start_run`, `start_approval` and
`start_tool_decision` put a Celery task on the queue and return; a worker picks
it up and drives the agent. Three tasks, matching the three ways a run starts,
and each one is a shell around the service function that already did the work.

```bash
celery -A helpdesk.config worker --pool=threads --concurrency=8 -Q agent_runs -l info
```

**Why a thread pool rather than the default.** A run is tens of seconds of
waiting on a model. Celery's prefork pool would hold a whole process for each
one, so eight concurrent runs would mean eight Django processes. Eight threads
hold eight runs in one process, because the waiting is what they are doing.

**Why `asyncio.run` inside each task.** The run is one WebSocket conversation
with the agent from start to finish and the relay opens its own connection
anyway, so there is nothing to keep warm between tasks.

### The three settings that decide whether a kill loses a run

These are the reason this page exists. Celery's defaults are built for short
idempotent tasks and are wrong here in a way that shows up the first time a
worker is killed mid-run.

| Setting | Here | Why |
| --- | --- | --- |
| `task_acks_late` | `True` | Acknowledge when the run finishes, not when it is picked up. On the default, a `kill -9` drops the task silently: it was acked on delivery and nothing is left to redeliver. |
| `task_reject_on_worker_lost` | `True` | Makes that true for a hard kill too, not only a clean shutdown. |
| `visibility_timeout` | 3600s | Redis has no server-side ack, so redelivery after a lost worker runs on this timer. It has to outlast both the longest run and `AGENT_RUN_CLAIM_TIMEOUT`: expire early and a running task is handed to a second worker too; expire before the lane goes stale and the redelivered run no-ops and acks, losing the work. |

It is a floor, not a schedule. The timeout says when a message becomes
*eligible* to be handed on; kombu sweeps for eligible messages on one call in
ten of its polling cycle (`restore_visible(..., interval=10)`), so the
hand-over lands well after it. `just crash-test` measures it: with the timeout
turned down to 10s, a killed worker's task came back after **91s**. Read the
hour here as "not before an hour", and a run lost to a hard kill as something
a person notices first. A sweeper that finds threads still waiting and picks
them up is the missing piece, and it is in the README's list of what is owed.

Retrying is safe because of two things that have nothing to do with Celery: a
redelivered task carries the state its run started from, so the agent carries on
rather than starting the thread over, and anything irreversible goes through the
at-most-once ledger. A queue without those two would make a redelivered refund a
second refund.

The third thing is the lane the dead run was holding. A redelivered task finds
that claim still there and takes it over once it has gone stale, and a question
that queued behind the dead run is kept rather than cleared, because nothing
has answered it and the recovering run is working something else. The customer's
lane queues no question - their message is on the ticket and a re-run reads the
thread - so only a question is carried over, and the same thread is not worked
twice. `agent_runs/tests/test_redelivery.py` drives all of it through `run`.

