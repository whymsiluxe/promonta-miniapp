from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED_JS = ROOT / "frontend" / "js" / "shared.js"


def _source() -> str:
    return SHARED_JS.read_text(encoding="utf-8")


def test_shared_api_has_timeout_abort_and_transient_retry_contract():
    src = _source()

    assert "const API_DEFAULT_TIMEOUT_MS = 18000;" in src
    assert "const API_DEFAULT_SAFE_RETRIES = 1;" in src
    assert "const API_SAFE_RETRY_METHODS = new Set(['GET', 'HEAD']);" in src
    assert "const API_RETRY_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);" in src
    assert "async function _apiFetchOnce(path, fetchOptions, timeoutMs, externalSignal)" in src
    assert "new AbortController()" in src
    assert "externalSignal.addEventListener('abort', onExternalAbort, { once: true })" in src
    assert "controller.abort();" in src
    assert "if (timedOut) throw _apiTimeoutError(timeoutMs);" in src
    assert "err.name = 'TimeoutError';" in src


def test_shared_api_does_not_retry_writes_without_explicit_retry():
    src = _source()

    assert "const method = String(options.method || 'GET').toUpperCase();" in src
    assert "const isSafeRetryMethod = API_SAFE_RETRY_METHODS.has(method);" in src
    assert "const explicitRetry = retry === true;" in src
    assert "const maxRetries = (isSafeRetryMethod || explicitRetry)" in src
    assert "if (err?.name === 'AbortError') return false;" in src
    assert "if (err?.name === 'TimeoutError') return true;" in src
    assert "if (err?.status) return API_RETRY_STATUSES.has(err.status);" in src
    assert "...fetchOptions" in src
    assert "method," in src
    assert "headers," in src
