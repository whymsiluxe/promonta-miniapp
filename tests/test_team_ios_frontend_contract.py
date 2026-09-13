from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
HOME_JS = ROOT / "frontend" / "js" / "home.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _working_objects_view_block(html: str) -> str:
    start = html.index('<div class="view ios-page" id="view-working-objects">')
    end = html.index('<div class="view" id="view-feed">', start)
    return html[start:end]


def test_team_view_uses_ios_page_segmented_buttons():
    html = _source(APP_HTML)
    block = _working_objects_view_block(html)

    assert '<div class="view ios-page" id="view-working-objects">' in block
    assert 'class="doc-type-switch wo-mode-switch ios-segmented"' in block
    assert '<button type="button" class="doc-type-opt active" data-wo-mode="summary">' in block
    assert '<button type="button" class="doc-type-opt" data-wo-mode="plan">' in block


def test_team_js_uses_ios_primitives_and_svg_plan_controls():
    js = _source(HOME_JS)

    assert "const WO_ICONS = {" in js
    for icon in ("calendar", "kontrol", "chevronDown"):
        assert f"{icon}:" in js

    for hook in (
        "wo-summary-tile ios-stat-tile",
        "wo-th-total ios-stat-tile",
        "wo-team-card ios-list-row",
        "wo-team-card-status wo-status-active ios-status-pill",
        "wo-worker-row ios-list-row",
        "wo-assign-btn ios-action-button",
        "wo-blocker-resolve-btn ios-action-button",
        "wo-plan-object-block ios-list",
        "wo-plan-row ios-list-row",
        "wo-plan-status-${a.assignment_status} ios-status-pill",
        "wo-assign-sheet-inner ios-bottom-sheet",
        "wo-assign-sheet-opt ios-list-row",
    ):
        assert hook in js

    assert 'type="button" class="wo-plan-date-opt' in js
    assert "wo-plan-control-btn ios-action-button" in js
    assert "${WO_ICONS.calendar}" in js
    assert "${WO_ICONS.kontrol}" in js
    assert "${WO_ICONS.chevronDown}" in js
    assert "📅" not in js
    assert "📊" not in js
    assert "▾" not in js
    assert "● Смена идёт" not in js


def test_team_css_bridges_summary_lists_plan_and_sheet_to_ios_language():
    html = _source(APP_HTML)

    for selector in (
        "#view-working-objects {",
        "#view-working-objects header h1",
        "#view-working-objects .wo-mode-switch",
        "#view-working-objects .wo-summary-bar",
        "#view-working-objects .wo-summary-tile",
        "#view-working-objects .wo-team-card",
        "#view-working-objects .wo-worker-row",
        "#view-working-objects .wo-th-row",
        "#view-working-objects .wo-plan-row",
        "#view-working-objects .wo-plan-date-opt.active",
        "#view-working-objects .wo-plan-control-btn",
        ".wo-assign-sheet .wo-assign-sheet-inner",
    ):
        assert selector in html

    assert "var(--ios-page-bg" in html
    assert "var(--ios-surface" in html
    assert "var(--ios-grouped-surface" in html
    assert "var(--ios-border" in html
    assert "var(--ios-radius-sheet" in html
    assert "text-transform: none;" in html
    assert "letter-spacing: 0;" in html
    assert "font-size: 36px;" in html
