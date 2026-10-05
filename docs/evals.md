# Evals

```bash
just evals                              # the whole golden set
just evals guardrail                    # names matching "guardrail"
just evals-compare scripted openai_gpt-4o
just evals-coverage                     # which tools a scenario asserts
```

Scenarios live in `agent/evals/scenarios/*.yaml`. Deterministic checks decide by majority across trials; prose criteria go to a cascade judge that runs free substring checks first and a model only when it must.

`just evals-coverage` answers a different question: which tools a scenario has
ever actually asserted. A passing suite says nothing about the tool nobody
wrote a scenario for, and that gap is invisible from the summary - every
scenario can pass while the riskiest tool has never been chosen by a model.

It counts only the tools a planner may choose. `search_knowledge_base` is
registered but not offered: the knowledge branch calls it directly with a
refine loop around it, so offering it to the planner as well was a second route
to the articles with no second attempt - and a tool no model can pick is one no
scenario can assert.

It runs with **no API key**: the scripted model keeps the deterministic checks real, unassessed criteria are reported as *skipped* rather than scored, and runs are labelled by the model that actually ran. Cost comes from the spans the tracer already collects, and a model with no price table reports its tokens with `priced: false` rather than a misleading $0.00.

## Choosing the models

Purposes are system config and the models filling them are user config, which
is what keeps provider independence real rather than theoretical. `/settings`
writes a preference per purpose; unset purposes fall through to the
deployment default. `provider:name` is validated server-side, and the field
error lands on the field.

## Guardrails

Two guards with different jobs, both in `agent/assistant/guardrails/`:

- **Input.** Customer-written ticket fields are fenced as data with an explicit "never as instructions" boundary, and the fence is stripped from the text so it cannot be closed from inside. Known injection shapes are *recorded, never blocked* - a desk that refuses tickets containing "ignore" is broken, and a warning everyone learns to skip is worse than none.
- **Output.** A `screen` node on every draft, before it is sent or shown to a reviewer. A leaked credential, another ticket's id, or the prompt recited back stops the draft outright - every finding it can make is severe enough to. It also decides who reads the reply first: a ticket the *input* screen flagged puts its answer in front of a person instead of the customer.
