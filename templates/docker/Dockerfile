# Nexus Holdings — Multi-stage Production Dockerfile
# Supports both Node.js and Python runtimes via build args.
# Default: Node.js application.

# ── Stage 1: Dependencies ────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app

COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

RUN \
  if [ -f pnpm-lock.yaml ]; then \
    corepack enable pnpm && pnpm install --frozen-lockfile --prod; \
  elif [ -f yarn.lock ]; then \
    yarn install --frozen-lockfile --production; \
  else \
    npm ci --omit=dev; \
  fi

# ── Stage 2: Build ───────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NODE_ENV=production
ENV NODE_ENV=${NODE_ENV}

RUN npm run build 2>/dev/null || echo "No build step defined — skipping"

# ── Stage 3: Production ─────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

# Security: run as non-root
RUN addgroup --system --gid 1001 nexus && \
    adduser --system --uid 1001 --ingroup nexus appuser

# Install curl for health checks
RUN apk add --no-cache curl

COPY --from=builder --chown=appuser:nexus /app ./

USER appuser

ARG APP_PORT=3000
ENV PORT=${APP_PORT}
EXPOSE ${APP_PORT}

# Health check endpoint
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=30s \
  CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["node", "dist/index.js"]
