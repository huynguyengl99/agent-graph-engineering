# Containers

```bash
just images      # build the three images
just app-up      # run them on top of the infrastructure, on http://localhost:8080
just app-down
```

Three images built from the repo root, because the uv and pnpm locks are
workspace locks. The web image is nginx serving the built app and proxying
`/api`, `/ws`, `/admin` and `/static` to the backend, because the app resolves
both its API and its socket from `location.host`: same origin means no CORS and
no build-time base URL to get wrong per environment.

The agent publishes no port. Only the backend calls it, and nginx proxies just
its two read-only documentation paths, `/agent/graphs` and `/agent/asyncapi`,
with the shared token added server side so the browser never holds it. Traces are
not among them: those go through the admin, behind staff auth.

Building the images is how four things got found, all of them invisible in
development because the workspace shares one virtualenv:

- `daphne` was in `INSTALLED_APPS` and in the dev dependency group, so a
  production install could not import settings at all. It is only there so
  `runserver` speaks ASGI, and granian does not need it.
- The backend used `httpx` without declaring it, and the agent used `psycopg`
  and `redis` without declaring them. Each was satisfied by a sibling package in
  the shared venv.
- Browsers send `Origin` on form posts and Django checks it, so the admin login
  failed behind the proxy with a bare "CSRF verification failed". Only in a
  browser: `curl` sends no `Origin`, so it passed. `CSRF_TRUSTED_ORIGINS` has to
  name the app's origin rather than the backend's.
