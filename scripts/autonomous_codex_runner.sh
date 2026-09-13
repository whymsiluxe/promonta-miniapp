#!/usr/bin/env bash
# Autonomous Codex runner for the Promonta miniapp production repo.
#
# Intended to be launched by autonomous-miniapp.service/timer on the VPS.
# It keeps one Codex run active at a time, resumes the same Codex thread after
# limits/timeouts, and leaves all work in git commits so the next run can
# continue cleanly.
set -euo pipefail

REPO="${PROMONTA_MINIAPP_REPO:-/home/promonta/agent/miniapp-repo}"
AGENT_ROOT="${PROMONTA_AGENT_ROOT:-/home/promonta/agent}"
PLAN_FILE="${PROMONTA_AUTONOMOUS_PLAN:-$REPO/docs/AUTONOMOUS_3_STAGES_13sep2026.md}"
LOCKFILE="${PROMONTA_AUTONOMOUS_LOCK:-$AGENT_ROOT/.codex-autonomous-miniapp.lock}"
LOGFILE="${PROMONTA_AUTONOMOUS_LOG:-$AGENT_ROOT/codex-autonomous-miniapp.log}"
LAST_MESSAGE="${PROMONTA_AUTONOMOUS_LAST_MESSAGE:-$AGENT_ROOT/codex-autonomous-miniapp.last.md}"
THREAD_FILE="${PROMONTA_AUTONOMOUS_THREAD_FILE:-$AGENT_ROOT/codex-autonomous-miniapp.thread}"
TIMEOUT_SECONDS="${PROMONTA_AUTONOMOUS_TIMEOUT:-10200}"
STALE_LOCK_SECONDS="${PROMONTA_AUTONOMOUS_STALE_LOCK_SECONDS:-14400}"

log() {
  printf '%s %s\n' "$(date -Iseconds)" "$*" >> "$LOGFILE"
}

if [ ! -d "$REPO/.git" ]; then
  log "ERROR repo not found: $REPO"
  exit 2
fi

if [ ! -s "$PLAN_FILE" ]; then
  log "ERROR autonomous plan not found: $PLAN_FILE"
  exit 2
fi

if [ ! -s "$HOME/.codex/auth.json" ]; then
  log "ERROR Codex auth missing for HOME=$HOME"
  exit 3
fi

if grep -q '^AUTONOMOUS_STATUS: DONE' "$PLAN_FILE"; then
  log "plan already DONE; nothing to run"
  exit 0
fi

if [ -f "$LOCKFILE" ]; then
  lock_age=$(($(date +%s) - $(stat -c %Y "$LOCKFILE" 2>/dev/null || echo 0)))
  if [ "$lock_age" -gt "$STALE_LOCK_SECONDS" ]; then
    log "stale lock removed age=${lock_age}s"
    rm -f "$LOCKFILE"
  else
    log "lock exists age=${lock_age}s; another run is active"
    exit 0
  fi
fi

touch "$LOCKFILE"

TMP_OUTPUT="$(mktemp)"
RESUME_PROMPT_FILE=""
cleanup() {
  rm -f "$LOCKFILE" "$TMP_OUTPUT"
  if [ -n "$RESUME_PROMPT_FILE" ]; then
    rm -f "$RESUME_PROMPT_FILE"
  fi
}
trap cleanup EXIT

cd "$REPO"
log "=== codex autonomous run start ==="
log "repo=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

if [ -z "$(git status --porcelain)" ]; then
  git fetch origin main >> "$LOGFILE" 2>&1 || true
  git pull --ff-only origin main >> "$LOGFILE" 2>&1 || true
else
  log "working tree is dirty before run; skip pull and let Codex inspect/resume"
  git status --short >> "$LOGFILE" 2>&1 || true
fi

set +e
if [ -s "$THREAD_FILE" ]; then
  THREAD_ID="$(tr -d '[:space:]' < "$THREAD_FILE")"
  log "resuming codex thread=$THREAD_ID"
  RESUME_PROMPT_FILE="$(mktemp)"
  cat > "$RESUME_PROMPT_FILE" <<'PROMPT'
Continue the existing autonomous Promonta miniapp run from exactly where it paused.

Use current git status and docs/AUTONOMOUS_3_STAGES_13sep2026.md as source of truth. Do not restart completed work. Inspect what is already committed/deployed, continue the next unfinished checklist item, then test, commit, push, deploy, update /home/promonta/agent/FILESYSTEM_MAP.md, and keep going until AUTONOMOUS_STATUS is DONE or this session hits a limit.
PROMPT
  RESUME_CMD=(codex exec resume --json --dangerously-bypass-approvals-and-sandbox --output-last-message "$LAST_MESSAGE")
  if [ -n "${CODEX_MODEL:-}" ]; then
    RESUME_CMD+=(-m "$CODEX_MODEL")
  fi
  timeout "$TIMEOUT_SECONDS" "${RESUME_CMD[@]}" "$THREAD_ID" - < "$RESUME_PROMPT_FILE" 2>&1 | tee -a "$LOGFILE" "$TMP_OUTPUT" >/dev/null
else
  log "starting new codex autonomous thread"
  CODEX_CMD=(codex exec --json -C "$REPO" --add-dir "$AGENT_ROOT" --dangerously-bypass-approvals-and-sandbox --output-last-message "$LAST_MESSAGE")
  if [ -n "${CODEX_MODEL:-}" ]; then
    CODEX_CMD+=(-m "$CODEX_MODEL")
  fi
  timeout "$TIMEOUT_SECONDS" "${CODEX_CMD[@]}" - < "$PLAN_FILE" 2>&1 | tee -a "$LOGFILE" "$TMP_OUTPUT" >/dev/null
fi
exit_code=$?
set -e

NEW_THREAD_ID="$(awk -F'"' '/"type":"thread.started"/ {for (i=1; i<=NF; i++) if ($i=="thread_id") {print $(i+2); exit}}' "$TMP_OUTPUT" || true)"
if [ -n "$NEW_THREAD_ID" ]; then
  printf '%s\n' "$NEW_THREAD_ID" > "$THREAD_FILE"
  chmod 600 "$THREAD_FILE"
  log "recorded codex thread=$NEW_THREAD_ID"
fi

log "=== codex autonomous run end exit=$exit_code ==="

# 124 means timeout. Non-zero can also mean rate/session limit; timer will retry.
exit "$exit_code"
