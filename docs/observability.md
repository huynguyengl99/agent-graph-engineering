# Observability

Every graph node opens a span and Pydantic AI nests its model calls underneath, so one run reads as a tree rather than a list of completions. It is the **Traces** tab in the console, beside Graphs: whoever asks why it answered that is the person who just watched it answer, and they are already there.

The agent serves the spans as JSON and the console renders them. It also decides which of a span's attributes are worth reading - which OpenTelemetry and Pydantic AI keys are noise is knowledge about the tracer, not about the page - so the rest collapse behind a count and expand on demand.

Where they go afterwards is one setting, `ASSISTANT_TRACE_EXPORT`: `local` writes a file per run under `ASSISTANT_TRACE_DIR`, `otlp` forwards to `OTEL_EXPORTER_OTLP_ENDPOINT`, `both` does both, `off` keeps nothing past the process. `both` is worth having rather than either: the files are the graph-shaped view, and a collector is where you keep things and compare runs. There is a test with a fake collector proving the request lands with its auth header intact.

It used to be inferred - a blank `ASSISTANT_TRACE_DIR` meant memory only, a blank endpoint meant no forwarding - which is two switches describing four states and no way to say "forward, do not write files". Asking to forward with no endpoint is now refused at startup instead of starting cleanly and sending nothing, which looks exactly like a collector that is not receiving.

## Traces carry the prompt

`gen_ai.input.messages` holds the customer's own words, because that is what was sent to the model. Two consequences:

- The files stay on the machine that produced them and keep everything. Seeing what the model was actually sent is the reason to keep a trace.
- `ASSISTANT_TRACE_REDACT_EXPORTS=true` strips message bodies on the way to a collector, leaving the shape: which node, how long, which model, what it decided, what it cost. Off by default, because a dashboard showing `[redacted]` everywhere is not worth having. Turn it on when the collector is somewhere you do not control.

Node spans record what the node decided, not what it wrote. Short scalars and the class name of a typed output; prose is skipped by length, so a drafted reply never reaches the trace store.

## Taking this to production

Files per run are the right shape for traces, and object storage is the same shape: write-once, read-rarely, always read by run. No index to maintain, nothing to vacuum, and retention becomes a lifecycle rule on the bucket rather than a cleanup job you write.

Two things to settle before swapping the backend, because neither is a detail:

**Appending does not exist.** S3 has no append, and GCS has `compose`, which concatenates objects rather than extending one. Writing a line per span as it finishes works on a local disk and does not port. The options, in rough order of how well they hold up:

| Approach | Crash safety | Cost |
|---|---|---|
| Local file as a write-ahead log, upload once at run end | spans survive a crash locally | one PUT per run |
| Rewrite the whole object per span | nothing lost | N PUTs, each rewriting a growing blob |
| One object per span | nothing lost | many small objects, read is list plus N gets |
| Buffer in memory, write at run end | a crash loses the whole run | one PUT per run |

The last is the tempting one and the worst, because a crashed run is exactly when the trace is worth having.

**The key layout decides whether erasure is possible.** Retention is free either way. Erasure is not: `traces/<run-id>.json` makes "delete everything about this customer" a full scan, while a prefix you can list by makes it a list and delete. That choice is cheap now and expensive once the bucket is full. Redacting at write time is cheaper still, because there is then little to erase.
