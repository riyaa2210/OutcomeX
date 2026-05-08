# ── Frontend Dockerfile ───────────────────────────────────────────────────────
# Multi-stage: node builder → nginx runtime
# Final image: nginx:alpine (~25 MB)

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first (layer cache)
COPY package.json package-lock.json ./

# Install deps (ci = reproducible, faster than install)
RUN npm ci --prefer-offline

# Copy source
COPY . .

# Build args for environment injection at build time
ARG VITE_API_URL
ARG VITE_API_BASE_URL
ARG VITE_WS_URL

ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_URL=${VITE_WS_URL}

RUN npm run build

# ── Stage 2: nginx runtime ────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

LABEL maintainer="OutcomeX Team"
LABEL org.opencontainers.image.title="outcomex-frontend"

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/health || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
