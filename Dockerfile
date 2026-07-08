# syntax=docker/dockerfile:1

# ---- Stage 1: build the React dashboard ----
FROM node:26-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime (no Node toolchain) ----
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# Install Python dependencies first for better layer caching. requirements.lock
# pins the exact resolved set (including the APScheduler 4 pre-release) so image
# builds are reproducible; pyproject.toml stays the source of truth for which
# packages are required. Regenerate the lock with:
#   uv pip compile backend/pyproject.toml --all-extras --universal -o backend/requirements.lock
COPY backend/pyproject.toml backend/requirements.lock ./
COPY backend/core ./core
COPY backend/modules ./modules
COPY backend/main.py ./
RUN pip install . -c requirements.lock

# Bring in the built SPA produced by stage 1.
COPY --from=frontend /frontend/dist ./frontend/dist

# Run as a non-root user; data/ holds the SQLite db and the Trakt token store.
RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser /app
USER appuser

# Image metadata; CI (docker/metadata-action) also injects these on published tags.
LABEL org.opencontainers.image.title="all-in-one-ARR" \
      org.opencontainers.image.description="Self-hosted Trakt-to-Seer sync with List-Syncarr, Bandwidth-Controllarr, Findarr and Deletarr modules" \
      org.opencontainers.image.source="https://github.com/eatbas/all-in-one-ARR" \
      org.opencontainers.image.licenses="MIT"

EXPOSE 3223

# python:3.11-slim ships python3 only (no `python` symlink) and no curl/wget, so
# the healthcheck probes /health with the standard library; any error exits 1
# quietly (no traceback in the container health log).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python3", "-c", "import urllib.request, sys\ntry: sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3223/health', timeout=3).status == 200 else 1)\nexcept Exception: sys.exit(1)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3223"]
