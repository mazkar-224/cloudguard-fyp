# syntax=docker/dockerfile:1

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — build: compile the Vite/React app into static files.
# ─────────────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app

# Copy lockfile first so `npm ci` caches until dependencies change.
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the source and produce the optimized static bundle in /app/dist.
COPY . .
RUN npm run build


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — serve: nginx serves the static bundle, proxies /api to the backend,
# and falls back to index.html for client-side (history-mode) routing.
# ─────────────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Replace the default server block with our SPA + API-proxy config.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Static build output is all we ship from the build stage.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# Simple liveness probe — the SPA shell must be served.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
