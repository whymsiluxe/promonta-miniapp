from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
TOOLS_JS = ROOT / "frontend" / "js" / "tools.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tools_markup_uses_ios_search_segmented_filters_and_owner_add_icon():
    html = _source(APP_HTML)

    assert '<div class="view ios-page" id="view-tools">' in html
    assert 'class="fab tools-add-btn ios-icon-button"' in html
    assert 'aria-label="Добавить инструмент"' in html
    assert 'title="Добавить инструмент"' in html
    assert '<svg viewBox="0 0 24 24" width="20" height="20"' in html

    assert html.count('class="tools-summary-tile') == 4
    assert 'class="tools-summary-tile active" data-filter="all" type="button" aria-pressed="true"' in html
    assert 'data-filter="free" type="button" aria-pressed="false"' in html
    assert 'data-filter="in-use" type="button" aria-pressed="false"' in html
    assert 'data-filter="repair" type="button" aria-pressed="false"' in html

    assert 'class="search-bar tools-search-wrap"' in html
    assert 'class="tools-search-icon" aria-hidden="true"' in html
    assert 'placeholder="Название, №, объект, сотрудник"' in html
    assert 'aria-label="Поиск инструментов"' in html
    assert 'autocomplete="off"' in html


def test_tools_css_bridges_to_premium_ios_list_language():
    html = _source(APP_HTML)

    for selector in (
        # 17.09: #view-tools header h1's own 36px/800 override removed as a
        # duplicate of the canonical top-level page-title, which now lives
        # only on the base `header h1` rule (28px/800) -- 36px overflowed the
        # header's centered column on real iPhone.
        "#view-tools .tools-add-btn",
        "#view-tools .tools-summary-bar",
        "#view-tools .tools-summary-tile",
        "#view-tools .tools-summary-tile.active",
        "#view-tools .tools-search-wrap",
        "#view-tools .tools-search-wrap input",
        "#view-tools .card.tool-card",
        "#view-tools .tool-card .tool-card-action-btn",
    ):
        assert selector in html

    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in html
    assert "text-transform: none;" in html
    assert "letter-spacing: 0;" in html
    assert "font-size: 16px;" in html
    assert "text-overflow: ellipsis;" in html
    assert "var(--ios-grouped-surface" in html
    assert "var(--ios-surface" in html
    assert "var(--bottom-nav-safe-pad" in html


def test_tools_init_handlers_are_wired_once_and_keep_pressed_state():
    js = _source(TOOLS_JS)

    assert "const addBtn = document.getElementById('add-tool');" in js
    assert "const searchInput = document.getElementById('tools-search');" in js
    assert "const summaryBar = document.getElementById('tools-summary-bar');" in js
    assert "addBtn.dataset.wired = '1';" in js
    assert "searchInput.dataset.wired = '1';" in js
    assert "summaryBar.dataset.wired = '1';" in js
    assert "t.setAttribute('aria-pressed', 'false');" in js
    assert "tile.setAttribute('aria-pressed', 'true');" in js
    assert "toolsActiveFilter = tile.dataset.filter;" in js
