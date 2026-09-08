#!/usr/bin/env bash
# KinTales Dev Stack Launcher
# Starts KinTales FastAPI Backend (Port 8001) and Frontend HTTP Server (Port 3000)

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=== Starting KinTales Services ==="

# Check backend venv
if [ ! -f "$DIR/backend/.venv/bin/python" ]; then
    echo "Creating backend virtualenv..."
    python3 -m venv "$DIR/backend/.venv"
    "$DIR/backend/.venv/bin/pip" install -r "$DIR/backend/requirements.txt"
fi

# Kill any previous processes on 8001 or 3000
pkill -f "main:app.*8001" 2>/dev/null
pkill -f "http.server 3000" 2>/dev/null

# 1. Start Backend on Port 8001
echo "Starting KinTales Backend on http://127.0.0.1:8001..."
cd "$DIR/backend"
"$DIR/backend/.venv/bin/python" -m uvicorn main:app --host 127.0.0.1 --port 8001 > "$DIR/backend/backend.log" 2>&1 &
BACKEND_PID=$!
echo "Backend running (PID: $BACKEND_PID, logs: backend/backend.log)"

# 2. Start Frontend Server on Port 3000
echo "Starting KinTales Frontend on http://localhost:3000..."
cd "$DIR"
python3 -m http.server 3000 > "$DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "Frontend running (PID: $FRONTEND_PID, logs: frontend.log)"

sleep 1

# Health check
echo "Verifying services..."
if curl -s http://127.0.0.1:8001/api/status | grep -q "online"; then
    echo "✅ KinTales Backend: ONLINE (http://127.0.0.1:8001)"
else
    echo "⚠️ KinTales Backend not responding yet. Check backend/backend.log"
fi

if curl -s -I http://localhost:3000 | grep -q "200 OK"; then
    echo "✅ KinTales Frontend: ONLINE (http://localhost:3000)"
else
    echo "⚠️ KinTales Frontend not responding yet. Check frontend.log"
fi

echo ""
echo "🚀 Open in your browser: http://localhost:3000"
