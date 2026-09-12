from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_kontrol_day_horizontal_strips_do_not_trigger_global_swipe_nav():
    src = _source(APP_HTML)

    assert 'id="kd-kpi-strip" class="kd-kpi-strip" data-no-swipe' in src
    assert 'id="kd-filters" class="kd-filters" data-no-swipe' in src
    assert ".kd-kpi-strip" in src and "touch-action: pan-x" in src
    assert ".kd-filters" in src and "overscroll-behavior-x: contain" in src


def test_kontrol_day_filter_chips_are_not_wired_once():
    src = _source(APP_HTML)

    assert "const filtersEl = document.getElementById('kd-filters')" in src
    assert "filtersEl.dataset.wired = '1'" in src
    assert "filtersEl.addEventListener('click', e =>" in src
    assert "once: true" not in src[src.index("const filtersEl = document.getElementById('kd-filters')"):src.index("// Detail close")]
