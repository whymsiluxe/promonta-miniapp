from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _splash_markup(html: str) -> str:
    start = html.index('<div id="splash-screen" class="splash-screen">')
    end = html.index("<!-- ═══════════ ОБЪЕКТЫ", start)
    return html[start:end]


def _splash_css(html: str) -> str:
    start = html.index("/* ── Splash screen: light premium iOS loading state")
    end = html.index("/* ── Ring-progress", start)
    return html[start:end]


def test_splash_markup_uses_light_ios_mark_and_keeps_bootstrap_ids():
    html = _source(APP_HTML)
    block = _splash_markup(html)

    assert '<div id="splash-screen" class="splash-screen">' in block
    assert '<div class="splash-visual" aria-hidden="true">' in block
    assert '<svg class="splash-mark" viewBox="0 0 64 64">' in block
    assert "splash-mark-surface" in block
    assert "splash-mark-line" in block
    assert "splash-mark-accent" in block
    assert 'id="splash-progress"' in block
    assert 'id="splash-error"' in block
    assert 'id="splash-error-text"' in block
    assert 'id="splash-retry-btn"' in block
    assert "splash-scene" not in block
    assert "splash-astronaut" not in block


def test_splash_css_uses_ios_tokens_and_reduced_motion():
    html = _source(APP_HTML)
    css = _splash_css(html)

    assert "background: var(--ios-page-bg" in css
    assert "background: var(--ios-surface" in css
    assert "border: 1px solid var(--ios-border" in css
    assert "background: var(--ios-accent" in css
    assert "color: var(--ios-text" in css
    assert "color: var(--ios-muted" in css
    assert "letter-spacing: 0;" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    for legacy in ("#14100a", "#050403", "#EAD9AE", "#D4AF5A", "splash-ring-expand", "splash-float"):
        assert legacy not in css


def test_splash_bootstrap_functions_still_target_existing_elements():
    html = _source(APP_HTML)

    for snippet in (
        "function showSplash()",
        "function hideSplash()",
        "document.getElementById('splash-screen')",
        "document.getElementById('splash-progress')",
        "document.getElementById('splash-error')",
        "document.getElementById('splash-error-text')",
        "document.getElementById('splash-retry-btn')",
    ):
        assert snippet in html
