# frontend/Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Multi-stage Next.js build.
#
# WHY MULTI-STAGE?
#   Stage 1 (deps):   installs ALL node_modules including devDependencies
#   Stage 2 (builder): builds the Next.js production bundle
#   Stage 3 (runner):  final image — only the built output + production deps
#
#   Result: final image is ~400 MB instead of ~1.2 GB if we kept everything.
#   Build tools (TypeScript compiler, webpack, etc.) are NOT in the final image.
#
# HOW NEXT.JS STANDALONE OUTPUT WORKS:
#   next.config.ts sets output: 'standalone'.
#   This makes Next.js bundle only the files the app actually needs,
#   with no need for node_modules in the final image except a small subset.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Install dependencies ────────────────────────────────────────────
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

# ── Stage 2: Build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_ vars must be available at BUILD TIME (they get inlined into JS)
# We use a placeholder here; the real value is set at runtime via environment
# variable in docker-compose. Next.js 14 supports runtime env vars for
# server components — but for client components we pass a build-time placeholder
# and override with NEXT_PUBLIC_API_URL at runtime.
ENV NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ── Stage 3: Production runner ────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Non-root user for security
RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

# Copy built output
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD wget -qO- http://localhost:3000/api/health 2>/dev/null || exit 1

CMD ["node", "server.js"]
