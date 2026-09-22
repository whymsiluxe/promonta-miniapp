"""22.09 iPhone screenshot audit (Item G/Calendar bottom-nav overlap finding):
--bottom-nav-safe-pad was referenced by CSS in 11 places across app.html but
was never actually SET anywhere -- no `--bottom-nav-safe-pad:` declaration, no
`setProperty('--bottom-nav-safe-pad', ...)` in any JS file. Every var(...) read
of it silently fell back to its second argument where one existed (a flat
guess like 7.5rem, ignoring the ACTUAL measured nav height) or to 0 bottom
padding where no fallback existed at all (body, #stages-view,
#view-object-detail) -- letting scrolled content sit directly behind or under
the floating bottom nav on real devices (owner-reported: Calendar's last
request card, Tasks, Tools, Working Objects, Profile).

All 11 usages were migrated to the real measured variable this app already
uses everywhere else, --app-bottom-nav-height (set by JS's
_applyBottomNavHeight() from the actual .bottom-nav element's offsetHeight).
This test locks in that --bottom-nav-safe-pad must never come back -- if a
future change reintroduces it, it must also actually set it, or use the real
measured variable instead.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"


def test_bottom_nav_safe_pad_dead_variable_is_not_referenced_anywhere():
    html = APP_HTML.read_text(encoding="utf-8")
    # Only mentions allowed are the explanatory comments left at the fix
    # sites -- no live `var(--bottom-nav-safe-pad` CSS read may remain.
    assert "var(--bottom-nav-safe-pad" not in html


def test_app_bottom_nav_height_is_actually_set_by_measured_js():
    html = APP_HTML.read_text(encoding="utf-8")
    assert "function _applyBottomNavHeight()" in html
    assert "document.documentElement.style.setProperty('--app-bottom-nav-height', h + 'px');" in html


def test_body_stages_view_and_object_detail_use_real_measured_bottom_padding():
    html = APP_HTML.read_text(encoding="utf-8")

    body_start = html.index("body {")
    body_block = html[body_start:html.index("}", body_start) + 1]
    assert "var(--app-bottom-nav-height, 70px)" in body_block

    stages_start = html.index("#stages-view { display: none;")
    stages_block = html[stages_start:html.index("}", stages_start) + 1]
    assert "var(--app-bottom-nav-height, 70px)" in stages_block

    detail_start = html.index("#view-object-detail { padding-bottom:")
    detail_block = html[detail_start:html.index("}", detail_start) + 1]
    assert "var(--app-bottom-nav-height, 70px)" in detail_block
