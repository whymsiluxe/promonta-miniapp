from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
TASKS_JS = ROOT / "frontend" / "js" / "tasks.js"
SHARED_JS = ROOT / "frontend" / "js" / "shared.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tasks_view_block(html: str) -> str:
    start = html.index('<div class="view ios-page" id="view-tasks">')
    end = html.index('<div class="view" id="view-mangel">', start)
    return html[start:end]


def test_needs_markup_uses_ios_page_icon_add_and_plain_voice_priority_labels():
    html = _source(APP_HTML)
    block = _tasks_view_block(html)

    assert '<div class="view ios-page" id="view-tasks">' in block
    assert 'class="fab tasks-new-btn ios-icon-button"' in block
    assert 'aria-label="Новая потребность"' in block
    assert '<svg viewBox="0 0 24 24" width="20" height="20"' in block
    assert 'id="tasks-voice-btn" class="fw-voice-btn tasks-voice-btn"' in block
    assert '<span>Голосом</span>' in block
    assert 'id="tasks-priority-row"' in block
    assert 'data-priority="срочно" style="flex:1;">Срочно</button>' in block
    assert "🎤 Голосом" not in block
    assert "🔴 Срочно" not in block


def test_needs_css_bridges_to_ios_summary_filters_and_list_rows():
    html = _source(APP_HTML)

    for selector in (
        "#view-tasks header h1",
        "#view-tasks .tasks-new-btn",
        "#view-tasks #tasks-form",
        "#view-tasks .tasks-voice-btn",
        "#view-tasks .tasks-counters",
        "#view-tasks .tasks-counter-tile",
        "#view-tasks .tasks-filters",
        "#view-tasks .tasks-filter-chip.active",
        "#view-tasks .task-card",
        "#view-tasks .task-primary-btn",
        "#view-tasks .task-chat-btn",
        "#view-tasks .task-menu-btn",
    ):
        assert selector in html

    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in html
    assert "text-transform: none;" in html
    assert "letter-spacing: 0;" in html
    assert "var(--ios-surface" in html
    assert "var(--ios-grouped-surface" in html
    assert "var(--bottom-nav-safe-pad" in html


def test_needs_js_renders_stat_tiles_svg_actions_and_wires_once():
    js = _source(TASKS_JS)

    assert "const TASK_ICONS = {" in js
    assert "TASK_ICONS.chat" in js
    assert "TASK_ICONS.more" in js
    assert "tasks-counter-tile ios-stat-tile" in js
    assert "task-primary-btn ios-action-button" in js
    assert "task-chat-btn ios-action-button" in js
    assert "task-menu-btn ios-icon-button" in js
    assert "Объекты недоступны — попробуй позже" in js
    assert "⚠️ Объекты недоступны" not in js

    assert "const filtersEl = document.getElementById('tasks-filters');" in js
    assert "filtersEl.dataset.wired = '1';" in js
    assert "const newBtn = document.getElementById('tasks-new-btn');" in js
    assert "newBtn.dataset.wired = '1';" in js
    assert "const priorityRow = document.getElementById('tasks-priority-row');" in js
    assert "priorityRow.dataset.wired = '1';" in js
    assert "const categoryRow = document.getElementById('tasks-category-row');" in js
    assert "categoryRow.dataset.wired = '1';" in js


def test_shared_voice_helper_restores_original_button_html():
    js = _source(SHARED_JS)

    assert "const idleHtml = buttonEl.innerHTML;" in js
    assert "buttonEl.innerHTML = idleHtml;" in js
    assert "buttonEl.textContent = 'Стоп';" in js
    assert "buttonEl.textContent = 'Распознаю...';" in js
    assert "buttonEl.textContent = '🎤';" not in js
