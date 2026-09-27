# The web image. Build the bundle with Node, serve it with nginx — the runtime
# carries no Node, no node_modules and no source, only static files.

# --- build ------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /build
# Dependencies first: this layer is cached unless the lockfile moves, so an
# edit to a component does not reinstall the world.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# The API base URL is baked in at build time — Vite inlines import.meta.env, so
# it cannot be changed by an environment variable on the running container. The
# compose file passes the value the stack actually uses.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# --- runtime ----------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY --from=build /build/dist /usr/share/nginx/html

# A template, not a finished config: the entrypoint runs envsubst over
# /etc/nginx/templates/*.template into /etc/nginx/conf.d/ before nginx starts.
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Restrict the substitution to `CSP_` names. Without this, envsubst would also
# replace nginx's own `$uri` and `$host` with empty strings and the try_files
# rule would stop serving the SPA — which is the classic way this feature
# breaks a working config.
ENV NGINX_ENVSUBST_FILTER=CSP_

# Where the browser is allowed to send requests: the API over http(s) and the
# live-price socket over ws(s). The default matches the compose stack, whose
# browser-facing API is localhost:8000. A single-origin deployment (the API
# serving the built SPA) narrows this to `'self'`; a split-origin one names
# the API host explicitly. It is deliberately not `*`.
ENV CSP_CONNECT_SRC="'self' http://localhost:8000 ws://localhost:8000"

EXPOSE 80

# 127.0.0.1, not localhost: that resolves to ::1 first and nginx's `listen 80`
# binds IPv4 only, so the check is refused while the server is serving happily.
# The container then sits unhealthy forever and anything waiting on
# `service_healthy` never starts.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
