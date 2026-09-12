from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MY_TASKS_JS = ROOT / "frontend" / "js" / "my-tasks.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_my_tasks_view_fails_soft_when_mount_is_missing():
    src = _source(MY_TASKS_JS)

    assert "const list = document.getElementById('my-tasks-list')" in src
    assert "if (!list) return;" in src


def test_decline_assignment_sheet_checks_required_dom_before_wiring():
    src = _source(MY_TASKS_JS)

    assert "const cancelBtn = document.getElementById('my-task-decline-cancel-btn')" in src
    assert "const closeBtn = document.getElementById('my-task-decline-close-btn')" in src
    assert "const retryBtn = document.getElementById('my-task-decline-retry-btn')" in src
    assert "const backdrop = sheet.querySelector('.obj-stage-add-sheet-backdrop')" in src
    assert "Форма отказа временно недоступна" in src
    assert "cancelBtn.addEventListener('click', close)" in src
    assert "closeBtn.addEventListener('click', close)" in src
    assert "retryBtn.addEventListener('click', submit)" in src
