"""DailyPlan store — единственный источник правды для исторических фактов.

Схема daily_plan_store.json:
  {
    "daily_plans": {plan_id: DailyPlan},
    "versions":    {plan_id: [DailyPlanVersion]},
    "acceptances": {acceptance_id: DailyPlanAcceptance},
    "amendments":  {amendment_id: PlanAmendment},
    "executions":  {session_id: DailyExecution},
    "carryovers":  {carryover_id: Carryover},
    "productivity_observations": {obs_id: ProductivityObservation},
    "productivity_aggregates":   {"{worker_id}:{work_type_id}": ProductivityAggregate},
    "work_calendar": WorkCalendar,
  }

Правило: Sheets = source of truth для будущего/редактируемого (план, этапы, нормы).
         Этот store = source of truth для исторического факта (что принято, что сделано).
         Sheets-редактирование после принятия → Amendment. Нельзя переписать принятое.
"""

import contextlib
import fcntl
import hashlib
import json
import os
import threading
import time
import uuid
from datetime import date, datetime, timedelta

_store_lock = threading.Lock()

# Устанавливается из main.py при импорте — DATA_ROOT из env
_STORE_FILE: str = ''
_SYNC_STATE_FILE: str = ''
_WORK_CALENDAR_FILE: str = ''

_EMPTY_STORE = {
    "daily_plans": {},
    "versions": {},
    "acceptances": {},
    "amendments": {},
    "executions": {},
    "carryovers": {},
    "productivity_observations": {},
    "productivity_aggregates": {},
    "blockers": {},
}

_EMPTY_WORK_CALENDAR = {
    "default_working_days": [1, 2, 3, 4, 5],  # ISO weekday: 1=Mon … 7=Sun
    "holiday_exceptions": [],    # ["YYYY-MM-DD", ...] — выходные дни вне расписания
    "extra_workdays": [],        # ["YYYY-MM-DD", ...] — рабочие дни вне расписания
}


# ── File I/O helpers ────────────────────────────────────────────────────────

def configure(store_file: str, sync_state_file: str, work_calendar_file: str) -> None:
    """Вызывается из main.py после определения DATA_ROOT."""
    global _STORE_FILE, _SYNC_STATE_FILE, _WORK_CALENDAR_FILE
    _STORE_FILE = store_file
    _SYNC_STATE_FILE = sync_state_file
    _WORK_CALENDAR_FILE = work_calendar_file


