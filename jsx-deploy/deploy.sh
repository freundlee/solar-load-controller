#!/usr/bin/env bash
# deploy.sh — push & redeploy jsx-app on a remote Linux VPS
# Usage: ./deploy.sh [user@host] [remote_dir]
#
# Example: ./deploy.sh root@1.2.3.4 /opt/jsx-app

set -euo pipefail

REMOTE="${1:-}"
REMOTE_DIR="${2:-/opt/jsx-app}"

if [[ -z "$REMOTE" ]]; then
  echo "Usage: $0 user@host [remote_dir]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "▶ Syncing files to $REMOTE:$REMOTE_DIR ..."
rsync -az --delete \
  --exclude 'app/node_modules' \
  --exclude 'app/dist' \
  "$SCRIPT_DIR/" "$REMOTE:$REMOTE_DIR/"

echo "▶ Building & restarting container on $REMOTE ..."
ssh "$REMOTE" bash -s << EOF
  set -e
  cd "$REMOTE_DIR"
  docker compose build --no-cache
  docker compose up -d --remove-orphans
  docker image prune -f
  echo "✔ Deployed. Running containers:"
  docker compose ps
EOF

echo "✔ Done. App is at http://$REMOTE:3000"
