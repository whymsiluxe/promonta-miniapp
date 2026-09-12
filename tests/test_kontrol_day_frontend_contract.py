from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
KONTROL_DAY_JS = ROOT / "frontend" / "js" / "kontrol-day.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_kontrol_day_horizontal_strips_do_not_trigger_global_swipe_nav():
    src = _source(APP_HTML)

    assert '<script src="js/kontrol-day.js"></script>' in src
    assert 'id="kd-kpi-strip" class="kd-kpi-strip" data-no-swipe' in src
    assert 'id="kd-filters" class="kd-filters" data-no-swipe' in src
    assert ".kd-kpi-strip" in src and "touch-action: pan-x" in src
    assert ".kd-filters" in src and "overscroll-behavior-x: contain" in src


def test_kontrol_day_filter_chips_are_not_wired_once():
    src = _source(KONTROL_DAY_JS)

    assert "const filtersEl = document.getElementById('kd-filters')" in src
    assert "filtersEl.dataset.wired = '1'" in src
    assert "filtersEl.addEventListener('click', e =>" in src
    filter_block = src[
        src.index("const filtersEl = document.getElementById('kd-filters')"):
        src.index("document.getElementById('kd-detail-close')")
    ]
    assert "once: true" not in filter_block


def test_kontrol_day_logic_is_not_inline_in_app_html():
    src = _source(APP_HTML)

    assert "function initKontrolDayView()" not in src
    assert "let _kdRows" not in src
