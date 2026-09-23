"""Worker UX V2, Этап 5 — «Сегодня» как рабочая операционная панель.

Source-assertion contract tests (same style as the rest of this repo's
*_frontend_contract.py suite). Covers:

- The 3 legacy tiles (Алерты важно/критично, Потребности wide-tile) are gone
  from initWorkerHomeView's markup, replaced by the unified Problems card;
  Сообщения/Задачи remain (not blockers by definition).
- The new DailyPlan preview card reads window._todayPlanState (does NOT
  duplicate checkAndShowTodayPlan's fetch/polling/offline-cache/acceptance
  logic) and opens the existing canonical overlay via _openPlanCard().
- The unified Problems card aggregates existing sources (/api/alerts,
  /api/tasks, /api/mangel/counts) with no new store, ranks
  critical > important > needs > defects, has an explicit empty state, and
  never turns an API error into "Проблем нет".
- The persistent DailyPlan bar is suppressed specifically on Home (where the
  compact card already shows the same status) and restored on other tabs,
  via _syncTodayPlanBarForView() called from switchView() -- not a competing
  CSS override on the bar's own inline display style (which already caused
  one real production bug for a different nav element, see applyRoleNav()).
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
HOME_JS = ROOT / "frontend" / "js" / "home.js"
TODAY_PLAN_JS = ROOT / "frontend" / "js" / "today-plan.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_legacy_alert_and_needs_tiles_removed_from_worker_home():
    src = _source(HOME_JS)
    start = src.index("async function initWorkerHomeView(")
    end = src.index("\n}\n", start)
    body = src[start:end]

    assert "worker-tile-important" not in body
    assert "worker-tile-critical" not in body
    assert "worker-tile-needs" not in body
    # Not blockers by definition -- explicitly kept per plan review
    assert 'id="worker-tile-messages"' in body
    assert 'id="worker-tile-tasks"' in body


def test_worker_home_renders_daily_plan_and_problems_cards():
    src = _source(HOME_JS)
    start = src.index("async function initWorkerHomeView(")
    end = src.index("\n}\n", start)
    body = src[start:end]

    assert 'id="worker-daily-plan-card"' in body
    assert 'id="worker-problems-card"' in body
    assert "_renderWorkerDailyPlanCard();" in body
    assert "_loadWorkerProblemsCard();" in body


def test_daily_plan_card_reuses_existing_state_and_overlay_no_new_fetch():
    src = _source(HOME_JS)
    start = src.index("function _renderWorkerDailyPlanCard(")
    end = src.index("\n}\n", start)
    body = src[start:end]

    # Reads the already-loaded state -- must not call api('/api/daily-plan/today') itself
    assert "window._todayPlanState" in body
    assert "api(" not in body
    # Opens the existing canonical overlay, does not render its own plan detail
    assert "_openPlanCard" in body


def _extract_problems_card_function(src: str) -> str:
    start = src.index("async function _loadWorkerProblemsCard(")
    next_fn = src.index("\nfunction ", start)
    next_async_fn = src.index("\nasync function ", start + 1)
    end = min(next_fn, next_async_fn) if next_fn != -1 and next_async_fn != -1 else max(next_fn, next_async_fn)
    return src[start:end]


def test_problems_card_aggregates_existing_sources_ranked_and_has_empty_state():
    body = _extract_problems_card_function(_source(HOME_JS))

    assert "api('/api/alerts')" in body
    assert "api('/api/tasks')" in body
    assert "api('/api/mangel/counts')" in body
    assert "rank: 0" in body  # critical alerts highest priority
    assert "rank: 3" in body  # defects lowest priority among problems
    assert "rows.sort((a, b) => a.rank - b.rank);" in body
    assert "Проблем нет" in body
    assert "const sourceErrors = []" in body
    assert "catch (e) {}" not in body
    assert "if (!rows.length && sourceErrors.length)" in body
    assert "Не удалось проверить проблемы" in body


def test_problems_card_deep_links_to_canonical_existing_views_no_new_screen():
    body = _extract_problems_card_function(_source(HOME_JS))

    assert "_openWorkerAlerts('red')" in body
    assert "_openWorkerAlerts('yellow')" in body
    assert "switchView('tasks')" in body
    assert "switchView('mangel')" in body


def test_open_defects_use_open_status_codes_not_resolved_ones():
    body = _extract_problems_card_function(_source(HOME_JS))

    assert "counts['gemeldet']" in body
    assert "counts['in Bearbeitung']" in body
    # Resolved/closed statuses must never be counted as open problems
    assert "'behoben'" not in body
    assert "'rejected'" not in body


def test_open_tasks_use_open_status_set_matching_backend_task_statuses():
    src = _source(HOME_JS)
    assert "const WORKER_OPEN_TASK_STATUSES = new Set(['открыто', 'в работе', 'заказано', 'принято']);" in src
    assert "String(t.status || '').trim().toLowerCase()" in src


def test_persistent_bar_hidden_on_home_synced_via_switch_view_not_css_override():
    app_src = _source(APP_HTML)
    assert "_syncTodayPlanBarForView(viewName);" in app_src

    tp_src = _source(TODAY_PLAN_JS)
    start = tp_src.index("function _syncTodayPlanBarForView(")
    end = tp_src.index("\n}\n", start)
    body = tp_src[start:end]

    assert "viewName === 'home'" in body
    assert "bar.style.display = 'none';" in body
    # Restoring on other tabs reuses the existing renderer, not a duplicated rule
    assert "_updateTodayPlanBar(_todayPlanState);" in body
