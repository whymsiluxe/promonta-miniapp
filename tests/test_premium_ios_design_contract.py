from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
TOKENS_CSS = ROOT / "frontend" / "css" / "tokens.css"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ios_component_primitives_exist_in_shared_tokens():
    src = _source(TOKENS_CSS)

    for token in (
        "--ios-page-bg",
        "--ios-surface",
        "--ios-grouped-surface",
        "--ios-border",
        "--ios-radius-card",
        "--ios-touch-target",
    ):
        assert token in src

    for cls in (
        ".ios-page",
        ".ios-section",
        ".ios-card",
        ".ios-list",
        ".ios-list-row",
        ".ios-segmented",
        ".ios-chip",
        ".ios-action-button",
        ".ios-icon-button",
        ".ios-bottom-sheet",
        ".ios-empty-state",
        ".ios-status-pill",
        ".ios-stat-tile",
    ):
        assert cls in src


def test_legacy_tabs_chips_cards_and_sheets_alias_to_ios_language():
    src = _source(APP_HTML)

    assert "13.09 Stage 1: premium iOS aliases" in src
    assert ".bottom-nav {" in src
    assert "var(--ios-surface" in src
    assert "var(--ios-grouped-surface" in src

    for selector in (
        ".doc-type-switch,",
        ".feed-saved-switch,",
        ".tasks-filters,",
        ".kd-filters,",
        ".profile-tabs,",
        ".profile-period-pills,",
        ".chat-category-tabs,",
        ".wx-city-tabs,",
        ".wx-object-tabs",
    ):
        assert selector in src

    for selector in (
        ".doc-type-opt.active,",
        ".feed-saved-opt.active,",
        ".filter-chip.active,",
        ".tasks-filter-chip.active,",
        ".kd-filter-chip.active,",
        ".profile-period-pill.active,",
        ".wx-city-tab.active,",
        ".wx-object-tab.active,",
        "#view-chat .chat-category-tabs .doc-type-opt.active",
    ):
        assert selector in src

    for selector in (
        ".home-shifts-section,",
        ".home-team-section,",
        ".home-rings-section,",
        ".home-calendar-widget,",
        ".active-shift-panel,",
        ".task-card,",
        ".mangel-column,",
        ".bottom-sheet-panel,",
        ".mangel-modal-content,",
        ".fw-inner,",
        ".kd-detail-sheet,",
    ):
        assert selector in src
