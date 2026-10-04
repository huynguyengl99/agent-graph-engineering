# Testing

```bash
just test    # backend, agent, and web suites
just check   # every project's checks in parallel
just fix     # the same set, writing the fixes it can
```

`just check` runs twelve checks at once and prints a summary, then the output of
only the ones that failed - a change that breaks two projects should not take
two runs to find. `just check ba` narrows it to the backend and the agent, and
`just check -e w` excludes the web app.

Python is checked twice, by mypy and by pyright, because they disagree
usefully: mypy understands Django through django-stubs, and pyright caught a
non-exhaustive `match` and a dead function that mypy passed over. Each one's
config turns off the rules that report the framework rather than this code.

Agent tests mock the LLM at the HTTP layer rather than stubbing Pydantic AI, so the real pipeline runs: SSE parsing, tool call assembly, streaming, and validation. Web tests swap only the socket, through chanx-js's `socketFactory`, so the client's framing and routing run for real. Evals against real models live separately and never run in CI, because they cost money.

## End-to-end

```bash
just seed       # the two accounts and some tickets
just e2e        # with all three services running
```

One pass through the product with **nothing mocked**: real Django, real agent,
real models, real browser. Kept out of `just test` because it writes to the dev
database and spends tokens.

It earns its place by catching what the mocked suites structurally cannot - a
Zodios client that threw on import, a create endpoint that returned no `id`,
a dependency upgrade that changed how models are constructed. Run it after any
of those.
