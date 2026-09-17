from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
ASSIGNMENT_SHEET = ROOT / "frontend" / "js" / "assignment-sheet.js"
TEAM_DRAG = ROOT / "frontend" / "js" / "team-drag-assign.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_team_drag_assign_script_is_loaded_after_assignment_sheet():
    html = _source(APP_HTML)

    assignment_idx = html.index('<script src="js/assignment-sheet.js"></script>')
    drag_idx = html.index('<script src="js/team-drag-assign.js"></script>')
    assert assignment_idx < drag_idx


def test_team_drag_assign_decorates_free_workers_and_object_dropzones():
    js = _source(TEAM_DRAG)

    assert "#wo-anchor-without-object .wo-worker-row[data-uid]" in js
    assert "wo-drag-handle" in js
    assert "wo-object-dropzone" in js
    assert "document.elementsFromPoint" in js
    assert "new MutationObserver(scheduleEnhance)" in js
    assert "api('/api/objects')" in js
    assert "normalizeObjectDto" in js


def test_drop_opens_full_assignment_sheet_with_worker_and_object_preselected():
    js = _source(TEAM_DRAG)

    assert "openAssignmentSheet({" in js
    assert "userId: drag.userId" in js
    assert "userName: drag.userName" in js
    assert "objectId: target.dataset.dragObjectId" in js
    assert "objectName: target.dataset.dragObjectName" in js
    assert "/api/objects/${opt.dataset.oid}/assign" not in js


def test_assignment_sheet_skips_redundant_picker_when_worker_and_object_known():
    js = _source(ASSIGNMENT_SHEET)

    assert "mode: knownObject && knownWorker ? 'from_worker_object'" in js
    assert "_asState.objectId && _asState.userIds.length ? 'task_note' : 'workers'" in js
    assert "initialDate = opts.initialDate || opts.dateFrom || ''" in js
    assert "openAssignmentSheet({ userId, userName, initialDate })" in js


def test_team_drag_assign_styles_are_present():
    html = _source(APP_HTML)

    for selector in (
        "#view-working-objects .wo-drag-handle",
        "#view-working-objects .wo-object-dropzone",
        "#view-working-objects .wo-object-dropzone.wo-drop-active",
        ".wo-drag-ghost",
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert selector in html
