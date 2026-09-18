#!/usr/bin/env python3
"""daily_plan_cutoff_check.py — owner alert when DailyPlan wasn't published in time.

Owner request (18.09): the plan should arrive the evening BEFORE the work day, not
be assembled the morning of. This does not block a worker's shift start -- start
without a plan stays freely allowed either way (checkin_start's existing behavior,
unchanged). It only alerts the owner once per day if, by CUTOFF_HOUR local time,
some worker who has an active object assignment for today still has no
published/accepted/amendment_pending/in_progress DailyPlan for today.

Does NOT run inline in FastAPI request handlers -- invoked by a systemd timer once
a day, same standalone-script pattern as backend/cleanup_old_attachments.py.

Deploy: like cleanup_old_attachments.py, this file is NOT copied automatically by
scripts/deploy.sh's manifest (it isn't imported by main.py, so it isn't a runtime
dependency of the app) -- copy it manually into the runtime package directory,
next to main.py (/home/promonta/agent/miniapp/), so `import main as backend`
below resolves the same top-level `main` module the systemd uvicorn service and
every tests/test_*.py file use (as opposed to the `miniapp.main` package import
uvicorn itself uses -- see main.py's own relative/absolute import fallback
comment for why both forms exist side by side in this codebase).
systemd unit + timer fire at 06:30 local time (server is already Europe/Berlin).

Idempotency: writes a per-day marker to $MINIAPP_DATA_ROOT/daily_plan_cutoff_state.json
so a timer misfire/retry on the same day does not spam duplicate alerts.
"""
import json
import logging
import os
import sys

logging.basicConfig(
    format='%(asctime)s [daily_plan_cutoff_check] %(levelname)s %(message)s',
    level=logging.INFO,
)
log = logging.getLogger(__name__)

DATA_ROOT = os.environ.get('MINIAPP_DATA_ROOT', '/home/promonta/agent/miniapp')
STATE_FILE = os.path.join(DATA_ROOT, 'daily_plan_cutoff_state.json')


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def main() -> int:
    import main as backend  # noqa: E402
    import daily_plan_lib as dpl  # noqa: E402

    today = backend.business_today_str()

    state = _load_state()
    if state.get('last_checked_date') == today:
        log.info("Already checked %s today, skipping (idempotent).", today)
        return 0

    roles = backend._load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    if not owner_id:
        log.warning("No owner found in roles, cannot send alert.")
        _save_state({**state, 'last_checked_date': today})
        return 0

    assignments = backend._load_assignments()
    # Workers with an accepted assignment covering today, per object.
    workers_without_plan = set()
    for object_id, candidates in assignments.items():
        for a in candidates:
            if backend._assignment_status(a) != 'accepted':
                continue
            d_from, d_to = a.get('date_from', ''), a.get('date_to', '')
            if d_from and d_to and not (d_from <= today <= d_to):
                continue
            worker_id = str(a.get('user_id', ''))
            if not worker_id:
                continue
            plan = dpl.get_today_plan_for_worker(worker_id, today)
            has_real_plan = plan is not None and plan.get('status') in (
                'published', 'accepted', 'amendment_pending', 'in_progress',
            )
            if not has_real_plan:
                workers_without_plan.add(worker_id)

    if not workers_without_plan:
        log.info("All assigned workers have a plan for %s. Nothing to alert.", today)
        _save_state({'last_checked_date': today})
        return 0

    profiles = backend._load_worker_profiles()
    names = [
        backend._sanitize_display_name(profiles.get(wid, {}).get('name'), wid)
        for wid in sorted(workers_without_plan)
    ]
    log.info("Workers without a plan for %s: %s", today, names)

    backend._create_critical_alert(
        target_user_id=owner_id,
        kind='plan_overdue',
        title=f"План на {today} не опубликован для {len(names)} "
              f"{'работника' if len(names) == 1 else 'работников'}",
        subtitle=', '.join(names)[:200],
    )

    _save_state({'last_checked_date': today})
    return 0


if __name__ == '__main__':
    sys.exit(main())
