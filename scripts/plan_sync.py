#!/usr/bin/env python3
"""plan_sync.py — Sheets → DailyPlan local-store sync worker.

Reads Plan_этапов and Plan_дня tabs from Google Sheets every 60 seconds,
computes stable content hashes, diffs against plan_sync_state.json, and
creates/updates DailyPlan records in daily_plan_store.json.

Does NOT write back to Sheets (the store is append-only from the sync direction).
Does NOT run inline in FastAPI request handlers — invoked by a systemd timer.

Deploy:
  1. Copy to /home/promonta/agent/miniapp/ (or keep in repo + symlink)
  2. Create promonta-plan-sync.service + promonta-plan-sync.timer (see docs/DEPLOYMENT.md)
  3. sudo systemctl enable --now promonta-plan-sync.timer

Environment (from /etc/claude-agent.env):
  MINIAPP_DATA_ROOT — data root (default /home/promonta/agent/miniapp)
  BOT_TOKEN — required for main.py import, not used by this script directly

Sheets IDs are read from OBJEKTE_SHEET_ID env (fallback: same as objekte_lib.SHEET_ID).
The 5 new tabs (Plan_этапов, Plan_дня, Нормы_работ, Факт_дня, Производительность)
are listed in REQUIRED_TABS; the worker creates them with stub headers if missing
(only after the owner has confirmed it's safe — see OPEN_QUESTIONS.md #Q4).
"""
import hashlib
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

# ── Environment setup ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [plan_sync] %(levelname)s %(message)s',
)
log = logging.getLogger('plan_sync')

DATA_ROOT = os.environ.get('MINIAPP_DATA_ROOT', '/home/promonta/agent/miniapp')
SHEETS_CRED = '/home/promonta/agent/.sheets.json'
SYNC_STATE_FILE = os.path.join(DATA_ROOT, 'plan_sync_state.json')
DAILY_PLAN_STORE_FILE = os.path.join(DATA_ROOT, 'daily_plan_store.json')

# Google Sheet ID (same spreadsheet as objekte_lib)
SHEET_ID = os.environ.get(
    'OBJEKTE_SHEET_ID',
    '14CXpSaW9ErmViK09zAh09X52EUmEJjnkxGUSmW3Z9sA',
)

# New Sheets tabs — NOT auto-created without owner approval (see OPEN_QUESTIONS.md #Q4)
PLAN_TABS = {
    'план_этапов': 'План_этапов',
    'план_дня': 'План_дня',
    'нормы_работ': 'Нормы_работ',
}

SYNC_INTERVAL_S = int(os.environ.get('PLAN_SYNC_INTERVAL', '60'))
MAX_BACKOFF_S = 300
QUOTA_PAUSE_S = 600

# ── OAuth token ──────────────────────────────────────────────────────────────
_token_cache: dict = {'token': None, 'expires_at': 0}


def _get_token() -> str:
    if _token_cache['token'] and time.time() < _token_cache['expires_at'] - 60:
        return _token_cache['token']
    try:
        c = json.load(open(SHEETS_CRED))
    except FileNotFoundError:
        raise RuntimeError(f"Sheets credential not found: {SHEETS_CRED}")
    payload = urllib.parse.urlencode({
        'client_id': c['client_id'],
        'client_secret': c['client_secret'],
        'refresh_token': c['refresh_token'],
        'grant_type': 'refresh_token',
    }).encode()
    resp = json.load(urllib.request.urlopen(
        'https://oauth2.googleapis.com/token', payload, timeout=20))
    _token_cache['token'] = resp['access_token']
    _token_cache['expires_at'] = time.time() + resp.get('expires_in', 3600)
    return _token_cache['token']


def _sheets_request(url: str) -> dict:
    token = _get_token()
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ── Sheets read ───────────────────────────────────────────────────────────────

def _read_tab(tab_name: str) -> list[dict] | None:
    """Reads a Sheets tab, returns list of row dicts keyed by header. None if tab missing."""
    encoded = urllib.parse.quote(tab_name)
    url = (
        f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}'
        f'/values/{encoded}?majorDimension=ROWS'
    )
    try:
        data = _sheets_request(url)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            log.warning("Tab %r not found in spreadsheet (HTTP 400)", tab_name)
            return None
        if e.code == 429:
            log.warning("Sheets quota exceeded (429) — pausing %ds", QUOTA_PAUSE_S)
            time.sleep(QUOTA_PAUSE_S)
            return None
        raise

    rows = data.get('values', [])
    if not rows:
        return []
    header = rows[0]
    return [dict(zip(header, r + [''] * max(0, len(header) - len(r)))) for r in rows[1:]]


