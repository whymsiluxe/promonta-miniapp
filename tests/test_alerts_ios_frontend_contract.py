from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
HOME_JS = ROOT / "frontend" / "js" / "home.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_alerts_sheet_uses_svg_title_close_and_button_tabs():
    js = _source(HOME_JS)

    assert "const HOME_ALERT_ICONS = {" in js
    for icon in ("title", "red", "yellow", "green", "activity", "close", "chevron"):
        assert f"{icon}:" in js

    assert "function _homeAlertIcon(alert)" in js
    assert "alerts-title-icon" in js
    assert 'aria-label="Закрыть"' in js
    assert 'type="button" class="alerts-tab active" data-filter="all"' in js
    assert 'type="button" class="alerts-tab" data-filter="red"' in js
    assert 'type="button" class="alerts-tab" data-filter="yellow"' in js
    assert "🔔 Алерты" not in js


def test_alerts_css_bridges_to_ios_bottom_sheet_language():
    html = _source(APP_HTML)

    for selector in (
        "#alerts-modal .alerts-modal-inner",
        "#alerts-modal .alerts-title-icon",
        "#alerts-modal .alerts-filter-tabs",
        "#alerts-modal .alerts-tab.active",
        "#alerts-modal .alerts-list",
        "#alerts-modal .alert-item-icon svg",
        "#alerts-modal .alerts-close-btn",
    ):
        assert selector in html

    assert "var(--ios-surface" in html
    assert "var(--ios-grouped-surface" in html
    assert "var(--ios-border" in html
    assert "var(--ios-radius-sheet" in html
    assert "text-transform: none;" in html
    assert "letter-spacing: 0;" in html


def test_alert_items_use_status_icons_without_emoji_severity_circles():
    js = _source(HOME_JS)
    render_start = js.index("function _renderAlerts(alerts)")
    render_block = js[render_start : js.index("// ═══════════ Worker Dashboard", render_start)]

    assert "_homeAlertIcon(a)" in render_block
    assert "alert-item-icon-${esc(a.type || 'green')}" in render_block
    assert "${HOME_ALERT_ICONS.chevron}" in render_block
    for emoji in ("🔴", "🟡", "🟢", "💬"):
        assert emoji not in render_block
