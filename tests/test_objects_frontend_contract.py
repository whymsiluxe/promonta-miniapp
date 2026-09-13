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
