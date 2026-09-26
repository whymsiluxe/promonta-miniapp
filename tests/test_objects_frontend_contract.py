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


def test_new_object_address_placeholder_is_a_real_german_street_example_not_a_raw_label():
    # 22.09 (iPhone screenshot audit, Item H): placeholder was the literal
    # untranslated field-label text "Straße, PLZ Ort" -- looked like a
    # forgotten localization, not an example value. Grandmont Group operates in
    # Germany, so a real German street/PLZ/city example is correct content
    # here (matches the "напр. Дом Шульц" example pattern used for Название).
    html = APP_HTML.read_text(encoding="utf-8")
    assert 'id="new-obj-adresse" placeholder="напр.' in html
    assert 'placeholder="Straße, PLZ Ort"' not in html


def test_new_object_submit_bar_uses_measured_nav_height_not_a_magic_number():
    # 22.09 (iPhone screenshot audit, Item H): the base .form-submit-bar rule
    # (used by any full-page form not inside a bottom sheet) hardcoded
    # `bottom: 7.5rem` as a guess for "above the bottom nav" -- same class of
    # bug as --bottom-nav-safe-pad. New Object itself uses the sheet-scoped
    # sticky override (#new-object-sheet .form-submit-bar) so is unaffected,
    # but any other consumer of the base rule needs the real measured height.
    html = APP_HTML.read_text(encoding="utf-8")
    start = html.index(".form-submit-bar {\n  position: fixed;")
    block = html[start:html.index("}", start) + 1]
    assert "var(--app-bottom-nav-height, 70px)" in block
    assert "bottom: 7.5rem" not in block
