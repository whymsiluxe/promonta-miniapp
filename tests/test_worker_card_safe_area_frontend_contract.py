"""22.09 iPhone screenshot audit: Worker Card overlay had two safe-area bugs
confirmed live on a real device:
  1. .worker-card-header had NO --tg-safe-top padding at all (unlike every
     other sticky/fixed header in this app) -- the header's own "Сотрудник"
     title sat underneath the Dynamic Island/native Telegram controls.
  2. Its own #wc-back button duplicated Telegram's native BackButton (the
     overlay is registered via NavigationManager.registerOverlay, so
     Telegram's control already closes it) -- both were visible at once.
  3. .wc-tabs used a hardcoded `top: 48px` guess at the header's height --
     once the header gained real safe-area padding (fix 1), it became TALLER
     on notch devices, so this fixed offset overlapped the header or left a
     gap depending on device.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"


def _source() -> str:
    return APP_HTML.read_text(encoding="utf-8")


def test_worker_card_header_has_safe_area_top_padding():
    html = _source()
    start = html.index(".worker-card-header {")
    block = html[start:html.index("}", start) + 1]
    assert "var(--tg-safe-top, env(safe-area-inset-top, 0px))" in block


def test_wc_back_hides_when_telegram_native_back_is_active():
    html = _source()
    assert "body.tg-native-back #wc-back { display: none; }" in html


def test_wc_tabs_sticky_offset_tracks_the_same_safe_area_term_as_the_header():
    html = _source()
    start = html.index(".wc-tabs {")
    block = html[start:html.index("}", start) + 1]
    assert "top: calc(48px + var(--tg-safe-top, env(safe-area-inset-top, 0px)));" in block
