from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
DOC_GALLERY_JS = ROOT / "frontend" / "js" / "document-gallery.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_documents_view_contains_object_document_gallery_and_keeps_pdf_builder():
    html = _source(APP_HTML)

    assert '<div class="view ios-page" id="view-documents">' in html
    assert 'id="document-gallery"' in html
    assert 'id="document-gallery-filters"' in html
    assert 'id="document-gallery-grid"' in html
    assert 'id="documents-builder-title"' in html
    assert 'id="angebot-content"' in html
    assert 'id="rechnung-content"' in html


def test_document_gallery_script_is_loaded_and_initialized_from_documents_view():
    html = _source(APP_HTML)

    assert '<script src="js/document-gallery.js"></script>' in html
    assert html.index('<script src="js/object-info.js"></script>') < html.index('<script src="js/document-gallery.js"></script>')
    assert "if (typeof initDocumentGallery === 'function') initDocumentGallery();" in html
    assert "const builderTitle = document.getElementById('documents-builder-title');" in html
    assert "if (opt.dataset.wired) return;" in html


def test_document_gallery_reuses_existing_object_document_endpoints():
    js = _source(DOC_GALLERY_JS)

    assert "const objectsData = await api('/api/objects');" in js
    assert "`/api/objects/${encodeURIComponent(objectId)}/documents`" in js
    assert "`/api/objects/${encodeURIComponent(doc.object_id)}/documents/${encodeURIComponent(doc.id)}`" in js
    assert "method: 'DELETE'" in js
    assert "authImageUrl(el.dataset.docGalleryThumbPath)" in js
    assert "data-doc-gallery-filter" in js


def test_document_gallery_quick_actions_preview_object_and_delete():
    js = _source(DOC_GALLERY_JS)

    assert "data-doc-gallery-preview" in js
    assert "_openObjInfoDocViewer(doc.object_id, doc.file, doc.content_type, doc.name)" in js
    assert "data-doc-gallery-object-open" in js
    assert "openObjectDetail(btn.dataset.docGalleryObjectOpen" in js
    assert "data-doc-gallery-delete" in js
    assert "currentRole === 'owner'" in js


def test_document_gallery_styles_are_present():
    html = _source(APP_HTML)

    for selector in (
        ".doc-gallery-section",
        ".doc-gallery-filters",
        ".doc-gallery-grid",
        ".doc-gallery-card",
        ".doc-gallery-thumb-image.loaded",
        ".doc-gallery-actions",
        ".documents-builder-section",
    ):
        assert selector in html
