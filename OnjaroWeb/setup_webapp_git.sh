#!/bin/bash
# Setup the webapp/ GitHub remote ONCE before first run.
# Usage: ./setup_webapp_git.sh https://github.com/Sabolo100/YOUR-WEBAPP-REPO.git

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEBAPP_DIR="$SCRIPT_DIR/webapp"
REMOTE_URL="$1"

if [ -z "$REMOTE_URL" ]; then
    echo "Usage: ./setup_webapp_git.sh <github-repo-url>"
    echo "Example: ./setup_webapp_git.sh https://github.com/Sabolo100/BikeWeb.git"
    exit 1
fi

echo "Setting up webapp git remote..."
echo "  Webapp dir: $WEBAPP_DIR"
echo "  Remote URL: $REMOTE_URL"

mkdir -p "$WEBAPP_DIR"

if [ ! -d "$WEBAPP_DIR/.git" ]; then
    git -C "$WEBAPP_DIR" init -b main
    git -C "$WEBAPP_DIR" config user.email "onjaro-bot@evolution.local"
    git -C "$WEBAPP_DIR" config user.name "Onjaro Evolution Bot"
    echo "  Git repo initialized"
fi

# Add or update remote
git -C "$WEBAPP_DIR" remote remove origin 2>/dev/null || true
git -C "$WEBAPP_DIR" remote add origin "$REMOTE_URL"
echo "  Remote 'origin' set to $REMOTE_URL"

echo ""
echo "Done. The system will push to $REMOTE_URL on every successful run."
echo "Make sure the GitHub repo exists and is empty before starting."
