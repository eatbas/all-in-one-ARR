#!/usr/bin/env bash
#
# Run the repository's backend, frontend, contract, and build checks from a
# clean, reproducible local entry point.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PY="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  "$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
fi

"$VENV_PY" -m pip install -e "./backend[dev]"

echo "==> Backend lint (ruff)"
(cd backend && "$VENV_PY" -m ruff check .)

echo "==> Backend format check (ruff)"
(cd backend && "$VENV_PY" -m ruff format --check .)

echo "==> Backend type check (mypy)"
(cd backend && "$VENV_PY" -m mypy)

echo "==> Backend tests"
(cd backend && "$VENV_PY" -m pytest)

echo "==> Frontend dependencies"
if [[ "${CI:-}" == "true" ]]; then
  (cd frontend && npm ci)
elif [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi

echo "==> OpenAPI schema and TypeScript types"
"$VENV_PY" scripts/export_openapi.py
(cd frontend && npm run api:types)
git diff --exit-code -- schema/openapi.json frontend/src/shared/lib/generated

echo "==> Frontend lint"
(cd frontend && npm run lint)

echo "==> Frontend format check"
(cd frontend && npm run format:check)

echo "==> Frontend type check"
(cd frontend && npm run test:types -- --pretty false)

echo "==> Frontend tests"
(cd frontend && npm test)

echo "==> Frontend build"
(cd frontend && npm run build)
