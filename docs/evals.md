# Evals

```bash
just evals                              # the whole golden set
just evals guardrail                    # names matching "guardrail"
just evals-compare scripted openai_gpt-4o
```

Scenarios live in `agent/evals/scenarios/*.yaml`. Deterministic checks decide by majority across trials; prose criteria go to a cascade judge that runs free substring checks first and a model only when it must.

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
- **Output.** A `screen` node between the drafted answer and the approval gate. A leaked credential, another ticket's id, or the prompt recited back stops the draft before a reviewer is asked. A machine check ahead of the human one.
