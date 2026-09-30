# Eval model sets

One file per model set. `just evals --config <name>` runs the same golden set
on it, and the run is labelled by the model that actually answered, so results
land in separate files and `just evals-compare a b` can diff them.

| Config | decision | answer |
|---|---|---|
| `openai` | `gpt-4o-mini` | `gpt-4o` |
| `claude` | `claude-haiku-4-5` | `claude-sonnet-5` |
| `mixed` | `gpt-5.2` | `claude-sonnet-5` |

`mixed` splits the purposes across providers: the cheaper, faster model decides
and routes, the stronger one writes the customer-facing prose. It is the shape
a production deployment tends to land on once the two jobs are priced
separately.

**The judge is the same model in every config on purpose.** Changing it
changes the scores, so a run judged differently is not comparable to the
others - and judging Anthropic with Anthropic is not a comparison at all.

## Trials

`trials: 1` is the default: fast and cheap for iterating, but a single bad
sample fails a scenario and nothing can be reported as flaky. Three trials
cost about 3x (measured: $0.019 -> $0.055 on the openai set) and let scoring
report a scenario that passed on majority without being unanimous.

```
just evals --trials 3              # settle a result before trusting it
just evals routing --trials 3      # or just the one that keeps moving
```
