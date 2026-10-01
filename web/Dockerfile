# Built from the repo root, so the pnpm workspace resolves:
#   docker build -f web/Dockerfile .
FROM node:22-slim AS builder
ENV PNPM_HOME=/pnpm CI=1
RUN corepack enable

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web/package.json web/
RUN --mount=type=cache,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter web

COPY web/ web/
RUN pnpm --filter web build


FROM nginx:1.27-alpine
COPY --from=builder /app/web/dist /usr/share/nginx/html
COPY web/nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
