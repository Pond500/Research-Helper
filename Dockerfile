# ---- deps stage ----
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- build stage ----
FROM node:22-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# These build args are baked into the Next.js standalone bundle at build time.
# next.config.mjs rewrites and NEXT_PUBLIC_* client vars are resolved here.
ARG REMOTE_ACTION_URL=http://localhost:2024/copilotkit
ARG AGENT_INTERNAL_URL=http://localhost:2024
ARG NEXT_PUBLIC_AGENT_URL=/api/agent/research_agent

ENV REMOTE_ACTION_URL=$REMOTE_ACTION_URL
ENV AGENT_INTERNAL_URL=$AGENT_INTERNAL_URL
ENV NEXT_PUBLIC_AGENT_URL=$NEXT_PUBLIC_AGENT_URL

# Ensure public dir exists even if empty (Next.js standalone requires it)
RUN mkdir -p public
RUN npm run build

# ---- runner stage ----
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public

RUN mkdir -p .next && chown nextjs:nodejs .next

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
