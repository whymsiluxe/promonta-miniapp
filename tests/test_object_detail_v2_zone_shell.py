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
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
OBJECTS_JS = ROOT / "frontend" / "js" / "objects.js"


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


def test_new_zone_panel_containers_exist_but_are_not_production_visible():
    html = _source(APP_HTML)
    assert 'id="obj-detail-panel-overview"' in html
    assert 'id="obj-detail-panel-work"' in html
    assert 'id="obj-detail-panel-media"' in html
    # Legacy panels must be untouched, still present, still the ones the
    # visible tab bar actually renders into.
    assert 'id="obj-detail-panel-chat"' in html
    assert 'id="obj-detail-panel-info"' in html
    assert 'id="obj-detail-panel-stages"' in html


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
