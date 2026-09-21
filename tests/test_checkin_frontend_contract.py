from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"
HOME_JS = ROOT / "frontend" / "js" / "home.js"
WORKER_CHECKIN_FAB_JS = ROOT / "frontend" / "js" / "worker-checkin-fab.js"
WORKER_SHIFT_STATE_JS = ROOT / "frontend" / "js" / "worker-shift-state.js"
RADIO_PLAYER_JS = ROOT / "frontend" / "js" / "components" / "radio-player.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_checkin_local_session_cache_handles_corrupt_json():
    src = _source(CHECKIN_JS)

    assert "const key = _checkinSessionKey(objectId)" in src
    assert "const raw = localStorage.getItem(key)" in src
    assert "return JSON.parse(raw)" in src
    assert "localStorage.removeItem(key)" in src
    assert "return null;" in src


def test_worker_stage_picker_has_real_modal_layer():
    html = _source(APP_HTML)
    fab = _source(WORKER_CHECKIN_FAB_JS)

    assert "#worker-object-picker-modal,\n#worker-stage-picker-modal,\n#worker-shift-status-modal" in html
    assert "z-index: 1800" in html
    assert "modal.id = 'worker-stage-picker-modal'" in fab
    assert "modal.dataset.noSwipe = '1';" in fab
    assert "function closeWorkerShiftPickers()" in fab
    assert "if (opts.isTabSwitch && typeof closeWorkerShiftPickers === 'function') closeWorkerShiftPickers();" in html


def test_worker_shift_pickers_registered_with_navigation_manager():
    # 18.09 audit finding (merged from upstream 4a69bc6, adapted to this
    # branch's own variable names -- functionally equivalent implementation,
    # not a duplicate): neither picker told NavigationManager about itself, so
    # Telegram BackButton/hardware-back had no way to know it should close the
    # picker first instead of leaving the app / going to the previous route.
    fab = _source(WORKER_CHECKIN_FAB_JS)

    assert "_workerObjectPickerOverlayUnregister" in fab
    assert "_workerStagePickerOverlayUnregister" in fab
    assert "_workerObjectPickerOverlayUnregister = NavigationManager.registerOverlay(_closeObjectPicker);" in fab
    assert "_workerStagePickerOverlayUnregister = NavigationManager.registerOverlay(_closeStagePicker);" in fab
    # closeWorkerShiftPickers() (the tab-switch cleanup path) must also unregister,
    # not just remove the DOM node -- otherwise a stale overlay-stack entry survives
    # a tab-switch close and a later Back press calls a close() bound to an already
    # gone element.
    assert "if (_workerObjectPickerOverlayUnregister) { _workerObjectPickerOverlayUnregister(); _workerObjectPickerOverlayUnregister = null; }" in fab
    assert "if (_workerStagePickerOverlayUnregister) { _workerStagePickerOverlayUnregister(); _workerStagePickerOverlayUnregister = null; }" in fab


def test_stage_picker_reregister_guard_avoids_duplicate_overlay_entries():
    # The stage picker re-renders itself in place after "add stage" (same modal id,
    # fresh DOM node) -- it must only call registerOverlay() on the FIRST render, not
    # on every re-render, or the Back-stack would grow one duplicate entry per stage
    # added in a single session.
    fab = _source(WORKER_CHECKIN_FAB_JS)

    assert "const isFirstRender = !existing;" in fab
    assert "if (isFirstRender && typeof NavigationManager !== 'undefined') {" in fab


def test_home_idle_shift_cta_uses_shared_start_flow():
    src = _source(HOME_JS)

    assert "resolveWorkerShiftState()" in src
    assert "WORKER_SHIFT_STATE.START_PENDING_SYNC" in src
    assert "WORKER_SHIFT_STATE.FINISH_PENDING_SYNC" in src
    assert "openWorkerShiftFlow({" in src
    assert "entryPoint: 'home'" in src


def test_worker_shift_state_resolver_prioritizes_outbox_before_server():
    html = _source(APP_HTML)
    src = _source(WORKER_SHIFT_STATE_JS)
    fab = _source(WORKER_CHECKIN_FAB_JS)

    assert '<script src="js/worker-shift-state.js"></script>' in html
    assert "async function resolveWorkerShiftState(options = {})" in src
    assert "promontaOutboxList(WORKER_SHIFT_OUTBOX_KIND_FINISH)" in src
    assert "promontaOutboxList(WORKER_SHIFT_OUTBOX_KIND_START)" in src
    assert "state: WORKER_SHIFT_STATE.FINISH_PENDING_SYNC" in src
    assert "state: WORKER_SHIFT_STATE.START_PENDING_SYNC" in src
    assert "api(path)" in src
    assert "async function openWorkerShiftFlow" in fab
    assert "openWorkerShiftStatusSheet(shiftState)" in fab


def test_worker_start_fab_base_position_uses_measured_nav_height_not_magic_number():
    # 18.09 (audit finding): .nav-item-start's base (non-radio-mini) position was
    # bottom: calc(max(14px, safe-area) + 96px) -- a fixed number not tied to the
    # bottom-nav's actual rendered height. Now uses --app-bottom-nav-height, same
    # measured-height pattern already used by .objects-fab and the radio-mini-visible
    # override for this same element.
    html = _source(APP_HTML)
    assert "bottom: calc(var(--app-bottom-nav-height, 70px) + max(10px, env(safe-area-inset-bottom)) + 20px);\n  z-index: 60;" in html
    assert "bottom: calc(max(14px, env(safe-area-inset-bottom)) + 96px);" not in html


def test_worker_start_fab_moves_above_radio_mini_player_everywhere():
    html = _source(APP_HTML)
    radio_js = _source(RADIO_PLAYER_JS)

    assert "body.radio-mini-visible .nav-item-start" in html
    assert "var(--app-bottom-nav-height, 70px) + max(10px, env(safe-area-inset-bottom)) + 74px" in html
    assert "body.keyboard-open .nav-item-start { display: none; }" in html
    assert "document.body.classList.toggle('radio-mini-visible', shouldShow);" in radio_js
    assert "document.body.classList.remove('radio-mini-visible');" in radio_js
