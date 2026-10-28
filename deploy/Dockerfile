# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS backend
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --create-home trainer
WORKDIR /app
COPY --from=backend --chown=trainer:trainer /app /app
COPY --from=frontend --chown=trainer:trainer /src/frontend/dist /app/frontend
COPY --chown=trainer:trainer content /app/content
COPY --chown=trainer:trainer personas /app/personas
COPY --chown=trainer:trainer corpus /app/corpus
COPY --chown=trainer:trainer frontend/src/assets/fonts /app/fonts
COPY --chown=trainer:trainer tools/account.py /app/tools/account.py
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    CONTENT_DIR=/app/content \
    PERSONAS_DIR=/app/personas \
    CORPUS_DIR=/app/corpus \
    FRONTEND_DIST=/app/frontend \
    FONTS_DIR=/app/fonts
USER trainer
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live')"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
