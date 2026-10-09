# Documentation

The repository README is the orientation. These are the parts worth reading on
their own, roughly in the order they become interesting.

| Page | What it covers |
|---|---|
| [Running it](running.md) | Prerequisites, the commands, swapping models, and a walkthrough of both lanes with the two seeded accounts |
| [Architecture](architecture.md) | What each service owns, the agent's boundary, how the two stay in sync, and the generated contracts that keep them honest |
| [Graphs and subgraphs](graphs.md) | The one graph and its three subgraphs, which drafts stop for a person, and the forms generated from a schema |
| [Evals](evals.md) | The golden set, the cascade judge, choosing the models, and the guardrails either side of them |
| [Observability](observability.md) | Per-run traces, what a span is allowed to carry, and what to settle before moving them to object storage |
| [Testing](testing.md) | What each suite mocks, and the end-to-end pass that mocks nothing |
| [Containers](containers.md) | The three images, and the four faults building them found |

`AGENTS.md` at the root and in each service is written for coding agents rather
than for people: conventions, invariants and the reasons behind them.
