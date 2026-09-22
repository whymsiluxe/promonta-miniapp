"""22.09 hotfix — owner's live iPhone regression pass reproduced a real bug in
Object Detail's embedded chat (embedObjectChat() in object-info.js, physically
moves #chat-thread-detail-view into #obj-detail-panel-chat): focusing the
composer textarea threw the composer/quick-reactions row almost to the top of
the screen, and after the keyboard closed it settled somewhere in the middle
instead of returning fully to the bottom.

Root cause: #obj-detail-panel-chat.obj-chat-active used
`height: var(--tg-vp-height, 100dvh)` -- --tg-vp-height is the LIVE
visualViewport height, which shrinks the instant the on-screen keyboard opens.
Root chat (#view-chat.active) solved this exact class of bug back in its own
v5-v9 iteration history (see that rule's comment): the fullscreen CONTAINER
must never change size on keyboard open/close -- only --tg-fullscreen-height
(a snapshot, refreshed only when the keyboard is confirmed CLOSED) -- keyboard
movement is handled exclusively by --chat-keyboard-inset translating
.chat-composer-stack via CSS transform. Using the live, keyboard-shrunk
--tg-vp-height for the embedded chat's own container double-compensated the
keyboard: the container itself shrank AND the composer was additionally
translated up by --chat-keyboard-inset.

Fix: #obj-detail-panel-chat.obj-chat-active now uses the same stable
--tg-fullscreen-height contract as #view-chat.active. No new JS, no new
keyboard state machine, no magic pixel offsets -- the embedded chat now
follows the exact macro-layout contract the root chat already proved correct.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"


def _source() -> str:
    return APP_HTML.read_text(encoding="utf-8")


def _block(html: str, selector_start: str) -> str:
    start = html.index(selector_start)
    return html[start:html.index("}", start) + 1]


def test_embedded_object_chat_uses_the_stable_fullscreen_height_variable():
    # --tg-vp-height (the live, keyboard-shrunk value) must never appear as an
    # actual CSS declaration in this rule block again -- that was the exact
    # root cause. Checks the literal `height:`/`min-height:` declarations, not
    # the whole block text, so an explanatory comment mentioning the old
    # variable by name (documenting what NOT to do) can't false-positive this.
    html = _source()
    block = _block(html, "#obj-detail-panel-chat.obj-chat-active {")
    assert "position: fixed" in block
    assert "inset: 0" in block
    assert "height: var(--tg-fullscreen-height, 100dvh);" in block
    assert "min-height: var(--tg-fullscreen-height, 100dvh);" in block
    assert "height: var(--tg-vp-height" not in block


def test_root_chat_container_still_uses_the_same_stable_height_contract():
    # The reference implementation this fix copied -- must still be true, or
    # the "same contract" claim above is meaningless. At least 2 occurrences:
    # the root #view-chat.active rule and this fix's #obj-detail-panel-chat rule.
    html = _source()
    assert html.count("var(--tg-fullscreen-height, 100dvh)") >= 2


def test_chat_composer_stack_keyboard_movement_is_exclusively_via_css_transform():
    # The ONE mechanism that may ever move the composer for the keyboard --
    # a second competing mechanism (another transform source, a JS-set inline
    # top/bottom, a second keyboard-inset variable) would reintroduce a race
    # between it and this CSS rule.
    html = _source()
    block = _block(html, ".chat-composer-stack {")
    assert "position: absolute" in block
    assert "transform: translate3d(0, calc(-1 * var(--chat-keyboard-inset, 0px)), 0);" in block


