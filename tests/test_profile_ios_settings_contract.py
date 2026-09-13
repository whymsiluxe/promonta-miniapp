from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
PROFILE_JS = ROOT / "frontend" / "js" / "profile.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_profile_markup_uses_ios_settings_lists_and_svg_icons():
    js = _source(PROFILE_JS)

    assert "const PROFILE_ICONS = {" in js
    assert "profile-settings-list profile-actions-list" in js
    assert "profile-settings-list profile-system-list" in js
    assert "profile-settings-list profile-access-list" in js
    assert "profile-icon-calendar" in js
    assert "profile-icon-object" in js
    assert "profile-icon-edit" in js
    assert "profile-icon-birthday" in js
    assert "profile-icon-skills" in js
    assert "profile-icon-sizes" in js
    assert ">📷<" not in js
    assert ">📅<" not in js
    assert ">🏗️<" not in js
    assert ">🎂<" not in js
    assert ">🛠<" not in js
    assert ">👕<" not in js


def test_profile_css_bridges_to_ios_settings_language():
    html = _source(APP_HTML)

    for selector in (
        "#view-profile .profile-header-card",
        "#view-profile .profile-tab-panel > .card",
        "#view-profile .profile-settings-list",
        "#view-profile .profile-owner-action-btn",
        "#view-profile .profile-app-status-row",
        "#view-profile .profile-team-row",
        "#view-profile .accordion-header",
        "#view-profile .accordion-icon svg",
        "#view-profile .profile-team-group-title",
    ):
        assert selector in html

    assert "font-size: 36px" in html
    assert "text-transform: none" in html
    assert "letter-spacing: 0" in html
    assert "var(--ios-surface" in html
    assert "var(--ios-separator" in html
    assert "min-height: var(--ios-touch-target, 44px)" in html
