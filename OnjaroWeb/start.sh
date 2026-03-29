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

# Load .env for display
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
