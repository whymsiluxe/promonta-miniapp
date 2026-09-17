from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
OBJECTS_JS = ROOT / "frontend" / "js" / "objects.js"
TASKS_JS = ROOT / "frontend" / "js" / "tasks.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_object_info_appends_task_kanban_between_budget_and_history():
    js = _source(OBJECTS_JS)

    assert ".then(() => renderObjectBudgetSection(_objDetailCurrentId))" in js
    assert ".then(() => renderObjectTaskKanbanSection(_objDetailCurrentId))" in js
    assert ".then(() => renderObjectHistorySection(_objDetailCurrentId))" in js
    assert 'id="obj-task-kanban-section"' in js
    assert 'id="obj-task-kanban-board"' in js
    assert "budgetSection.insertAdjacentHTML('afterend', html)" in js


def test_object_task_kanban_uses_existing_object_scoped_tasks_workflow():
    js = _source(OBJECTS_JS)

    assert "`/api/tasks?object_id=${encodeURIComponent(objectId)}`" in js
    assert "const groups = { new: [], accepted: [], done: [] }" in js
    assert "return 'открыто';" in js
    assert "return 'в работе';" in js
    assert "return 'закрыто';" in js
    assert "{ key: 'new', title: 'Нужно' }" in js
    assert "{ key: 'accepted', title: 'В работе' }" in js
    assert "{ key: 'done', title: 'Готово' }" in js


def test_object_task_kanban_has_owner_actions_drag_drop_and_chat():
    js = _source(OBJECTS_JS)

    assert 'draggable="true"' in js
    assert "data-kanban-set-status" in js
    assert "await api(`/api/tasks/${taskId}`, { method: 'PATCH'" in js
    assert "dataTransfer.setData('text/plain', card.dataset.kanbanTaskId)" in js
    assert "dataTransfer.getData('text/plain')" in js
    assert "_objectTaskKanbanStatusFor(targetStage)" in js
    assert "openObjectOrMangelChat(`task:${btn.dataset.kanbanChat}`" in js


def test_task_screen_status_changes_refresh_object_kanban():
    js = _source(TASKS_JS)

    assert "if (typeof _refreshObjTaskKanban === 'function') _refreshObjTaskKanban();" in js


def test_object_task_kanban_styles_are_present():
    html = _source(APP_HTML)

    for selector in (
        ".obj-task-kanban-board",
        ".obj-task-kanban-columns",
        ".obj-task-kanban-lane",
        ".obj-task-kanban-drop-active",
        ".obj-task-kanban-card",
        ".obj-task-kanban-action",
        ".obj-task-kanban-chat",
    ):
        assert selector in html
