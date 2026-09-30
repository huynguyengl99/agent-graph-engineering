# End-to-end smoke

One pass through the product with **nothing mocked**: real Django, real agent,
real models, real browser.

```bash
just infra-up          # postgres + redis
just backend           # :8000
just agent             # :8001
just frontend          # :5173
just e2e               # then this
```

It needs a user to log in as. `just e2e-seed` creates one and a couple of
tickets.

Kept out of `just test` on purpose: it writes to the dev database and spends
real tokens. Run it before a release, and after any dependency upgrade that
touches how models or HTTP clients are built - it has caught several things
the mocked suites structurally cannot.