# ── Content hash ─────────────────────────────────────────────────────────────

def _hash_rows(rows: list[dict]) -> str:
    canonical = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ── Sync state ────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if not os.path.exists(SYNC_STATE_FILE):
        return {}
    try:
        with open(SYNC_STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    tmp = SYNC_STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SYNC_STATE_FILE)


# ── DailyPlan store helpers (minimal — don't import full main.py) ─────────────

def _load_plan_store() -> dict:
    if not os.path.exists(DAILY_PLAN_STORE_FILE):
        return {"daily_plans": {}, "versions": {}, "acceptances": {},
                "amendments": {}, "executions": {}, "carryovers": {},
                "productivity_observations": {}, "productivity_aggregates": {}}
    try:
        with open(DAILY_PLAN_STORE_FILE) as f:
            return json.load(f)
    except Exception:
        log.error("daily_plan_store.json is corrupt — skipping store write this cycle")
        return None  # type: ignore


def _save_plan_store(store: dict) -> None:
    tmp = DAILY_PLAN_STORE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DAILY_PLAN_STORE_FILE)


# ── Plan_этапов processing ────────────────────────────────────────────────────

def _process_stage_rows(rows: list[dict], state: dict) -> int:
    """Syncs stage-level plan rows to plan_sync_state for later use by DailyPlan builder."""
    new_hash = _hash_rows(rows)
    old_hash = state.get('plan_etapov_hash')
    if new_hash == old_hash:
        return 0

    state['plan_etapov_hash'] = new_hash
    state['plan_etapov_rows'] = rows
    state['plan_etapov_synced_at'] = time.time()
    log.info("Plan_этапов updated: %d rows", len(rows))
    return len(rows)


def _process_daily_plan_rows(rows: list[dict], state: dict) -> int:
    """Syncs Plan_дня rows, creates/updates DailyPlan records in the local store."""
    new_hash = _hash_rows(rows)
    old_hash = state.get('plan_dnya_hash')
    if new_hash == old_hash:
        return 0

    state['plan_dnya_hash'] = new_hash
    state['plan_dnya_rows'] = rows
    state['plan_dnya_synced_at'] = time.time()
    log.info("Plan_дня updated: %d rows", len(rows))

    # Phase 2 of sync: update local DailyPlan records from changed rows
    # (stub — Phase 2 implementation deferred to after Plan_дня schema is confirmed)
    # This prevents creating plans from Sheets rows with unverified column names.
    # TODO Round 1 final: implement once Plan_дня tab schema is confirmed with owner.
    return len(rows)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_once() -> bool:
    """Runs one sync cycle. Returns True on success, False on retriable error."""
    state = _load_state()
    changed_total = 0

    try:
        for tab_key, tab_name in PLAN_TABS.items():
            rows = _read_tab(tab_name)
            if rows is None:
                log.info("Tab %r not found — skipping (create it manually when ready)", tab_name)
                continue

            if tab_key == 'план_этапов':
                changed_total += _process_stage_rows(rows, state)
            elif tab_key == 'план_дня':
                changed_total += _process_daily_plan_rows(rows, state)
            # нормы_работ: read-only cache only (no local plan-store writes for norms)
            elif tab_key == 'нормы_работ':
                nh = _hash_rows(rows)
                if nh != state.get('normy_hash'):
                    state['normy_hash'] = nh
                    state['normy_rows'] = rows
                    state['normy_synced_at'] = time.time()
                    log.info("Нормы_работ updated: %d rows", len(rows))
                    changed_total += len(rows)

    except urllib.error.URLError as e:
        log.warning("Sheets network error: %s", e)
        return False
    except Exception as e:
        log.error("Unexpected error in sync cycle: %s", e, exc_info=True)
        return False

    state['last_sync_at'] = time.time()
    state['last_sync_ok'] = True
    _save_state(state)

    if changed_total:
        log.info("Sync cycle complete — %d rows changed", changed_total)
    return True


def main():
    log.info("plan_sync starting — interval=%ds, sheet=%s", SYNC_INTERVAL_S, SHEET_ID)
    consecutive_failures = 0
    backoff = 5

    while True:
        success = run_once()
        if success:
            consecutive_failures = 0
            backoff = 5
        else:
            consecutive_failures += 1
            backoff = min(backoff * 2, MAX_BACKOFF_S)
            log.warning("Sync failed (attempt %d) — retry in %ds", consecutive_failures, backoff)

        if success:
            time.sleep(SYNC_INTERVAL_S)
        else:
            time.sleep(backoff)


if __name__ == '__main__':
    main()
