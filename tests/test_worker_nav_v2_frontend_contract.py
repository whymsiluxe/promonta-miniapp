"""Worker UX V2, Этап 4 — navigation contract (matrix п.16-18).

Same source-assertion style as tests/test_checkin_offline_outbox_frontend_contract.py.
Covers: worker bottom-nav is exactly 4 tabs (Сегодня/Объекты/Чат/Ещё), owner
bottom-nav is untouched (5 tabs, unchanged labels/order), the new `more` view
exists and only re-links to existing views (no duplicated business logic),
and `data-view="home"` id is preserved (only its label changed) so
NavigationManager's root-fallback (navigation-manager.js: back() -> 'home')
keeps working without modification.
"""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
NAV_MANAGER_JS = ROOT / "frontend" / "js" / "ui" / "navigation-manager.js"


def _source() -> str:
    return APP_HTML.read_text(encoding="utf-8")


def _extract_block(src: str, start_marker: str, end_marker: str) -> str:
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


def test_owner_bottom_nav_unchanged():
    src = _source()
    block = _extract_block(src, '<div class="bottom-nav" id="bottom-nav-owner">', '<div class="bottom-nav" id="bottom-nav-worker"')

    for view in ('feed', 'home', 'chat', 'objects', 'profile'):
        assert f'data-view="{view}"' in block, f"owner nav missing tab: {view}"

    assert '<span class="nav-label">Лента</span>' in block
    assert '<span class="nav-label">Главная</span>' in block
    assert '<span class="nav-label">Чат</span>' in block
    assert '<span class="nav-label">Объекты</span>' in block
    assert '<span class="nav-label">Профиль</span>' in block
    assert 'data-view="more"' not in block


def test_worker_bottom_nav_has_exactly_four_tabs():
    src = _source()
    block = _extract_block(src, '<div class="bottom-nav" id="bottom-nav-worker"', '<!-- Check-in FAB')

    assert block.count('nav-item') >= 4
    for view in ('home', 'objects', 'chat', 'more'):
        assert f'data-view="{view}"' in block, f"worker nav missing tab: {view}"
    # Removed as top-level worker tabs (still reachable via "Ещё"/existing views)
    assert 'data-view="feed"' not in block
    assert 'data-view="profile"' not in block


def test_worker_home_tab_keeps_its_route_id_label_renamed_to_segodnya():
    src = _source()
    block = _extract_block(src, '<div class="bottom-nav" id="bottom-nav-worker"', '<!-- Check-in FAB')

    assert 'data-view="home"' in block
    assert '<span class="nav-label">Сегодня</span>' in block
    assert '<span class="nav-label">Главная</span>' not in block


def test_more_view_exists_and_only_relinks_existing_views_no_duplicated_logic():
    src = _source()
    assert '<div class="view" id="view-more">' in src

    block = _extract_block(src, '<div class="view" id="view-more">', '<div class="view" id="view-profile">')

    # Every action must route through the existing switchView()/_openProfileTab()
    # mechanism onto an ALREADY EXISTING view id -- never a fresh view-more-* id.
    for target in ("switchView('abwesenheit')", "switchView('tools')",
                   "switchView('documents')", "switchView('profile')",
                   "switchView('feed')", "_openProfileTab('me')", "_openProfileTab('settings')"):
        assert target in block, f"'Ещё' item missing expected re-link: {target}"

    assert 'view-more-' not in src  # no sub-view sprawl under a "more/*" namespace


def test_open_profile_tab_helper_reuses_existing_tab_click_mechanism():
    src = _source()
    start = src.index('function _openProfileTab(')
    end = src.index('\n}\n', start) + len('\n}\n')
    body = src[start:end]

    assert "switchView('profile')" in body
    assert '.profile-tab[data-tab="${tab}"]' in body
    assert '.click()' in body  # reuses the same path a real user tap takes


def test_tab_order_is_split_per_role_matching_each_navs_real_dom_order():
    # 21.09 (owner review finding): a single shared TAB_ORDER (owner's DOM
    # order) was also used for the worker tab-bar's slide-direction math, but
    # bottom-nav-worker's real order is home/objects/chat/more, not
    # feed/home/chat/objects/profile -- Объекты<->Чат visually goes
    # left-to-right for a worker but TAB_ORDER.indexOf() said objects(3) >
    # chat(2), animating the wrong direction. Not a functional break, just
    # felt wrong -- but the fix is to key off the DOM each role actually has.
    src = _source()
    assert "const OWNER_TAB_ORDER = ['feed', 'home', 'chat', 'objects', 'profile', 'more'];" in src
    assert "const WORKER_TAB_ORDER = ['home', 'objects', 'chat', 'more'];" in src
    assert "function _currentTabOrder()" in src
    assert "currentRole === 'worker' ? WORKER_TAB_ORDER : OWNER_TAB_ORDER" in src
    assert "const _tabOrder = _currentTabOrder();" in src
    assert "_tabOrder.indexOf(_lastActiveTabView)" in src
    assert "_tabOrder.indexOf(viewName)" in src


def test_worker_tab_order_matches_bottom_nav_worker_dom_order():
    html = _source()
    nav_start = html.index('id="bottom-nav-worker"')
    nav_end = html.index('Check-in FAB', nav_start)
    nav_html = html[nav_start:nav_end]
    views_in_dom_order = re.findall(r'data-view="(\w+)"', nav_html)
    assert views_in_dom_order == ['home', 'objects', 'chat', 'more']


def test_profile_more_documents_id_exists_so_the_worker_hide_toggle_actually_runs():
    # 21.09 (owner review finding): applyRoleNav() reads
    # document.getElementById('profile-more-documents') to hide "Документы"
    # from the worker's "Ещё" menu (28.07: not their tool, owner-only) -- but
    # the more-menu-item never had that id, so getElementById() always
    # returned null and the hide never ran. Documents silently stayed visible
    # to workers this whole time.
    html = _source()
    assert 'id="profile-more-documents" onclick="switchView(\'documents\')"' in html
    assert "const docsMenuItem = document.getElementById('profile-more-documents');" in html
    assert "docsMenuItem.style.display = currentRole === 'worker' ? 'none' : '';" in html


def test_navigation_manager_root_fallback_still_targets_home_unchanged():
    # Confirms the deliberate choice: rename the LABEL only, not the route id,
    # so this fallback (and everything else keyed on 'home') needed zero changes.
    src = NAV_MANAGER_JS.read_text(encoding="utf-8")
    assert "current().screen !== 'home'" in src
    assert "switchView('home', { isTabSwitch: true });" in src
