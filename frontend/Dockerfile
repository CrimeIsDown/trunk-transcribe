FROM node:24-alpine AS base

# Check https://github.com/nodejs/docker-node/tree/b4117f9333da4138b03a546ec926ef50a31506c3#nodealpine to understand why libc6-compat might be needed.
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Install full dependency tree for the build
FROM base AS deps
COPY package.json package-lock.json* ./
RUN \
  if [ -f package-lock.json ]; then npm install; \
  else echo "Lockfile not found." && exit 1; \
  fi

# Build the Tanstack Start application
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json* ./
COPY vite.config.ts tsconfig.json biome.json ./
COPY public ./public
COPY src ./src
COPY .env ./
RUN npm run build

# Install runtime dependencies only
FROM base AS prod-deps
COPY package.json package-lock.json* ./
RUN \
  if [ -f package-lock.json ]; then npm install --omit=dev; \
  else echo "Lockfile not found." && exit 1; \
  fi

# Production image, copy all the files and run the server
FROM base AS runner
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 tanstack

COPY --from=prod-deps /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/.output ./.output
COPY --from=builder /app/public ./public

USER tanstack

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start the Tanstack Start server (node .output/server/index.mjs)
CMD ["npm", "run", "start"]
