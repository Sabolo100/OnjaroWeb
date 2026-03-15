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
echo "Dashboard: http://localhost:5555"
echo "Run interval: 30 minutes"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Ensure Python path includes project root
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Start the orchestrator
python3 -m orchestrator.main
