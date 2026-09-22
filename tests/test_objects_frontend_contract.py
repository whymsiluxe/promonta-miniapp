from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"


def test_objects_sheet_keyboard_and_fab_motion_contracts():
    src = APP_HTML.read_text(encoding="utf-8")

    assert "#new-object-sheet {" in src
    assert "height: var(--tg-fullscreen-height, 100dvh)" in src
    assert "calc(28px - var(--keyboard-inset, 0px))" in src
    assert "#new-object-sheet.open .bottom-sheet-panel" in src
    assert "#view-objects .obj-card-hero::after" in src
    assert ".objects-fab::before" in src
    assert "objects-fab-pulse" in src
    assert "z-index: 240" in src
    assert "touch-action: manipulation" in src
    assert "@media (prefers-reduced-motion: reduce)" in src
    assert 'id="new-obj-name" placeholder="напр. Дом Шульц" autocomplete="off" autocorrect="off" spellcheck="false"' in src
    assert 'id="new-obj-budget" placeholder="10000" autocomplete="off"' in src


def test_object_info_uses_compact_rows_instead_of_duplicate_section_tabs():
    info_src = (ROOT / "frontend" / "js" / "object-info.js").read_text(encoding="utf-8")
    html = APP_HTML.read_text(encoding="utf-8")

    assert "obj-info-section-compact" in html
    assert "obj-info-line-action" in html
    assert ">Центр управления<" not in info_src
    assert ">Фото объекта<" not in info_src
    assert ">Статус объекта<" not in info_src
    assert ">Описание<" not in info_src
    assert ">Работы<" not in info_src
    assert ">Потребности<" not in info_src
    assert "#view-objects .metrics" in html


def test_objects_cards_reserve_space_under_the_fab_and_bottom_nav():
    # 22.09 (iPhone screenshot audit): #objects-cards (.cards, no dedicated
    # override) had no bottom-padding reserve at all -- a real device showed
    # the last object card's budget data visually covered by the FAB/bottom
    # nav. Same measured-height pattern as .objects-fab's own position.
    html = APP_HTML.read_text(encoding="utf-8")
    start = html.index("#objects-list-view .cards {")
    block = html[start:html.index("}", start) + 1]
    assert "var(--app-bottom-nav-height, 70px)" in block
    assert "env(safe-area-inset-bottom)" in block