@contextlib.contextmanager
def _store_flock():
    """Cross-process exclusive lock alongside the in-process thread lock.
    Uses a .lock sidecar file so both FastAPI and plan_sync.py serialize writes."""
    if not _STORE_FILE:
        yield
        return
    lock_path = _STORE_FILE + '.lock'
    with open(lock_path, 'a') as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _atomic_write(path: str, data: dict) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _load_store() -> dict:
    if not _STORE_FILE:
        raise RuntimeError("daily_plan_lib not configured — call configure() first")
    if not os.path.exists(_STORE_FILE):
        return {k: v.copy() if isinstance(v, dict) else v
                for k, v in _EMPTY_STORE.items()}
    try:
        with open(_STORE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Ensure all top-level keys exist (forward-compat for new keys)
        for k, v in _EMPTY_STORE.items():
            if k not in data:
                data[k] = v.copy() if isinstance(v, dict) else v
        return data
    except json.JSONDecodeError:
        raise  # caller (main.py) handles via CorruptJsonError mechanism


def _save_store(data: dict) -> None:
    _atomic_write(_STORE_FILE, data)


def get_store_snapshot() -> dict:
    """Public read-only accessor for owner-side read-heavy routes.
    Returns the full store dict — callers must not mutate it."""
    return _load_store()


def _load_work_calendar() -> dict:
    if not _WORK_CALENDAR_FILE or not os.path.exists(_WORK_CALENDAR_FILE):
        return _EMPTY_WORK_CALENDAR.copy()
    try:
        with open(_WORK_CALENDAR_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return _EMPTY_WORK_CALENDAR.copy()


# ── Working calendar helpers ────────────────────────────────────────────────

def is_working_day(d: date) -> bool:
    cal = _load_work_calendar()
    ds = d.strftime('%Y-%m-%d')
    if ds in cal.get('holiday_exceptions', []):
        return False
    if ds in cal.get('extra_workdays', []):
        return True
    return d.isoweekday() in cal.get('default_working_days', [1, 2, 3, 4, 5])


def next_working_day(d: date) -> date | None:
    """Следующий рабочий день после d. None если ни одного в ближайшие 60 дней."""
    candidate = d + timedelta(days=1)
    for _ in range(60):
        if is_working_day(candidate):
            return candidate
        candidate += timedelta(days=1)
    return None


# ── Content hash ────────────────────────────────────────────────────────────

def _items_hash(items: list) -> str:
    canonical = json.dumps(items, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ── DailyPlan CRUD ──────────────────────────────────────────────────────────

def create_plan(
    object_id: str,
    stage_key: str,
    date_str: str,
    assigned_worker_ids: list,
    items: list,
    created_by: str,
    sheets_source_row: int | None = None,
) -> dict:
    """Создаёт DailyPlan (версия 1, статус draft). Не требует Sheets-блокировки."""
    plan_id = uuid.uuid4().hex
    content_hash = _items_hash(items)
    now = time.time()
    version_id = uuid.uuid4().hex

    plan = {
        "id": plan_id,
        "object_id": object_id,
        "stage_key": stage_key,
        "date": date_str,
        "assigned_worker_ids": list(assigned_worker_ids),
        "status": "draft",
        "version": 1,
        "content_hash": content_hash,
        "items": items,
        "published_at": None,
        "created_at": now,
        "created_by": created_by,
        "sheets_source_row": sheets_source_row,
    }

    version = {
        "id": version_id,
        "daily_plan_id": plan_id,
        "version": 1,
        "items_snapshot": items,
        "content_hash": content_hash,
        "created_at": now,
        "change_type": "initial",
        "change_summary": "Первая версия плана",
    }

    with _store_lock, _store_flock():
        store = _load_store()
        store["daily_plans"][plan_id] = plan
        store["versions"].setdefault(plan_id, []).append(version)
        _save_store(store)

    return plan


def publish_plan(plan_id: str, published_by: str) -> dict:
    """Переводит план в статус published — доступен работникам."""
    with _store_lock, _store_flock():
        store = _load_store()
        plan = store["daily_plans"].get(plan_id)
        if not plan:
            raise KeyError(f"Plan {plan_id} not found")
        if plan["status"] not in ("draft",):
            raise ValueError(f"Cannot publish plan with status={plan['status']!r}")
        plan["status"] = "published"
        plan["published_at"] = time.time()
        _save_store(store)
    return plan


def update_plan_items(
    plan_id: str,
    new_items: list,
    change_type: str,
    change_summary: str,
    updated_by: str,
) -> dict:
    """Обновляет содержимое плана (из Sheets-синка или ручного редактирования).
    Если план уже принят (accepted) — создаёт Amendment вместо прямого изменения.
    Если принят и смена началась — также создаёт Amendment."""
    with _store_lock, _store_flock():
        store = _load_store()
        plan = store["daily_plans"].get(plan_id)
        if not plan:
            raise KeyError(f"Plan {plan_id} not found")

        new_hash = _items_hash(new_items)
        if new_hash == plan["content_hash"]:
            return plan  # идемпотент: содержимое не изменилось

        old_version = plan["version"]
        new_version = old_version + 1
        now = time.time()
        version_record = {
            "id": uuid.uuid4().hex,
            "daily_plan_id": plan_id,
            "version": new_version,
            "items_snapshot": new_items,
            "content_hash": new_hash,
            "created_at": now,
            "change_type": change_type,
            "change_summary": change_summary,
        }
        plan["version"] = new_version
        plan["content_hash"] = new_hash
        plan["items"] = new_items

        has_acceptance = any(
            a["daily_plan_id"] == plan_id
            for a in store["acceptances"].values()
        )
        if has_acceptance:
            # Post-acceptance: план переходит в amendment_pending
            plan["status"] = "amendment_pending"
            amendment = {
                "id": uuid.uuid4().hex,
                "daily_plan_id": plan_id,
                "plan_version_before": old_version,
                "plan_version_after": new_version,
                "diff": _compute_diff(
                    store["versions"].get(plan_id, [])[-1]["items_snapshot"]
                    if store["versions"].get(plan_id) else [],
                    new_items,
                ),
                "created_at": now,
                "created_by": updated_by,
                "acknowledged_by": {},  # {worker_id: timestamp} — per-worker acks
            }
            store["amendments"][amendment["id"]] = amendment
        else:
            # Pre-acceptance: просто новая версия, статус не меняется
            pass

        store["versions"].setdefault(plan_id, []).append(version_record)
        _save_store(store)
    return plan


def _compute_diff(old_items: list, new_items: list) -> dict:
    old_by_id = {i["id"]: i for i in old_items}
    new_by_id = {i["id"]: i for i in new_items}
    added = [i for i in new_items if i["id"] not in old_by_id]
    removed = [i for i in old_items if i["id"] not in new_by_id]
    changed = [
        {"old": old_by_id[i["id"]], "new": i}
        for i in new_items
        if i["id"] in old_by_id and i != old_by_id[i["id"]]
    ]
    return {"added": added, "removed": removed, "changed": changed}


# ── Acceptance ──────────────────────────────────────────────────────────────

ACCEPT_IDEMPOTENCY_PREFIX = "accept"


def accept_plan(plan_id: str, plan_version: int, worker_id: str) -> dict:
    """Работник нажал «ПЛАН ПОНЯТЕН — БЕРУ В РАБОТУ». Идемпотент по (plan_id, worker_id)."""
    idempotency_key = f"{ACCEPT_IDEMPOTENCY_PREFIX}:{plan_id}:{worker_id}"

    with _store_lock, _store_flock():
        store = _load_store()
        plan = store["daily_plans"].get(plan_id)
        if not plan:
            raise KeyError(f"Plan {plan_id} not found")
        if str(worker_id) not in [str(w) for w in plan["assigned_worker_ids"]]:
            raise PermissionError(f"Worker {worker_id} is not assigned to plan {plan_id}")

        # Идемпотентность: уже принял эту версию → вернуть существующее ДО проверки статуса
        existing = next(
            (a for a in store["acceptances"].values()
             if a["daily_plan_id"] == plan_id and str(a["worker_id"]) == str(worker_id)
             and a["plan_version"] == plan_version),
            None,
        )
        if existing:
            return existing

        # "accepted" is allowed: another worker may have already accepted a multi-worker plan.
        if plan["status"] not in ("published", "amendment_pending", "accepted"):
            raise ValueError(f"Plan status {plan['status']!r} cannot be accepted")

        # Snapshot hash на момент принятия — фиксируем что именно принял работник
        versions = store["versions"].get(plan_id, [])
        snap = next((v for v in reversed(versions) if v["version"] == plan_version), None)
        accepted_snapshot_hash = snap["content_hash"] if snap else plan["content_hash"]

        acceptance = {
            "id": uuid.uuid4().hex,
            "idempotency_key": idempotency_key,
            "daily_plan_id": plan_id,
            "plan_version": plan_version,
            "worker_id": str(worker_id),
            "accepted_at": time.time(),
            "accepted_snapshot_hash": accepted_snapshot_hash,
        }

        # Если было amendment_pending — ack этим работником. Только когда ВСЕ ackнули → accepted.
        if plan["status"] == "amendment_pending":
            for a in store["amendments"].values():
                if a["daily_plan_id"] == plan_id and not _amendment_acked_by(a, str(worker_id)):
                    a.setdefault("acknowledged_by", {})[str(worker_id)] = acceptance["accepted_at"]
            # Check if all assigned workers have now acked all pending amendments
            all_acked = all(
                _amendment_acked_by_all(a, plan["assigned_worker_ids"])
                for a in store["amendments"].values()
                if a["daily_plan_id"] == plan_id
            )
            if all_acked:
                plan["status"] = "accepted"

        elif plan["status"] == "published":
            plan["status"] = "accepted"

        store["acceptances"][acceptance["id"]] = acceptance
        _save_store(store)

    return acceptance


def acknowledge_amendment(plan_id: str, amendment_id: str, worker_id: str) -> dict:
    """Работник подтверждает Amendment (уже принятый план, изменённый после старта)."""
    with _store_lock, _store_flock():
        store = _load_store()
        amendment = store["amendments"].get(amendment_id)
        if not amendment:
            raise KeyError(f"Amendment {amendment_id} not found")
        if amendment["daily_plan_id"] != plan_id:
            raise ValueError("Amendment does not belong to this plan")
        plan = store["daily_plans"].get(plan_id)
        if plan and str(worker_id) not in [str(w) for w in plan["assigned_worker_ids"]]:
            raise PermissionError("Worker not assigned to this plan")
        amendment.setdefault("acknowledged_by", {})[str(worker_id)] = time.time()
        if plan and plan["status"] == "amendment_pending":
            # Переходим в accepted только когда ВСЕ assigned workers ackнули ВСЕ amendments
            all_acked = all(
                _amendment_acked_by_all(a, plan.get("assigned_worker_ids", []))
                for a in store["amendments"].values()
                if a["daily_plan_id"] == plan_id
            )
            if all_acked:
                plan["status"] = "accepted"
        _save_store(store)
    return amendment


# ── Execution (Finish fact-report) ──────────────────────────────────────────

EXECUTION_IDEMPOTENCY_PREFIX = "execution"


def apply_daily_execution(
    session_id: str,
    daily_plan_id: str,
    plan_version: int,
    worker_id: str,
    date_str: str,
    object_id: str,
    item_results: list,
) -> dict:
    """Идемпотентный проектор: применяет результат смены к DailyPlan.
    Если session_id уже есть → возвращает существующую запись без повторной обработки.
    Вызывается из checkin_finish (после того как сессия уже записана в CHECKIN_META).
    """
    idempotency_key = f"{EXECUTION_IDEMPOTENCY_PREFIX}:{session_id}"

    with _store_lock, _store_flock():
        store = _load_store()

        existing = store["executions"].get(session_id)
        if existing:
            return existing

        execution = {
            "session_id": session_id,
            "idempotency_key": idempotency_key,
            "daily_plan_id": daily_plan_id,
            "plan_version": plan_version,
            "worker_id": str(worker_id),
            "date": date_str,
            "object_id": object_id,
            "item_results": item_results,
            "applied_at": time.time(),
        }

        plan = store["daily_plans"].get(daily_plan_id)
        if plan:
            assigned = [str(w) for w in plan.get("assigned_worker_ids", [])]
            if assigned:
                # Count workers who have already submitted executions + current worker
                executed_workers = {
                    e["worker_id"]
                    for e in store["executions"].values()
                    if e.get("daily_plan_id") == daily_plan_id
                }
                executed_workers.add(str(worker_id))
                if set(assigned) <= executed_workers:
                    plan["status"] = "completed"
                else:
                    plan["status"] = "in_progress"
            else:
                # No assigned_worker_ids (legacy plan) — mark complete on first finish
                plan["status"] = "completed"

        store["executions"][session_id] = execution

        # Создаём Carryover для незавершённых пунктов
        tomorrow = next_working_day(
            datetime.strptime(date_str, '%Y-%m-%d').date()
        )
        tomorrow_str = tomorrow.strftime('%Y-%m-%d') if tomorrow else None

        plan_items = {i["id"]: i for i in (plan["items"] if plan else [])}
        for result in item_results:
            if result.get("status") in ("partial", "not_done", "blocked"):
                item = plan_items.get(result["item_id"], {})
                planned_qty = item.get("planned_quantity")
                actual_qty = result.get("actual_quantity")
                remaining = (
                    round(planned_qty - (actual_qty or 0), 4)
                    if planned_qty is not None and actual_qty is not None
                    else planned_qty
                )
                carryover_key = f"carryover:{daily_plan_id}:{result['item_id']}"
                # Идемпотент: не создаём дубль carryover для того же (plan, item)
                already = next(
                    (c for c in store["carryovers"].values()
                     if c.get("idempotency_key") == carryover_key),
                    None,
                )
                if not already:
                    co = {
                        "id": uuid.uuid4().hex,
                        "idempotency_key": carryover_key,
                        "source_plan_id": daily_plan_id,
                        "source_date": date_str,
                        "target_date": tomorrow_str,
                        "worker_id": str(worker_id),
                        "object_id": object_id,
                        "item_id": result["item_id"],
                        "item_title": item.get("title", ""),
                        "unit": item.get("unit", ""),
                        "remaining_quantity": remaining,
                        "reason_code": result.get("reason_code", "not_done"),
                        "comment": result.get("comment", ""),
                        "created_at": time.time(),
                        "status": "pending",
                    }
                    store["carryovers"][co["id"]] = co

        _save_store(store)

    return execution


# ── Productivity ─────────────────────────────────────────────────────────────

PRIOR_HOURS = float(os.environ.get('PRODUCTIVITY_PRIOR_HOURS', '40'))


def record_productivity_observation(
    session_id: str,
    worker_id: str,
    work_type_id: str,
    date_str: str,
    actual_quantity: float,
    unit: str,
    person_hours: float,
    crew_size: int = 1,
    confidence: str = "solo",
    contribution_weight: float = 1.0,
) -> dict:
    """Записывает наблюдение за производительностью. Идемпотент по session_id+work_type."""
    if person_hours <= 0:
        raise ValueError("person_hours must be > 0")
    obs_id = f"{session_id}:{work_type_id}"
    observed_rate = round(actual_quantity / person_hours, 4)

    with _store_lock, _store_flock():
        store = _load_store()
        if obs_id in store["productivity_observations"]:
            return store["productivity_observations"][obs_id]

        obs = {
            "id": obs_id,
            "worker_id": str(worker_id),
            "work_type_id": work_type_id,
            "date": date_str,
            "session_id": session_id,
            "actual_quantity": actual_quantity,
            "unit": unit,
            "person_hours": person_hours,
            "observed_rate": observed_rate,
            "confidence": confidence,
            "contribution_weight": contribution_weight,
            "crew_size": crew_size,
        }
        store["productivity_observations"][obs_id] = obs

        # Пересчёт агрегата
        agg_key = f"{worker_id}:{work_type_id}"
        agg = store["productivity_aggregates"].get(agg_key, {
            "worker_id": str(worker_id),
            "work_type_id": work_type_id,
            "observation_count": 0,
            "total_person_hours": 0.0,
            "weighted_rate": None,
            "manual_baseline_factor": None,
            "effective_rate": None,
            "last_updated": None,
        })

        agg["observation_count"] += 1
        agg["total_person_hours"] += person_hours * contribution_weight

        # Взвешенное среднее по накопленным часам
        all_obs = [
            o for o in store["productivity_observations"].values()
            if o["worker_id"] == str(worker_id) and o["work_type_id"] == work_type_id
        ]
        total_weighted_h = sum(o["person_hours"] * o["contribution_weight"] for o in all_obs)
        weighted_rate = (
            sum(o["observed_rate"] * o["person_hours"] * o["contribution_weight"] for o in all_obs)
            / total_weighted_h
            if total_weighted_h > 0 else None
        )
        agg["weighted_rate"] = round(weighted_rate, 4) if weighted_rate is not None else None

        # Blend: чем больше часов накоплено, тем меньше вес baseline
        baseline = agg.get("manual_baseline_factor")
        if baseline and total_weighted_h < PRIOR_HOURS:
            alpha = total_weighted_h / PRIOR_HOURS  # 0..1
            effective = alpha * (weighted_rate or baseline) + (1 - alpha) * baseline
            agg["effective_rate"] = round(effective, 4)
        elif weighted_rate is not None:
            agg["effective_rate"] = agg["weighted_rate"]
        elif baseline:
            agg["effective_rate"] = baseline

        agg["last_updated"] = time.time()
        store["productivity_aggregates"][agg_key] = agg
        _save_store(store)

    return obs


def auto_record_execution_productivity(
    session_id: str,
    worker_id: str,
    plan: dict,
    item_results: list,
    shift_hours: float,
) -> list:
    """Auto-creates productivity observations from execution results.

    Called after apply_daily_execution when shift_hours > 0.
    Only processes 'done' items with actual_quantity > 0 and work_type_id.
    Hours distributed proportionally by time_estimate_hours (equal split if none).

    For multi-worker plans: records a crew observation (confidence='crew',
    contribution_weight=1/crew_size) so individual effective rates are not
    inflated by shared team output.
    """
    if shift_hours <= 0:
        return []

    plan_items_by_id = {i["id"]: i for i in (plan.get("items") or [])}
    assigned_workers = plan.get("assigned_worker_ids", [])
    crew_size = max(1, len(assigned_workers))
    confidence = "crew" if crew_size > 1 else "solo"
    # For crew work, each worker gets proportional credit — prevents inflating
    # individual rates when total output is a joint product.
    contribution_weight = round(1.0 / crew_size, 4)

    eligible = []
    for result in item_results:
        if result.get("status") != "done":
            continue
        qty = result.get("actual_quantity")
        if not qty or float(qty) <= 0:
            continue
        item = plan_items_by_id.get(result.get("item_id", ""), {})
        work_type_id = item.get("work_type_id") or ""
        if not work_type_id:
            continue
        eligible.append({
            "item_id": result["item_id"],
            "work_type_id": work_type_id,
            "actual_quantity": float(qty),
            "unit": item.get("unit", ""),
            "time_estimate_hours": float(item.get("time_estimate_hours") or 0.0),
        })

    if not eligible:
        return []

    total_est = sum(e["time_estimate_hours"] for e in eligible)
    recorded = []
    for e in eligible:
        if total_est > 0 and e["time_estimate_hours"] > 0:
            person_hours = shift_hours * (e["time_estimate_hours"] / total_est)
        else:
            person_hours = shift_hours / len(eligible)
        person_hours = round(person_hours, 4)
        if person_hours <= 0:
            continue
        try:
            obs = record_productivity_observation(
                session_id=f"{session_id}:{e['item_id']}",
                worker_id=worker_id,
                work_type_id=e["work_type_id"],
                date_str=plan.get("date", ""),
                actual_quantity=e["actual_quantity"],
                unit=e["unit"],
                person_hours=person_hours,
                crew_size=crew_size,
                confidence=confidence,
                contribution_weight=contribution_weight,
            )
            recorded.append(obs)
        except Exception:
            pass
    return recorded


# ── Read helpers ─────────────────────────────────────────────────────────────

def get_plan(plan_id: str) -> dict | None:
    store = _load_store()
    return store["daily_plans"].get(plan_id)


def get_plan_by_sheets_source_row(sheets_source_row: str) -> dict | None:
    """Find a plan by its sheets_source_row identifier (Plan_дня plan_id column)."""
    store = _load_store()
    return next(
        (p for p in store["daily_plans"].values()
         if str(p.get("sheets_source_row", "")) == str(sheets_source_row)),
        None,
    )


def get_today_plan_for_worker(worker_id: str, date_str: str) -> dict | None:
    """Возвращает первый план работника на эту дату (по порядку: published/accepted/
    amendment_pending в приоритете над draft)."""
    store = _load_store()
    wid = str(worker_id)
    candidates = [
        p for p in store["daily_plans"].values()
        if p["date"] == date_str and wid in [str(w) for w in p["assigned_worker_ids"]]
    ]
    STATUS_PRIORITY = {"accepted": 0, "amendment_pending": 1, "published": 2,
                       "completed": 3, "draft": 4}
    candidates.sort(key=lambda p: STATUS_PRIORITY.get(p["status"], 99))
    return candidates[0] if candidates else None


def get_accepted_snapshot(plan_id: str, worker_id: str) -> list:
    """Возвращает items из версии, которую принял работник. Если нет принятия — текущие items."""
    store = _load_store()
    plan = store["daily_plans"].get(plan_id, {})
    acceptance = next(
        (a for a in store["acceptances"].values()
         if a["daily_plan_id"] == plan_id and str(a["worker_id"]) == str(worker_id)),
        None,
    )
    if not acceptance:
        return plan.get("items", [])
    snap_hash = acceptance["accepted_snapshot_hash"]
    versions = store["versions"].get(plan_id, [])
    snap = next((v for v in versions if v["content_hash"] == snap_hash), None)
    return snap["items_snapshot"] if snap else plan.get("items", [])


def get_carryovers_for_worker(worker_id: str, target_date_str: str) -> list:
    store = _load_store()
    wid = str(worker_id)
    return [
        c for c in store["carryovers"].values()
        if str(c["worker_id"]) == wid
        and c.get("target_date") == target_date_str
        and c["status"] == "pending"
    ]


def get_pending_plans_for_owner_today(date_str: str) -> list:
    """Все планы на эту дату для Контроль дня — используется в owner/today endpoint."""
    store = _load_store()
    return [p for p in store["daily_plans"].values() if p["date"] == date_str]


def get_worker_productivity(worker_id: str) -> dict | None:
    store = _load_store()
    wid = str(worker_id)
    aggs = {k: v for k, v in store["productivity_aggregates"].items()
            if v["worker_id"] == wid}
    obs = [o for o in store["productivity_observations"].values() if o["worker_id"] == wid]
    return {"aggregates": aggs, "observations": obs} if (aggs or obs) else None


def get_plan_versions(plan_id: str) -> list:
    store = _load_store()
    return store["versions"].get(plan_id, [])


def get_acceptance(plan_id: str, worker_id: str) -> dict | None:
    store = _load_store()
    return next(
        (a for a in store["acceptances"].values()
         if a["daily_plan_id"] == plan_id and str(a["worker_id"]) == str(worker_id)),
        None,
    )


def _amendment_acked_by(amendment: dict, worker_id: str) -> bool:
    """Returns True if this specific worker has acked the amendment."""
    acked_by = amendment.get("acknowledged_by")
    if isinstance(acked_by, dict):
        return str(worker_id) in acked_by
    # Backward compat: old schema had a single worker_acknowledged_at timestamp
    return amendment.get("worker_acknowledged_at") is not None


def _amendment_acked_by_all(amendment: dict, worker_ids: list) -> bool:
    """Returns True if every assigned worker has acked the amendment."""
    if not worker_ids:
        return True
    return all(_amendment_acked_by(amendment, str(w)) for w in worker_ids)


def get_pending_amendments(plan_id: str, worker_id: str | None = None) -> list:
    """Returns amendments pending acknowledgement.
    If worker_id given: amendments this specific worker hasn't acked yet.
    If worker_id is None: amendments not acked by all assigned workers."""
    store = _load_store()
    plan = store["daily_plans"].get(plan_id)
    assigned = plan.get("assigned_worker_ids", []) if plan else []
    result = []
    for a in store["amendments"].values():
        if a["daily_plan_id"] != plan_id:
            continue
        if worker_id is not None:
            if not _amendment_acked_by(a, str(worker_id)):
                result.append(a)
        else:
            if not _amendment_acked_by_all(a, assigned):
                result.append(a)
    return result


def get_execution(session_id: str) -> dict | None:
    store = _load_store()
    return store["executions"].get(session_id)


def mark_carryover_applied(carryover_id: str) -> None:
    with _store_lock, _store_flock():
        store = _load_store()
        co = store["carryovers"].get(carryover_id)
        if co:
            co["status"] = "applied"
            _save_store(store)


def get_blockers_for_plan(plan_id: str) -> list:
    """Возвращает все blockers для данного плана (нерешённые)."""
    store = _load_store()
    return [
        b for b in store.get("blockers", {}).values()
        if b.get("daily_plan_id") == plan_id and b.get("resolved_at") is None
    ]


def record_blocker(plan_id: str, worker_id: str, reason_code: str, comment: str) -> dict:
    """Записывает препятствие от работника при утреннем принятии плана.
    Идемпотентно: одинаковый (plan_id, worker_id, reason_code) без resolved_at → возвращает существующий."""
    with _store_lock, _store_flock():
        store = _load_store()
        if "blockers" not in store:
            store["blockers"] = {}
        # Idempotency: return existing unresolved blocker with same composite key
        for existing in store["blockers"].values():
            if (existing["daily_plan_id"] == plan_id
                    and existing["worker_id"] == str(worker_id)
                    and existing["reason_code"] == reason_code
                    and existing["resolved_at"] is None):
                return existing
        blocker = {
            "id": uuid.uuid4().hex,
            "daily_plan_id": plan_id,
            "worker_id": str(worker_id),
            "reason_code": reason_code,
            "comment": comment,
            "reported_at": time.time(),
            "resolved_at": None,
        }
        store["blockers"][blocker["id"]] = blocker
        _save_store(store)
    return blocker


def set_manual_baseline(worker_id: str, work_type_id: str, baseline: float) -> dict:
    """Владелец устанавливает/корректирует prior (manual_baseline_factor)."""
    with _store_lock, _store_flock():
        store = _load_store()
        agg_key = f"{worker_id}:{work_type_id}"
        agg = store["productivity_aggregates"].get(agg_key, {
            "worker_id": str(worker_id),
            "work_type_id": work_type_id,
            "observation_count": 0,
            "total_person_hours": 0.0,
            "weighted_rate": None,
            "manual_baseline_factor": None,
            "effective_rate": None,
            "last_updated": None,
        })
        agg["manual_baseline_factor"] = baseline
        # Пересчёт effective_rate
        wr = agg.get("weighted_rate")
        total_h = agg.get("total_person_hours", 0.0)
        if wr is not None and total_h >= PRIOR_HOURS:
            agg["effective_rate"] = wr
        elif wr is not None:
            alpha = total_h / PRIOR_HOURS
            agg["effective_rate"] = round(alpha * wr + (1 - alpha) * baseline, 4)
        else:
            agg["effective_rate"] = baseline
        agg["last_updated"] = time.time()
        store["productivity_aggregates"][agg_key] = agg
        _save_store(store)
    return agg
