# AgenticChief web — build from frontend/:
#   docker build -f frontend/Dockerfile frontend
#
# Dokploy:
#   Dockerfile Path      = Dockerfile
#   Docker Context Path  = frontend
#   Domain               = chro.lokibots.ai
#   Build arg            = NEXT_PUBLIC_API_URL=https://chro.lokibots.ai
FROM node:24-slim

RUN corepack enable
WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

ARG NEXT_PUBLIC_API_URL=https://chro.lokibots.ai
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN pnpm build

EXPOSE 3000
CMD ["pnpm", "start"]
