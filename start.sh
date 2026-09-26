#!/usr/bin/env bash
# VoxForge one-command launcher.
# Boots the self-hosted voice backend + the web dev server together, installs
# anything missing on first run, and shuts both down cleanly on Ctrl+C.
#
#   ./start.sh            # install (if needed) + run both
#   ./start.sh --setup    # only install dependencies, don't run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WEB="$ROOT/web"
SERVER="$ROOT/server"
VENV="$SERVER/.venv"
PY="$VENV/bin/python"
WEB_PORT=5173
API_PORT=8000

c_blue() { printf "\033[1;34m%s\033[0m\n" "$1"; }
c_green() { printf "\033[1;32m%s\033[0m\n" "$1"; }

# --- 1. Install dependencies if missing ----------------------------------- #
if [ ! -d "$WEB/node_modules" ]; then
  c_blue "==> Installing web dependencies…"
  (cd "$WEB" && npm install)
fi

if [ ! -x "$PY" ]; then
  c_blue "==> Creating Python venv…"
  # Prefer 3.12/3.13: the Piper neural voice (onnxruntime) has no 3.14 wheel.
  # Falls back to whatever python3 is available (macOS `say` still works there).
  PYBIN="$(command -v python3.12 || command -v python3.13 || command -v python3)"
  "$PYBIN" -m venv "$VENV"
fi
if ! "$PY" -c "import starlette, uvicorn" >/dev/null 2>&1; then
  c_blue "==> Installing backend dependencies…"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r "$SERVER/requirements.txt"
fi

if [ "${1:-}" = "--setup" ]; then
  c_green "Setup complete. Run ./start.sh to launch."
  exit 0
fi

# --- 1b. Ensure PostgreSQL is running + the database exists ----------------- #
DB_NAME="${VOXFORGE_DB_NAME:-ayaanvoice}"
if command -v pg_isready >/dev/null 2>&1; then
  if ! pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
    c_blue "==> Starting PostgreSQL…"
    if command -v brew >/dev/null 2>&1; then
      brew services start "$(brew list 2>/dev/null | grep -m1 '^postgresql' || echo postgresql)" >/dev/null 2>&1 || true
    fi
    for _ in $(seq 1 20); do
      pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1 && break; sleep 1
    done
  fi
  if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
    createdb "$DB_NAME" >/dev/null 2>&1 || true   # no-op if it already exists
  else
    echo "!! PostgreSQL is not reachable on 127.0.0.1:5432 — the backend needs it."
    echo "   Start it (e.g. 'brew services start postgresql@18') and re-run."
  fi
else
  echo "!! psql not found — install PostgreSQL (brew install postgresql@18)."
fi

# --- 2. Free the ports (in case a previous run is lingering) --------------- #
for port in $WEB_PORT $API_PORT; do
  pids="$(lsof -ti:"$port" 2>/dev/null || true)"
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
done

# --- 3. Launch both, tear down together ----------------------------------- #
pids=()
cleanup() {
  c_blue "\n==> Shutting down…"
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

c_blue "==> Starting backend  → http://127.0.0.1:$API_PORT"
# HF_HUB_OFFLINE: all models are cached locally, so never hit the network (or
# need a token) at runtime — important for the gated Parler model.
( cd "$SERVER" && HF_HUB_OFFLINE=1 exec "$VENV/bin/uvicorn" app:app \
    --host 127.0.0.1 --port "$API_PORT" ) &
pids+=($!)

c_blue "==> Starting frontend → http://localhost:$WEB_PORT"
( cd "$WEB" && exec npm run dev ) &
pids+=($!)

c_green "\nVoxForge is running. Open http://localhost:$WEB_PORT  (Ctrl+C to stop)"
wait
