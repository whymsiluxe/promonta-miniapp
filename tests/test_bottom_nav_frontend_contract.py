from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_bottom_nav_active_item_is_scoped_to_current_role_nav():
    src = _source(APP_HTML)

    assert "function _activeBottomNavEl()" in src
    assert "function _syncBottomNavActive(viewName)" in src
    assert "const roleNav = currentRole === 'worker' ? workerNav : ownerNav;" in src
    assert "nav.querySelector(`.nav-item[data-view=\"${viewName}\"]`)" in src
    assert "_syncBottomNavActive(viewName);" in src
    assert "_syncBottomNavActive(activeView);" in src
    assert "document.querySelector(`.nav-item[data-view=\"${viewName}\"]`)" not in src


def test_bottom_nav_active_state_has_unified_apple_depth_for_owner_and_worker():
    src = _source(APP_HTML)

    assert ".bottom-nav .nav-item.active .nav-icon-svg" in src
    assert "radial-gradient(circle at 32% 18%" in src
    assert "transform: translateY(-2px) scale(1.03);" in src
    assert "inset 0 1px 1px rgba(255,255,255,0.85)" in src
    assert ".bottom-nav .nav-item.active .nav-label" in src
