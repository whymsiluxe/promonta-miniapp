"""Object Detail V2 (Этап 7), migration step 1 — internal zone shell.

Per docs/OBJECT_DETAIL_V2_IMPLEMENTATION_PLAN.md's corrected migration order
(owner review found a real sequencing bug in an earlier version of that plan):
the new Обзор/Работа/Медиа/Чат zone-routing architecture is added BEFORE the
visible tab bar changes, not the other way around. This step must NOT:
  - expose all 7 tabs (3 legacy + 4 new) to the user at once
  - replace the production tab bar with empty "Скоро будет" placeholders
  - duplicate renderObjectStagesTab/embedObjectChat with a second implementation

This file locks in that step-1 contract: the production UI (chat/info/stages)
is untouched, the new zone containers/routing exist internally, 'work' and
'chat' reuse the existing renderers (not a second implementation), and
'overview'/'media' are real containers with no content wired in yet.

22.09 addendum (step 2, safety revert): a same-session attempt to rename the
LIVE stages panel's id to end in "-work" broke production -- both
openObjectDetail() and _objDetailTabClick() build the DOM id as
`obj-detail-panel-${tab}` where tab is the routing-key STRING 'stages' (never
renamed), so the rename made them look up a now-nonexistent id and throw on
`.style.display`. Reverted: #obj-detail-panel-stages stays the one live
mount, #obj-detail-panel-work stays a separate INERT V2-shell container --
never a fallback for the other, never merged into one id. The canonical
cutover (tab key + panel id + routing + renderer + every caller, changed
together in one atomic step) is still a real future step, not done here.
frontend/js/object-work-shift-panel.js exists in the repo as an unwired
draft for that future cutover -- its <script> tag was deliberately removed
from app.html so it cannot execute in the live app; see that file's own
top-of-file comment for what it will need to be wired into and why.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
OBJECTS_JS = ROOT / "frontend" / "js" / "objects.js"
OBJECT_INFO_JS = ROOT / "frontend" / "js" / "object-info.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fn(src: str, signature: str) -> str:
    start = src.index(signature)
    depth = 0
    i = src.index("{", start + len(signature))
    j = i
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


def test_production_tab_bar_is_still_exactly_the_3_legacy_tabs():
    # The visible #obj-detail-tabs markup and OBJ_DETAIL_TAB_ORDER must be
    # completely unchanged by this step -- the new zones are internal only.
    html = _source(APP_HTML)
    assert 'data-obj-tab="chat"' in html
    assert 'data-obj-tab="info"' in html
    assert 'data-obj-tab="stages"' in html
    assert 'data-obj-tab="overview"' not in html, "Обзор must not be in the visible tab bar yet"
    assert 'data-obj-tab="work"' not in html, "Работа must not be in the visible tab bar yet"
    assert 'data-obj-tab="media"' not in html, "Медиа must not be in the visible tab bar yet"

    src = _source(OBJECTS_JS)
    assert "const OBJ_DETAIL_TAB_ORDER = ['chat', 'info', 'stages'];" in src


def test_live_stages_panel_and_v2_work_shell_are_two_separate_inert_containers():
    # 22.09 safety revert: exactly one #obj-detail-panel-stages (the LIVE
    # production mount) and exactly one #obj-detail-panel-work (an inert V2
    # shell, not yet wired to any renderer) -- never one id doing both jobs,
    # never a duplicate of either.
    html = _source(APP_HTML)
    assert html.count('id="obj-detail-panel-stages"') == 1
    assert html.count('id="obj-detail-panel-work"') == 1
    assert 'id="obj-detail-panel-overview"' in html
    assert 'id="obj-detail-panel-media"' in html
    assert 'id="obj-detail-panel-chat"' in html
    assert 'id="obj-detail-panel-info"' in html


def test_render_object_stages_tab_targets_only_the_live_stages_panel():
    # renderObjectStagesTab() must mount into #obj-detail-panel-stages and
    # NEVER look up #obj-detail-panel-work -- no OR-fallback between the two
    # ids either (`getElementById('work') || getElementById('stages')` would
    # mask the architecture problem instead of resolving it).
    src = _source(OBJECT_INFO_JS)
    body = _fn(src, "async function renderObjectStagesTab(objectId)")
    assert body.count("getElementById('obj-detail-panel-stages')") == 1
    assert "getElementById('obj-detail-panel-work')" not in body
    assert "obj-detail-panel-work" not in src


def test_object_detail_tab_switching_never_looks_up_a_missing_panel_id():
    # openObjectDetail() and _objDetailTabClick() both build the DOM id as
    # `obj-detail-panel-${tab}` from the routing-key string -- for tab==
    # 'stages' that must resolve to an id that actually exists in app.html,
    # or .style.display throws on null. This is exactly the bug the 22.09
    # rename attempt introduced and this test guards against it recurring.
    objects_src = _source(OBJECTS_JS)
    html = _source(APP_HTML)

    open_body = _fn(objects_src, "function openObjectDetail(")
    tab_click_body = _fn(objects_src, "function _objDetailTabClick(tab)")
    assert "`obj-detail-panel-${tab}`" in open_body
    assert "`obj-detail-panel-${tab}`" in tab_click_body

    # The routing keys these functions are ever called with for the visible
    # tab bar are exactly chat/info/stages (test above) -- each must have a
    # matching real panel id.
    for routing_key in ("chat", "info", "stages"):
        assert f'id="obj-detail-panel-{routing_key}"' in html


def test_zone_renderers_map_exists_and_reuses_existing_functions_not_new_ones():
    src = _source(OBJECTS_JS)
    assert "const ZONE_RENDERERS = {" in src
    body = _fn(src, "const ZONE_RENDERERS = {")
    # 'work' must call the EXISTING stages renderer, not a new implementation --
    # this is the exact "reuse, don't duplicate" principle the migration doc
    # applies to Start/Finish/stage-list.
    assert "renderObjectStagesTab(objectId)" in body
    # 'chat' must call the EXISTING embed function, not a new implementation.
    assert "embedObjectChat(objectId, objectName)" in body
    # overview/media have no renderer yet -- populated in later migration steps.
    assert "overview: null" in body
    assert "media: null" in body


def test_zone_renderers_are_lazily_resolved_not_bound_at_parse_time():
    # objects.js loads BEFORE object-info.js (script order in app.html) --
    # renderObjectStagesTab/embedObjectChat don't exist yet when ZONE_RENDERERS
    # itself is parsed. Binding them directly (`work: renderObjectStagesTab`)
    # would throw ReferenceError and halt this script's entire execution.
    html = _source(APP_HTML)
    objects_idx = html.index('<script src="js/objects.js"></script>')
    object_info_idx = html.index('<script src="js/object-info.js"></script>')
    assert objects_idx < object_info_idx

    src = _source(OBJECTS_JS)
    body = _fn(src, "const ZONE_RENDERERS = {")
    assert "typeof renderObjectStagesTab === 'function'" in body
    assert "typeof embedObjectChat === 'function'" in body


def test_zone_routing_function_exists_but_is_not_wired_into_the_tab_click_handler():
    # _renderObjectDetailZone must exist (the future entry point) but must NOT
    # be called from _objDetailTabClick/_initObjDetailTab yet -- those still
    # drive the legacy chat/info/stages production path unchanged.
    src = _source(OBJECTS_JS)
    assert "function _renderObjectDetailZone(zone)" in src

    tab_click_body = _fn(src, "function _objDetailTabClick(tab)")
    assert "_renderObjectDetailZone(" not in tab_click_body

    init_tab_body = _fn(src, "function _initObjDetailTab(tab)")
    assert "_renderObjectDetailZone(" not in init_tab_body


def test_work_shift_panel_draft_exists_but_is_not_loaded_by_the_app():
    # object-work-shift-panel.js (Object Detail V2 step 2 draft: timer/pause/
    # manual-time-entry panels for the future Работа zone) stays in the repo
    # as a draft, but must NOT be in app.html's <script> list -- wiring it in
    # is a deliberate future cutover commit, not an accidental side effect of
    # this step. renderWorkShiftPanel() must also not be referenced from any
    # production entry point (ZONE_RENDERERS, tab click/init handlers, the
    # checkin shortcut) yet.
    draft_path = ROOT / "frontend" / "js" / "object-work-shift-panel.js"
    assert draft_path.exists()

    html = _source(APP_HTML)
    assert '<script src="js/object-work-shift-panel.js"></script>' not in html

    for src_path in (OBJECTS_JS, OBJECT_INFO_JS):
        assert "renderWorkShiftPanel(" not in _source(src_path)
