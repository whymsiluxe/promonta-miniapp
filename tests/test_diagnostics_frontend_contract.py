"""22.09 iPhone screenshot audit: Diagnostics screen showed internal technical
values directly to the owner (not_configured, "4 objects" in English, a
duplicated build SHA like "c28ff97 · c28ff97" or a malformed one like
"c23894d4 · vc23894d"), and a green "✅ Все системы работают" headline
directly contradicted three yellow warning rows below it (see
test_diagnostics_severity_model.py for the backend-side overall fix this
frontend renders).
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS_JS = ROOT / "frontend" / "js" / "diagnostics.js"
APP_HTML = ROOT / "frontend" / "app.html"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fn(src: str, signature: str) -> str:
    start = src.index(signature)
    depth = 0
    i = src.index("{", start + len(signature))
    j = i
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


def test_diag_values_are_localized_not_raw_backend_tokens():
    src = _source(DIAGNOSTICS_JS)
    assert "const DIAG_VALUE_LABELS = {" in src
    assert "not_configured: 'Не настроено'" in src
    assert "function _pluralizeObjects(n)" in src
    body = _fn(src, "function _localizeDiagValue(value)")
    assert "DIAG_VALUE_LABELS[value]" in body
    assert "objMatch" in body
    assert "_pluralizeObjects" in body


def test_fmt_diag_value_uses_the_localizer_not_raw_string():
    body = _fn(_source(DIAGNOSTICS_JS), "function _fmtDiagValue(value, extra)")
    assert "_localizeDiagValue(value)" in body
    assert "String(value)" not in body


def test_build_sha_and_version_are_not_duplicated():
    # 22.09: build_sha and build_version are frequently the SAME underlying
    # commit SHA in this repo (no separate "version" concept from the deploy
    # commit) -- a real device showed "c28ff97 · c28ff97". Only show the
    # second value when it is genuinely DIFFERENT from the SHA already shown.
    body = _fn(_source(DIAGNOSTICS_JS), "function _renderDiagnostics(d)")
    assert "const versionDiffersFromSha = d.build_version && d.build_version !== 'unknown' && d.build_version !== d.build_sha && d.build_version !== shaShort;" in body
    assert "versionDiffersFromSha ? ` · v${d.build_version}` : ''" in body


def test_overall_headline_reflects_the_three_state_severity_model():
    # 22.09: `overall` is ok/warning/error (backend), not the old binary
    # ok/degraded -- the headline text must match what the row table below it
    # actually shows, not a blanket "все хорошо" that ignores warning rows.
    body = _fn(_source(DIAGNOSTICS_JS), "function _renderDiagnostics(d)")
    assert "ok: '✅ Все системы работают'" in body
    assert "warning: '⚠️ Основные системы работают · есть предупреждения'" in body
    assert "error: '❌ Есть проблемы с ключевыми системами'" in body


def test_diag_overall_error_css_class_exists():
    html = _source(APP_HTML)
    assert ".diag-overall-error {" in html
