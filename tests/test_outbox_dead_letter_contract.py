"""Outbox dead-letter transition contract (test matrix п.13: "Dead-letter не
блокирует навсегда, retryable").

Тот же source-assertion стиль, что tests/test_checkin_offline_outbox_frontend_contract.py
-- эта логика (promontaOutboxRecordFailure/promontaOutboxManualRetry в shared.js)
чистая по данным, но зависит от promontaOutboxPatch (IndexedDB side effect) и
navigator.onLine (browser global), поэтому исполнять её напрямую в pytest
потребовало бы вводить новую node-subprocess/DOM-mock инфраструктуру, которой
в репозитории сознательно нет ни для одного из остальных *_frontend_contract.py
тестов. Проверяем точный текст порогового условия и terminal-state перехода --
это уже покрывает регрессию "кто-то тихо поменял MAX_ATTEMPTS/убрал проверку
exhausted и старый record снова крутится в queued вечно".
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED_JS = ROOT / "frontend" / "js" / "shared.js"


def _source() -> str:
    return SHARED_JS.read_text(encoding="utf-8")


def test_max_attempts_constant_exists_and_is_finite():
    src = _source()
    assert "const PROMONTA_OUTBOX_MAX_ATTEMPTS = 5;" in src


def test_non_transient_or_exhausted_failure_moves_to_dead_letter():
    src = _source()
    start = src.index("async function promontaOutboxRecordFailure(")
    end = src.index("async function promontaOutboxManualRetry(", start)
    body = src[start:end]

    # Terminal condition: real server rejection (non-transient) OR attempts
    # exhausted -- either one alone must be enough to dead-letter the record.
    assert "const exhausted = attempts >= PROMONTA_OUTBOX_MAX_ATTEMPTS;" in body
    assert "if (!transient || exhausted) {" in body
    assert "state: 'dead_letter'," in body
    # Transient failures below the threshold must go back to 'queued', not
    # get silently dropped or retried outside the outbox mechanism.
    assert "return promontaOutboxPatch(record.id, { state: 'queued', lastError:" in body


def test_dead_letter_is_not_picked_up_by_retry_loops_automatically():
    src = _source()
    # The DLQ contract documented at shared.js:475-479: retry loops must not
    # themselves re-queue dead_letter records -- only promontaOutboxManualRetry
    # (explicit user/owner action) may reset one back to 'queued'.
    assert "Retry loops must stop picking up dead_letter records themselves" in src
    assert "a\n// manual retry (resets state to 'queued', attempts to 0) or manual delete is\n// the only way out once dead_letter" in src


def test_manual_retry_resets_state_and_attempts_to_zero():
    src = _source()
    start = src.index("async function promontaOutboxManualRetry(")
    end = src.index("\n}\n", start) + len("\n}\n")
    body = src[start:end]

    assert "return promontaOutboxPatch(id, { state: 'queued', attempts: 0, lastError: null });" in body
