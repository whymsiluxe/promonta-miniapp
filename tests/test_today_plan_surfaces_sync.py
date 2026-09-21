"""Regression coverage for two P1s found in owner review of the fix-shift-start
merge, both about Today's DailyPlan surfaces (persistent bar + home.js's compact
card) and the Problems card going stale.

1. _updateTodayPlanBar() alone used to be called from the 60s poll and the
   amendment-accept flow -- home.js's _renderWorkerDailyPlanCard() (the DailyPlan
   card shown ON Today itself) was never re-rendered by either, so it kept
   showing stale data (e.g. an old item count) until Home was fully
   re-initialized. _updateWorkerDailyPlanSurfaces() is the single entry point
   that now updates both.

2. _updateTodayPlanBar() used to unconditionally set display:flex regardless of
   which view was currently active -- only _syncTodayPlanBarForView('home'),
   called from switchView() on tab-switch, suppressed it on Home. The 60s poll
   bypassed that check entirely, so a worker who stayed on Home past one poll
   tick saw the persistent bar reappear duplicating the same status already
   shown in the Home card -- exactly the duplicate Worker UX V2's Today
   redesign was built to eliminate. _updateTodayPlanBar() now checks the DOM
   itself (view-home.active) rather than relying only on the tab-switch hook.

3. Home for workers used to be gated by the same loadedViews cache as every
   other tab, but initWorkerHomeView() already has its own always-refresh
   behavior for workers (a lighter dashboard than owner's, by design) --
   the outer loadedViews gate sat OUTSIDE that and defeated it, so a worker
   who created a Defect and returned to Today saw the Problems card still
   say "Проблем нет" until a full app reload.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TODAY_PLAN_JS = ROOT / "frontend" / "js" / "today-plan.js"
FINISH_WIZARD_JS = ROOT / "frontend" / "js" / "finish-wizard.js"
APP_HTML = ROOT / "frontend" / "app.html"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fn(src: str, signature: str) -> str:
    start = src.index(signature)
    depth = 0
    i = src.index("{", start + len(signature))
    j = i
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


def test_shared_surfaces_updater_exists_and_updates_both():
    src = _source(TODAY_PLAN_JS)
    body = _fn(src, "function _updateWorkerDailyPlanSurfaces(data)")
    assert "_updateTodayPlanBar(data)" in body
    assert "_renderWorkerDailyPlanCard()" in body


def test_poll_interval_uses_shared_surfaces_updater_not_bar_alone():
    body = _fn(_source(TODAY_PLAN_JS), "function _startTodayPlanPolling(")
    assert "_updateWorkerDailyPlanSurfaces(data)" in body
    assert "_updateTodayPlanBar(data)" not in body, (
        "polling must refresh the Home card too, not just the persistent bar"
    )


def test_amendment_accept_and_plan_accept_use_shared_surfaces_updater():
    src = _source(TODAY_PLAN_JS)
    assert src.count("_updateWorkerDailyPlanSurfaces(freshData)") == 1
    assert src.count("_updateWorkerDailyPlanSurfaces(_todayPlanState)") >= 1


def test_finish_wizard_clears_plan_surfaces_via_shared_updater():
    body = _fn(_source(FINISH_WIZARD_JS), "function _fwMarkFinishConfirmed(record, notify)")
    assert "_updateWorkerDailyPlanSurfaces({ has_plan: false })" in body


def test_bar_checks_home_view_itself_not_only_the_tab_switch_hook():
    src = _source(TODAY_PLAN_JS)
    assert "function _isHomeViewCurrentlyActive()" in src
    body = _fn(src, "function _updateTodayPlanBar(data)")
    assert "_isHomeViewCurrentlyActive()" in body


def test_home_is_exempted_from_the_loaded_views_once_only_gate():
    # 21.09 (P1, owner review finding): initHomeView() must run on every
    # switchView('home', ...), not just the first one this session -- it
    # already has its own internal re-entry logic (initWorkerHomeView always
    # re-runs for workers; _homeLoaded short-circuits repeats for owners).
    html = _source(APP_HTML)
    gate_idx = html.index("if (!loadedViews.has(viewName)) {")
    home_call_idx = html.index("if (viewName === 'home') initHomeView();")
    assert home_call_idx < gate_idx, (
        "initHomeView() must be called BEFORE (outside) the loadedViews "
        "once-only gate, or Home only ever initializes on the first visit "
        "per session and Problems/DailyPlan cards go stale after that."
    )
