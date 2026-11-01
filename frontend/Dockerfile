# AgenticChief web — build from frontend/:
#   docker build -f frontend/Dockerfile frontend
#
# Dokploy: Dockerfile Path = Dockerfile (or frontend/Dockerfile with context frontend),
#          Docker Context Path = frontend
# Build arg NEXT_PUBLIC_API_URL = public URL of the API (baked into the client bundle).
FROM node:24-slim

RUN corepack enable
WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN pnpm build

EXPOSE 3000
CMD ["pnpm", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
