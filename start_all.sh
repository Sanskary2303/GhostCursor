#!/usr/bin/env bash
set -e

# Ghost Cursor - Full Stack Runner
# Starts Hosted Orchestrator (port 8080) and ShopHive Demo App (port 8081)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "👻 Starting Ghost Cursor Full Stack Prototype"
echo "=========================================================="

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Virtualenv not found at .venv. Creating and installing..."
    python3 -m venv .venv
    .venv/bin/pip install -e packages/sdk-server-python
    .venv/bin/pip install -r services/orchestrator/requirements.txt
    .venv/bin/pip install -r demo/shophive/backend/requirements.txt
fi

# Build Frontend SDK if needed
if [ ! -f "packages/sdk-frontend/dist/ghost-cursor.es.js" ]; then
    echo "📦 Building Frontend SDK..."
    npm run build --workspace=packages/sdk-frontend
fi

# Build ShopHive Frontend if needed
if [ ! -f "demo/shophive/frontend/dist/index.html" ]; then
    echo "📦 Building ShopHive Storefront Frontend..."
    npm run build --workspace=demo/shophive/frontend
fi

# Kill any existing processes on 8080 or 8081
fuser -k 8080/tcp 2>/dev/null || true
fuser -k 8081/tcp 2>/dev/null || true

export USE_MOCK_LLM="${USE_MOCK_LLM:-true}"
export GHOST_CURSOR_API_KEY="${GHOST_CURSOR_API_KEY:-test-key-shophive-demo}"
export GHOST_CURSOR_SERVICE_URL="${GHOST_CURSOR_SERVICE_URL:-http://127.0.0.1:8080}"
export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/packages/sdk-server-python:$SCRIPT_DIR/demo/shophive/backend"

echo "🚀 Starting Ghost Cursor Orchestrator on http://127.0.0.1:8080 ..."
"$VENV_PYTHON" -m uvicorn services.orchestrator.app.main:app --host 127.0.0.1 --port 8080 &
ORCH_PID=$!

echo "🚀 Starting ShopHive Storefront on http://127.0.0.1:8081 ..."
"$VENV_PYTHON" -m uvicorn demo.shophive.backend.main:app --host 127.0.0.1 --port 8081 &
SHOP_PID=$!

cleanup() {
    echo ""
    echo "🛑 Shutting down Ghost Cursor services..."
    kill "$ORCH_PID" 2>/dev/null || true
    kill "$SHOP_PID" 2>/dev/null || true
    wait "$ORCH_PID" 2>/dev/null || true
    wait "$SHOP_PID" 2>/dev/null || true
    echo "✅ Shutdown complete."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo "=========================================================="
echo "✨ Ghost Cursor is LIVE!"
echo "   - ShopHive Storefront:  http://127.0.0.1:8081"
echo "   - Hosted Orchestrator:  http://127.0.0.1:8080"
echo "   - Test Health Check:    http://127.0.0.1:8080/health"
echo "   - Press Ctrl+C to stop both services."
echo "=========================================================="

wait

