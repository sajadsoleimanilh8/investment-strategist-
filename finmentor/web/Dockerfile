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
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null || exit 1
