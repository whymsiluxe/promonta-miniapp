from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"
HOME_JS = ROOT / "frontend" / "js" / "home.js"
WORKER_CHECKIN_FAB_JS = ROOT / "frontend" / "js" / "worker-checkin-fab.js"


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

    assert "#worker-object-picker-modal,\n#worker-stage-picker-modal" in html
    assert "z-index: 1800" in html
    assert "modal.id = 'worker-stage-picker-modal'" in fab
    assert "modal.dataset.noSwipe = '1';" in fab


def test_home_idle_shift_cta_uses_shared_start_flow():
    src = _source(HOME_JS)

    assert "if (typeof _openStagePickerThenStart === 'function' && single)" in src
    assert "_openStagePickerThenStart(single['ID объекта']);" in src
    assert "else if (typeof _openWorkerObjectPicker === 'function')" in src
    assert "_openWorkerObjectPicker();" in src
