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
    assert "feed-photo-like-action" in src
    assert "feed-photo-comment-action" in src
    assert "feed-photo-save-action" in src
    assert "togglePhotoLike" in src
    assert "IG_ICONS.heart" in src
    assert "IG_ICONS.comment" in src
    assert "IG_ICONS.share" in src
    assert "feed-photo-caption" in src
    assert "feed-photo-img-error" in src
    assert "feed-photo-meta" not in src


def test_photo_feed_css_uses_large_vertical_media_card():
    src = _source(APP_HTML)

    assert ".feed-photo-post {" in src
    assert "border-radius: 8px" in src
    assert "aspect-ratio: 4 / 5" in src
    assert ".feed-photo-post-header" in src
    assert ".feed-photo-icon-action svg" in src
    assert ".feed-photo-like-action.liked" in src
    assert ".feed-photo-img-wrap-error .feed-photo-img-error" in src
    assert ".feed-photo-caption" in src


def test_comment_modal_is_bottom_sheet_not_route_page():
    src = _source(APP_HTML)
    feed_src = _source(FEED_JS)

    assert '<div id="photo-comments-modal" class="photo-comments-modal" style="display:none;">' in src
    assert '<div class="pc-sheet">' in src
    assert "height: var(--tg-fullscreen-height, 100dvh)" in src
    assert "min-height: 100dvh" in src
    assert "var(--keyboard-inset, 0px)" in src
    assert "translate3d(0, calc(-1 * var(--keyboard-inset, 0px)), 0)" in src
    assert '<div id="pc-reply-bar" class="pc-reply-bar" style="display:none;"></div>' in src
    assert '<div class="pc-sheet pc-news-sheet">' in src
    assert '<div id="nc-reply-bar" class="pc-reply-bar" style="display:none;"></div>' in src
    assert 'data-comment-kind="photo"' in src
    assert 'data-comment-kind="news"' in src
    assert 'class="pc-quick-reaction"' in src
    assert "pc-quick-reaction-hit" in src
    assert ".comment-action-sheet" in src
    assert "z-index: 6001" in src
    assert "touch-action: none" in src
    assert "_renderUnifiedFeedComment" in feed_src
    assert "_insertFeedQuickReaction" in feed_src
    assert "pointerdown" in feed_src
    assert "_setFeedCommentReply('photo'" in feed_src
    assert "_setFeedCommentReply('news'" in feed_src


def test_feed_uses_unified_instagram_style_icons():
    src = _source(FEED_JS)
    css = _source(APP_HTML)

    assert "const IG_ICONS" in src
    assert "wx-heart" in src
    assert "news-like-btn" in src
    assert "${IG_ICONS.bookmark}" in src
    assert ".wx-act svg" in css
    assert ".news-react-btn svg" in css
    assert ".news-like-btn.active svg" in css


def test_feed_saved_filters_are_per_tab_not_mixed_tab():
    src = _source(APP_HTML)
    feed_src = _source(FEED_JS)

    assert 'data-feed="weather">Погода' in src
    assert 'data-feed="saved"' not in src
    assert 'data-feed-saved-kind="photos"' in src
    assert 'data-feed-saved-kind="news"' in src
    assert 'data-feed-saved-kind="weather"' in src
    assert 'id="feed-saved-count-photos"' in src
    assert 'id="feed-saved-count-news"' in src
    assert 'id="feed-saved-count-weather"' in src
    assert "toggleFeedSave" in feed_src
    assert "'/api/feed/saved'" in feed_src
    assert "FEED_SAVED_FILTERS = { photos: 'all', news: 'all', weather: 'all' }" in feed_src
    assert "news-save-btn" in feed_src
    assert "wx-save-btn" in feed_src
    assert "_renderFeedPhotosFromCache" in feed_src
    assert "_renderNewsFromCache" in feed_src


def test_ios_input_zoom_and_ai_composer_visibility_contracts():
    src = _source(APP_HTML)
    tokens = _source(ROOT / "frontend" / "css" / "tokens.css")

    assert ".form-field input, .form-field select, .form-field textarea" in src
    assert ".field input, .field select, .field textarea" in src
    assert ".obj-search-input" in src and "font-size: 16px" in src
    assert "body:has(#view-ai.active) .bottom-nav" in src
    assert "display: none" in src
    assert "'SF Pro Text'" in tokens


def test_auth_img_marks_feed_media_failures_visibly():
    src = _source(SHARED_JS)

    assert "imgEl.classList.add('auth-img-error')" in src
    assert "feed-photo-img-wrap-error" in src
    assert "imgEl.classList.remove('auth-img-error')" in src
