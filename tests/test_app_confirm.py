"""Regression coverage for appConfirm() (18.09, audit finding): the app
had 10 call sites across 7 files using the native browser confirm() -- a
jarring OS-chrome popup on top of an otherwise fully custom iOS-like UI, not
brandable/stylable, and blocking the JS thread synchronously. appConfirm()
(shared.js) is the one reusable async replacement, built on the same
.bottom-sheet-overlay/.bottom-sheet-panel CSS every other bottom sheet in the
app already uses, registered with NavigationManager so Telegram Back closes it
like every other overlay.

chat.js's own _openChatConfirmSheet (a separate, pre-existing chat-specific
confirm implementation, already covered by its own contract test in
test_chat_frontend_contract.py) is intentionally NOT migrated here -- out of
scope for this pass, not a gap.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_JS = ROOT / "frontend" / "js" / "shared.js"
APP_HTML = ROOT / "frontend" / "app.html"

MIGRATED_JS_FILES = [
    ROOT / "frontend" / "js" / "finish-wizard.js",
    ROOT / "frontend" / "js" / "checkin.js",
    ROOT / "frontend" / "js" / "document-gallery.js",
    ROOT / "frontend" / "js" / "mangel.js",
    ROOT / "frontend" / "js" / "object-info.js",
    ROOT / "frontend" / "js" / "objects.js",
    ROOT / "frontend" / "js" / "profile.js",
]


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_app_confirm_is_defined_in_shared_js():
    js = _source(SHARED_JS)
    assert "function appConfirm(message" in js
    assert "return new Promise(resolve => {" in js
    # Must integrate with the existing overlay-stack mechanism, not just be a
    # standalone popup with no Telegram Back support.
    assert "NavigationManager.registerOverlay(() => settle(false));" in js
    # Reuses the shared bottom-sheet CSS layer -- no new overlay chrome.
    assert "overlay.className = 'bottom-sheet-overlay app-confirm-overlay';" in js


def test_app_confirm_css_reuses_shared_bottom_sheet_classes():
    html = _source(APP_HTML)
    assert ".app-confirm-panel" in html
    assert ".app-confirm-actions" in html
    # Buttons reuse the same .obj-confirm-cancel/.obj-confirm-ok class NAMES
    # already used by the stage-add-sheet footer (consistent visual language),
    # scoped under .app-confirm-actions so the two don't collide.
    assert ".app-confirm-actions .obj-confirm-cancel" in html
    assert ".app-confirm-actions .obj-confirm-ok" in html


def test_no_native_confirm_left_in_migrated_files():
    for path in MIGRATED_JS_FILES:
        js = _source(path)
        assert "await appConfirm(" in js, f"{path.name} should call appConfirm()"
        # Match an actual `confirm(` CALL, not appConfirm(...)/confirmLabel/
        # a code comment mentioning "confirm(" as prose (e.g. explaining what
        # was replaced) -- only flag lines that are executable code containing
        # a bare, unqualified confirm( invocation.
        for line in js.splitlines():
            code = line.split('//', 1)[0]
            stripped = code.strip()
            if not stripped or "appConfirm(" in stripped or "confirmLabel" in stripped:
                continue
            assert "confirm(" not in stripped, (
                f"{path.name} still has a native confirm() call: {stripped!r}"
            )
