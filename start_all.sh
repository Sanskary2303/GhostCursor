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
    echo "❌ Virtualenv not found at .venv. Creating..."
    python3 -m venv .venv
fi

.venv/bin/pip install -q -e packages/sdk-server-python
.venv/bin/pip install -q -r services/orchestrator/requirements.txt
.venv/bin/pip install -q -r demo/shophive/backend/requirements.txt

if [ ! -d node_modules ]; then npm ci; fi

# Build Frontend SDK
echo "📦 Building Frontend SDK..."
npm run build --workspace=packages/sdk-frontend
npm run build --workspace=packages/sdk-react

# Build ShopHive Frontend
echo "📦 Building ShopHive Storefront Frontend..."
npm run build --workspace=demo/shophive/frontend

for port in 8080 8081; do
  if (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null; then echo "Port $port is in use; stop that process first."; exit 1; fi
done

KEY="$("$VENV_PYTHON" -c 'import secrets; print(secrets.token_hex(32))')"
export GHOST_CURSOR_API_KEY="$KEY"
export GHOST_TENANT_KEYS="{\"$KEY\": \"shophive_demo\"}"
export GHOST_PROVIDER=mock GHOST_STORE=memory
export GHOST_RATE_LIMIT_PER_MIN="${GHOST_RATE_LIMIT_PER_MIN:-100000}"
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

