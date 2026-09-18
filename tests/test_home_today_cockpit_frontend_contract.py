from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
HOME_JS = ROOT / "frontend" / "js" / "home.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_owner_home_renders_today_cockpit_from_operational_sources():
    src = _source(HOME_JS)

    assert 'id="home-today-cockpit"' in src
    assert "async function _loadHomeTodayCockpit()" in src
    assert "_loadHomeTodayCockpit();" in src
    assert "/api/dashboard/shifts-today" in src
    assert "/api/dashboard/active-blockers" in src
    assert "/api/daily-plan/owner/today" in src
    assert "/api/tasks" in src
    assert "not_started" in src
    assert "awaiting_response" in src
    assert "overdueTasks" in src
    assert "budgetRisks" in src
    assert "planRisks" in src
    assert "Остальное спокойно" in src
    assert "Активные смены" in src
    assert "Внимание" in src
    assert "<small>рабочих</small>" in src
    assert "<small>работников</small>" not in src


def test_home_dashboard_uses_today_title_and_flat_ios_surfaces():
    src = _source(APP_HTML)

    assert '<header><h1>Сегодня</h1></header>' in src
    assert ".home-today-cockpit {" in src
    assert ".home-today-stats {" in src
    assert ".home-today-row {" in src
    assert "#view-home .kpi-tile," in src
    assert "transform: none !important;" in src
    assert "#view-home .kpi-tile::after" in src
    assert "display: none;" in src


def test_home_dashboard_renders_sparklines_from_shift_series():
    html = _source(APP_HTML)
    js = _source(HOME_JS)

    assert ".home-today-sparklines" in html
    assert ".home-sparkline-svg" in html
    assert "function _homeSparklineSvg(values)" in js
    assert "const sparkDays = shiftsData.sparkline?.days || [];" in js
    assert "_homeTodaySparkCard('Часы'" in js
    assert "sparkDays.map(d => d.hours)" in js
    assert "sparkDays.map(d => d.shifts)" in js
    assert "sparkDays.map(d => d.finished)" in js


def test_home_dashboard_does_not_render_duplicate_legacy_kpi_grid():
    src = _source(HOME_JS)

    assert 'id="home-today-cockpit"' in src
    assert 'id="home-kpi-bar"' not in src
    assert 'id="home-kpi-bar-2"' not in src


def test_home_dashboard_has_message_and_calendar_counters():
    js = _source(HOME_JS)

    assert 'id="home-chat-badge"' in js
    assert 'id="home-calendar-badge"' in js
    assert "function _homeCounterLabel(count)" in js
    assert "return n > 99 ? '99+' : String(n);" in js
    assert "_setHomeCounter('home-chat-badge', count);" in js
    assert "_setHomeCounter('home-calendar-badge', upcoming.length);" in js


def test_home_calendar_widget_uses_polished_ios_rows():
    html = _source(APP_HTML)

    assert ".home-calendar-widget .home-section-title" in html
    assert ".hcw-row:last-child" in html
    assert ".hcw-status { max-width: 44%;" in html
    assert ".hcw-free { background:" in html
    assert ".hcw-assigned { background:" in html
    assert ".hcw-working { background:" in html
    assert ".hcw-absent { background:" in html
    assert "font-variant-numeric: tabular-nums;" in html
