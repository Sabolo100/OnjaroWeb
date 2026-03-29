#!/bin/bash
# Onjaro Evolution System - Start Script
# Usage: ./start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Onjaro Autonomous Evolution System"
echo "=========================================="
echo ""
echo "Project root: $SCRIPT_DIR"
echo "Dashboard:    http://localhost:5555"
echo ""

# ── Guard: kill any already-running orchestrator instances ──────────────────
EXISTING=$(pgrep -f "orchestrator.main" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
    echo "⚠️  Futó orchestrator process(ek) találhatók: $EXISTING"
    echo "   Leállítás..."
    kill $EXISTING 2>/dev/null || true
    sleep 2
    # Force-kill if still alive
    STILL=$(pgrep -f "orchestrator.main" 2>/dev/null || true)
    if [ -n "$STILL" ]; then
        kill -9 $STILL 2>/dev/null || true
        sleep 1
    fi
    echo "   Régi process(ek) leállítva."
    echo ""
fi

# ── Remove stale lock files ─────────────────────────────────────────────────
LOCK_FILE="$SCRIPT_DIR/data/.research.lock"
if [ -f "$LOCK_FILE" ]; then
    echo "   Régi research lock fájl törölve: $LOCK_FILE"
    rm -f "$LOCK_FILE"
fi
EVOL_LOCK="$SCRIPT_DIR/data/.lock"
if [ -f "$EVOL_LOCK" ]; then
    echo "   Régi evolution lock fájl törölve: $EVOL_LOCK"
    rm -f "$EVOL_LOCK"
fi

# ── Load .env for display ───────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a; source "$SCRIPT_DIR/.env"; set +a
fi

EVOL_STATUS=$([ "${EVOLUTION_ENABLED:-1}" = "1" ] && echo "BE" || echo "KI")
RESRCH_STATUS=$([ "${RESEARCH_ENABLED:-1}" = "1" ] && echo "BE" || echo "KI")
STARTUP_STATUS=$([ "${RUN_ON_STARTUP:-0}" = "1" ] && echo "igen" || echo "nem")

echo "Evolution AI:  $EVOL_STATUS"
echo "Research AI:   $RESRCH_STATUS"
echo "Run on start:  $STARTUP_STATUS"
echo ""
echo "Módosítás: .env  ->  EVOLUTION_ENABLED / RESEARCH_ENABLED / RUN_ON_STARTUP"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Ensure Python path includes project root
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Start the orchestrator
python3 -m orchestrator.main
