#!/bin/bash
# Promonta miniapp deploy — syncs repo → VPS (backend + frontend), with
# backups and a syntax check before touching the live service. Run manually
# from the repo root on the VPS (/home/promonta/agent/miniapp-repo) after
# reviewing your diff. Does not restart the backend by default — pass
# --restart to also bounce promonta-miniapp.service (needs root).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_SRC="$REPO_DIR/backend/main.py"
BACKEND_DST="/home/promonta/agent/miniapp/main.py"
FRONTEND_SRC="$REPO_DIR/frontend/"
FRONTEND_DST="/var/www/miniapp/"
TS="$(date +%Y%m%d%H%M%S)"

RESTART=0
if [[ "${1:-}" == "--restart" ]]; then
  RESTART=1
fi

echo "== 1/5 Syntax check backend =="
python3 -m py_compile "$BACKEND_SRC"
echo "OK"

echo "== 2/5 Backup + sync backend =="
if [[ -f "$BACKEND_DST" ]]; then
  cp "$BACKEND_DST" "${BACKEND_DST}.bak-pre-deploy-${TS}"
fi
cp "$BACKEND_SRC" "$BACKEND_DST"
python3 -m py_compile "$BACKEND_DST"
echo "OK"

echo "== 3/5 Backup + sync frontend =="
# rsync into the root-owned /var/www/miniapp/ requires sudo on this box —
# this script assumes it's being run as a user with write access there
# (root), or that /var/www/miniapp/ has been chowned for promonta.
mkdir -p "/var/www/miniapp/.bak-pre-deploy-${TS}"
rsync -a --exclude='.bak-*' "$FRONTEND_DST" "/var/www/miniapp/.bak-pre-deploy-${TS}/" 2>/dev/null || true
rsync -av --exclude='.bak-*' --exclude='.archived-legacy' "$FRONTEND_SRC" "$FRONTEND_DST"
echo "OK"

echo "== 4/5 Restart backend =="
if [[ "$RESTART" -eq 1 ]]; then
  systemctl restart promonta-miniapp.service
  sleep 2
  systemctl is-active promonta-miniapp.service
else
  echo "skipped (pass --restart to bounce promonta-miniapp.service)"
fi

echo "== 5/5 Smoke check =="
curl -s -o /dev/null -w 'app.html -> %{http_code}\n' "https://app.promonta.fun/app.html"
curl -s -o /dev/null -w 'api/health -> %{http_code}\n' "https://app.promonta.fun/api/health" || true

echo "Done. Backups: ${BACKEND_DST}.bak-pre-deploy-${TS}, /var/www/miniapp/.bak-pre-deploy-${TS}/"
