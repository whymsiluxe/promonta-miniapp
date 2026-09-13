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
