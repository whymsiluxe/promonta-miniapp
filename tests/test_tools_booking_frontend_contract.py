from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
TOOLS_JS = ROOT / "frontend" / "js" / "tools.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tools_view_has_booking_calendar_controls():
    html = _source(APP_HTML)
    js = _source(TOOLS_JS)

    assert 'id="tool-booking-panel"' in html
    assert 'Календарь инструмента' in html
    assert 'id="tool-booking-tool"' in html
    assert 'id="tool-booking-object"' in html
    assert 'id="tool-booking-holder"' in html
    assert 'id="tool-booking-from"' in html
    assert 'id="tool-booking-to"' in html
    assert 'id="tool-booking-submit"' in html

    assert "let TOOL_BOOKINGS = [];" in js
    assert "async function loadToolBookings()" in js
    assert "async function _submitToolBooking()" in js
    assert "api(`/api/tools/bookings?date_from=" in js
    assert "api(`/api/tools/${encodeURIComponent(toolId)}/bookings`" in js
    assert "method: 'DELETE'" in js
    assert "currentRole === 'owner'" in js


def test_tools_booking_css_is_ios_compact_and_non_overlapping():
    html = _source(APP_HTML)

    assert "#view-tools .tool-booking-panel" in html
    assert "#view-tools .tool-booking-form" in html
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in html
    assert "#view-tools .tool-booking-row" in html
    assert "#view-tools .tool-booking-cancel" in html
