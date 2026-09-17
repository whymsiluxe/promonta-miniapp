from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
OBJECTS_JS = ROOT / "frontend" / "js" / "objects.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_object_info_tab_renders_owner_budget_dashboard_before_history():
    js = _source(OBJECTS_JS)

    assert ".then(() => renderObjectBudgetSection(_objDetailCurrentId))" in js
    assert ".then(() => renderObjectHistorySection(_objDetailCurrentId))" in js
    assert "id=\"obj-budget-section\"" in js
    assert "id=\"obj-budget-dashboard\"" in js
    assert "controlSection.insertAdjacentHTML('afterend', html)" in js


def test_object_budget_dashboard_uses_existing_budget_fields_and_aliases():
    js = _source(OBJECTS_JS)

    assert "'Бюджет (EUR)'" in js
    assert "'Потрачено (EUR)'" in js
    assert "'потрачено в % от бюджета', '% бюджета', 'Потрачено %'" in js
    assert "_objectBudgetAmount" in js
    assert "_objectBudgetPercent(obj, budget, spent)" in js
    assert "_objectBudgetMoney" in js


def test_object_budget_dashboard_is_owner_only_and_has_risk_states():
    js = _source(OBJECTS_JS)

    assert "if (currentRole !== 'owner') return;" in js
    assert "obj-budget-risk-${risk.key}" in js
    assert "pct >= 90" in js
    assert "pct >= 60" in js
    assert "Превышение бюджета" in js
    assert "Бюджет недоступен" in js


def test_object_budget_styles_are_present():
    html = _source(APP_HTML)

    for selector in (
        ".obj-budget-dashboard",
        ".obj-budget-head",
        ".obj-budget-risk-danger",
        ".obj-budget-meter-fill",
        ".obj-budget-stats",
        ".obj-budget-note",
    ):
        assert selector in html
