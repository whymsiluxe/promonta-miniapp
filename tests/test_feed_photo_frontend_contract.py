from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
FEED_JS = ROOT / "frontend" / "js" / "feed.js"
SHARED_JS = ROOT / "frontend" / "js" / "shared.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_photo_feed_renders_instagram_style_posts():
    src = _source(FEED_JS)

    assert '<article class="feed-photo-post"' in src
    assert "feed-photo-post-header" in src
    assert "feed-photo-avatar" in src
    assert "feed-photo-action-row" in src
    assert "feed-photo-comment-action" in src
    assert "feed-photo-caption" in src
    assert "feed-photo-img-error" in src
    assert "feed-photo-meta" not in src


def test_photo_feed_css_uses_large_vertical_media_card():
    src = _source(APP_HTML)

    assert ".feed-photo-post {" in src
    assert "border-radius: 8px" in src
    assert "aspect-ratio: 4 / 5" in src
    assert ".feed-photo-post-header" in src
    assert ".feed-photo-comment-action svg" in src
    assert ".feed-photo-img-wrap-error .feed-photo-img-error" in src
    assert ".feed-photo-caption" in src


def test_auth_img_marks_feed_media_failures_visibly():
    src = _source(SHARED_JS)

    assert "imgEl.classList.add('auth-img-error')" in src
    assert "feed-photo-img-wrap-error" in src
    assert "imgEl.classList.remove('auth-img-error')" in src
