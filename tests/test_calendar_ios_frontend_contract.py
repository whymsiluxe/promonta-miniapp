from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
ABW_JS = ROOT / "frontend" / "js" / "abwesenheit.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _reason_select_block(html: str) -> str:
    start = html.index('<select id="abw-reason-select"')
    end = html.index("</select>", start)
    return html[start:end]


def _abw_palette_block(html: str) -> str:
    start = html.index("--abw-bg:")
    end = html.index("}\n\n#view-abwesenheit.active", start)
    return html[start:end]


def test_calendar_screen_uses_light_ios_page_and_month_controls():
    html = _source(APP_HTML)
    palette = _abw_palette_block(html)

    assert '<div class="view ios-page" id="view-abwesenheit">' in html
    assert "--abw-bg: var(--ios-page-bg" in palette
    assert "--abw-surface: var(--ios-surface" in palette
    assert "--abw-surface-raised: var(--ios-grouped-surface" in palette
    assert "#2A2D27" not in palette
    assert "#34382F" not in palette
    assert "#3D423A" not in palette

    assert 'id="abw-prev-month" class="abw-month-btn" type="button" aria-label="Предыдущий месяц"' in html
    assert 'id="abw-next-month" class="abw-month-btn" type="button" aria-label="Следующий месяц"' in html
    assert "#view-abwesenheit .abwesenheit-month-nav" in html
    assert "#view-abwesenheit .abw-month-btn" in html
    assert "#view-abwesenheit .heatmap-cell" in html
    assert "#view-abwesenheit .abw-state-available" in html


def test_calendar_period_filters_and_cards_bridge_to_ios_language():
    html = _source(APP_HTML)

    for selector in (
        "#view-abwesenheit .abw-period-pills",
        "#view-abwesenheit .abw-period-pill",
        "#view-abwesenheit .abw-period-pill.active",
        "#view-abwesenheit .abw-metric-chip",
        "#view-abwesenheit .abw-period-grid",
        "#view-abwesenheit .abw-request-card",
        "#view-abwesenheit .abw-request-chat-btn",
        "#view-abwesenheit .abw-request-avatar",
    ):
        assert selector in html

    assert "text-transform: none" in html
    assert "letter-spacing: 0" in html
    assert "var(--ios-surface" in html
    assert "var(--ios-grouped-surface" in html
    # 22.09 (iPhone screenshot audit): --bottom-nav-safe-pad was NEVER set
    # anywhere in the codebase -- a real device showed the calendar's bottom
    # nav almost overlapping the last request card's action row. Real
    # measured height now used instead (see .abw-request-card:last-child).
    assert "var(--app-bottom-nav-height" in html


def test_calendar_reason_select_removes_emoji_labels():
    block = _reason_select_block(_source(APP_HTML))

    assert '<option value="Krankheit">Болезнь</option>' in block
    assert '<option value="Urlaub">Отпуск</option>' in block
    assert '<option value="Sonstiges">Другое</option>' in block
    for emoji in ("🤒", "🏖", "📋"):
        assert emoji not in block


def test_calendar_js_uses_svg_icons_and_wires_controls_once():
    js = _source(ABW_JS)

    assert "const ABW_ICONS = {" in js
    assert "ABW_ICONS.chat" in js
    assert "ABW_ICONS.calendar" in js
    assert "ABW_ICONS.clock" in js
    assert "aria-label=\"Написать в чат\"" in js
    assert "💬" not in js
    assert "📅" not in js
    assert "⚠️ Работники недоступны" not in js

    assert "async function _shiftAbwMonth(delta)" in js
    assert "const prevBtn = document.getElementById('abw-prev-month');" in js
    assert "const nextBtn = document.getElementById('abw-next-month');" in js
    assert "const reasonSheet = document.getElementById('abw-reason-sheet');" in js
    assert "prevBtn.dataset.wired = '1';" in js
    assert "nextBtn.dataset.wired = '1';" in js
    assert "reasonSheet.dataset.wired = '1';" in js
    assert "saveBtn.dataset.wired = '1';" in js
