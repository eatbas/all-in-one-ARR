# syntax=docker/dockerfile:1

# ---- Stage 1: build the React dashboard ----
FROM node:20-slim AS frontend
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

# Install Python dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY core ./core
COPY modules ./modules
COPY main.py ./
RUN pip install .

# Bring in the built SPA produced by stage 1.
COPY --from=frontend /frontend/dist ./frontend/dist

# Run as a non-root user; data/ holds the SQLite db and the Trakt token store.
RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser /app
USER appuser

EXPOSE 3223
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3223"]
