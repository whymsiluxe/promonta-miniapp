#!/usr/bin/env python3
"""Promonta Mini App — FastAPI backend. Фаза 2 плана: скелет + initData-auth + roles.
Запуск: uvicorn main:app --host 127.0.0.1 --port 8001
"""
import copy
import csv
import hashlib
import hmac
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, quote

from fastapi import FastAPI, Header, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
import base64
from pydantic import BaseModel

sys.path.insert(0, '/home/promonta/agent')

# 30.07 (Инструменты cleanup, изолированный фикс): sys.path выше -- ГЛОБАЛЬНЫЙ и
# специально ставит /home/promonta/agent первым, чтобы roadmap_lib/objekte_lib/другие
# shared runtime-модули резолвились так же, как всегда (изменение этого порядка в
# предыдущем коммите сломало 2 roadmap-теста -- откачено). tools_lib.py тем не менее
# должен гарантированно грузиться из репозитория (backend/tools_lib.py), не из
# untracked /home/promonta/agent/tools_lib.py -- решение точечное: загрузка по явному
# пути к файлу через importlib.util, без малейшего влияния на глобальный sys.path.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.environ.get('MINIAPP_DATA_ROOT', '/home/promonta/agent/miniapp')
AGENT_ROOT = os.environ.get('PROMONTA_AGENT_ROOT', '/home/promonta/agent')
CREATE_OBJECT_SCRIPT = os.environ.get('PROMONTA_CREATE_OBJECT_SCRIPT', os.path.join(AGENT_ROOT, 'create_object.py'))
CREATE_OBJECT_FOLDER_SCRIPT = os.environ.get('PROMONTA_CREATE_OBJECT_FOLDER_SCRIPT', os.path.join(AGENT_ROOT, 'create_object_folder.py'))

_PROD_DATA_ROOT = '/home/promonta/agent/miniapp'
_is_test_context = (
    os.environ.get('PROMONTA_ENV') == 'test'
    or 'pytest' in sys.modules
)
if _is_test_context and DATA_ROOT == _PROD_DATA_ROOT:
    raise RuntimeError(
        f"REFUSING TO RUN TESTS AGAINST PRODUCTION DATA ROOT ({_PROD_DATA_ROOT}). "
        "Set MINIAPP_DATA_ROOT to a temp directory before importing this module "
        "in test context. conftest.py should have handled this automatically."
    )
TOOLS_LIB_PATH = os.path.join(BACKEND_DIR, 'tools_lib.py')
MANGEL_LIB_PATH = os.path.join(BACKEND_DIR, 'mangel_lib.py')
OBJEKTE_LIB_PATH = os.path.join(BACKEND_DIR, 'objekte_lib.py')
ROADMAP_LIB_PATH = os.path.join(BACKEND_DIR, 'roadmap_lib.py')
_repo_tools_lib = None
_repo_mangel_lib = None
_repo_objekte_lib = None
_repo_roadmap_lib = None


def _load_repo_module(path: str, internal_name: str, cache: dict, cache_key: str):
    """Общая логика для _load_repo_tools_lib()/_load_repo_mangel_lib() -- грузит
    модуль под уникальным внутренним именем (не 'tools_lib'/'mangel_lib', чтобы не
    столкнуться с/не подменить то, что уже могло быть закэшировано в sys.modules
    из-за глобального /home/promonta/agent в sys.path). Кэш передаётся вызывающим
    как dict с одним ключом -- эмулирует module-level global без глобальной
    переменной на каждый модуль."""
    if cache.get(cache_key) is not None:
        return cache[cache_key]
    spec = importlib.util.spec_from_file_location(internal_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f'не удалось загрузить {os.path.basename(path)} из {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cache[cache_key] = module
    return module


_repo_module_cache: dict = {}


def _load_repo_tools_lib():
    return _load_repo_module(TOOLS_LIB_PATH, 'promonta_repo_tools_lib', _repo_module_cache, 'tools_lib')


def _load_repo_mangel_lib():
    """30.07 (Release-аудит P1): mangel_lib.py был полностью вне git и импортировался
    обычным `import mangel_lib as ml` -- тот же класс риска, что чинили для tools_lib.py
    (import мог молча резолвиться в untracked-копию на диске сервера вместо
    репозиторной, даже если содержимое разошлось). Тот же изолированный loader."""
    return _load_repo_module(MANGEL_LIB_PATH, 'promonta_repo_mangel_lib', _repo_module_cache, 'mangel_lib')


def _load_repo_objekte_lib():
    """31.07 (Release-аудит P2): objekte_lib.py -- последний shared runtime-модуль вне
    git, тем же путём: import резолвился через глобальный sys.path на
    /home/promonta/agent/objekte_lib.py, что и работает в prod, но не существует на
    CI runner (нет /home/promonta там) -- CI падал ModuleNotFoundError. Тот же
    изолированный loader, что и tools_lib/mangel_lib."""
    return _load_repo_module(OBJEKTE_LIB_PATH, 'promonta_repo_objekte_lib', _repo_module_cache, 'objekte_lib')


def _load_repo_roadmap_lib():
    """31.07 (Release-аудит П2): roadmap_lib.py — последний shared runtime-модуль,
    грузившийся обычным `import roadmap_lib as rl` через глобальный sys.path, тот же
    риск резолва в untracked-копию на диске сервера вместо репозиторной. Тот же
    изолированный loader, что и tools_lib/mangel_lib/objekte_lib."""
    return _load_repo_module(ROADMAP_LIB_PATH, 'promonta_repo_roadmap_lib', _repo_module_cache, 'roadmap_lib')


# 01.08 (доп.раунд): предыдущее предположение "обычный import безопасен, uvicorn
# кладёт BACKEND_DIR в sys.path[0]" было ВЕРНО только для `uvicorn main:app` из
# BACKEND_DIR напрямую -- production запускается как `uvicorn miniapp.main:app`
# с WorkingDirectory=/home/promonta/agent (см. systemd unit), это package-import
# (miniapp -- implicit namespace package, нет __init__.py), и в этом случае Python
# кладёт в sys.path[0] именно WorkingDirectory (/home/promonta/agent), НЕ директорию
# main.py (/home/promonta/agent/miniapp/) -- `import work_types` внутри main.py не
# находит work_types.py вообще, реальный ImportError в проде, не пойманный тестами
# (тесты всегда грузят main.py напрямую как top-level module, не как package member).
# Fix: relative import сначала (работает для package-import сценария, т.к. `from .
# import work_types` резолвится относительно ПАКЕТА miniapp, не sys.path), fallback на
# обычный import для top-level запуска (тесты, uvicorn main:app из BACKEND_DIR). НЕ
# добавляем НИКАКОГО ДОПОЛНИТЕЛЬНОГО вызова, вставляющего путь в sys.path -- именно
# такой вызов уже один раз сломал resolution других shared-модулей (см.
# test_main_py_restores_original_global_sys_path_insert).
try:
    from . import work_types as wt
    from . import profile_skills as pskills
    from . import assignment_matching as amatch
    from . import daily_plan_lib as dpl
except ImportError:
    import work_types as wt  # noqa: E402
    import profile_skills as pskills  # noqa: E402
    import assignment_matching as amatch  # noqa: E402
    import daily_plan_lib as dpl  # noqa: E402


BOT_TOKEN = os.environ['BOT_TOKEN']
# Phase A: ~45 JSON-store/dir path constants moved to backend/core/paths.py.
# Imported by name (not `from core import paths`) so `backend.ROLES_FILE` etc.
# keep working for tests that do `import main as backend`. Relative-then-
# absolute fallback, same pattern as core.time and the work_types/etc. block.
try:
    from .core.paths import (
        CHAT_ARCHIVE_FILE,
        OBJECT_INFO_FILE,
        TASKS_FILE,
        OBJECT_DOC_DIR,
        CHAT_ATTACH_DIR,
        CHAT_FILE,
        ANGEBOT_OUT_DIR,
        CHECKIN_PHOTO_BASE,
        ACTIVITY_ALERTS_FILE,
        WORK_CALENDAR_FILE,
        WORKER_PROFILES_FILE,
        OBJECT_ASSIGNMENTS_FILE,
        AI_MODEL_FILE,
        WEATHER_REACTIONS_FILE,
        CHAT_THREAD_META_FILE,
        PHOTO_DIR,
        NOTIFIED_USERS_FILE,
        RECHNUNG_OUT_DIR,
        DAILY_PLAN_STORE_FILE,
        OBJECT_IMAGES_FILE,
        CHECKIN_META_FILE,
        NEWS_COMMENTS_FILE,
        BLOCKER_PHOTO_DIR,
        TRANSCRIBE_AUDIO_DIR,
        ALERT_DISMISSALS_FILE,
        BIRTHDAY_ALERTS_FILE,
        AI_RATE_FILE,
        CONTRACT_INGEST_STATE_FILE,
        AVATAR_DIR,
        CHAT_READS_FILE,
        NEWS_READS_FILE,
        WORKER_AI_RATE_FILE,
        FINISH_OUTBOX_FILE,
        PHOTO_META_FILE,
        NEWS_REACTIONS_FILE,
        ROLES_FILE,
        AUDIT_FILE,
        APP_VERSION_FILE,
        OBJECT_PHOTO_DIR,
        CRITICAL_ALERT_PHOTO_DIR,
        CRITICAL_ALERTS_FILE,
        FEED_READS_FILE,
        CHAT_REACTIONS_FILE,
        PLAN_SYNC_STATE_FILE,
        MANGEL_PHOTO_DIR,
        ABWESENHEIT_FILE,
    )
except ImportError:
    from core.paths import (  # noqa: E402
        CHAT_ARCHIVE_FILE,
        OBJECT_INFO_FILE,
        TASKS_FILE,
        OBJECT_DOC_DIR,
        CHAT_ATTACH_DIR,
        CHAT_FILE,
        ANGEBOT_OUT_DIR,
        CHECKIN_PHOTO_BASE,
        ACTIVITY_ALERTS_FILE,
        WORK_CALENDAR_FILE,
        WORKER_PROFILES_FILE,
        OBJECT_ASSIGNMENTS_FILE,
        AI_MODEL_FILE,
        WEATHER_REACTIONS_FILE,
        CHAT_THREAD_META_FILE,
        PHOTO_DIR,
        NOTIFIED_USERS_FILE,
        RECHNUNG_OUT_DIR,
        DAILY_PLAN_STORE_FILE,
        OBJECT_IMAGES_FILE,
        CHECKIN_META_FILE,
        NEWS_COMMENTS_FILE,
        BLOCKER_PHOTO_DIR,
        TRANSCRIBE_AUDIO_DIR,
        ALERT_DISMISSALS_FILE,
        BIRTHDAY_ALERTS_FILE,
        AI_RATE_FILE,
        CONTRACT_INGEST_STATE_FILE,
        AVATAR_DIR,
        CHAT_READS_FILE,
        NEWS_READS_FILE,
        WORKER_AI_RATE_FILE,
        FINISH_OUTBOX_FILE,
        PHOTO_META_FILE,
        NEWS_REACTIONS_FILE,
        ROLES_FILE,
        AUDIT_FILE,
        APP_VERSION_FILE,
        OBJECT_PHOTO_DIR,
        CRITICAL_ALERT_PHOTO_DIR,
        CRITICAL_ALERTS_FILE,
        FEED_READS_FILE,
        CHAT_REACTIONS_FILE,
        PLAN_SYNC_STATE_FILE,
        MANGEL_PHOTO_DIR,
        ABWESENHEIT_FILE,
    )

# Phase A step 3: numeric limits/TTLs moved to backend/core/limits.py.
try:
    from .core.limits import (
        ONLINE_THRESHOLD_SECONDS,
        CHECKIN_MAX_BYTES,
        PHOTO_MAX_FILES,
        INIT_DATA_MAX_AGE,
        ALERT_DISMISS_TTL,
        PHOTO_MAX_COUNT,
        AI_UPLOAD_MAX_BYTES,
        PHOTO_MAX_BYTES,
        SHEETS_CACHE_TTL,
        SESSION_TOKEN_MAX_AGE,
        NOTIFIED_USERS_TTL,
        OBJECT_PHOTO_MAX,
        AI_RATE_WINDOW,
        WORKER_AI_RATE_LIMIT,
        AVATAR_MAX_BYTES,
        TRANSCRIBE_MAX_BYTES,
        CHAT_RETENTION_SECONDS,
        _IDEMPOTENCY_TTL,
        CHAT_MAX,
        AI_RATE_LIMIT,
    )
except ImportError:
    from core.limits import (  # noqa: E402
        ONLINE_THRESHOLD_SECONDS,
        CHECKIN_MAX_BYTES,
        PHOTO_MAX_FILES,
        INIT_DATA_MAX_AGE,
        ALERT_DISMISS_TTL,
        PHOTO_MAX_COUNT,
        AI_UPLOAD_MAX_BYTES,
        PHOTO_MAX_BYTES,
        SHEETS_CACHE_TTL,
        SESSION_TOKEN_MAX_AGE,
        NOTIFIED_USERS_TTL,
        OBJECT_PHOTO_MAX,
        AI_RATE_WINDOW,
        WORKER_AI_RATE_LIMIT,
        AVATAR_MAX_BYTES,
        TRANSCRIBE_MAX_BYTES,
        CHAT_RETENTION_SECONDS,
        _IDEMPOTENCY_TTL,
        CHAT_MAX,
        AI_RATE_LIMIT,
    )

# Phase A step 4: MIME allowlists/sniffers + simple enum constants moved to
# backend/core/constants.py.
try:
    from .core.constants import (
        _ALLOWED_IMAGE_MIME_EXT,
        sniff_image,
        sniff_image_or_pdf,
        _ALLOWED_AUDIO_MIME_EXT,
        _ALLOWED_CHAT_ATTACHMENT_MIME_EXT,
        sniff_audio,
        sniff_chat_attachment,
        _INVISIBLE_FILLER_CHARS,
        BUDGET_FIELDS,
        VALID_OBJECT_STATUSES,
        CHAT_REACTION_OPTIONS,
        THREAD_TYPE_BY_PREFIX,
        DEFAULT_THREAD_PREFS,
        AI_MODELS,
        AI_MODEL_DEFAULT,
        _OWNER_AI_ENV_ALLOWLIST,
        TASK_PRIORITIES,
        TASK_CATEGORIES,
        TASK_STATUSES,
        ABWESENHEIT_REASONS,
        ABWESENHEIT_PUBLIC_FIELDS,
        _EMPTY_CONTRACT_STORE,
    )
except ImportError:
    from core.constants import (  # noqa: E402
        _ALLOWED_IMAGE_MIME_EXT,
        sniff_image,
        sniff_image_or_pdf,
        _ALLOWED_AUDIO_MIME_EXT,
        _ALLOWED_CHAT_ATTACHMENT_MIME_EXT,
        sniff_audio,
        sniff_chat_attachment,
        _INVISIBLE_FILLER_CHARS,
        BUDGET_FIELDS,
        VALID_OBJECT_STATUSES,
        CHAT_REACTION_OPTIONS,
        THREAD_TYPE_BY_PREFIX,
        DEFAULT_THREAD_PREFS,
        AI_MODELS,
        AI_MODEL_DEFAULT,
        _OWNER_AI_ENV_ALLOWLIST,
        TASK_PRIORITIES,
        TASK_CATEGORIES,
        TASK_STATUSES,
        ABWESENHEIT_REASONS,
        ABWESENHEIT_PUBLIC_FIELDS,
        _EMPTY_CONTRACT_STORE,
    )

# Phase A step 5: JSON storage safety layer moved to backend/core/storage.py.
# CRITICAL_JSON_PATHS is imported BY REFERENCE (same set object) -- the
# CRITICAL_JSON_PATHS.update({...}) call at the end of this file mutates
# that same object, core.storage sees the same final contents at call time.
try:
    from .core.storage import (
        CRITICAL_JSON_PATHS,
        CorruptJsonError,
        _corrupt_lock_path,
        _quarantine_corrupt_json,
        _json_locks,
        _json_locks_guard,
        _lock_for,
        _atomic_write_json,
        update_json_transaction,
        _safe_load_json,
    )
except ImportError:
    from core.storage import (  # noqa: E402
        CRITICAL_JSON_PATHS,
        CorruptJsonError,
        _corrupt_lock_path,
        _quarantine_corrupt_json,
        _json_locks,
        _json_locks_guard,
        _lock_for,
        _atomic_write_json,
        update_json_transaction,
        _safe_load_json,
    )
# moved to core/paths.py -- ROLES_FILE

# DailyPlan store — производственный контроль (Round 1)
# moved to core/paths.py -- DAILY_PLAN_STORE_FILE
# moved to core/paths.py -- PLAN_SYNC_STATE_FILE
# moved to core/paths.py -- WORK_CALENDAR_FILE
dpl.configure(DAILY_PLAN_STORE_FILE, PLAN_SYNC_STATE_FILE, WORK_CALENDAR_FILE)

# Finish projector outbox — durable event log for session_id→daily_execution application.
# Written before apply_daily_execution so a crash between checkin commit and plan update
# leaves a pending event that can be retried on startup.
# moved to core/paths.py -- FINISH_OUTBOX_FILE
_finish_outbox_lock = __import__('threading').Lock()

# Contract ingestion state (Round 5 — Drive scope gated)
# moved to core/paths.py -- CONTRACT_INGEST_STATE_FILE
_CONTRACT_INGEST_LOCK = __import__('threading').Lock()
CONTRACTS_DRIVE_FOLDER_ID = os.environ.get('CONTRACTS_DRIVE_FOLDER_ID', '')
# moved to core/limits.py -- INIT_DATA_MAX_AGE

# 31.07 (Release-аудит П4): для этих сторов corrupt JSON НЕ должен молча деградировать
# к default -- следующий же write через _atomic_write_json/update_json_transaction
# записал бы default ПОВЕРХ повреждённого файла, необратимо уничтожая реальные данные
# (roles/assignments/checkin/chat/abwesenheit/profiles/tasks/alerts/roadmap/stage_requests).
# Для этих путей: карантин повреждённого файла (.corrupt-<ts>) + mutation вызывает 503,
# read-only endpoint получает 503 вместо тихого пустого результата (см. exception_handler
# ниже, регистрация путей -- в самом конце файла, см. CRITICAL_JSON_PATHS.update(...)).
# moved to core/storage.py -- CRITICAL_JSON_PATHS, CorruptJsonError,
# _corrupt_lock_path, _quarantine_corrupt_json


app = FastAPI(title="Promonta Mini App", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://web.telegram.org"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup():
    """Retry pending finish-outbox events from a previous crash, and reconcile
    any finished checkin session whose outbox event never got written at all
    (crash between checkin_meta commit and outbox write)."""
    try:
        reconciled = _reconcile_missing_outbox_events()
        if reconciled:
            print(f"[startup] Reconciled {reconciled} missing finish-outbox event(s)")
    except Exception as e:
        print(f"[startup] finish-outbox reconciliation failed: {e}")
    try:
        retried = _retry_pending_outbox_events()
        if retried:
            print(f"[startup] Retried {retried} pending finish-outbox event(s)")
    except Exception as e:
        print(f"[startup] finish-outbox retry failed: {e}")


@app.exception_handler(CorruptJsonError)
async def _corrupt_json_handler(request, exc: CorruptJsonError):
    """31.07 (Release-аудит П4): единая точка -- любой _load_*/update_json_transaction
    на критичном сторе (roles/assignments/checkin/chat/abwesenheit/profiles/tasks/
    critical_alerts/roadmap/stage_requests), наткнувшись на повреждённый JSON, карантинит
    файл (_quarantine_corrupt_json) и поднимает это исключение вместо тихой деградации
    к default -- перехватывается здесь для ЛЮБОГО эндпоинта (GET/POST/PATCH/DELETE)
    без необходимости оборачивать каждый вызывающий код по отдельности."""
    from starlette.responses import JSONResponse
    return JSONResponse(
        status_code=503,
        content={"detail": "Данные временно недоступны (повреждённый файл), обратитесь к владельцу"},
    )

# moved to core/paths.py -- AUDIT_FILE
AUDIT_LOCK = __import__('threading').Lock()


@app.middleware("http")
async def audit_log_middleware(request, call_next):
    # 28.07 (real bug found by external audit, ТЗ п.25): было await request.body() для
    # ЛЮБОГО POST/PATCH/DELETE, включая multipart file upload (photo/voice/document) --
    # тело файла дублировалось в памяти дважды (readable once, buffered here + re-injected
    # via _receive override for the real handler below). Логируемая entry ниже НЕ включает
    # тело файла и никогда не включала -- этот буфер существовал только чтобы вернуть body
    # обратно эндпоинту, не для самого лога. Для multipart пропускаем чтение целиком: не
    # трогаем request._receive, FastAPI/Starlette читают upload stream штатно сами.
    is_multipart = request.headers.get("content-type", "").startswith("multipart/form-data")
    if request.method in ("POST", "PATCH", "DELETE") and not is_multipart:
        body_bytes = await request.body()

        async def receive():
            return {"type": "http.request", "body": body_bytes}
        request._receive = receive

    response = await call_next(request)

    # 30.07 (Release-аудит Этап 6): раньше логировались только успешные мутации
    # (status < 400) -- отклонения (400/403/404/413 на upload, 401 на auth) не
    # попадали в audit.log вообще, только в разрозненные print() в отдельных
    # местах кода. Теперь пишем обе категории отдельными полями -- rejection не
    # включает тело запроса/файла (тот же принцип, что и раньше: НЕ initData,
    # НЕ BOT_TOKEN, НЕ содержимое сообщений/GPS, только method/path/status/user_id).
    if request.method in ("POST", "PATCH", "DELETE"):
        user_id = None
        try:
            init_data = request.headers.get("x-telegram-init-data", "")
            parsed = dict(parse_qsl(init_data))
            user_id = json.loads(parsed.get("user", "{}")).get("id")
        except Exception:
            pass
        entry = {
            "ts": int(time.time()),
            "user_id": user_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "rejected": response.status_code >= 400,
        }
        with AUDIT_LOCK:
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return response


def _secret_key() -> bytes:
    return hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()


def validate_init_data(init_data: str) -> dict:
    """HMAC-валидация Telegram WebApp initData.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        raise HTTPException(401, "initData: malformed")
    received_hash = parsed.pop('hash', None)
    if not received_hash:
        raise HTTPException(401, "initData: no hash")

    auth_date = parsed.get('auth_date')
    try:
        if not auth_date:
            raise HTTPException(401, "initData: expired")
        age = time.time() - int(auth_date)
        if age > INIT_DATA_MAX_AGE or age < -60:
            raise HTTPException(401, "initData: expired")
    except ValueError:
        raise HTTPException(401, "initData: malformed auth_date")

    data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(parsed.items()))
    computed_hash = hmac.new(_secret_key(), data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(401, "initData: invalid signature")

    try:
        return json.loads(parsed['user'])
    except (KeyError, json.JSONDecodeError):
        raise HTTPException(401, "initData: no user")


# ---------- Session tokens (03.08, ТЗ Задача 1) ----------
# initData протухает через INIT_DATA_MAX_AGE (1 час) -- Telegram переподписывает его сам
# при каждом реальном открытии мини-аппы, но WebView НЕ переоткрывает приложение сам по
# себе посреди долгой смены, так что фронтенд слал один и тот же initData часами и
# получал 401 в середине смены. Решение: после ОДНОЙ успешной HMAC-проверки initData
# backend выдаёт свой собственный подписанный token на 12 часов -- НЕ продлевает доверие
# к initData бесконечно, просто переносит источник truth на отдельный, backend-контролируемый
# срок жизни. Whitelist/роль НЕ кэшируются в токене (token несёт только user_id + exp) --
# каждый запрос по-прежнему смотрит актуальный roles.json, так что revoke долступа
# работает мгновенно даже с валидным токеном.
# moved to core/limits.py -- SESSION_TOKEN_MAX_AGE


def _session_secret() -> bytes:
    """Домен-разделённый от _secret_key() (initData HMAC) -- разный "usage" в HMAC над
    тем же BOT_TOKEN, так что компрометация одного не равна компрометации другого."""
    return hmac.new(b"SessionToken", BOT_TOKEN.encode(), hashlib.sha256).digest()


def create_session_token(user_id) -> str:
    """Token = base64url(user_id.exp).hex(hmac). Полезная нагрузка содержит ТОЛЬКО
    user_id и unix-время истечения -- никаких паролей/ключей/ролей внутри, роль каждый
    раз проверяется заново по актуальному roles.json (см. get_current_user)."""
    exp = int(time.time()) + SESSION_TOKEN_MAX_AGE
    payload = f"{user_id}.{exp}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')
    sig = hmac.new(_session_secret(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_session_token(token: str) -> str:
    """Возвращает user_id (str) при валидной подписи и не истёкшем токене, иначе 401.
    hmac.compare_digest -- constant-time сравнение, не `==` (timing-attack защита)."""
    try:
        payload_b64, sig = token.rsplit('.', 1)
    except ValueError:
        raise HTTPException(401, "session token: malformed")

    expected_sig = hmac.new(_session_secret(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, sig):
        raise HTTPException(401, "session token: invalid signature")

    try:
        padded = payload_b64 + '=' * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(padded.encode()).decode()
        user_id_str, exp_str = payload.split('.', 1)
        exp = int(exp_str)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(401, "session token: malformed payload")

    if time.time() > exp:
        raise HTTPException(401, "session token: expired")

    return user_id_str


# moved to core/storage.py -- _json_locks, _json_locks_guard, _lock_for,
# _atomic_write_json, update_json_transaction, _safe_load_json


# moved to core/constants.py -- _ALLOWED_IMAGE_MIME_EXT, sniff_image,
# sniff_image_or_pdf, _ALLOWED_AUDIO_MIME_EXT, _ALLOWED_CHAT_ATTACHMENT_MIME_EXT,
# sniff_audio, sniff_chat_attachment


def _csv_safe(value) -> str:
    """CSV formula injection: Excel/LibreOffice выполняет ячейку, начинающуюся с
    =, +, -, @ как формулу при открытии. object_id в stundenzettel идёт от
    checkin_start (Form-параметр, только .strip()[:100], без sanitize) -- worker
    теоретически мог стартовать смену с object_id вроде `=cmd|'/c calc'!A1` и
    отравить CSV, который потом открывает owner. Префикс апострофом -- стандартный
    экранирующий приём, Excel показывает апостроф не отображая, LibreOffice тоже."""
    s = str(value)
    if s and s[0] in ('=', '+', '-', '@'):
        return "'" + s
    return s


def _load_roles() -> dict:
    return _safe_load_json(ROLES_FILE, {})


def _save_roles(roles: dict):
    _atomic_write_json(ROLES_FILE, roles)


# moved to core/paths.py -- NOTIFIED_USERS_FILE
# moved to core/limits.py -- NOTIFIED_USERS_TTL


def _load_notified_users() -> dict:
    raw = _safe_load_json(NOTIFIED_USERS_FILE, {})
    if isinstance(raw, list):
        # миграция со старого формата (список без timestamp) — считаем уведомлёнными сейчас
        now = time.time()
        return {uid: now for uid in raw}
    cutoff = time.time() - NOTIFIED_USERS_TTL
    return {uid: ts for uid, ts in raw.items() if ts >= cutoff}


def _save_notified_users(notified: dict):
    _atomic_write_json(NOTIFIED_USERS_FILE, notified)


def _notify_owner_new_user(user: dict, roles: dict):
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    if not owner_id:
        return
    notified = _load_notified_users()
    uid = str(user['id'])
    if uid in notified:
        return
    name = user.get('first_name', '') + (' ' + user['last_name'] if user.get('last_name') else '')
    username = f" (@{user['username']})" if user.get('username') else ''
    text = f"Новый пользователь открыл miniapp:\n{name.strip() or '—'}{username}\nID: {uid}\n\nДобавьте в roles.json, чтобы дать доступ."
    try:
        send_telegram_message(owner_id, text)
    except Exception:
        return  # уведомление best-effort — не блокировать 403-ответ, если Telegram недоступен
    notified[uid] = time.time()
    _save_notified_users(notified)


# 24.07: online-статус для чата (зелёный дот на аватаре в личных чатах, Connecteam-
# референс из брифа) — in-memory, не персистентный на диск. Обновляется на каждый
# authenticated-запрос (get_current_user — центральная точка, вызывается везде через
# Depends), не отдельный heartbeat-эндпоинт. Переживает не рестарт сервиса (все "не в
# сети" до первого запроса после рестарта) — приемлемо для присутствия-индикатора,
# не для чего-то critical.
_last_seen: dict = {}
# moved to core/limits.py -- ONLINE_THRESHOLD_SECONDS


def get_current_user(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> dict:
    """03.08 (ТЗ Задача 1): предпочитаем Authorization: Bearer <session token> --
    12-часовой backend-token, не требует свежего initData на каждый запрос.
    X-Telegram-Init-Data остаётся как fallback для обратной совместимости со старыми
    клиентами/вкладками, которые ещё не обновились на новый auth-путь -- временно,
    убрать после того, как весь трафик перейдёт на токены (см. PROJECT_STATE.md)."""
    if authorization and authorization.lower().startswith('bearer '):
        token = authorization[7:].strip()
        user_id = verify_session_token(token)
        user = {'id': int(user_id)} if user_id.lstrip('-').isdigit() else {'id': user_id}
    elif x_telegram_init_data:
        user = validate_init_data(x_telegram_init_data)
    else:
        raise HTTPException(401, "Нет initData и нет session token")

    # Whitelist (Фаза 10.1): доступ только тем, кого владелец явно добавил в roles.json —
    # раньше любой Telegram user_id молча получал worker-права по умолчанию (см. get_role ниже).
    # 03.08: проверяется на КАЖДЫЙ запрос заново независимо от источника auth (initData
    # или session token) -- владелец, удаливший работника из whitelist, обрывает доступ
    # немедленно, даже если у клиента ещё живой 12-часовой токен.
    roles = _load_roles()
    if str(user['id']) not in roles:
        if x_telegram_init_data and not (authorization and authorization.lower().startswith('bearer ')):
            _notify_owner_new_user(user, roles)
        raise HTTPException(403, "Доступ не предоставлен. Обратитесь к владельцу.")
    _last_seen[str(user['id'])] = time.time()
    return user


def get_role(user: dict = Depends(get_current_user)) -> str:
    roles = _load_roles()
    return roles.get(str(user['id']), 'worker')


def require_owner(role: str = Depends(get_role)):
    if role != 'owner':
        raise HTTPException(403, "owner only")


# Phase A: leaf business_now() moved to backend/core/time.py (zero deps).
# business_today()/business_today_str()/_today_berlin_str() STAY here, calling
# the module-local `business_now` name -- tests monkeypatch `backend.business_now`
# via patch.object(backend, 'business_now', ...), and these wrappers must keep
# resolving that same patched name at call time, not a separate copy baked into
# core.time's own namespace (which patch.object(backend, ...) would not reach).
# Same relative-then-absolute fallback as the work_types/profile_skills/etc.
# import block above (line ~119) -- `from .core.time import` resolves when
# main.py is imported as `miniapp.main` (package member, production/uvicorn),
# plain `from core.time import` resolves when main.py is loaded as a top-level
# module (tests, `uvicorn main:app` from backend_dir).
try:
    from .core.time import business_now
except ImportError:
    from core.time import business_now  # noqa: E402


def business_today():
    """date-объект 'сегодня' по Europe/Berlin -- для арифметики с timedelta
    (week_start = business_today() - timedelta(days=6) и т.п.)."""
    return business_now().date()


def business_today_str() -> str:
    """'YYYY-MM-DD' по Europe/Berlin -- для сравнения со строковыми датами в JSON-сторах
    (assignments date_from/date_to и т.п., которые уже хранятся как ISO-строки)."""
    return business_now().strftime('%Y-%m-%d')


def _today_berlin_str() -> str:
    """03.08: тонкая обёртка над business_today_str() -- has_active_object_access()
    уже использовала это имя до появления единого business_*() набора хелперов,
    переименовывать вызывающий код везде не требовалось, раз поведение идентично."""
    return business_today_str()


def has_active_object_access(user_id: str, object_id: str, today: str | None = None) -> bool:
    """03.08 (доп.раунд П2): единый helper для ПОЛНОГО доступа к данным объекта --
    отличается от простого "назначение существует". Worker должен иметь ровно ОДНО
    accepted-назначение на этот объект, чей период [date_from, date_to] включает
    сегодняшний день (Europe/Berlin) включительно. Назначение без date_from/date_to
    (легаси-записи до введения периодов) трактуется как бессрочное -- backward compat,
    та же логика уже была в _get_active_assignment_for_checkin.

    НЕ вызывать напрямую для owner -- эта функция только про worker-назначения,
    вызывающий код (require_object_access/has_active_object_access_for_role) сам
    решает, что owner имеет доступ всегда."""
    if today is None:
        today = _today_berlin_str()
    assignments = _load_assignments().get(str(object_id), [])
    for a in assignments:
        if str(a.get('user_id')) != str(user_id):
            continue
        if _assignment_status(a) != 'accepted':
            continue
        d_from, d_to = a.get('date_from', ''), a.get('date_to', '')
        if not (d_from and d_to):
            return True  # легаси-назначение без периода -- бессрочный доступ
        if d_from <= today <= d_to:
            return True
    return False


def can_access_object(user: dict, role: str, object_id: str) -> bool:
    """owner видит/управляет всем; worker -- только объекты, на которые назначен
    И чей период назначения активен сегодня (Europe/Berlin). Единая точка правды для
    object-scoped routes -- раньше большинство из них проверяли только
    get_current_user (авторизован ли вообще), не было ли это чужим объектом.

    03.08 (доп.раунд П2, реальный найденный баг): раньше accepted-назначение давало
    ПОЛНЫЙ доступ независимо от периода -- worker с назначением на будущий месяц уже
    сегодня мог открыть чат/этапы/файлы объекта, доступ к которому должен появиться
    только в date_from. Период теперь обязательная часть проверки (has_active_object_access)."""
    if role == 'owner':
        return True
    return has_active_object_access(str(user['id']), object_id)


def require_object_access(object_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """FastAPI матчит `object_id` по имени пути -- подключать как обычный Depends
    в любом route, где путь содержит {object_id}."""
    if not can_access_object(user, role, object_id):
        raise HTTPException(403, "Нет доступа к этому объекту")


class RoleSetBody(BaseModel):
    user_id: str
    role: str  # 'owner' | 'worker'


@app.get("/api/roles")
def list_roles(user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """10.29 (Fable-аудит): раньше добавление воркера требовало ручной SSH+правку JSON —
    теперь owner может смотреть/менять whitelist прямо из приложения."""
    roles = _load_roles()
    notified = _load_notified_users()
    profiles = _load_worker_profiles()
    # 09.09: pending раньше строился ТОЛЬКО из notified_users - roles -- пользователь,
    # который прошёл онбординг (появился в worker_profiles.json) но никогда не попадал
    # в notified_users (например если процесс уведомления сбоил, или профиль создан
    # каким-то другим путём), был невидим здесь целиком: не в roles (нет доступа), не
    # в pending (не в notified) -- "призрак", которого Access-вкладка не показывала
    # вообще, хотя /api/workers считал его активным работником (тот же баг, см.
    # комментарий там). Теперь pending = любой профиль без активной роли, не
    # пересечение с notified -- notified_users используется только чтобы ПОМЕТИТЬ
    # (was_notified), не как обязательное условие попадания в список.
    pending_ids = sorted(set(profiles.keys()) - set(roles.keys()))
    return {
        "roles": [{"user_id": uid, "role": r,
                   "name": _sanitize_display_name(profiles.get(uid, {}).get('name'), uid)}
                  for uid, r in roles.items()],
        "pending": [{"user_id": uid,
                     "name": _sanitize_display_name(profiles.get(uid, {}).get('name'), uid),
                     "was_notified": uid in notified}
                    for uid in pending_ids],
    }


@app.post("/api/roles")
def set_role(body: RoleSetBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    if body.role not in ('owner', 'worker'):
        raise HTTPException(400, "role должен быть owner или worker")
    roles = _load_roles()
    if body.role == 'worker' and roles.get(str(body.user_id)) == 'owner':
        remaining_owners = sum(1 for r in roles.values() if r == 'owner') - 1
        if remaining_owners < 1:
            raise HTTPException(400, "Нельзя понизить последнего owner — фирма останется без владельца в приложении")
    roles[str(body.user_id)] = body.role
    _save_roles(roles)
    try:
        send_telegram_message(int(body.user_id), f"Вам предоставлен доступ к miniapp (роль: {body.role}).")
    except Exception:
        pass
    return {"status": "ok"}


@app.delete("/api/roles/{target_user_id}")
def revoke_role(target_user_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    if target_user_id == str(user['id']):
        raise HTTPException(400, "Нельзя удалить свою же роль")
    roles = _load_roles()
    if roles.get(target_user_id) == 'owner':
        remaining_owners = sum(1 for r in roles.values() if r == 'owner') - 1
        if remaining_owners < 1:
            raise HTTPException(400, "Нельзя удалить последнего owner — фирма останется без владельца в приложении")
    roles.pop(target_user_id, None)
    _save_roles(roles)
    return {"status": "ok"}


# 30.07 (Release-аудит Этап 6): commit SHA для /api/health читается из файла рядом
# с main.py, который пишет deploy-скрипт при выкладке -- НЕ subprocess'ом git на
# каждый health-запрос (дорого, плюс serving-путь /home/promonta/agent/miniapp/
# не является git-репозиторием, git там просто не сработает). Файл опционален --
# если деплой был сделан вручную без записи VERSION, health всё равно отвечает,
# просто без SHA.
# moved to core/paths.py -- APP_VERSION_FILE


def _read_app_version() -> dict:
    if not os.path.isfile(APP_VERSION_FILE):
        return {"version": "unknown", "commit": "unknown"}
    try:
        with open(APP_VERSION_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return {"version": data.get('version', 'unknown'), "commit": data.get('commit', 'unknown')}
    except (json.JSONDecodeError, OSError):
        return {"version": "unknown", "commit": "unknown"}


@app.get("/api/health")
def health():
    """Лёгкая liveness-проверка -- процесс жив, отвечает. Не трогает диск/сеть
    (кроме чтения маленького локального VERSION-файла) -- безопасно дёргать часто
    из мониторинга. Никаких токенов/секретов/путей к credentials/персональных
    данных в ответе (30.07, Release-аудит Этап 6)."""
    version_info = _read_app_version()
    return {
        "status": "ok",
        "service": "promonta-miniapp",
        "version": version_info["version"],
        "commit": version_info["commit"],
        "time": datetime.utcnow().isoformat() + 'Z',
    }


@app.get("/api/health/ready")
def health_ready(user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """Readiness-проверка для Owner/внутреннего мониторинга -- owner-only (в отличие
    от /api/health): проверяет реальную готовность обслуживать запросы, не только
    "процесс жив". Каждая проверка дешёвая (stat/os.access), НЕ дорогой сетевой
    запрос к Google Sheets на каждый вызов -- иначе readiness сам стал бы точкой
    перегрузки при частом опросе мониторингом."""
    checks = {}

    # storage: базовые директории для загрузок существуют и доступны для записи.
    storage_dirs = [
        ('object_photos', OBJECT_PHOTO_DIR),
        ('chat_attachments', CHAT_ATTACH_DIR),
    ]
    storage_ok = True
    for name, path in storage_dirs:
        if not (os.path.isdir(path) and os.access(path, os.W_OK)):
            storage_ok = False
            break
    checks['storage'] = 'ok' if storage_ok else 'error'

    # uploads: реальная проверка записи -- временный файл создаётся и сразу удаляется
    # (не просто os.access, который может соврать про эффективные права на некоторых ФС).
    try:
        probe_path = os.path.join(OBJECT_PHOTO_DIR, f'.health-probe-{os.getpid()}')
        with open(probe_path, 'wb') as f:
            f.write(b'ok')
        os.remove(probe_path)
        checks['uploads'] = 'ok'
    except OSError:
        checks['uploads'] = 'error'

    # tools_lib.py -- наличие рядом с main.py (Release-аудит: изолированный
    # importlib-loader должен находить файл по TOOLS_LIB_PATH).
    checks['tools_lib'] = 'ok' if os.path.isfile(TOOLS_LIB_PATH) else 'missing'
    checks['mangel_lib'] = 'ok' if os.path.isfile(MANGEL_LIB_PATH) else 'missing'
    # 01.08 (доп.раунд П1): work_types.py/profile_skills.py/assignment_matching.py --
    # если import упал в проде (см. try/except в шапке файла), main.py вообще не
    # стартует и этот эндпоинт недостижим -- но если файлы отсутствуют РЯДОМ с
    # main.py (deploy.sh забыл их скопировать), это ловится тут же, до того как
    # реальный запрос на /api/work-types упадёт 500-кой.
    checks['work_types'] = 'ok' if os.path.isfile(os.path.join(BACKEND_DIR, 'work_types.py')) else 'missing'
    checks['profile_skills'] = 'ok' if os.path.isfile(os.path.join(BACKEND_DIR, 'profile_skills.py')) else 'missing'
    checks['assignment_matching'] = 'ok' if os.path.isfile(os.path.join(BACKEND_DIR, 'assignment_matching.py')) else 'missing'

    # runtime JSON -- ROLES_FILE обязателен для работы whitelist-авторизации,
    # его отсутствие -- реальный readiness-блокер (не просто "пусто").
    checks['roles_file'] = 'ok' if os.path.isfile(ROLES_FILE) else 'missing'

    overall_ok = all(v == 'ok' for v in checks.values())
    return {
        "status": "ready" if overall_ok else "degraded",
        "checks": checks,
    }


@app.get("/api/diagnostics")
def diagnostics(_: None = Depends(require_owner)):
    """Owner-only system status snapshot — all checks are cheap (file I/O + in-memory cache
    inspection only, no live Sheets or Drive API calls). Designed so a "данные не грузятся"
    report can be diagnosed in under a minute without touching prod data."""
    now = time.time()
    result = {}

    # ── Backend ──────────────────────────────────────────────────────────────
    data_root_ok = os.path.isdir(DATA_ROOT) and os.access(DATA_ROOT, os.R_OK)
    roles_ok = os.path.isfile(ROLES_FILE)
    result['backend'] = 'ok' if (data_root_ok and roles_ok) else 'degraded'

    # ── Sheets ────────────────────────────────────────────────────────────────
    # Report based on the in-memory cache, not a live API call (fast, cheap).
    # _sheets_cache maps tab_name → (timestamp, rows); the freshest entry tells us
    # when Sheets was last successfully read since this process started.
    sheets_entries = [(ts, tab) for tab, (ts, _) in _sheets_cache.items()]
    if sheets_entries:
        last_ts, _ = max(sheets_entries, key=lambda x: x[0])
        age = int(now - last_ts)
        result['sheets'] = 'ok' if age < SHEETS_CACHE_TTL * 4 else 'stale'
        result['sheets_last_read_s'] = age
    else:
        result['sheets'] = 'not_loaded'
        result['sheets_last_read_s'] = None

    # ── Objects ───────────────────────────────────────────────────────────────
    obj_cache = _sheets_cache.get('Объекты')
    if obj_cache:
        _, rows = obj_cache
        obj_count = max(0, len(rows) - 1)  # subtract header row
        result['objects'] = f'{obj_count} objects'
    else:
        result['objects'] = 'not_loaded'

    # ── Feed ──────────────────────────────────────────────────────────────────
    feed_ok = os.path.isfile(os.path.join(DATA_ROOT, 'activity_alerts.json'))
    news_ok = os.path.isfile(NEWS_FEED_FILE)
    result['feed'] = ('ok' if feed_ok else 'missing_alerts') + ('' if news_ok else '+news_missing')
    if result['feed'] == 'ok':
        result['feed'] = 'ok'

    # ── Chat ──────────────────────────────────────────────────────────────────
    result['chat'] = 'ok' if os.path.isfile(CHAT_FILE) else 'missing'

    # ── DailyPlan-sync ────────────────────────────────────────────────────────
    sync_state = _safe_load_json(PLAN_SYNC_STATE_FILE, {})
    if sync_state.get('last_sync_at'):
        sync_age = int(now - sync_state['last_sync_at'])
        result['dailyplan_sync'] = 'ok' if sync_age < 3600 else 'stale'
        result['dailyplan_sync_age_s'] = sync_age
    elif os.path.isfile(PLAN_SYNC_STATE_FILE):
        result['dailyplan_sync'] = 'file_exists_no_sync'
        result['dailyplan_sync_age_s'] = None
    else:
        result['dailyplan_sync'] = 'not_configured'
        result['dailyplan_sync_age_s'] = None

    # ── Finish outbox (DailyPlan execution projection) ──────────────────────────
    _dead_letter_count = _outbox_dead_letter_count()
    result['finish_outbox'] = 'red' if _dead_letter_count > 0 else 'ok'
    result['finish_outbox_dead_letter_count'] = _dead_letter_count

    # ── Drive / Contracts ─────────────────────────────────────────────────────
    result['drive_contracts'] = 'configured' if CONTRACTS_DRIVE_FOLDER_ID else 'not_configured'
    result['contracts_ingested'] = len(
        _safe_load_json(CONTRACT_INGEST_STATE_FILE, {}).get('contracts', {}) if os.path.isfile(CONTRACT_INGEST_STATE_FILE) else {}
    )

    # ── Build SHA ─────────────────────────────────────────────────────────────
    version_info = _read_app_version()
    result['build_sha'] = version_info['commit']
    result['build_version'] = version_info['version']

    overall = 'ok' if all(
        v in ('ok', 'configured', 'not_configured')
        for k, v in result.items()
        if k in ('backend', 'sheets', 'chat')
    ) else 'degraded'
    result['overall'] = overall
    return result


@app.get("/api/me")
def me(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    return {"user_id": user['id'], "name": user.get('first_name'), "role": role}


@app.post("/api/session")
def create_session(x_telegram_init_data: str = Header(...)) -> dict:
    """03.08 (ТЗ Задача 1): выдаёт 12-часовой session token. Требует ЖИВОЙ initData
    (обычная HMAC + 1-час TTL проверка через get_current_user-путь ниже, не отдельный
    ослабленный код) -- токен можно получить только пройдя ту же проверку, что раньше
    требовалась на каждый запрос. Whitelist-проверка тоже здесь: не-whitelisted юзер
    не получает токен вообще, не только 403 на защищённых эндпоинтах."""
    user = get_current_user(authorization=None, x_telegram_init_data=x_telegram_init_data)
    token = create_session_token(user['id'])
    return {
        "token": token,
        "expires_in": SESSION_TOKEN_MAX_AGE,
        "user_id": user['id'],
    }


# ---------- Workers list (для bubble-assign, Фаза 2 → доделано в Фазе 3) ----------
@app.get("/api/workers")
def list_workers(user: dict = Depends(get_current_user)):
    roles = _load_roles()
    profiles = _load_worker_profiles()
    # 09.09: roster/access invariant fix (owner report -- worker "Иван" appeared in
    # team/dashboard, had no avatar, Worker Card 404'd, and was missing from the
    # Доступ tab). Root cause: this endpoint unioned roles.json + worker_profiles.json
    # keys, then did `roles.get(uid, 'worker')` -- a DEFAULT of 'worker' for ANY uid
    # not in roles.json at all, not just those explicitly granted that role. The same
    # exact bug was already found and fixed in get_assignment_candidates() (01.08,
    # comment above worker_ids there) but never applied here -- this endpoint kept
    # presenting profile-only users (filled onboarding, never granted or since revoked
    # access) as if they were active workers with real access. Every one of this
    # endpoint's 6 frontend consumers already filters on `w.role === 'worker'`
    # (mangel.js, tools.js, home.js, abwesenheit.js, today-plan.js) -- fixing the
    # default here makes those filters correct automatically, no frontend change
    # needed for the worker-picker call sites. `access_granted` is new, additive --
    # existing consumers reading only `role`/`name` are unaffected.
    all_ids = set(roles.keys()) | set(profiles.keys())
    workers = []
    for uid in all_ids:
        p = profiles.get(uid, {})
        last_seen = _last_seen.get(uid)
        role = roles.get(uid)  # None if not in roles.json -- no more silent 'worker' default
        workers.append({
            'user_id': uid,
            'role': role,
            'access_granted': role is not None,
            'name': _sanitize_display_name(p.get('name'), uid),
            'skills': p.get('skills', []),
            'has_avatar': bool(p.get('avatar')),
            'quiz_completed': p.get('quiz_completed', False),
            'online': bool(last_seen and (time.time() - last_seen) < ONLINE_THRESHOLD_SECONDS),
        })
    return {'workers': workers}


# ---------- Профиль работника: навыки + онбординг-квиз (Фаза 2/8) ----------
# moved to core/paths.py -- WORKER_PROFILES_FILE
# 01.08 (единый каталог видов работ): SKILL_OPTIONS был вручную продублированным
# списком из 19 строк, отдельно от frontend ONBOARDING_GROUPS/BUBBLE_STAGE_OPTIONS --
# новый навык мог появиться в одном месте и отсутствовать в другом (реальный
# найденный дрифт: SKILL_STAGE_MAP покрывал только 8 из 19). Источник истины теперь
# один -- work_types.py, SKILL_OPTIONS оставлен как производный список ИМЁН active
# work types (тот же порядок что в каталоге) только для legacy-полей API-ответов
# (skill_options в /api/profile/me), которые старый frontend-код ещё может читать.
SKILL_OPTIONS = [w['name'] for w in wt.WORK_TYPES if w['active']]


def _load_worker_profiles() -> dict:
    return _safe_load_json(WORKER_PROFILES_FILE, {})


def _save_worker_profiles(profiles: dict):
    _atomic_write_json(WORKER_PROFILES_FILE, profiles)


def _get_worker_profile(user_id) -> dict:
    profiles = _load_worker_profiles()
    return profiles.get(str(user_id), {"skills": [], "quiz_completed": False})


@app.get("/api/work-types")
def get_work_types(user: dict = Depends(get_current_user)):
    """01.08: единый каталог видов работ -- доступен любому авторизованному
    пользователю (не owner-only), т.к. Worker выбирает навыки в onboarding/профиле,
    не только Owner в Assignment Sheet."""
    return wt.work_types_catalog()


def _get_worker_skills_v2(user_id) -> list:
    """Профиль работника -> нормализованный skills_v2, с idempotent миграцией
    legacy 'skills' (список названий) при первом обращении -- ТОЛЬКО если реально
    нужна миграция (skills_v2 отсутствует), файл не переписывается на каждый read."""
    profiles = _load_worker_profiles()
    key = str(user_id)
    profile = profiles.get(key, {"skills": [], "quiz_completed": False})
    skills_v2, changed = pskills.normalize_profile_skills(profile)
    if changed:
        profile['skills_v2'] = skills_v2
        profiles[key] = profile
        _save_worker_profiles(profiles)
    return skills_v2


# moved to core/constants.py -- _INVISIBLE_FILLER_CHARS


def _gps_suspect(lat: str, lon: str) -> bool:
    """Грубая эвристика, не блокирует check-in (GPS на стройке часто глючит --
    подвалы, между зданиями), только помечает координаты как подозрительные для owner:
    (0,0) -- Null Island, классический fallback GPS-модуля при полном отсутствии сигнала;
    либо явно вне разумного диапазона Германии (широта ~47-55, долгота ~5-16)."""
    try:
        f_lat, f_lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return True
    if f_lat == 0 and f_lon == 0:
        return True
    if not (47 <= f_lat <= 55.5 and 5 <= f_lon <= 16):
        return True
    return False


def _sanitize_display_name(raw: str | None, fallback: str) -> str:
    """Telegram first_name может быть невидимыми символами (заполнители Hangul,
    zero-width, чистые пробелы) или бессмысленным набором ('X13') — сохранённым
    как есть при первой авторизации. На экране это выглядит как "битый"/нечитаемый
    паттерн, а не как проблема шрифта (баг 23.07: юзер видел "нечитаемый паттерн"
    в имени и "X13" вместо имени в подписи графика — оба места брали profile['name']
    без проверки на осмысленность).
    Hangul filler (U+3164 и родня) — валидная Unicode-буква категории Lo, поэтому
    обычный \\w её не отсеивает; сначала вычищаем known invisible-filler + все
    юникод-символы категории Cf (format, включает zero-width space/joiner и т.п.),
    и только потом проверяем, остался ли хоть один "буквенный" символ."""
    if not raw:
        return fallback
    stripped = raw.strip()
    if not stripped:
        return fallback
    import re
    import unicodedata
    visible = ''.join(
        ch for ch in stripped
        if ch not in _INVISIBLE_FILLER_CHARS and unicodedata.category(ch) != 'Cf'
    ).strip()
    if not visible or not re.search(r'\w', visible, re.UNICODE):
        return fallback
    return stripped


def _is_meaningful_name(raw: str | None, user_id: str) -> bool:
    """Раунд 6 §4.1: строка — настоящее отображаемое имя, а не заглушка/ID.
    Строже, чем _sanitize_display_name (тот пропускает цифры и сам user_id как
    'валидные' \\w-строки): используется для one-time completion-gate существующих
    пользователей без имени. Пусто/пробелы/невидимое/==user_id/только цифры/<2/>100 -> False."""
    cleaned = _sanitize_display_name(raw, '')
    if not cleaned:
        return False
    s = cleaned.strip()
    if len(s) < 2 or len(s) > 100:
        return False
    if s.isdigit():
        return False
    if s == str(user_id):
        return False
    return True


def _validate_birthday(raw: str) -> str:
    """Раунд 6 §3.1: валидирует дату рождения. Формат YYYY-MM-DD, реальная дата,
    не в будущем (Europe/Berlin). Возвращает нормализованную ISO-строку либо HTTP 400."""
    if raw is None or not str(raw).strip():
        raise HTTPException(400, "Укажите дату рождения")
    s = str(raw).strip()
    try:
        d = datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(400, "Некорректная дата рождения (формат ГГГГ-ММ-ДД)")
    if d > business_today():
        raise HTTPException(400, "Дата рождения не может быть в будущем")
    return d.isoformat()


def _profile_completion_status(user: dict, profile: dict, role: str) -> dict:
    """Раунд 6 §3.2/§4: какие обязательные поля профиля не заполнены.
    name — для всех; birthday — только для Worker (Owner не обязан заполнять)."""
    uid = str(user['id'])
    name_ok = _is_meaningful_name(profile.get('name') or user.get('first_name'), uid)
    birthday_ok = bool(profile.get('birthday'))
    return {
        'name_required': not name_ok,
        'birthday_required': (role == 'worker') and not birthday_ok,
    }


@app.get("/api/profile/me")
def get_my_profile(user: dict = Depends(get_current_user)):
    profile = _get_worker_profile(user['id'])
    healed_name = _sanitize_display_name(profile.get('name'), '') or None
    if not healed_name and user.get('first_name'):
        # Раньше имя сохранялось только при загрузке аватара — работник без аватара
        # отображался у всех числовым Telegram ID (в чате, people-dots, Abwesenheit).
        # 23.07: то же самое — если сохранённое имя оказалось "битым" (невидимые
        # символы/бессмысленный набор из Telegram first_name), перезаписываем его
        # текущим Telegram first_name (обычно тем же значением — тогда ничего не
        # меняется — но если юзер уже поправил имя в Telegram, подхватываем новое).
        candidate = _sanitize_display_name(user.get('first_name'), '')
        if candidate:
            profiles = _load_worker_profiles()
            key = str(user['id'])
            profile = profiles.get(key, {"skills": [], "quiz_completed": False})
            profile['name'] = candidate
            profiles[key] = profile
            _save_worker_profiles(profiles)
            healed_name = candidate
    if healed_name:
        profile = {**profile, 'name': healed_name}
    else:
        # Item 5 fix (owner report: square/garbled glyphs in profile name):
        # the healing above only overwrites profile['name'] when a usable
        # replacement (Telegram first_name) exists. If BOTH the stored name
        # AND the current first_name fail sanitization (real case: Telegram
        # first_name genuinely contains only Hangul filler characters, not a
        # rendering/font bug -- confirmed by reading the raw string, not
        # guessed), the original unsanitized value was passed straight
        # through to the client. Never silently strip a legitimate Cyrillic
        # name (sanitize_display_name already handles that correctly) --
        # only replace when sanitization proves there is truly nothing
        # displayable left, falling back to the Telegram user_id like the
        # rest of the app already does when no name is available at all.
        existing_sanitized = _sanitize_display_name(profile.get('name'), '')
        if not existing_sanitized:
            profile = {**profile, 'name': str(user['id'])}
    skills_v2 = _get_worker_skills_v2(user['id'])
    role = _load_roles().get(str(user['id']), 'worker')
    return {
        "user_id": user['id'],
        "skill_options": SKILL_OPTIONS,  # legacy -- старый frontend-код может ещё это читать
        **profile,
        "role": role,
        "skills": pskills.legacy_skill_names_from_v2(skills_v2),  # legacy-совместимый список строк
        "skills_v2": skills_v2,  # новый источник истины
        "onboarding_completed": bool(profile.get('onboarding_completed') or profile.get('quiz_completed')),
        "onboarding_version": profile.get('onboarding_version', 1),
        # Раунд 6 §3.2/§4/§6: bootstrap показывает completion-экран если что-то обязательное пусто
        "needs_completion": _profile_completion_status(user, profile, role),
    }


@app.get("/api/users/{target_id}/card")
def get_user_card(target_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """Публичная карточка (10.10) — доступна любому авторизованному пользователю,
    в отличие от /api/profile/stats (там чужой профиль видит только owner).
    Только неконфиденциальные поля: имя, роль, навыки. Без часов/истории объектов/бюджета.

    30.07 (спек: expanded user-card): текущий объект/статус смены -- это МЕСТОПОЛОЖЕНИЕ
    работника, та же чувствительность что у /api/dashboard/shifts-today (уже owner-only).
    Не добавляем эти поля для worker-to-worker просмотра (нарушило бы существующий явный
    privacy-дизайн этого endpoint'а) -- только когда card смотрит owner."""
    roles = _load_roles()
    if target_id not in roles:
        raise HTTPException(404, "Пользователь не найден")
    profile = _get_worker_profile(target_id)
    has_avatar = bool(profile.get('avatar'))
    skills_v2 = _get_worker_skills_v2(target_id)
    card = {
        "user_id": target_id,
        "name": _sanitize_display_name(profile.get('name'), target_id),
        "role": roles[target_id],
        "skills": pskills.legacy_skill_names_from_v2(skills_v2),
        "skills_v2": skills_v2,
        "has_avatar": has_avatar,
    }
    if role == 'owner' and roles[target_id] != 'owner':
        today = datetime.now().strftime('%Y-%m-%d')
        sessions = [s for s in _load_checkin_meta() if str(s.get('user_id')) == target_id and s.get('date') == today]
        open_session = next((s for s in sessions if s.get('finish_at') is None), None)
        rows = _cached_get_used_range('Объекты')
        object_names = {}
        if rows:
            header, data = rows[0], rows[1:]
            for r in data:
                obj = dict(zip(header, r))
                object_names[str(obj.get('ID объекта', ''))] = obj.get('Объект', '')
        if open_session:
            card["shift_status"] = "working"
            card["object_name"] = object_names.get(open_session['object_id'], open_session['object_id'])
            card["stage_name"] = open_session.get('stage_name') or ''
            card["start_at"] = open_session.get('start_at')
        else:
            card["shift_status"] = "idle"
    return card


class SkillV2Body(BaseModel):
    skill_id: str
    level: str
    verified: bool = False


class ProfileUpdateBody(BaseModel):
    name: str | None = None  # 24.07: ручное имя — нужно, когда Telegram first_name
    # пуст/скрыт/состоит из невидимых символов (self-heal в get_my_profile не может
    # исцелиться нечем в этом случае).
    skills: list[str] | None = None  # legacy -- принимается для обратной совместимости
    skills_v2: list[SkillV2Body] | None = None  # 01.08: новый источник истины
    quiz_completed: bool | None = None
    onboarding_completed: bool | None = None
    onboarding_version: int | None = None
    pants_size: str | None = None
    shirt_size: str | None = None
    shoe_size: str | None = None
    birthday: str | None = None  # YYYY-MM-DD
    # Раунд 6 §3: владелец ОТМЕНИЛ прежнее решение (01.08), запрещавшее дату рождения в
    # onboarding и профиле. Поле снова обязательно для Worker в onboarding и completion-
    # экране, редактируется в профиле, используется для календаря и birthday-алертов.
    # Валидация — _validate_birthday() ниже (формат + не в будущем, Europe/Berlin).


@app.patch("/api/profile/me")
def update_my_profile(body: ProfileUpdateBody, user: dict = Depends(get_current_user)):
    profiles = _load_worker_profiles()
    key = str(user['id'])
    profile = profiles.get(key, {"skills": [], "quiz_completed": False})
    role = _load_roles().get(key, 'worker')
    updates = body.dict(exclude_unset=True)
    if 'name' in updates:
        cleaned = _sanitize_display_name(updates['name'], '')
        if not cleaned:
            raise HTTPException(400, "Имя не должно быть пустым")
        updates['name'] = cleaned[:100]
    # Раунд 6 §3.1: дата рождения — валидируем формат/не-в-будущем при любом сохранении.
    if 'birthday' in updates and updates['birthday'] is not None:
        updates['birthday'] = _validate_birthday(updates['birthday'])
    if 'skills_v2' in updates:
        for s in updates['skills_v2']:
            if s.get('level') not in pskills.SKILL_LEVELS:
                raise HTTPException(400, f"Недопустимый уровень навыка: {s.get('level')!r}")
        # 01.08 (доп.раунд П3): было -- ЛЮБОЙ PATCH skills_v2 сбрасывал verified=False
        # для ВСЕГО списка, включая навыки, которые вообще не менялись (реальный баг:
        # owner подтверждает 3 навыка, worker меняет уровень 4-го -- все 3 подтверждения
        # молча слетали). Теперь: verified сохраняется, если И skill_id, И level
        # совпадают с тем, что уже было в сохранённом профиле; новый/изменённый навык
        # получает verified=False (worker всё ещё не может сам его подтвердить -- см.
        # verify_worker_skill ниже, единственный способ поставить True).
        existing_by_id = {s['skill_id']: s for s in (profile.get('skills_v2') or []) if 'skill_id' in s}
        normalized = []
        for s in updates['skills_v2']:
            prior = existing_by_id.get(s.get('skill_id'))
            unchanged = prior is not None and prior.get('level') == s.get('level')
            normalized.append({
                "skill_id": s.get('skill_id'),
                "level": s.get('level'),
                "verified": bool(prior.get('verified')) if unchanged else False,
            })
        updates['skills_v2'] = normalized
    # 01.08 (спека п.3): onboarding_completed нельзя установить, пока обязательные
    # условия не выполнены -- проверяем на РЕЗУЛЬТИРУЮЩЕМ профиле (после merge с
    # уже сохранёнными полями), не только на этом одном PATCH-запросе, т.к. frontend
    # сохраняет профиль по шагам (спека: "Сначала сохранить профиль, затем
    # установить onboarding_completed: true").
    if updates.get('onboarding_completed'):
        merged_name = updates.get('name', profile.get('name'))
        merged_skills = updates.get('skills_v2', profile.get('skills_v2', []))
        merged_birthday = updates.get('birthday', profile.get('birthday'))
        if not _sanitize_display_name(merged_name, ''):
            raise HTTPException(400, "Укажите имя, чтобы завершить регистрацию")
        # Раунд 6 §3.1: дата рождения обязательна для Worker (Owner — нет).
        if role == 'worker' and not merged_birthday:
            raise HTTPException(400, "Укажите дату рождения, чтобы завершить регистрацию")
        if not merged_skills:
            raise HTTPException(400, "Выберите хотя бы один навык")
        for s in merged_skills:
            level = s.get('level') if isinstance(s, dict) else None
            if level not in pskills.SKILL_LEVELS:
                raise HTTPException(400, "Укажите уровень для каждого выбранного навыка")
        updates['onboarding_completed_at'] = datetime.utcnow().isoformat() + 'Z'
        updates['onboarding_version'] = 2
        updates['quiz_completed'] = True  # legacy-совместимость (спека п.3)
    profile.update(updates)
    profiles[key] = profile
    _save_worker_profiles(profiles)
    return profile


class SkillVerificationBody(BaseModel):
    verified: bool


@app.patch("/api/workers/{user_id}/skills/{skill_id}/verification")
def verify_worker_skill(user_id: str, skill_id: str, body: SkillVerificationBody,
                         user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """01.08 (спека п.4): только Owner подтверждает навык работника. Worker не может
    сам выставить verified: true -- см. update_my_profile выше, self-service PATCH
    всегда сбрасывает verified в False."""
    profiles = _load_worker_profiles()
    key = str(user_id)
    profile = profiles.get(key)
    if not profile:
        raise HTTPException(404, "Профиль не найден")
    skills_v2, _changed = pskills.normalize_profile_skills(profile)
    skills_v2, found = pskills.set_skill_verification(skills_v2, skill_id, body.verified)
    if not found:
        raise HTTPException(404, "У работника нет такого навыка")
    profile['skills_v2'] = skills_v2
    profiles[key] = profile
    _save_worker_profiles(profiles)
    return {"skill_id": skill_id, "verified": body.verified}


# ---------- Фаза 8: аватар + агрегированная статистика профиля ----------
# moved to core/paths.py -- AVATAR_DIR
# moved to core/limits.py -- AVATAR_MAX_BYTES
os.makedirs(AVATAR_DIR, exist_ok=True)


@app.post("/api/profile/me/avatar")
async def upload_my_avatar(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    raw = await file.read()
    if len(raw) > AVATAR_MAX_BYTES:
        raise HTTPException(400, "Аватар слишком большой (макс. 4 МБ)")
    detected = sniff_image(raw)
    if not detected:
        raise HTTPException(400, "Файл должен быть изображением")
    ext = _ALLOWED_IMAGE_MIME_EXT[detected]
    uid = str(user['id'])
    # держим ровно один файл на юзера — старое расширение убираем
    for fname in os.listdir(AVATAR_DIR):
        if fname.startswith(uid + '.'):
            os.remove(os.path.join(AVATAR_DIR, fname))
    with open(os.path.join(AVATAR_DIR, f"{uid}.{ext}"), 'wb') as f:
        f.write(raw)
    profiles = _load_worker_profiles()
    profile = profiles.get(uid, {"skills": [], "quiz_completed": False})
    profile['avatar'] = True
    if not profile.get('name'):
        profile['name'] = user.get('first_name', uid)
    profiles[uid] = profile
    _save_worker_profiles(profiles)
    return {"status": "ok"}


@app.get("/api/profile/{user_id}/avatar")
def get_avatar(user_id: str, user: dict = Depends(get_current_user)):
    if not user_id.isdigit():
        raise HTTPException(400, "user_id должен быть числовым Telegram ID")
    for ext in ('jpg', 'png', 'webp'):
        path = os.path.join(AVATAR_DIR, f"{user_id}.{ext}")
        if os.path.exists(path):
            return FileResponse(path)
    raise HTTPException(404, "Аватар не найден")


def _hours_from_session(s: dict) -> float:
    """Часы из check-in сессии: фото-сессия = finish-start-пауза, ручная = end-start-пауза.
    10.32: раньше фото-checkin паузу не вычитал вообще (только manual_entry) — юзер
    теперь явно спрашивает pause_minutes в finish-опроснике для обоих типов сессий."""
    if s.get('manual_entry'):
        try:
            h1, m1 = map(int, s['start_time'].split(':'))
            h2, m2 = map(int, s['end_time'].split(':'))
            mins = (h2 * 60 + m2) - (h1 * 60 + m1) - int(s.get('pause_minutes') or 0)
            return max(0, mins) / 60.0
        except Exception:
            return 0.0
    if s.get('start_at') and s.get('finish_at'):
        pause_seconds = int(s.get('pause_minutes') or 0) * 60
        return max(0, (s['finish_at'] - s['start_at']) - pause_seconds) / 3600.0
    return 0.0


def _session_hours_live(s: dict) -> float:
    """Как _hours_from_session, но НЕзавершённую фото-смену (finish_at is None)
    досчитывает текущим моментом как условным концом (минус накопленная live-пауза) --
    для "часов за сегодня/неделю" на экране Команда, где идущая смена должна отражаться
    сразу, а не как 0 до финиша. Незавершённая смена считается ОДИН раз (нет второй
    записи с finish_at на тот же интервал). Зеркалит логику hours_today_total в
    get_dashboard_shifts_today. Раунд1 Задача 1.6."""
    if s.get('finish_at') is not None or s.get('manual_entry'):
        return _hours_from_session(s)
    if s.get('start_at'):
        elapsed = (time.time() - s['start_at'] - (s.get('pause_accumulated_seconds') or 0)) / 3600.0
        return max(0.0, elapsed)
    return 0.0


def _extra_works_summary_text(session: dict) -> str:
    """Сериализует structured extra_works[] в читаемый текст для Sheets/Telegram --
    оба места раньше показывали одну свободную строку (extra_work: str), теперь
    wizard пишет структурированный список, но получатели (бухгалтерия в Sheets,
    owner в Telegram) не должны видеть сырой JSON."""
    if session.get('extra_work'):
        return session['extra_work']
    works = session.get('extra_works') or []
    if not works:
        return ''
    parts = []
    for w in works:
        if not isinstance(w, dict):
            continue
        desc = str(w.get('description', '')).strip()
        if not desc:
            continue
        zone = str(w.get('zone', '')).strip()
        parts.append(f"{desc} ({zone})" if zone else desc)
    return '; '.join(parts)


def _write_zeiterfassung_row(session: dict, object_id: str, user_id: str):
    """24.07: учёт времени в Google Sheets (лист Zeiterfassung) — раньше писался
    только в checkin_meta.json на VPS, не был виден владельцу как таблица для
    бухгалтерии/отчётности заказчику. Вызывается из checkin_finish и checkin_manual,
    best-effort (не блокирует ответ пользователю при сбое записи в Sheets)."""
    try:
        o = _load_repo_objekte_lib()
        profiles = _load_worker_profiles()
        worker_name = _sanitize_display_name(profiles.get(str(user_id), {}).get('name'), str(user_id))

        rows = _cached_get_used_range('Объекты')
        object_name = object_id
        if rows:
            header, data = rows[0], rows[1:]
            for r in data:
                obj = dict(zip(header, r))
                if str(obj.get('ID объекта', '')) == str(object_id):
                    object_name = obj.get('Объект', object_id)
                    break

        if session.get('manual_entry'):
            start_time = session.get('start_time', '')
            end_time = session.get('end_time', '')
            date_str = session.get('date', '')
        else:
            start_time = datetime.fromtimestamp(session['start_at']).strftime('%H:%M') if session.get('start_at') else ''
            end_time = datetime.fromtimestamp(session['finish_at']).strftime('%H:%M') if session.get('finish_at') else ''
            date_str = datetime.fromtimestamp(session['start_at']).strftime('%Y-%m-%d') if session.get('start_at') else ''

        hours = round(_hours_from_session(session), 2)
        done_summary = session.get('done_summary') or session.get('description') or ''
        extra_work = _extra_works_summary_text(session)

        o.append_row_safe('Zeiterfassung', [
            object_name, worker_name, date_str, start_time, end_time,
            str(session.get('pause_minutes') or 0), str(hours), done_summary, extra_work,
        ])
    except Exception as e:
        print(f'WARNING: Zeiterfassung sheet write failed: {e}')


@app.get("/api/profile/stats")
def profile_stats(user_id: str = '', period: str = 'week', user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """Агрегированная статистика для экрана профиля (Фаза 8 + 21.07 period-pills).
    Часы/история вычисляются на чтении из checkin_meta + assignments — не дублируются в хранении.
    Работник видит только себя; owner может запросить любого через ?user_id=.
    period: week (7 колец, дефолт, обратная совместимость) | month (heatmap 30 дней) |
    3months | year (агрегация по неделям/месяцам — 3 разных визуальных режима, не один рендер с другим диапазоном)."""
    from datetime import timedelta
    target = user_id if (role == 'owner' and user_id) else str(user['id'])
    sessions = [s for s in _load_checkin_meta() if str(s.get('user_id')) == target]

    # 21.07: owner смотрит СВОЙ профиль (без ?user_id=) — не отмечает check-in физически,
    # личные часы всегда пусты. Вместо этого — агрегат "часы по каждому работнику за неделю".
    team_hours = None
    if role == 'owner' and not user_id:
        roles = _load_roles()
        worker_ids = [uid for uid, r in roles.items() if r == 'worker']
        profiles_map = _load_worker_profiles()
        today0 = business_today()  # 03.08 (ТЗ Задача 5): было date.today() (UTC) -- вечером Berlin это уже "завтра" UTC
        week_start = today0 - timedelta(days=6)
        team_hours = []
        for wid in worker_ids:
            w_sessions = [s for s in _load_checkin_meta() if str(s.get('user_id')) == wid
                         and week_start.isoformat() <= s.get('date', '') <= today0.isoformat()]
            hours = round(sum(_hours_from_session(s) for s in w_sessions), 1)
            team_hours.append({
                'user_id': wid,
                'name': _sanitize_display_name(profiles_map.get(wid, {}).get('name'), wid),
                'hours': hours,
            })
        team_hours.sort(key=lambda t: t['hours'], reverse=True)

    # period-агрегаты (batch 1 Kalo референс): month = heatmap по дням, 3months/year = bar по неделям/месяцам
    period_data = None
    if period == 'month':
        today0 = business_today()  # 03.08 (ТЗ Задача 5): было date.today() (UTC)
        days = []
        for i in range(29, -1, -1):
            d = today0 - timedelta(days=i)
            iso = d.isoformat()
            hours = sum(_hours_from_session(s) for s in sessions if s.get('date') == iso)
            days.append({'date': iso, 'hours': round(hours, 2)})
        period_data = {'kind': 'heatmap', 'days': days, 'total_hours': round(sum(d['hours'] for d in days), 1)}
    elif period in ('3months', 'year'):
        weeks_back = 13 if period == '3months' else 52
        today0 = business_today()  # 03.08 (ТЗ Задача 5): было date.today() (UTC)
        buckets = []
        for i in range(weeks_back - 1, -1, -1):
            week_end = today0 - timedelta(days=i * 7)
            week_start = week_end - timedelta(days=6)
            hours = sum(_hours_from_session(s) for s in sessions
                        if week_start.isoformat() <= s.get('date', '') <= week_end.isoformat())
            buckets.append({'label': week_start.isoformat(), 'hours': round(hours, 2)})
        period_data = {'kind': 'bar', 'buckets': buckets, 'total_hours': round(sum(b['hours'] for b in buckets), 1)}

    # 7 кругов дней недели: последние 7 дней, часы на день
    today = business_today()  # 03.08 (ТЗ Задача 5): было date.today() (UTC)
    week = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        iso = d.isoformat()
        hours = sum(_hours_from_session(s) for s in sessions if s.get('date') == iso)
        week.append({'date': iso, 'weekday': d.weekday(), 'hours': round(hours, 2)})

    # История объектов: check-in сессии + назначения (bubble-assign)
    by_obj = {}
    for s in sessions:
        oid = str(s.get('object_id', ''))
        rec = by_obj.setdefault(oid, {'object_id': oid, 'sessions': 0, 'total_hours': 0.0, 'last_date': '', 'assigned_stages': []})
        rec['sessions'] += 1
        rec['total_hours'] += _hours_from_session(s)
        rec['last_date'] = max(rec['last_date'], s.get('date', ''))
    for oid, lst in _load_assignments().items():
        for a in lst:
            if a.get('user_id') == target:
                rec = by_obj.setdefault(str(oid), {'object_id': str(oid), 'sessions': 0, 'total_hours': 0.0, 'last_date': '', 'assigned_stages': []})
                if a.get('stage_id'):
                    rec['assigned_stages'].append(a['stage_id'])
    objects_hist = sorted(by_obj.values(), key=lambda r: r['last_date'], reverse=True)
    for rec in objects_hist:
        rec['total_hours'] = round(rec['total_hours'], 1)
    try:
        rows = _cached_get_used_range('Объекты')
        names = {}
        if rows:
            hdr = rows[0]
            for r in rows[1:]:
                row = dict(zip(hdr, r))
                names[str(row.get('ID объекта', ''))] = row.get('Объект', '')
        for rec in objects_hist:
            rec['object_name'] = names.get(rec['object_id']) or rec['object_id']
    except Exception:
        for rec in objects_hist:
            rec['object_name'] = rec['object_id']

    # Work-speed: из AI-анализов прогресса (Фаза 4b); аккуратно опускается, если анализов не было
    finished = [s for s in sessions if not s.get('manual_entry') and s.get('finish_at')]
    avg_session_hours = round(sum(_hours_from_session(s) for s in finished) / len(finished), 2) if finished else None
    analyzed = [s for s in sessions if (s.get('analysis') or {}).get('progress')]
    work_speed = None
    if analyzed:
        last = max(analyzed, key=lambda s: s.get('finish_at') or 0)
        work_speed = {
            'analyzed_sessions': len(analyzed),
            'last_summary': (last['analysis']['progress'] or '')[:400],
        }

    # Урлауб-баланс: 24 рабочих дня в год (немецкий минимум) минус одобренные Urlaub-заявки (10.31)
    URLAUB_YEARLY_DAYS = 24
    this_year = str(today.year)
    urlaub_used = 0
    krankheit_used = 0
    for e in _load_abwesenheit():
        if str(e.get('user_id')) != target or e.get('status') != 'approved':
            continue
        if not e.get('date_from', '').startswith(this_year):
            continue
        d1 = datetime.strptime(e['date_from'], '%Y-%m-%d').date()
        d2 = datetime.strptime(e['date_to'], '%Y-%m-%d').date()
        days = (d2 - d1).days + 1
        if e.get('reason') == 'Urlaub':
            urlaub_used += days
        elif e.get('reason') == 'Krankheit':
            krankheit_used += days

    profile = _get_worker_profile(target)
    # 01.08 (доп.раунд П2): frontend (profile.js _loadProfileStats) читает stats.skills_v2
    # для уровня/verified -- backend отдавал только сырой legacy 'skills' (список
    # названий), skills_v2 отсутствовал вообще, owner никогда не видел уровень/verified
    # чужого работника на этом экране.
    stats_skills_v2 = _get_worker_skills_v2(target)
    return {
        'user_id': target,
        'name': _sanitize_display_name(
            profile.get('name') or (user.get('first_name') if target == str(user['id']) else None),
            target,
        ),
        'role': _load_roles().get(target, 'worker'),
        'skills': pskills.legacy_skill_names_from_v2(stats_skills_v2),
        'skills_v2': stats_skills_v2,
        'sizes': {
            'pants': profile.get('pants_size', ''),
            'shirt': profile.get('shirt_size', ''),
            'shoe': profile.get('shoe_size', ''),
        },
        'has_avatar': bool(profile.get('avatar')),
        # Раунд 6 §3.3: полную дату рождения видит только Owner или сам работник —
        # этот endpoint и так отдаёт чужой профиль исключительно owner'у (target-гейт выше).
        'birthday': profile.get('birthday'),
        'urlaub': {'used': urlaub_used, 'total': URLAUB_YEARLY_DAYS, 'remaining': max(0, URLAUB_YEARLY_DAYS - urlaub_used)},
        'krankheit_days_this_year': krankheit_used,
        'week': week,
        'week_total_hours': round(sum(d['hours'] for d in week), 1),
        'period': period,
        'period_data': period_data,
        'team_hours': team_hours,
        'avg_session_hours': avg_session_hours,
        'work_speed': work_speed,
        'objects': objects_hist,
    }


@app.get("/api/dashboard/team-hours")
def get_dashboard_team_hours(date_from: str = '', date_to: str = '',
                             user: dict = Depends(get_current_user),
                             _: None = Depends(require_owner)):
    """Раунд1 Задача 1.6: часы ВСЕЙ команды за неделю для экрана Команда → Сводка.
    owner-only (Worker -> 403, та же чувствительность что shifts-today -- агрегирует
    личные часы всех работников). Период по умолчанию -- текущая календарная неделя
    Пн-Вс Europe/Berlin; date_from/date_to опциональны (прошлая неделя).

    profile_stats.team_hours отдаёт только {user_id,name,hours} без today/is_working_now/
    current_object -- недостаточно для этого блока, поэтому отдельный endpoint. Часы:
    завершённые смены -- finish-start-pause; идущая смена -- elapsed до текущего момента
    (считается один раз, не дублируется); manual -- end-start-pause."""
    from datetime import timedelta, date as _date

    def _parse(s):
        try:
            return _date.fromisoformat(s)
        except Exception:
            return None

    today = business_today()
    d_from, d_to = _parse(date_from), _parse(date_to)
    if not (d_from and d_to):
        d_from = today - timedelta(days=today.weekday())   # понедельник этой недели
        d_to = d_from + timedelta(days=6)                  # воскресенье
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    if (d_to - d_from).days > 62:                          # разумный предел окна
        d_to = d_from + timedelta(days=62)
    from_iso, to_iso, today_iso = d_from.isoformat(), d_to.isoformat(), today.isoformat()
    today_in_range = from_iso <= today_iso <= to_iso

    roles = _load_roles()
    worker_ids = [uid for uid, r in roles.items() if r == 'worker']
    profiles_map = _load_worker_profiles()
    all_sessions = _load_checkin_meta()

    object_names = {}
    try:
        rows = _cached_get_used_range('Объекты')
        if rows:
            hdr = rows[0]
            for r in rows[1:]:
                row = dict(zip(hdr, r))
                object_names[str(row.get('ID объекта', ''))] = row.get('Объект', '')
    except Exception:
        object_names = {}

    def _safe_team_name(wid):
        # _sanitize_display_name fallback -- сам wid (числовой Telegram ID); ТЗ 1.2 явно
        # запрещает показывать ID вместо имени -> fallback "Сотрудник", плюс страховка
        # если сохранённое имя само оказалось чисто числовым.
        nm = _sanitize_display_name(profiles_map.get(wid, {}).get('name'), 'Сотрудник')
        return 'Сотрудник' if (nm.strip() == str(wid) or nm.strip().isdigit()) else nm

    workers = []
    for wid in worker_ids:
        w_sessions = [s for s in all_sessions if str(s.get('user_id')) == wid]
        in_range = [s for s in w_sessions if from_iso <= s.get('date', '') <= to_iso]
        hours_week = round(sum(_session_hours_live(s) for s in in_range), 1)
        today_sess = [s for s in w_sessions if s.get('date', '') == today_iso] if today_in_range else []
        hours_today = round(sum(_session_hours_live(s) for s in today_sess), 1)
        open_s = next((s for s in today_sess
                       if s.get('finish_at') is None and not s.get('manual_entry')), None)
        is_working_now = open_s is not None
        cur_oid = str(open_s.get('object_id', '')) if open_s else ''
        workers.append({
            'user_id': wid,
            'name': _safe_team_name(wid),
            'has_avatar': bool(profiles_map.get(wid, {}).get('avatar')),
            'hours_today': hours_today,
            'hours_week': hours_week,
            'is_working_now': is_working_now,
            'current_object_id': cur_oid,
            'current_object_name': (object_names.get(cur_oid, cur_oid) if cur_oid else ''),
        })
    # сортировка (ТЗ 1.2): 1) кто сейчас работает, 2) часы недели убыв., 3) с 0 часами в конце
    workers.sort(key=lambda w: (not w['is_working_now'], -w['hours_week'], w['name'].lower()))
    return {
        'date_from': from_iso,
        'date_to': to_iso,
        'total_hours': round(sum(w['hours_week'] for w in workers), 1),
        'today_hours': round(sum(w['hours_today'] for w in workers), 1),
        'workers_with_hours': sum(1 for w in workers if w['hours_week'] > 0),
        'workers': workers,
    }


# ---------- Назначения работников на объекты (Фаза 2c, восстановлено после инцидента Фазы 3) ----------
# moved to core/paths.py -- OBJECT_ASSIGNMENTS_FILE
# moved to core/paths.py -- OBJECT_IMAGES_FILE
# moved to core/paths.py -- OBJECT_PHOTO_DIR


def _load_assignments() -> dict:
    return _safe_load_json(OBJECT_ASSIGNMENTS_FILE, {})


def _save_assignments(assignments: dict):
    _atomic_write_json(OBJECT_ASSIGNMENTS_FILE, assignments)


def _load_object_images() -> dict:
    return _safe_load_json(OBJECT_IMAGES_FILE, {})


def _save_object_images(images: dict):
    _atomic_write_json(OBJECT_IMAGES_FILE, images)


# moved to core/limits.py -- OBJECT_PHOTO_MAX


@app.post("/api/objects/{object_id}/image")
async def upload_object_image(object_id: str, file: UploadFile = File(...),
                               user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    # 28.07 v2: расширено до массива фото (carousel в карточке объекта, PHASE F спека) --
    # раньше был единственный fname (перезаписывался при повторной загрузке). Только owner.
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Фото слишком большое (макс. 8 МБ)")
    detected = sniff_image(raw)
    if not detected:
        raise HTTPException(400, "Файл должен быть изображением")
    ext = _ALLOWED_IMAGE_MIME_EXT[detected]
    os.makedirs(OBJECT_PHOTO_DIR, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(OBJECT_PHOTO_DIR, fname)
    with open(fpath, 'wb') as f_out:
        f_out.write(raw)

    # 28.07 v3 (real bug found by external audit): было _load_object_images() +
    # _save_object_images() как два отдельных вызова -- read происходил СНАРУЖИ лока,
    # два параллельных upload на один object_id могли оба прочитать одинаковый
    # existing-список и один затирал фото, добавленное другим. update_json_transaction
    # держит read+mutate+write под одним захватом _lock_for(path).
    def _mutator(images):
        existing = images.get(object_id) or []
        if len(existing) >= OBJECT_PHOTO_MAX:
            raise HTTPException(400, f"Максимум {OBJECT_PHOTO_MAX} фото на объект")
        images[object_id] = existing + [fname]
        return images[object_id]

    try:
        photos = update_json_transaction(OBJECT_IMAGES_FILE, {}, _mutator)
    except HTTPException:
        # 28.07: metadata-транзакция не прошла (лимит фото достигнут) -- не оставляем
        # orphan-файл на диске без записи в metadata (ТЗ п.24: "не оставлять файл на
        # диске при неуспешной транзакции").
        if os.path.exists(fpath):
            os.remove(fpath)
        raise
    return {"status": "ok", "photos": photos}


@app.delete("/api/objects/{object_id}/image/{fname}")
def delete_object_image(object_id: str, fname: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    safe_name = os.path.basename(fname)

    def _mutator(images):
        existing = images.get(object_id) or []
        if safe_name not in existing:
            raise HTTPException(404, "Фото не найдено")
        images[object_id] = [f for f in existing if f != safe_name]
        return images[object_id]

    photos = update_json_transaction(OBJECT_IMAGES_FILE, {}, _mutator)
    path = os.path.join(OBJECT_PHOTO_DIR, safe_name)
    if os.path.exists(path):
        os.remove(path)
    return {"status": "ok", "photos": photos}


@app.get("/api/objects/{object_id}/image/file")
def get_object_image_file(object_id: str, index: int = 0, user: dict = Depends(get_current_user)):
    # 30.07 (Release-аудит P1-5): нет require_object_access -- согласовано с
    # GET /api/objects (весь список объектов виден любому авторизованному, см.
    # тот же паттерн у /stages, /roadmap notes GET). Upload/delete фото остаются
    # owner-only. Не меняем это в рамках feature freeze -- задокументировано как
    # by-design consistency с остальным просмотром объектов, не отдельная дыра.
    images = _load_object_images()
    photos = images.get(object_id) or []
    if not photos or index < 0 or index >= len(photos):
        raise HTTPException(404, "Фото не загружено")
    path = os.path.join(OBJECT_PHOTO_DIR, photos[index])
    if not os.path.exists(path):
        raise HTTPException(404, "Файл отсутствует")
    return FileResponse(path)


_sheets_cache: dict = {}
# moved to core/limits.py -- SHEETS_CACHE_TTL
                        # на каждый запрос, блокируя event loop на время RTT (10.29, Fable-аудит)


def _cached_get_used_range(tab_name: str):
    now = time.time()
    cached = _sheets_cache.get(tab_name)
    if cached and now - cached[0] < SHEETS_CACHE_TTL:
        return cached[1]
    o = _load_repo_objekte_lib()
    rows = o.get_used_range(tab_name)
    _sheets_cache[tab_name] = (now, rows)
    return rows


# All known column names for the budget-percent field (live Sheet uses 'потрачено в % от бюджета';
# objekte_lib historically wrote '% бюджета'; alerts route also fell back to 'Потрачено %').
# Strip ALL aliases from worker DTOs so a column rename cannot accidentally re-expose the field.
# moved to core/constants.py -- BUDGET_FIELDS


@app.get("/api/objects")
def list_objects(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    rows = _cached_get_used_range('Объекты')
    if not rows:
        return {"objects": []}
    header, data = rows[0], rows[1:]
    assignments = _load_assignments()
    profiles = _load_worker_profiles()
    images = _load_object_images()
    # 28.07 (external audit ТЗ п.20): batch stage summary -- один вызов all_stages_grouped()
    # для ВСЕХ объектов разом, не N+1 запросов к Google Sheets (один на каждую карточку).
    o = _load_repo_objekte_lib()
    stages_by_object = o.all_stages_grouped()

    def _user_info(uid: str, assignment: dict | None = None) -> dict:
        p = profiles.get(str(uid), {})
        # 28.07 (external audit ТЗ п.21): реальная аватарка вместо только инициалов,
        # если работник её загрузил (has_avatar уже трекается профилем, /api/profile
        # avatar endpoint уже существует -- переиспользуем, не строим параллельный).
        info = {
            "user_id": str(uid),
            "name": _sanitize_display_name(p.get('name'), str(uid)),
            "has_avatar": bool(p.get('avatar')),
        }
        if assignment is not None:
            # 29.07 ТЗ п.9: owner видит, принял ли worker назначение -- без этого
            # владелец не узнаёт об отказе иначе как случайно спросив у worker'а лично.
            info["assignment_status"] = _assignment_status(assignment)
            info["decline_reason"] = assignment.get('decline_reason', '')
            info["task_note"] = assignment.get('task_note', '')
            # 01.08 (Команда и смены переработка): assignment_id/даты/вид работ нужны
            # для ⋯ меню (изменить/удалить конкретное назначение) в object-info.js.
            info["assignment_id"] = assignment.get('id', '')
            info["date_from"] = assignment.get('date_from', '')
            info["date_to"] = assignment.get('date_to', '')
            work_type_id = assignment.get('work_type_id', '')
            info["work_type_id"] = work_type_id
            info["work_type_name"] = pskills.skill_display_name(work_type_id) if work_type_id else ''
            info["stage_id"] = assignment.get('stage_id', '')
        return info

    def _stage_summary(oid: str) -> dict | None:
        stages = stages_by_object.get(oid.upper())
        if not stages:
            return None
        completed = [s.get('Название этапа', '') for s in stages if s.get('Статус') == 'готово']
        current = next((s for s in stages if s.get('Статус') == 'в процессе'), None)
        current_idx = stages.index(current) if current else -1
        if current:
            next_stage = stages[current_idx + 1] if current_idx + 1 < len(stages) else None
        else:
            # Раунд 4: ни один этап не в работе -> "next" = первый незавершённый (для состояния
            # "Ничего не начато: Следующий: Демонтаж"). Если все готово -> next=None.
            next_stage = next((s for s in stages if s.get('Статус') != 'готово'), None)
        return {
            "completed": completed,
            "completed_count": len(completed),
            "current": current.get('Название этапа', '') if current else None,
            "next": next_stage.get('Название этапа', '') if next_stage else None,
            "total": len(stages),
        }

    objects = []
    for r in data:
        obj = dict(zip(header, r))
        oid = str(obj.get('ID объекта', ''))
        obj_assignments = assignments.get(oid, [])
        if role == 'owner':
            # 09.09: dedupe by user_id -- this list feeds the object CARD's avatar
            # stack (a "who's on the team" summary, one dot per person), not the
            # per-assignment detail view. Before this fix it mapped every raw
            # assignment record 1:1 -- harmless while one worker had at most one
            # assignment per object, but the multi-work-type feature (961a3b9, same
            # session) made one worker having 2+ assignment records on the SAME
            # object (one per selected work type) a normal, common case. Owner
            # confirmed live: the same worker's avatar appeared multiple times on
            # one object's card. First assignment record per user_id wins (order
            # from obj_assignments, i.e. creation order) -- the per-work-type detail
            # is still fully available via /api/objects/{id}/info-items's team
            # section, which correctly shows one row per assignment.
            #
            # Also filters to assignments relevant TODAY, not every historical/
            # future/declined record ever created for this object -- the card
            # visually implies "this is the current team," and before this fix it
            # showed declined/past/future assignments as if they were active right
            # now. status != declined, and (date_from <= today <= date_to) OR the
            # assignment is legacy/undated (no dates recorded at all -- treated as
            # indefinite/always-current everywhere else in this codebase, e.g.
            # _assignment_periods_overlap() above and _assignment_status()).
            today_str = business_today_str()
            seen_uids = set()
            deduped_users = []
            detail_users = []
            for a in obj_assignments:
                if _assignment_status(a) == 'declined':
                    continue
                a_from, a_to = a.get('date_from', ''), a.get('date_to', '')
                is_dated = bool(a_from and a_to)
                if is_dated and not (a_from <= today_str <= a_to):
                    continue
                uid = str(a['user_id'])
                # assigned_users_detail: ONE ENTRY PER ASSIGNMENT (still filtered to
                # active-today/non-declined above) -- Object Info's "Команда и смены"
                # needs to show every work type a worker has on this object, grouped
                # under that worker, not collapsed to one row. Kept separate from
                # assigned_users below (which IS deduped, for the card avatar stack
                # and any consumer that just wants "who's on this team" as a set).
                detail_users.append(_user_info(uid, a))
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
                deduped_users.append(_user_info(uid, a))
            obj['assigned_users'] = deduped_users
            obj['assigned_users_detail'] = detail_users
            obj['photo_count'] = len(images.get(oid) or [])
            obj['stage_summary'] = _stage_summary(oid)
        else:
            obj = _serialize_object_for_worker(obj, str(user['id']), obj_assignments, _user_info, _stage_summary, images)
        objects.append(obj)
    return {"objects": objects}


def _serialize_object_for_worker(obj: dict, viewer_user_id: str, obj_assignments: list,
                                  user_info_fn, stage_summary_fn, images: dict) -> dict:
    """03.08 (ТЗ Задача 3): единая точка, ГДЕ worker теряет доступ к чужим assignment-
    метаданным -- раньше list_objects просто снимал BUDGET_FIELDS и отдавал ВСЁ
    остальное как есть, включая assignment_id/task_note/decline_reason/date_from/
    date_to/work_type/pending-declined статус КАЖДОГО работника на объекте (реальная
    находка: worker A мог прочитать, что worker B отказался от смены и почему).

    Worker получает:
      - object_id/название/адрес/общий статус/этапы/фото -- как раньше (уже public)
      - assigned_users: ПУБЛИЧНЫЙ список команды (user_id/name/has_avatar), без
        assignment-полей коллег вообще
      - my_assignments: ПОЛНЫЕ собственные назначения (включая future/pending/declined --
        нужно, чтобы принять/отклонить), той же формы, что owner видит для всех.

    oid берётся из obj САМ (та же 'ID объекта' колонка, что уже читает list_objects) --
    не передаётся отдельным параметром, чтобы не рассинхронизировать с images/stage_summary
    lookup, которые тоже keyed по этому oid."""
    oid = str(obj.get('ID объекта', ''))
    public_team = []
    my_assignments = []
    for a in obj_assignments:
        uid = str(a.get('user_id'))
        if uid == viewer_user_id:
            my_assignments.append(user_info_fn(uid, a))
        # Публичный список команды -- только user_id/name/has_avatar, без единого
        # assignment-поля (см. docstring выше). user_info_fn(uid) без assignment
        # аргумента уже возвращает ровно этот узкий набор (см. _user_info в list_objects).
        if not any(t.get('user_id') == uid for t in public_team):
            public_team.append(user_info_fn(uid))

    obj = dict(obj)
    obj['assigned_users'] = public_team
    obj['my_assignments'] = my_assignments
    obj['photo_count'] = len(images.get(oid) or [])
    obj['stage_summary'] = stage_summary_fn(oid)
    for f in BUDGET_FIELDS:
        # 10.5: бюджет — финансовая информация, работнику видеть не должен (сохранено
        # как было до этого рефакторинга).
        obj.pop(f, None)
    return obj


@app.get("/api/my-assignments")
def my_assignments(user: dict = Depends(get_current_user)):
    """Список назначений текущего воркера — объект/этап/период, для экрана
    "Мои задачи" (24.07: раньше верхняя dashboard-плитка "Задачи" ошибочно
    вела на общий список Объекты, юзер запросил отдельный экран)."""
    assignments = _load_assignments()
    uid = str(user['id'])
    rows = _cached_get_used_range('Объекты')
    names = {}
    if rows:
        header, data = rows[0], rows[1:]
        for r in data:
            obj = dict(zip(header, r))
            oid_key = str(obj.get('ID объекта', ''))
            # 03.08 (ТЗ Задача 6a, реальный найденный баг): читалось obj.get('Название')
            # -- эта колонка не существует в Google Sheets 'Объекты' (реальная колонка
            # называется 'Объект', см. list_objects/везде остальном в этом файле), так
            # что имя объекта в "Моих назначениях" всегда падало на obj.get('Адрес')
            # или пустую строку. Полная fallback-цепочка: Объект -> Название (на
            # случай, если колонку когда-то переименуют/добавят) -> Адрес -> сам id.
            names[oid_key] = obj.get('Объект') or obj.get('Название') or obj.get('Адрес') or oid_key

    result = []
    for oid, lst in assignments.items():
        for a in lst:
            if a.get('user_id') != uid:
                continue
            work_type_id = a.get('work_type_id', '')
            result.append({
                "id": a.get('id', ''),  # 29.07 (аудит): фронт передаёт это в /respond
                "object_id": oid,
                "object_name": names.get(oid, oid),
                "stage_id": a.get('stage_id', ''),
                "work_type_id": work_type_id,
                "work_type_name": pskills.skill_display_name(work_type_id) if work_type_id else '',
                "date_from": a.get('date_from', ''),
                "date_to": a.get('date_to', ''),
                "assigned_at": a.get('assigned_at', ''),
                "status": _assignment_status(a),
                "decline_reason": a.get('decline_reason', ''),
                "task_note": a.get('task_note', ''),
            })
    result.sort(key=lambda r: r['date_from'] or '', reverse=True)
    return {"assignments": result}


class AssignBody(BaseModel):
    user_id: str
    stage_id: str = ''
    work_type_id: str = ''  # 01.08: новый источник истины matching'а; stage_id остаётся
    # для legacy-совместимости (текстовое отображение старых этапов, см. work_types.py).
    date_from: str = ''
    date_to: str = ''
    task_note: str = ''


def _dates_overlap(a_from: str, a_to: str, b_from: str, b_to: str) -> bool:
    if not (a_from and a_to and b_from and b_to):
        return False
    return a_from <= b_to and b_from <= a_to


def _assignment_periods_overlap(a: dict, b: dict) -> bool:
    """09.09 (P0 assignment integrity fix): _dates_overlap() above returns False
    whenever EITHER period is missing a date -- correct for its other callers
    (absence checks, plain date-range comparisons where an empty range simply
    means "no data"), but WRONG for cross-object assignment conflict checks:
    a legacy assignment created before date_from/date_to existed as fields has
    both empty, and every other part of this system (Worker Home, shift display,
    _assignment_status()) already treats an undated assignment as open-ended/
    indefinite, not as "no period at all". Using plain _dates_overlap() here let
    a worker with an old undated assignment on object A get a NEW, perfectly
    valid dated assignment on object B with zero conflict detected -- the
    exact hole owner's live data exposed (worker legitimately assigned OBJ-001
    9/11 + OBJ-003 9/12, no real overlap there, but the underlying dedup-only
    fix wouldn't have caught a REAL overlap involving an undated legacy record
    either). This helper: a period missing either date is treated as
    overlapping with everything (indefinite), matching how the rest of the
    system already reads that shape."""
    a_from, a_to = a.get('date_from', ''), a.get('date_to', '')
    b_from, b_to = b.get('date_from', ''), b.get('date_to', '')
    if not (a_from and a_to) or not (b_from and b_to):
        return True  # legacy/undated period -- indefinite, always a potential conflict
    return a_from <= b_to and b_from <= a_to


@app.post("/api/objects/{object_id}/assign")
def assign_user(object_id: str, body: AssignBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    key = str(object_id)

    # 28.07 (real bug found by external audit): было _load_assignments()+_save_assignments()
    # как отдельные вызовы -- read вне лока, два параллельных assign на один объект могли
    # оба увидеть список ДО добавления и один запрос затирал назначение, добавленное другим
    # (та же гонка что чинили для object photos). update_json_transaction держит все проверки
    # + мутацию под одним захватом _lock_for(path).
    def _mutator(assignments):
        if key not in assignments:
            assignments[key] = []
        # 29.07 (аудит): declined-назначение НЕ должно считаться дубликатом -- иначе
        # повторное назначение того же worker'а на тот же этап после отказа молча
        # не создавало новую запись (endpoint возвращал успех, но ничего не менялось).
        already = any(
            a['user_id'] == str(body.user_id) and a.get('stage_id', '') == body.stage_id
            and _assignment_status(a) != 'declined'
            for a in assignments[key]
        )
        if already:
            raise HTTPException(409, "Это назначение уже существует")
        # 22.07: одобренный отпуск/больничный блокирует назначение — жёсткая проверка,
        # не просто цветовая подсказка в календаре (юзер подтвердил явно).
        for e in _load_abwesenheit():
            if str(e.get('user_id')) != str(body.user_id) or e.get('status') != 'approved':
                continue
            if _dates_overlap(body.date_from, body.date_to, e.get('date_from', ''), e.get('date_to', '')):
                raise HTTPException(
                    409,
                    f"Работник недоступен ({e.get('reason', 'отсутствие')}) "
                    f"{e.get('date_from')} — {e.get('date_to')}"
                )
        # 29.07 (аудит): declined-назначения на ДРУГИХ объектах не должны участвовать
        # в проверке пересечений периодов -- worker, отклонивший объект А, не должен
        # быть заблокирован от назначения на объект Б в те же даты.
        for other_oid, other_list in assignments.items():
            if other_oid == key:
                continue
            for a in other_list:
                if a['user_id'] != str(body.user_id) or _assignment_status(a) == 'declined':
                    continue
                # 09.09: _assignment_periods_overlap() -- не голый _dates_overlap(),
                # который возвращал False (т.е. "не пересекается") для legacy-записей
                # без date_from/date_to, пропуская их через эту проверку. См. helper's
                # docstring для полного контекста.
                if _assignment_periods_overlap(
                    {'date_from': body.date_from, 'date_to': body.date_to}, a
                ):
                    raise HTTPException(
                        409,
                        f"Этот работник уже назначен на объект {other_oid} "
                        f"на период {a.get('date_from') or '(без даты)'} — {a.get('date_to') or '(без даты)'}"
                    )
        assignments[key].append({
            # 29.07 (аудит): уникальный assignment_id -- respond-endpoint раньше искал
            # "первый pending этого worker'а на объект", что ломалось при нескольких
            # назначениях одного worker'а на разные этапы/периоды одного объекта.
            'id': uuid.uuid4().hex,
            'user_id': str(body.user_id),
            'stage_id': body.stage_id,
            'work_type_id': body.work_type_id,
            'date_from': body.date_from,
            'date_to': body.date_to,
            'assigned_at': datetime.utcnow().isoformat(),
            # 29.07 ТЗ п.9: назначение теперь требует подтверждения worker'а -- новые
            # назначения стартуют pending, worker явно принимает/отклоняет. Старые записи
            # без этого поля (созданные до этой правки) трактуются как 'accepted' везде,
            # где статус читается (см. _assignment_status() ниже) -- compatibility rule,
            # не полная миграция файла, чтобы не трогать данные, которые и так работали.
            'status': 'pending',
            'decline_reason': '',
            'responded_at': '',
            'task_note': body.task_note.strip()[:500],
        })

    update_json_transaction(OBJECT_ASSIGNMENTS_FILE, {}, _mutator)
    return {"status": "ok"}


@app.delete("/api/objects/{object_id}/assign/{user_id}")
def unassign_user(object_id: str, user_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """01.08 (доп.раунд П4, реальный найденный баг): предыдущая версия фильтровала
    "активные" назначения по ВСЕМ user_id на объекте, не по переданному user_id --
    DELETE для одного работника мог 409-ить из-за ЧУЖИХ активных назначений на том
    же объекте, а при единственном активном (не именно этого работника, а вообще)
    строка `assignments[key] = [declined only]` СТИРАЛА ВСЕ назначения других
    работников, оставляя только declined-записи. Теперь: фильтр строго по
    str(user_id), не трогает записи других людей вообще.
    Правила: нет активного назначения этого работника -> 404; ровно одно активное ->
    удалить только его; несколько активных -> 409 с просьбой использовать
    assignment_id; declined-записи (этого и других работников) не трогаются."""
    key = str(object_id)
    uid = str(user_id)
    result_holder = {}

    def _mutator(assignments):
        lst = assignments.get(key, [])
        active_indices = [i for i, a in enumerate(lst)
                           if str(a.get('user_id')) == uid and _assignment_status(a) != 'declined']
        if not active_indices:
            result_holder['not_found'] = True
            return
        if len(active_indices) > 1:
            result_holder['multiple'] = True
            return
        # 03.08 (реальный найденный баг): раньше искали по assignment['id'], у legacy
        # записей (созданных до введения id) это None -- фильтр `a.get('id') != None`
        # удалял ВСЕ записи с реальным id (включая других работников) и оставлял
        # только другие безымянные legacy-записи. Теперь удаляем по позиции в списке --
        # работает одинаково для записей с id и без, не зависит от его наличия.
        target_index = active_indices[0]
        assignments[key] = [a for i, a in enumerate(lst) if i != target_index]

    update_json_transaction(OBJECT_ASSIGNMENTS_FILE, {}, _mutator)
    if result_holder.get('not_found'):
        raise HTTPException(404, "Активное назначение этого работника не найдено")
    if result_holder.get('multiple'):
        raise HTTPException(409, "У работника несколько назначений. Используйте assignment_id.")
    return {"status": "ok"}


class AssignmentUpdateBody(BaseModel):
    work_type_id: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    task_note: str | None = None


@app.patch("/api/objects/{object_id}/assignments/{assignment_id}")
def update_assignment(object_id: str, assignment_id: str, body: AssignmentUpdateBody,
                       user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """01.08 (спека п.9): точечное редактирование ОДНОГО назначения по assignment_id.
    При РЕАЛЬНОМ изменении уже принятого назначения (работа/период/задача) статус
    возвращается в pending -- worker должен подтвердить обновлённые условия заново.

    01.08 (доп.раунд П6): раньше не проверялось вообще ничего -- work_type
    существование/active, валидность дат, роль worker, объект, абсенс, пересечения
    (исключая само это назначение). И no-op PATCH (пустой updates.dict но всё равно
    truthy `{}` -- нет, нюанс в том что даже совпадающие значения считались
    "изменением" и сбрасывали accepted -- сравниваем итоговое значение с уже
    сохранённым, не просто "ключ присутствовал в body")."""
    key = str(object_id)
    updates = body.dict(exclude_unset=True)
    if 'task_note' in updates and updates['task_note'] is not None:
        updates['task_note'] = updates['task_note'].strip()[:500]

    if 'work_type_id' in updates and updates['work_type_id'] is not None:
        wtype = wt.get_work_type(updates['work_type_id'])
        if wtype is None or not wtype.get('active'):
            raise HTTPException(400, "Неизвестный или неактивный вид работ")
    if 'date_from' in updates and updates['date_from'] is not None:
        _validate_date_str(updates['date_from'], 'date_from')
    if 'date_to' in updates and updates['date_to'] is not None:
        _validate_date_str(updates['date_to'], 'date_to')

    key = str(object_id)
    result_holder = {}

    def _mutator(assignments):
        lst = assignments.get(key, [])
        target = next((a for a in lst if a.get('id') == assignment_id), None)
        if target is None:
            result_holder['not_found'] = True
            return

        merged_work_type = updates.get('work_type_id', target.get('work_type_id'))
        merged_date_from = updates.get('date_from', target.get('date_from', ''))
        merged_date_to = updates.get('date_to', target.get('date_to', ''))
        if merged_date_from and merged_date_to and merged_date_from > merged_date_to:
            result_holder['error'] = "date_from не может быть позже date_to"
            return

        uid = str(target.get('user_id'))
        role = _load_roles().get(uid)
        if role != 'worker':
            result_holder['error'] = f"Пользователь {uid} не является Worker (роль: {role})"
            return

        rows = _cached_get_used_range('Объекты')
        object_row = None
        if rows:
            header, data = rows[0], rows[1:]
            for r in data:
                row = dict(zip(header, r))
                if str(row.get('ID объекта', '')) == str(object_id):
                    object_row = row
                    break
        if object_row is None:
            result_holder['error'] = "Объект не найден"
            return

        abwesenheit = _load_abwesenheit()
        if any(str(e.get('user_id')) == uid and e.get('status') == 'approved'
               and _dates_overlap(merged_date_from, merged_date_to, e.get('date_from', ''), e.get('date_to', ''))
               for e in abwesenheit):
            result_holder['error'] = "Работник недоступен (отсутствие) на этот период"
            return

        # пересечения с ДРУГИМИ назначениями этого же работника, исключая само target
        overlap = False
        for other_oid, other_list in assignments.items():
            for a in other_list:
                if a.get('id') == assignment_id:
                    continue  # исключаем текущее назначение из проверки на самого себя
                if str(a.get('user_id')) != uid or _assignment_status(a) == 'declined':
                    continue
                # 09.09: same-object пересечение с другим work_type_id этого же
                # работника разрешено (multi-work-type -- один человек, несколько
                # видов работ на одном объекте в те же даты, см. 961a3b9) -- не
                # конфликт, только межобъектное пересечение реально означает "работник
                # физически не может быть в двух местах одновременно".
                if other_oid == key:
                    continue
                # _assignment_periods_overlap(), не голый _dates_overlap() -- legacy
                # запись без date_from/date_to трактуется как бессрочная/занятая, не
                # молча пропускается через проверку (см. helper's docstring).
                if _assignment_periods_overlap(
                    {'date_from': merged_date_from, 'date_to': merged_date_to}, a
                ):
                    overlap = True
                    break
            if overlap:
                break
        if overlap:
            result_holder['error'] = "Пересекается с другим назначением этого работника на другом объекте"
            return

        result_holder['ok'] = True
        was_accepted = _assignment_status(target) == 'accepted'
        # 01.08 (доп.раунд П6, реальный найденный баг): "реальное изменение" -- сравниваем
        # ИТОГОВОЕ значение каждого затронутого поля с уже сохранённым, не просто факт
        # присутствия ключа в updates. PATCH с тем же work_type_id/датами/note, что уже
        # сохранены, не должен сбрасывать accepted -> pending.
        significant_change = (
            merged_work_type != target.get('work_type_id') or
            merged_date_from != target.get('date_from', '') or
            merged_date_to != target.get('date_to', '') or
            ('task_note' in updates and updates['task_note'] != target.get('task_note', ''))
        )
        target.update({k: v for k, v in updates.items() if v is not None})
        if was_accepted and significant_change:
            target['status'] = 'pending'
            target['decline_reason'] = ''
            target['responded_at'] = ''
        target['updated_at'] = datetime.utcnow().isoformat()

    update_json_transaction(OBJECT_ASSIGNMENTS_FILE, {}, _mutator)
    if result_holder.get('not_found'):
        raise HTTPException(404, "Назначение не найдено")
    if result_holder.get('error'):
        raise HTTPException(409 if 'Пересекается' in result_holder['error'] or 'недоступен' in result_holder['error'] else 400, result_holder['error'])
    return {"status": "ok"}


@app.delete("/api/objects/{object_id}/assignments/{assignment_id}")
def delete_assignment(object_id: str, assignment_id: str,
                       user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """01.08 (спека п.9): удаляет РОВНО одно назначение по assignment_id -- в отличие
    от старого DELETE .../assign/{user_id} (см. выше), который теперь тоже защищён,
    но этот endpoint -- предпочтительный путь для frontend, без неоднозначности вообще."""
    key = str(object_id)
    found = {}

    def _mutator(assignments):
        lst = assignments.get(key, [])
        if not any(a.get('id') == assignment_id for a in lst):
            return
        found['ok'] = True
        assignments[key] = [a for a in lst if a.get('id') != assignment_id]

    update_json_transaction(OBJECT_ASSIGNMENTS_FILE, {}, _mutator)
    if not found.get('ok'):
        raise HTTPException(404, "Назначение не найдено")
    return {"status": "ok"}


def _assignment_status(a: dict) -> str:
    """Compatibility rule (ТЗ п.9): назначения, созданные до введения поля status,
    трактуются как уже принятые -- иначе Worker Home у всех существующих объектов
    внезапно показал бы "ожидает подтверждения" для того, что реально уже идёт."""
    return a.get('status') or 'accepted'


class AssignmentRespondBody(BaseModel):
    accept: bool
    decline_reason: str = ''
    # 29.07 (аудит): assignment_id -- убирает неоднозначность "первый pending" при
    # нескольких назначениях одного worker'а на разные этапы/периоды одного объекта.
    # Опционально (не required=True): легаси-записи, созданные ДО этого фикса, не
    # имеют поля 'id' вообще -- для них остаётся старый fallback ниже.
    assignment_id: str = ''


@app.post("/api/objects/{object_id}/assign/{user_id}/respond")
def respond_to_assignment(object_id: str, user_id: str, body: AssignmentRespondBody,
                           user: dict = Depends(get_current_user)):
    # Worker подтверждает СВОЁ собственное назначение -- не owner, не чужое user_id.
    if str(user['id']) != str(user_id):
        raise HTTPException(403, "Можно отвечать только на собственное назначение")
    if not body.accept and not body.decline_reason.strip():
        raise HTTPException(400, "Укажите причину отказа")
    key = str(object_id)

    def _mutator(assignments):
        lst = assignments.get(key, [])
        if body.assignment_id:
            target = next((a for a in lst if a.get('id') == body.assignment_id
                           and a['user_id'] == str(user_id) and _assignment_status(a) == 'pending'), None)
        else:
            # Легаси-путь для записей без 'id' -- тот же риск неоднозначности, что и раньше,
            # но такие записи существуют только до этого фикса и естественно вымрут.
            target = next((a for a in lst if a['user_id'] == str(user_id) and _assignment_status(a) == 'pending'), None)
        if not target:
            raise HTTPException(404, "Ожидающее назначение не найдено")
        target['status'] = 'accepted' if body.accept else 'declined'
        target['decline_reason'] = body.decline_reason.strip()[:500] if not body.accept else ''
        target['responded_at'] = datetime.utcnow().isoformat()
        return target

    return update_json_transaction(OBJECT_ASSIGNMENTS_FILE, {}, _mutator)


@app.get("/api/assignment-candidates")
def get_assignment_candidates(object_id: str, work_type_id: str, date_from: str, date_to: str,
                               user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """01.08 (спека п.7): кандидаты для Assignment Sheet -- recommended (точное
    совпадение навыка) / available (навык не указан, но доступен) / unavailable
    (пересечение/абсенс/занят сегодня). Не N+1 -- все файлы читаются ОДИН раз,
    матчинг чисто в памяти (assignment_matching.build_candidates)."""
    if not _sanitize_display_name(work_type_id, ''):
        raise HTTPException(400, "work_type_id обязателен")
    _validate_date_str(date_from, 'date_from')
    _validate_date_str(date_to, 'date_to')

    roles = _load_roles()
    profiles = _load_worker_profiles()
    # 01.08 (доп.раунд П6, реальный найденный баг): второй set-comprehension делал
    # `roles.get(uid, 'worker')` -- ДЕФОЛТ 'worker' для любого uid, которого нет в
    # roles вообще, а не только для явно назначенных worker. Профиль в
    # worker_profiles.json без активной whitelist-записи (уволенный/удалённый из
    # roles) всё равно попадал в кандидаты. Теперь строго: только roles[uid]=='worker'.
    worker_ids = {uid for uid, r in roles.items() if r == 'worker'}

    workers = []
    for uid in worker_ids:
        profile = profiles.get(uid, {})
        name = _sanitize_display_name(profile.get('name'), uid)
        workers.append({
            "user_id": uid, "name": name,
            "has_avatar": bool(profile.get('avatar')),
            "profile": profile,
        })

    all_assignments = _load_assignments()
    abwesenheit_entries = _load_abwesenheit()
    checkin_sessions = _load_checkin_meta()

    return amatch.build_candidates(
        work_type_id, object_id, date_from, date_to,
        workers, all_assignments, abwesenheit_entries, checkin_sessions,
    )


class BatchAssignBody(BaseModel):
    user_ids: list[str]
    work_type_ids: list[str]
    date_from: str
    date_to: str
    task_note: str = ''


@app.post("/api/objects/{object_id}/assignments/batch")
def batch_assign(object_id: str, body: BatchAssignBody,
                  user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """01.08 (спека п.8): назначить нескольких работников одним запросом -- каждому
    отдельная запись с уникальным id, весь read/check/write под одним transaction lock
    (update_json_transaction), без дублей на того же worker+work_type+пересекающийся
    период. Партиальный успех -- 200 с created/skipped; ни одного успеха -- 409.

    01.08 (доп.раунд П6): усилена валидация -- раньше не проверялось, что объект
    вообще существует/не завершён, что user_id реально есть в roles, что его роль
    именно worker (owner или человек без роли мог случайно попасть в назначение).

    09.09: work_type_id (одиночный) -> work_type_ids (список) -- owner попросил
    отмечать несколько видов работ сразу в Assignment Sheet вместо одного запроса
    на каждый вид работы с фронтенда. Создаёт одно назначение на каждую пару
    (user_id, work_type_id) -- та же дедупликация/absence/cross-object проверка,
    что раньше, просто теперь по обеим осям, не только по user_id."""
    work_type_ids = list(dict.fromkeys(body.work_type_ids))  # без дублей, сохраняя порядок
    if not work_type_ids:
        raise HTTPException(400, "Укажите хотя бы один вид работ")
    wtypes = {}
    for wtid in work_type_ids:
        wtype = wt.get_work_type(wtid)
        if wtype is None or not wtype.get('active'):
            raise HTTPException(400, "Неизвестный или неактивный вид работ")
        wtypes[wtid] = wtype

    rows = _cached_get_used_range('Объекты')
    object_row = None
    if rows:
        header, data = rows[0], rows[1:]
        for r in data:
            row = dict(zip(header, r))
            if str(row.get('ID объекта', '')) == str(object_id):
                object_row = row
                break
    if object_row is None:
        raise HTTPException(404, "Объект не найден")
    if object_row.get('Статус') == 'Завершён':
        raise HTTPException(400, "Объект завершён, назначение недоступно")

    user_ids = list(dict.fromkeys(body.user_ids))  # без дублей, сохраняя порядок
    if not user_ids:
        raise HTTPException(400, "Укажите хотя бы одного работника")
    _validate_date_str(body.date_from, 'date_from')
    _validate_date_str(body.date_to, 'date_to')
    if body.date_from > body.date_to:
        raise HTTPException(400, "date_from не может быть позже date_to")
    task_note = body.task_note.strip()[:500]

    # 01.08 (доп.раунд П6): каждый user_id обязан существовать в roles с role=='worker' --
    # старый профиль без активной whitelist-записи (уволенный/никогда не добавленный)
    # не должен становиться доступным для назначения только потому что когда-то
    # прошёл onboarding и оставил worker_profiles.json запись.
    roles = _load_roles()
    for uid in user_ids:
        role = roles.get(uid)
        if role is None:
            raise HTTPException(400, f"Пользователь {uid} не найден в списке доступа")
        if role != 'worker':
            raise HTTPException(400, f"Пользователь {uid} не является Worker (роль: {role})")

    key = str(object_id)
    result_holder = {"created": [], "skipped": []}

    def _mutator(assignments):
        if key not in assignments:
            assignments[key] = []
        abwesenheit = _load_abwesenheit()
        created, skipped = [], []
        for uid in user_ids:
            for wtid in work_type_ids:
                # duplicate check: тот же worker, тот же work_type, пересекающийся период,
                # статус не declined -- та же логика что assign_user() выше, для консистентности.
                dup = any(
                    a['user_id'] == uid and a.get('work_type_id') == wtid
                    and _assignment_status(a) != 'declined'
                    and _dates_overlap(body.date_from, body.date_to, a.get('date_from', ''), a.get('date_to', ''))
                    for a in assignments[key]
                )
                if dup:
                    skipped.append({"user_id": uid, "work_type_id": wtid, "reason": "overlap"})
                    continue
                absence_hit = any(
                    str(e.get('user_id')) == uid and e.get('status') == 'approved'
                    and _dates_overlap(body.date_from, body.date_to, e.get('date_from', ''), e.get('date_to', ''))
                    for e in abwesenheit
                )
                if absence_hit:
                    skipped.append({"user_id": uid, "work_type_id": wtid, "reason": "absence"})
                    continue
                # 09.09: _assignment_periods_overlap(), не голый _dates_overlap() --
                # legacy назначение без date_from/date_to трактовалось как "не
                # пересекается" и молча пропускало эту проверку, позволяя создать
                # новое назначение на другом объекте поверх бессрочного legacy.
                cross_object_hit = False
                for other_oid, other_list in assignments.items():
                    if other_oid == key:
                        continue
                    if any(a['user_id'] == uid and _assignment_status(a) != 'declined'
                           and _assignment_periods_overlap({'date_from': body.date_from, 'date_to': body.date_to}, a)
                           for a in other_list):
                        cross_object_hit = True
                        break
                if cross_object_hit:
                    skipped.append({"user_id": uid, "work_type_id": wtid, "reason": "overlap"})
                    continue
                assignment_id = uuid.uuid4().hex
                assignments[key].append({
                    'id': assignment_id,
                    'user_id': uid,
                    'stage_id': wtypes[wtid]['name'],  # legacy-совместимость (текстовое отображение)
                    'work_type_id': wtid,
                    'date_from': body.date_from,
                    'date_to': body.date_to,
                    'assigned_at': datetime.utcnow().isoformat(),
                    'status': 'pending',
                    'decline_reason': '',
                    'responded_at': '',
                    'task_note': task_note,
                    'created_by': str(user['id']),
                })
                created.append({"user_id": uid, "work_type_id": wtid, "assignment_id": assignment_id})
        result_holder['created'] = created
        result_holder['skipped'] = skipped

    update_json_transaction(OBJECT_ASSIGNMENTS_FILE, {}, _mutator)
    if not result_holder['created']:
        raise HTTPException(409, "Ни одно назначение не создано (все пропущены)")
    return result_holder


# ---------- Owner dashboard: смены сегодня (B5, 27.07) ----------
@app.get("/api/dashboard/shifts-today")
def get_dashboard_shifts_today(user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """Кто сейчас работает / кто назначен но не начал / все смены за сегодня --
    для owner dashboard. owner-only: агрегирует GPS/личные данные всех работников,
    та же чувствительность что у GET /api/checkin (уже owner-gated для чужих сессий)."""
    today = datetime.now().strftime('%Y-%m-%d')
    sessions = _load_checkin_meta()
    today_sessions = [s for s in sessions if s.get('date') == today]

    profiles = _load_worker_profiles()
    rows = _cached_get_used_range('Объекты')
    object_names = {}
    if rows:
        header, data = rows[0], rows[1:]
        for r in data:
            obj = dict(zip(header, r))
            object_names[str(obj.get('ID объекта', ''))] = obj.get('Объект', '')

    def _worker_name(uid):
        return _sanitize_display_name(profiles.get(str(uid), {}).get('name'), str(uid))

    def _worker_specialty(uid):
        skills = profiles.get(str(uid), {}).get('skills') or []
        return skills[0] if skills else ''

    working_now = []
    finished_today = []
    for s in today_sessions:
        entry = {
            "user_id": str(s['user_id']),
            "worker_name": _worker_name(s['user_id']),
            "specialty": _worker_specialty(s['user_id']),
            "object_id": s['object_id'],
            "object_name": object_names.get(s['object_id'], s['object_id']),
            "start_at": s.get('start_at'),
        }
        if s.get('finish_at') is None:
            working_now.append(entry)
        else:
            entry['finish_at'] = s.get('finish_at')
            finished_today.append(entry)

    working_uids = {e['user_id'] for e in working_now}
    finished_uids = {e['user_id'] for e in finished_today}

    # 30.07 v2 (аудит): собираем ВСЕ назначения на сегодня по user_id СНАЧАЛА, потом
    # одна итоговая группа на worker по строгому приоритету -- чинит реальный баг,
    # где worker с accepted на одном объекте И pending на другом мог одновременно
    # попасть и в "не вышел", и в "ожидает подтверждения" (прошлая версия группировала
    # per-(object, assignment) в одном проходе, не per-worker).
    assignments = _load_assignments()
    by_uid = {}  # uid -> list of (oid, assignment) на сегодня
    for oid, lst in assignments.items():
        for a in lst:
            uid = str(a.get('user_id', ''))
            date_from, date_to = a.get('date_from', ''), a.get('date_to', '')
            if not uid or not (date_from and date_to and date_from <= today <= date_to):
                continue
            by_uid.setdefault(uid, []).append((oid, a))

    def _entry(uid, oid, a):
        return {
            "user_id": uid, "worker_name": _worker_name(uid), "specialty": _worker_specialty(uid),
            "object_id": oid, "object_name": object_names.get(oid, oid),
            "stage_id": a.get('stage_id', ''), "date_from": a.get('date_from', ''),
            "date_to": a.get('date_to', ''), "task_note": a.get('task_note', ''),
            "assignment_status": _assignment_status(a),
        }

    not_started = []
    awaiting_response = []
    for uid, pairs in by_uid.items():
        if uid in working_uids or uid in finished_uids:
            continue  # приоритет 1/готово сегодня -- уже показан там, здесь не дублируем
        accepted_pair = next((p for p in pairs if _assignment_status(p[1]) == 'accepted'), None)
        if accepted_pair:
            not_started.append(_entry(uid, *accepted_pair))
            continue
        pending_pair = next((p for p in pairs if _assignment_status(p[1]) == 'pending'), None)
        if pending_pair:
            awaiting_response.append(_entry(uid, *pending_pair))

    # "Доступны сегодня" -- все остальные работники, не занятые ни в одной из групп
    # выше (включая тех, у кого только declined-назначения -- declined не занимает)
    # и без approved-отсутствия на сегодня.
    busy_uids = working_uids | finished_uids | {e['user_id'] for e in not_started} | {e['user_id'] for e in awaiting_response}
    absent_uids = {
        str(e.get('user_id')) for e in _load_abwesenheit()
        if e.get('status') == 'approved' and e.get('date_from', '') <= today <= e.get('date_to', '')
    }
    roles = _load_roles()
    available_today = [
        {"user_id": uid, "worker_name": _worker_name(uid), "specialty": _worker_specialty(uid)}
        for uid in profiles
        if roles.get(uid, 'worker') != 'owner' and uid not in busy_uids and uid not in absent_uids
    ]

    # 30.07 v2: "Работают сейчас" тоже несёт stage_name (если известен из checkin) --
    # аудит просит этот контекст для группы 1 наравне с 2/3.
    for e in working_now:
        s = next((s for s in today_sessions if str(s.get('user_id')) == e['user_id'] and s.get('finish_at') is None), None)
        e['stage_name'] = (s or {}).get('stage_name') or ''

    # 30.07 v3 (спек: "Часы команды" на экране Команда) -- сумма часов за СЕГОДНЯ по
    # всем today_sessions (включая ещё идущие -- _hours_from_session на open-сессии
    # без finish_at даёт 0, отдельно досчитываем текущим временем как условный "конец").
    hours_today_total = 0.0
    for s in today_sessions:
        if s.get('finish_at') is not None or s.get('manual_entry'):
            hours_today_total += _hours_from_session(s)
        elif s.get('start_at'):
            elapsed = (time.time() - s['start_at'] - (s.get('pause_accumulated_seconds') or 0)) / 3600.0
            hours_today_total += max(0.0, elapsed)

    return {
        "date": today,
        "working_now": working_now,
        "hours_today_total": round(hours_today_total, 1),
        "not_started": not_started,
        "finished_today": finished_today,
        "awaiting_response": awaiting_response,
        "available_today": available_today,
    }


@app.get("/api/dashboard/active-blockers")
def get_active_blockers(user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """30.07 (спек: "Команда"→"Требует внимания", тип 3 -- "Сообщил о проблеме").
    stage_blocks в roadmap.json хранится по stage_key (='ID строки этапа' в Sheets),
    без object_id/stage_name -- матчим через all_stages_grouped() (один batch-запрос,
    не N+1 по каждому объекту). owner-only, та же чувствительность что shifts-today."""
    o = _load_repo_objekte_lib()
    store = _safe_load_json(rl.ROADMAP_FILE, rl._default_store())
    stage_blocks = store.get('stage_blocks', {})
    if not stage_blocks:
        return {"blockers": []}
    rows = _cached_get_used_range('Объекты')
    object_names = {}
    if rows:
        header, data = rows[0], rows[1:]
        for r in data:
            obj = dict(zip(header, r))
            object_names[str(obj.get('ID объекта', ''))] = obj.get('Объект', '')
    profiles = _load_worker_profiles()
    grouped = o.all_stages_grouped()
    result = []
    for oid, stages in grouped.items():
        for s in stages:
            stage_key = s.get('ID строки этапа')
            meta = stage_blocks.get(stage_key)
            if not meta:
                continue
            blocked_by = str(meta.get('blocked_by', ''))
            result.append({
                "object_id": oid, "object_name": object_names.get(oid, oid),
                "stage_name": s.get('Название этапа', ''), "row_num": s.get('_row'),
                "reason": meta.get('quick_reason') or meta.get('comment') or '',
                "reported_by_name": _sanitize_display_name(profiles.get(blocked_by, {}).get('name'), blocked_by),
                "blocked_at": meta.get('blocked_at'),
            })
    result.sort(key=lambda b: b.get('blocked_at') or 0, reverse=True)
    return {"blockers": result}


@app.get("/api/dashboard/team-plan")
def get_team_plan(date: str = '', user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    """30.07 (спек: экран "Команда" → вкладка "План"). Отвечает только "кто запланирован
    на дату и на каком объекте" -- читает существующие assignments, ничего не хранит
    отдельно. Для date == сегодня дополнительно отдаёт фактический статус смены
    (идёт/не начата/завершена) из checkin_meta; для будущих дат факт не считается --
    его физически ещё не может быть."""
    target_date = date or business_today_str()  # 03.08 (ТЗ Задача 5): было date.today() (UTC)

    rows = _cached_get_used_range('Объекты')
    object_names = {}
    if rows:
        header, data = rows[0], rows[1:]
        for r in data:
            obj = dict(zip(header, r))
            object_names[str(obj.get('ID объекта', ''))] = obj.get('Объект', '')

    profiles = _load_worker_profiles()

    def _worker_name(uid):
        return _sanitize_display_name(profiles.get(str(uid), {}).get('name'), str(uid))

    # Cleanup-commit (спек п.4): stage_id в assignments -- уже человекочитаемый текст
    # (вид работ из BUBBLE_STAGE_OPTIONS либо "Текущий этап" объекта на момент назначения),
    # но не всегда совпадает с актуальным названием строки этапа в Sheets. Один batch-запрос
    # (не N+1 по каждому назначению) -- матчим по названию этапа того же объекта, при
    # совпадении отдаём каноничное имя, иначе используем stage_id как есть (fallback).
    o = _load_repo_objekte_lib()
    stage_names_by_object = {}
    for oid, stages in o.all_stages_grouped().items():
        stage_names_by_object[oid] = {s.get('Название этапа', '').strip().lower(): s.get('Название этапа', '') for s in stages}

    def _resolve_stage_name(oid, stage_id):
        names = stage_names_by_object.get(oid, {})
        return names.get((stage_id or '').strip().lower(), '')

    is_today = target_date == business_today_str()  # 03.08 (ТЗ Задача 5): было date.today() (UTC)
    sessions_by_uid = {}
    if is_today:
        for s in _load_checkin_meta():
            if s.get('date') == target_date:
                sessions_by_uid.setdefault(str(s.get('user_id')), []).append(s)

    assignments = _load_assignments()
    by_object = {}
    for oid, lst in assignments.items():
        for a in lst:
            date_from, date_to = a.get('date_from', ''), a.get('date_to', '')
            if not (date_from and date_to and date_from <= target_date <= date_to):
                continue
            status = _assignment_status(a)
            # Cleanup-commit (спек п.5): declined больше НЕ пропускается -- owner должен
            # видеть, что запланированный сотрудник отклонил назначение.
            uid = str(a.get('user_id', ''))
            stage_id = a.get('stage_id', '')
            entry = {
                "user_id": uid,
                "worker_name": _worker_name(uid),
                "stage_id": stage_id,
                "stage_name": _resolve_stage_name(oid, stage_id),
                "task_note": a.get('task_note', ''),
                "date_from": date_from,
                "date_to": date_to,
                "assignment_status": status,
            }
            # shift_state имеет смысл только для уже принятого назначения на сегодня --
            # pending ещё ничего не подтвердил, declined отклонил, для них факта смены
            # физически быть не может.
            if is_today and status == 'accepted':
                uid_sessions = sessions_by_uid.get(uid, [])
                active = next((s for s in uid_sessions if s.get('object_id') == oid and s.get('finish_at') is None), None)
                finished = next((s for s in uid_sessions if s.get('object_id') == oid and s.get('finish_at') is not None), None)
                if active:
                    entry['shift_state'] = 'active'
                elif finished:
                    entry['shift_state'] = 'finished'
                else:
                    entry['shift_state'] = 'not_started'
            by_object.setdefault(oid, {"object_id": oid, "object_name": object_names.get(oid, oid), "assignments": []})
            by_object[oid]["assignments"].append(entry)

    objects_plan = sorted(by_object.values(), key=lambda o: o['object_name'] or o['object_id'])
    return {"date": target_date, "objects": objects_plan}


# ---------- Alerts inbox — role-aware агрегация (Фаза 2g, восстановлено после инцидента Фазы 3) ----------
@app.get("/api/alerts")
def get_alerts(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    alerts = []

    # Budget alerts (owner sees) — жёлтый ≥60%, красный ≥90%
    try:
        rows = _cached_get_used_range('Объекты')
        if rows:
            header, data_rows = rows[0], rows[1:]
            for row in data_rows:
                obj = dict(zip(header, row))
                try:
                    pct = float(_load_repo_objekte_lib().get_budget_percent(obj) or 0)
                except (ValueError, TypeError):
                    pct = 0
                oid = obj.get('ID объекта', '')
                name = obj.get('Объект', oid)
                if pct >= 90:
                    alerts.append({
                        'id': f'budget-red-{oid}', 'type': 'red', 'role_filter': 'owner',
                        'title': f'Бюджет перегружен: {name}',
                        'subtitle': f'{int(pct)}% использовано', 'at': None
                    })
                elif pct >= 60:
                    alerts.append({
                        'id': f'budget-yellow-{oid}', 'type': 'yellow', 'role_filter': 'owner',
                        'title': f'Бюджет под угрозой: {name}',
                        'subtitle': f'{int(pct)}% использовано', 'at': None
                    })
    except Exception:
        pass

    # Tool issues (owner) — красный при ремонте/не найден
    try:
        tl = _load_repo_tools_lib()
        tools_list = tl.list_tools()
        for t in tools_list:
            raw_st = (t.get('Статус') or '').strip().lower()
            if raw_st in ('в ремонте', 'не найден'):
                alerts.append({
                    'id': f'tool-{t.get("Серийный #","")}', 'type': 'red', 'role_filter': 'owner',
                    'title': f'Инструмент: {t.get("Название Инструмента","")}',
                    'subtitle': f'Статус: {t.get("Статус","")}', 'at': None
                })
    except Exception:
        pass

    # Worker assignment alerts (worker sees yellow when assigned)
    if role == 'worker':
        assignments = _load_assignments()
        uid = str(user['id'])
        for obj_id, assigned_list in assignments.items():
            for a in assigned_list:
                if a.get('user_id') == uid:
                    stage_txt = f'Этап: {a["stage_id"]}' if a.get('stage_id') else 'Новое назначение'
                    alerts.append({
                        'id': f'assign-{obj_id}-{a.get("stage_id","")}', 'type': 'yellow',
                        'role_filter': 'worker',
                        'title': 'Вы назначены на объект',
                        'subtitle': stage_txt, 'at': a.get('assigned_at')
                    })

    # Pending abwesenheit requests (owner sees red until decided) — 10.15
    if role == 'owner':
        for e in _load_abwesenheit():
            if e.get('status', 'pending') == 'pending':
                alerts.append({
                    'id': f'abw-pending-{e.get("id", "")}', 'type': 'red', 'role_filter': 'owner',
                    'title': f'Заявка на отсутствие: {e.get("name", e.get("user_id", "?"))}',
                    'subtitle': f'{e.get("date_from", "?")} — {e.get("date_to", "?")} · {e.get("reason", "?")}',
                    'at': e.get('created_at')
                })

        alerts.extend(_overdue_task_alerts())

    # Persisted critical alerts (Фаза 10.16 — global critical alert popup)
    for ca in _load_critical_alerts():
        if ca.get('target_user_id') != str(user['id']):
            continue
        if ca.get('acknowledged_at'):
            continue
        alerts.append({
            'id': f'critical-{ca["id"]}', 'type': 'red', 'role_filter': role,
            'title': ca['title'], 'subtitle': ca.get('subtitle', ''), 'at': ca.get('created_at'),
            'critical_alert_id': ca['id'],
        })

    # Раунд 6 §5.2: in-app activity alerts о новых комментариях (агрегируем по публикации).
    try:
        acts = [a for a in _load_activity_alerts()
                if a.get('target_user_id') == str(user['id']) and not a.get('read_at')]
        agg = {}
        for a in acts:
            agg.setdefault((a['kind'], a['ref_id']), []).append(a)
        for (kind, ref_id), group in agg.items():
            n = len(group)
            latest = max(group, key=lambda x: x.get('created_at', 0))
            noun = 'новости' if kind == 'news_comment' else 'фото'
            title = (f"{n} новых комментария к {noun}" if n > 1 else latest.get('title', ''))
            alerts.append({
                'id': f'activity-{kind}-{ref_id}', 'type': 'info', 'role_filter': role,
                'title': title, 'subtitle': latest.get('subtitle', ''),
                'at': latest.get('created_at'),
                'activity_kind': kind, 'activity_ref_id': ref_id,
                'activity_deep_link': ('news' if kind == 'news_comment' else 'photos'),
            })
    except Exception:
        pass

    filtered = [a for a in alerts if a['role_filter'] == role]

    # 25.07: "прочитано" для derived-алертов (бюджет/инструмент/назначение) -- раньше
    # счётчик на Home всегда показывал реальное активное количество, юзер жаловался
    # "не сбрасывается после просмотра". Persisted critical alerts уже имеют свой
    # ack-механизм (acknowledged_at) выше -- не трогаем их отдельным dismiss-слоем.
    # Dismiss истекает через 24ч: если проблема (перегруженный бюджет и т.п.) всё ещё
    # активна на следующий день, алерт напоминает о себе снова -- не даёт навсегда
    # забыть про нерешённую проблему, просто не мозолит глаза сразу после просмотра.
    dismissals = _load_alert_dismissals().get(str(user['id']), {})
    now = int(time.time())
    filtered = [a for a in filtered if now - dismissals.get(a['id'], 0) > ALERT_DISMISS_TTL]

    return {"alerts": filtered, "count": len(filtered)}


# moved to core/paths.py -- ALERT_DISMISSALS_FILE
# moved to core/limits.py -- ALERT_DISMISS_TTL


def _load_alert_dismissals() -> dict:
    return _safe_load_json(ALERT_DISMISSALS_FILE, {})


def _save_alert_dismissals(data: dict):
    _atomic_write_json(ALERT_DISMISSALS_FILE, data)


class AlertDismissBody(BaseModel):
    alert_ids: list[str]


@app.post("/api/alerts/dismiss")
def dismiss_alerts(body: AlertDismissBody, user: dict = Depends(get_current_user)):
    data = _load_alert_dismissals()
    my_id = str(user['id'])
    entry = data.setdefault(my_id, {})
    now = int(time.time())
    for aid in body.alert_ids:
        entry[aid] = now
    _save_alert_dismissals(data)
    return {"ok": True}


@app.get("/api/tools")
def list_tools(user: dict = Depends(get_current_user)):
    tl = _load_repo_tools_lib()
    return {"tools": tl.list_tools()}


@app.get("/api/tools/{serial}/history")
def tool_history(serial: str, user: dict = Depends(get_current_user)):
    tl = _load_repo_tools_lib()
    return {"history": tl.tool_history(serial)}


class CheckoutBody(BaseModel):
    object_name: str
    # 30.07 (Инструменты cleanup): optional только для обратной совместимости --
    # backend больше НЕ доверяет holder от клиента (реальный найденный баг: Worker
    # мог вписать чужое имя, "Кто взял" и "ID держателя" относились бы к разным людям).
    # Держатель всегда определяется из авторизованного Telegram user ниже.
    holder: str = ''


def _holder_name_from_user(user: dict) -> str:
    """Порядок: first_name+last_name -> first_name -> username -> str(id).
    Единственный источник имени держателя для self-checkout -- клиентский holder
    из CheckoutBody игнорируется целиком, не подмешивается ни в каком виде."""
    first_name = (user.get('first_name') or '').strip()
    last_name = (user.get('last_name') or '').strip()
    holder_name = ' '.join(v for v in [first_name, last_name] if v).strip()
    if not holder_name:
        holder_name = (user.get('username') or '').strip()
    if not holder_name:
        holder_name = str(user['id'])
    return holder_name


_tool_locks: dict = {}
_tool_locks_guard = __import__('threading').Lock()


def _lock_for_tool(serial: str):
    """31.07 (Release-аудит П6): один Lock на serial -- checkout/return читают статус
    из Sheets (tools_lib.py, никакого threading.Lock внутри) и пишут отдельным вызовом;
    без лока, охватывающего ВЕСЬ цикл read-check-write, два конкурентных checkout на
    один serial могли оба пройти проверку mapped_status()=='free' до того как первый
    успевал записать нового держателя -- тот же класс гонки, что _lock_for()/
    update_json_transaction закрывают для JSON-сторов (см. их docstring выше), только
    здесь бэкенд данных -- Google Sheets, не JSON-файл."""
    with _tool_locks_guard:
        if serial not in _tool_locks:
            _tool_locks[serial] = __import__('threading').Lock()
        return _tool_locks[serial]


@app.patch("/api/tools/{serial}/checkout")
def checkout_tool(serial: str, body: CheckoutBody, user: dict = Depends(get_current_user)):
    tl = _load_repo_tools_lib()
    if not body.object_name.strip():
        raise HTTPException(400, "Укажи объект")
    with _lock_for_tool(serial):
        tool = tl.get_tool(serial)
        if tool is None:
            raise HTTPException(404, f'инструмент {serial} не найден')
        if tl.mapped_status(tool) != 'free':
            raise HTTPException(409, "Инструмент уже выдан или недоступен")
        # 22.07: worker сам оформляет checkout — user['id'] это и есть реальный держатель,
        # пишем как holder_id чтобы avatar на карточке инструмента был кликабельным (openUserCard).
        holder_name = _holder_name_from_user(user)
        tl.checkout_tool(serial, holder_name, body.object_name, holder_name, holder_id=str(user['id']))
    return {"status": "ok"}


@app.patch("/api/tools/{serial}/return")
def return_tool(serial: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """30.07 (Инструменты-редизайн, п.11, реальный найденный баг): предыдущая версия
    "возврата" вызывала /checkout с пустыми holder/object_name -- checkout_tool всё равно
    пишет holder_id текущего юзера безусловно, так что "возврат" на деле мог сделать
    держателем СВОБОДНОГО инструмента того, кто на самом деле его не брал. Отдельный
    endpoint: текущий держатель или owner -- разрешено, посторонний worker -- 403.

    31.07 (Release-аудит П6): read-check-write под тем же _lock_for_tool(serial), что
    checkout -- та же гонка, зеркально (два одновременных return, или return+checkout
    на один serial)."""
    tl = _load_repo_tools_lib()
    with _lock_for_tool(serial):
        tool = tl.get_tool(serial)
        if tool is None:
            raise HTTPException(404, f'инструмент {serial} не найден')
        holder_id = (tool.get('ID держателя') or '').strip()
        if role != 'owner' and str(user['id']) != holder_id:
            raise HTTPException(403, "Можно вернуть только инструмент, который взят вами")
        tl.return_tool(serial, user.get('first_name', str(user['id'])))
    return {"status": "ok"}


class ToolUpdateBody(BaseModel):
    status: str
    holder: str = ''
    object_name: str = ''
    # 30.07 (Инструменты-редизайн, п.7): Owner теперь выбирает Worker из /api/workers
    # вместо ручного ввода имени -- holder_id делает avatar держателя в карточке
    # кликабельным (openUserCard), тот же смысл что уже есть у worker-self checkout.
    holder_id: str = ''


@app.patch("/api/tools/{serial}")
def update_tool(serial: str, body: ToolUpdateBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    tl = _load_repo_tools_lib()
    try:
        tl.update_tool_status(serial, body.status, body.holder, body.object_name,
                               user.get('first_name', str(user['id'])), holder_id=body.holder_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "ok"}


class NewToolBody(BaseModel):
    name: str
    category: str


_tool_create_lock = __import__('threading').Lock()


@app.post("/api/tools")
def create_tool(body: NewToolBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    # 31.07 (доп.раунд, П5): tl.add_tool() читает существующие serial, вычисляет
    # next=max+1, добавляет строку и пишет историю -- без lock, охватывающего весь
    # цикл, два конкурентных POST могли оба прочитать один и тот же max ДО того как
    # первый успевал записать новую строку, оба бы вычислили ОДИНАКОВЫЙ serial.
    # Отдельный module-level lock (не per-serial -- serial ещё не существует на
    # момент входа в этот эндпоинт, в отличие от checkout/return выше).
    tl = _load_repo_tools_lib()
    with _tool_create_lock:
        serial = tl.add_tool(body.name, body.category, user.get('first_name', str(user['id'])))
    return {"serial": serial}


# ---------- Angebot generator ----------
import subprocess
import uuid
import urllib.request as _urlreq
from fastapi.responses import FileResponse


# moved to core/telegram.py -- send_telegram_message (extracted ahead of the
# rest of Phase A's permissions.py step, to unblock it later: get_current_user
# -> _notify_owner_new_user -> send_telegram_message was the one upward edge
# out of the permissions chain back into main.py-local code, per the Phase A
# dependency map's R4 risk. This leaf move stands on its own regardless of
# whether/when the rest of permissions.py gets extracted.)
try:
    from .core.telegram import send_telegram_message
except ImportError:
    from core.telegram import send_telegram_message  # noqa: E402


def send_pdf_to_chat(chat_id, file_path, filename, caption):
    """Отправляет PDF пользователю в чат с ботом (multipart/form-data вручную,
    т.к. в проекте нет requests — только стандартная библиотека)."""
    boundary = uuid.uuid4().hex
    with open(file_path, 'rb') as f:
        file_data = f.read()

    parts = []
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f'Content-Type: application/pdf\r\n\r\n'.encode()
    )
    parts.append(file_data)
    parts.append(f'\r\n--{boundary}--\r\n'.encode())
    body = b''.join(parts)

    req = _urlreq.Request(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
        data=body, method='POST',
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )
    try:
        _urlreq.urlopen(req, timeout=20)
    except Exception as e:
        print(f'WARNING: sendDocument fehlgeschlagen: {e}')


def _run_pdf_generator(script_path: str, config: dict, timeout: int = 30):
    if not os.path.isfile(script_path):
        raise HTTPException(500, f'PDF-Generator fehlt: {os.path.basename(script_path)}')

    tmp = tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.json', delete=False)
    try:
        with tmp:
            json.dump(config, tmp, ensure_ascii=False)
        result = subprocess.run(['node', script_path, tmp.name], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise HTTPException(504, 'PDF-Generierung dauert zu lange') from e
    finally:
        try:
            os.remove(tmp.name)
        except FileNotFoundError:
            pass

    if result.returncode != 0:
        raise HTTPException(500, f'PDF-Generierung fehlgeschlagen: {result.stderr[-500:]}')
    return result


def _safe_pdf_filename(prefix: str, customer_name: str) -> str:
    name = re.sub(r'[^\w.-]+', '_', (customer_name or '').strip(), flags=re.UNICODE).strip('._')
    if name.lower().endswith('.pdf'):
        name = name[:-4].rstrip('._')
    return f"{prefix}_{(name or 'kunde')[:80]}.pdf"


def _require_server_script(script_path: str, label: str):
    if not script_path or not os.path.isfile(script_path):
        raise HTTPException(500, f'{label} не найден: {script_path or "-"}')
    return script_path


ANGEBOT_SCRIPT = os.path.join(BACKEND_DIR, 'angebot_free.js')
# moved to core/paths.py -- ANGEBOT_OUT_DIR
os.makedirs(ANGEBOT_OUT_DIR, exist_ok=True)


def require_angebot_access(role: str = Depends(get_role)):
    # 'manager' role is intentionally excluded: set_role() hard-rejects any role
    # other than 'owner'/'worker', so 'manager' can never be assigned in practice.
    # Keeping it here would be a latent escalation path if that validation is ever relaxed.
    if role != 'owner':
        raise HTTPException(403, "только owner может создавать Angebot")


class AngebotKunde(BaseModel):
    typ: str = 'privat'
    anrede: str = ''
    name: str
    kontakt: str = ''
    ustId: str = ''
    adresse: str = ''
    email: str = ''


class AngebotPosition(BaseModel):
    titel: str
    beschreibung: str = ''
    menge: float
    einheit: str = 'Stk'
    preis: float


class AngebotBody(BaseModel):
    kunde: AngebotKunde
    objektAdresse: str = ''
    positionen: list[AngebotPosition]
    gueltigTage: int = 14
    mwstSatz: float = 19
    anzahlungPct: float = 40
    signatureBase64: str | None = None  # Фаза 7: canvas-подпись, PNG data без префикса data:...


@app.post("/api/angebot")
def create_angebot(body: AngebotBody, user: dict = Depends(get_current_user), _: None = Depends(require_angebot_access)):
    if not body.positionen:
        raise HTTPException(400, "mindestens eine Position erforderlich")

    out_path = os.path.join(ANGEBOT_OUT_DIR, f'{uuid.uuid4().hex}.pdf')
    config = body.model_dump()
    config['outPath'] = out_path
    if config.get('signatureBase64'):
        config['signedAt'] = datetime.now().strftime('%d.%m.%Y %H:%M')

    _run_pdf_generator(ANGEBOT_SCRIPT, config)

    filename = _safe_pdf_filename('Angebot', body.kunde.name)
    send_pdf_to_chat(user['id'], out_path, filename, f'Angebot für {body.kunde.name}')
    return FileResponse(out_path, media_type='application/pdf', filename=filename)


# ---------- Aufgaben (tasks) ----------
@app.get("/api/objects/{object_id}/tasks")
def get_tasks(object_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    o = _load_repo_objekte_lib()
    return {"tasks": o.list_tasks(object_id)}


class TaskBody(BaseModel):
    text: str


@app.post("/api/objects/{object_id}/tasks")
def create_task(object_id: str, body: TaskBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    o = _load_repo_objekte_lib()
    if not body.text.strip():
        raise HTTPException(400, "Текст не может быть пустым")
    task_id = o.add_task(object_id, body.text.strip(), user.get('first_name', str(user['id'])))
    return {"task_id": task_id}


@app.patch("/api/tasks/{task_id}/complete")
def complete_task(task_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    o = _load_repo_objekte_lib()
    try:
        o.complete_task(task_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "ok"}


# ---------- Инфо объекта (24.07, Step 3): work-items + документы ----------
# moved to core/paths.py -- OBJECT_INFO_FILE
# moved to core/paths.py -- OBJECT_DOC_DIR
os.makedirs(OBJECT_DOC_DIR, exist_ok=True)


def _load_object_info() -> dict:
    return _safe_load_json(OBJECT_INFO_FILE, {})


def _save_object_info(data: dict):
    _atomic_write_json(OBJECT_INFO_FILE, data)


def _new_object_info_entry() -> dict:
    return {"items": [], "documents": [], "description": ""}


def _ensure_object_info_entry(data: dict, object_id: str) -> dict:
    entry = data.setdefault(object_id, _new_object_info_entry())
    entry.setdefault("items", [])
    entry.setdefault("documents", [])
    entry.setdefault("description", "")
    return entry


def _object_info_entry(object_id: str) -> dict:
    data = _load_object_info()
    return data.get(object_id, _new_object_info_entry())


# 25.07: Инфо-таб реструктурирован (6 плоских табов -> 2), владелец попросил
# добавить нормальный блок "Описание объекта" -- переиспользуем тот же per-object
# JSON store, что уже хранит items/documents, не заводим отдельный файл.
@app.get("/api/objects/{object_id}/description")
def get_object_description(object_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    return {"description": _object_info_entry(object_id).get("description", "")}


class ObjectDescriptionBody(BaseModel):
    description: str


@app.patch("/api/objects/{object_id}/description")
def update_object_description(object_id: str, body: ObjectDescriptionBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    description = body.description.strip()[:2000]

    def _mutator(data):
        entry = _ensure_object_info_entry(data, object_id)
        entry["description"] = description
        return entry["description"]

    saved = update_json_transaction(OBJECT_INFO_FILE, {}, _mutator)
    return {"description": saved}


@app.get("/api/objects/{object_id}/info-items")
def get_object_info_items(object_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    return {"items": _object_info_entry(object_id).get("items", [])}


class InfoItemBody(BaseModel):
    text: str
    qty: str = ''


@app.post("/api/objects/{object_id}/info-items")
def create_object_info_item(object_id: str, body: InfoItemBody, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    if not body.text.strip():
        raise HTTPException(400, "Текст не может быть пустым")
    item = {
        "id": uuid.uuid4().hex,
        "text": body.text.strip()[:300],
        "qty": body.qty.strip()[:50],
        "created_by": user.get('first_name', str(user['id'])),
        "created_at": int(time.time()),
    }

    def _mutator(data):
        entry = _ensure_object_info_entry(data, object_id)
        entry["items"].append(item)
        return item

    update_json_transaction(OBJECT_INFO_FILE, {}, _mutator)
    return {"item": item}


@app.delete("/api/objects/{object_id}/info-items/{item_id}")
def delete_object_info_item(object_id: str, item_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    def _mutator(data):
        entry = data.get(object_id)
        if not entry:
            raise HTTPException(404, "Не найдено")
        before = len(entry.get("items", []))
        entry["items"] = [i for i in entry.get("items", []) if i["id"] != item_id]
        if len(entry["items"]) == before:
            raise HTTPException(404, "Не найдено")

    update_json_transaction(OBJECT_INFO_FILE, {}, _mutator)
    return {"status": "ok"}


@app.get("/api/objects/{object_id}/documents")
def get_object_documents(object_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    return {"documents": _object_info_entry(object_id).get("documents", [])}


@app.post("/api/objects/{object_id}/documents")
async def upload_object_document(object_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    data_bytes = await file.read()
    if len(data_bytes) > 8 * 1024 * 1024:
        raise HTTPException(400, "Файл слишком большой (макс. 8 МБ)")
    detected = sniff_image_or_pdf(data_bytes)
    if not detected:
        raise HTTPException(400, "Разрешены только изображения и PDF")
    content_type = detected
    ext = ('.pdf' if detected == 'application/pdf' else '.' + _ALLOWED_IMAGE_MIME_EXT[detected])
    fname = f'{uuid.uuid4().hex}{ext}'
    with open(os.path.join(OBJECT_DOC_DIR, fname), 'wb') as f:
        f.write(data_bytes)

    doc = {
        "id": uuid.uuid4().hex,
        "file": fname,
        "name": file.filename or fname,
        "content_type": content_type,
        "uploaded_by": user.get('first_name', str(user['id'])),
        "uploaded_at": int(time.time()),
    }

    def _mutator(data):
        entry = _ensure_object_info_entry(data, object_id)
        entry["documents"].append(doc)
        return doc

    update_json_transaction(OBJECT_INFO_FILE, {}, _mutator)
    return {"document": doc}


@app.delete("/api/objects/{object_id}/documents/{doc_id}")
def delete_object_document(object_id: str, doc_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    def _mutator(data):
        entry = data.get(object_id)
        if not entry:
            raise HTTPException(404, "Не найдено")
        doc = next((d for d in entry.get("documents", []) if d["id"] == doc_id), None)
        if not doc:
            raise HTTPException(404, "Не найдено")
        entry["documents"] = [d for d in entry.get("documents", []) if d["id"] != doc_id]
        return doc

    doc = update_json_transaction(OBJECT_INFO_FILE, {}, _mutator)
    fpath = os.path.join(OBJECT_DOC_DIR, doc["file"])
    if os.path.exists(fpath):
        os.remove(fpath)
    return {"status": "ok"}


@app.get("/api/objects/{object_id}/documents/{fname}/file")
def get_object_document_file(object_id: str, fname: str, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    entry = _object_info_entry(object_id)
    doc = next((d for d in entry.get("documents", []) if d["file"] == fname), None)
    if not doc:
        raise HTTPException(404, "Файл не найден")
    path = os.path.join(OBJECT_DOC_DIR, fname)
    if not os.path.exists(path):
        raise HTTPException(404, "Файл не найден")
    return FileResponse(path, media_type=doc.get("content_type") or None)


# ---------- Neues Objekt ----------
class NewObjectBody(BaseModel):
    name: str
    adresse: str
    budget: str
    start: str = ''
    end: str = ''


@app.post("/api/objects")
def create_object_endpoint(body: NewObjectBody, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    _require_server_script(CREATE_OBJECT_SCRIPT, "Скрипт создания объекта")
    _require_server_script(CREATE_OBJECT_FOLDER_SCRIPT, "Скрипт создания папки объекта")

    args = [sys.executable, CREATE_OBJECT_SCRIPT, body.name, body.adresse, body.budget]
    if body.start:
        args.append(f'--start={body.start}')
    if body.end:
        args.append(f'--end={body.end}')
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise HTTPException(500, f'Objekt-Erstellung fehlgeschlagen: {result.stderr[-500:]}')

    object_id = None
    for line in result.stdout.splitlines():
        if line.startswith('OK: '):
            object_id = line.split(' ')[1]
            break

    if object_id:
        background_tasks.add_task(
            subprocess.run,
            [sys.executable, CREATE_OBJECT_FOLDER_SCRIPT, object_id, body.name],
            capture_output=True, text=True, timeout=30
        )

    return {"result": result.stdout.strip(), "object_id": object_id}


class StatusBody(BaseModel):
    status: str


# moved to core/constants.py -- VALID_OBJECT_STATUSES


@app.patch("/api/objects/{object_id}/status")
def update_object_status(object_id: str, body: StatusBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    if body.status not in VALID_OBJECT_STATUSES:
        raise HTTPException(400, f'Недопустимый статус: {body.status}')
    o = _load_repo_objekte_lib()
    try:
        o.update_object_field(object_id, 'Статус', body.status)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "ok"}


# ---------- Rechnung generator ----------
RECHNUNG_SCRIPT = os.path.join(BACKEND_DIR, 'rechnung.js')
# moved to core/paths.py -- RECHNUNG_OUT_DIR
os.makedirs(RECHNUNG_OUT_DIR, exist_ok=True)


class RechnungKunde(BaseModel):
    typ: str = 'privat'
    anrede: str = ''
    name: str
    kontakt: str = ''
    ustId: str = ''
    adresse: str = ''
    email: str = ''


class RechnungPosition(BaseModel):
    titel: str
    beschreibung: str = ''
    menge: float
    einheit: str = 'Stk'
    preis: float


class RechnungBody(BaseModel):
    nummer: str
    kunde: RechnungKunde
    projekt: str = ''
    positionen: list[RechnungPosition]
    zahlungsfristTage: int = 14
    mwstSatz: float = 19
    signatureBase64: str | None = None  # Фаза 7: canvas-подпись, PNG data без префикса data:...


@app.post("/api/rechnung")
def create_rechnung(body: RechnungBody, user: dict = Depends(get_current_user), _: None = Depends(require_angebot_access)):
    if not body.nummer.strip():
        raise HTTPException(400, "Rechnung-Nr. erforderlich")
    if not body.positionen:
        raise HTTPException(400, "mindestens eine Position erforderlich")

    out_path = os.path.join(RECHNUNG_OUT_DIR, f'{uuid.uuid4().hex}.pdf')
    config = body.model_dump()
    config['outPath'] = out_path
    if config.get('signatureBase64'):
        config['signedAt'] = datetime.now().strftime('%d.%m.%Y %H:%M')

    _run_pdf_generator(RECHNUNG_SCRIPT, config)

    filename = _safe_pdf_filename('Rechnung', body.kunde.name)
    send_pdf_to_chat(user['id'], out_path, filename, f'{body.nummer} — {body.kunde.name}')
    return FileResponse(out_path, media_type='application/pdf', filename=filename)


# ---------- Weather feed ----------
WEATHER_FEED_FILE = '/home/promonta/agent/.weather_feed.json'


# moved to core/paths.py -- WEATHER_REACTIONS_FILE
# {entry_key: {user_id: true}} — entry_key = "{object}::{created}" (weather-записи не имеют своего id).


def _weather_entry_key(entry: dict) -> str:
    return f"{entry.get('object', '')}::{entry.get('created', '')}"


def _load_weather_reactions() -> dict:
    return _safe_load_json(WEATHER_REACTIONS_FILE, {})


def _save_weather_reactions(data: dict):
    _atomic_write_json(WEATHER_REACTIONS_FILE, data)


@app.get("/api/feed/weather")
def get_weather_feed(user: dict = Depends(get_current_user)):
    if not os.path.exists(WEATHER_FEED_FILE):
        return {"feed": []}
    with open(WEATHER_FEED_FILE, encoding='utf-8') as f:
        feed = json.load(f)
    reactions = _load_weather_reactions()
    uid = str(user['id'])
    for entry in feed:
        key = _weather_entry_key(entry)
        entry_reactions = reactions.get(key, {})
        entry['likes'] = len(entry_reactions)
        entry['liked_by_me'] = uid in entry_reactions
    return {"feed": feed}


@app.post("/api/feed/weather/react")
def react_weather_entry(body: dict, user: dict = Depends(get_current_user)):
    """21.07: реальные лайки на погодных карточках (были декоративные, localStorage-only).
    Ключ записи — object+created, т.к. weather-записи не имеют своего id (генерируются cron-пайплайном)."""
    key = f"{body.get('object', '')}::{body.get('created', '')}"
    reactions = _load_weather_reactions()
    entry_reactions = reactions.setdefault(key, {})
    uid = str(user['id'])
    liked = bool(body.get('liked'))
    if liked:
        entry_reactions[uid] = True
    else:
        entry_reactions.pop(uid, None)
    _save_weather_reactions(reactions)
    return {"likes": len(entry_reactions), "liked_by_me": liked}


# ---------- News feed (Фаза 9, 10.32 — лайки + read-tracking для адаптивной фильтрации) ----------
# Наполняется отдельным cron-пайплайном на VPS (WebSearch/RSS → AI-саммари), здесь чтение + реакции.
NEWS_FEED_FILE = '/home/promonta/agent/.news_feed.json'
# moved to core/paths.py -- NEWS_REACTIONS_FILE
# {post_id: {user_id: "like"|"dislike"}} — по одной реакции на пост от юзера, апдейт при повторном клике.
# moved to core/paths.py -- NEWS_READS_FILE
# {user_id: {category: read_count}} — накопитель для будущей адаптивной фильтрации ленты под интересы.


def _load_news_reactions() -> dict:
    return _safe_load_json(NEWS_REACTIONS_FILE, {})


def _save_news_reactions(data: dict):
    _atomic_write_json(NEWS_REACTIONS_FILE, data)


def _load_news_reads() -> dict:
    return _safe_load_json(NEWS_READS_FILE, {})


def _save_news_reads(data: dict):
    _atomic_write_json(NEWS_READS_FILE, data)


# moved to core/paths.py -- BIRTHDAY_ALERTS_FILE
def _load_birthday_alerts() -> list:
    return _safe_load_json(BIRTHDAY_ALERTS_FILE, [])


def _save_birthday_alerts(items: list):
    _atomic_write_json(BIRTHDAY_ALERTS_FILE, items)


def _check_upcoming_birthdays():
    """10.31 + Раунд 5 §14: два алерта на день рождения worker'а —
    «За 3 дня» и «В день рождения» — с idempotency ключами
    birthday:<uid>:<year>:3days / birthday:<uid>:<year>:today (проверка по
    Europe/Berlin), чтобы один и тот же alert не создавался повторно при каждом
    заходе. Ленивая проверка при GET /api/feed/birthdays (миниапп открывают каждый
    день) — не отдельный systemd timer."""
    profiles = _load_worker_profiles()
    today = business_today()
    d3 = today + timedelta(days=3)
    alerts = _load_birthday_alerts()
    already = {a.get('idem') for a in alerts if a.get('idem')}
    owner_id = next((o for o, r in _load_roles().items() if r == 'owner'), None)

    def _emit(uid, name, occ_date, kind, idem, title):
        alerts.append({
            'user_id': uid, 'name': name, 'year': occ_date.year, 'kind': kind,
            'idem': idem, 'date': occ_date.strftime('%Y-%m-%d'), 'created_at': int(time.time()),
        })
        try:
            _create_critical_alert(target_user_id=owner_id or uid, kind='birthday', title=title, ref_id=uid)
        except Exception:
            pass

    for uid, profile in profiles.items():
        bday = profile.get('birthday')
        if not bday:
            continue
        try:
            bd = datetime.strptime(bday, '%Y-%m-%d').date()
        except ValueError:
            continue
        name = _sanitize_display_name(profile.get('name'), uid)

        # За 3 дня
        if (bd.month, bd.day) == (d3.month, d3.day):
            idem = f'birthday:{uid}:{d3.year}:3days'
            if idem not in already:
                _emit(uid, name, d3, '3days', idem,
                      f'🎂 Через 3 дня день рождения у {name}. Не забудьте подготовить подарок и поздравление.')

        # В день рождения
        if (bd.month, bd.day) == (today.month, today.day):
            idem = f'birthday:{uid}:{today.year}:today'
            if idem not in already:
                _emit(uid, name, today, 'today', idem, f'🎂 Сегодня день рождения у {name}')

    _save_birthday_alerts(alerts)


@app.get("/api/feed/birthdays")
def get_birthday_feed(user: dict = Depends(get_current_user)):
    _check_upcoming_birthdays()
    today = business_today_str()
    upcoming = [a for a in _load_birthday_alerts() if a['date'] >= today]
    return {"birthdays": upcoming}


@app.get("/api/feed/news")
def get_news_feed(user: dict = Depends(get_current_user)):
    if not os.path.exists(NEWS_FEED_FILE):
        return {"feed": []}
    with open(NEWS_FEED_FILE, encoding='utf-8') as f:
        feed = json.load(f)
    reactions = _load_news_reactions()
    comments = _load_news_comments()
    uid = str(user['id'])
    for post in feed:
        post['my_reaction'] = reactions.get(post['id'], {}).get(uid)
        pc = comments.get(post['id'], [])
        post['comment_count'] = len(pc)
        post['last_comment_at'] = max((c.get('ts', 0) for c in pc), default=0)

    reads = _load_news_reads()
    user_reads = reads.setdefault(uid, {})
    for post in feed:
        cat = post.get('category') or 'Другое'
        user_reads[cat] = user_reads.get(cat, 0) + 1
    _save_news_reads(reads)

    return {"feed": feed}


class NewsReactionIn(BaseModel):
    reaction: str  # "like" | "dislike" | "none" (снять реакцию)


@app.post("/api/feed/news/{post_id}/react")
def react_news_post(post_id: str, body: NewsReactionIn, user: dict = Depends(get_current_user)):
    if body.reaction not in ('like', 'dislike', 'none'):
        raise HTTPException(400, "reaction должна быть like/dislike/none")
    if not os.path.exists(NEWS_FEED_FILE):
        raise HTTPException(404, "лента новостей пуста")
    with open(NEWS_FEED_FILE, encoding='utf-8') as f:
        feed = json.load(f)
    post = next((p for p in feed if p['id'] == post_id), None)
    if not post:
        raise HTTPException(404, "пост не найден")

    reactions = _load_news_reactions()
    post_reactions = reactions.setdefault(post_id, {})
    uid = str(user['id'])
    prev = post_reactions.get(uid)

    if prev == 'like':
        post['likes'] = max(0, post.get('likes', 0) - 1)
    elif prev == 'dislike':
        post['dislikes'] = max(0, post.get('dislikes', 0) - 1)

    if body.reaction == 'none':
        post_reactions.pop(uid, None)
    else:
        post_reactions[uid] = body.reaction
        if body.reaction == 'like':
            post['likes'] = post.get('likes', 0) + 1
        else:
            post['dislikes'] = post.get('dislikes', 0) + 1

    _save_news_reactions(reactions)
    _atomic_write_json(NEWS_FEED_FILE, feed)
    return {"ok": True, "likes": post['likes'], "dislikes": post['dislikes'], "my_reaction": body.reaction if body.reaction != 'none' else None}


# ---------- News comments + per-user feed read markers (Раунд 5 §8) ----------
# Комментарии к новостям хранятся ОТДЕЛЬНО от .news_feed.json (его перезаписывает
# cron-пайплайн) — {post_id: [ {id,user_id,name,text,ts,reply_to} ]}. Тот же lifecycle,
# что у фото-комментариев. Read-markers — {user_id: {last_news_read_at, last_photos_read_at,
# last_info_read_at}} (epoch); unread = публикации/активность новее отметки.
# moved to core/paths.py -- NEWS_COMMENTS_FILE
# moved to core/paths.py -- FEED_READS_FILE


def _load_news_comments() -> dict:
    return _safe_load_json(NEWS_COMMENTS_FILE, {})


def _save_news_comments(data: dict):
    _atomic_write_json(NEWS_COMMENTS_FILE, data)


def _load_feed_reads() -> dict:
    return _safe_load_json(FEED_READS_FILE, {})


def _save_feed_reads(data: dict):
    _atomic_write_json(FEED_READS_FILE, data)


class NewsCommentBody(BaseModel):
    text: str
    reply_to: str = None


@app.post("/api/feed/news/{post_id}/comments")
def add_news_comment(post_id: str, body: NewsCommentBody, user: dict = Depends(get_current_user)):
    text = (body.text or '').strip()[:500]
    if not text:
        raise HTTPException(400, "Комментарий не может быть пустым")
    comments = _load_news_comments()
    plist = comments.setdefault(post_id, [])
    prior_ids = {c.get('user_id') for c in plist}  # комментаторы ДО нового — до append
    actor_name = _sanitize_display_name(user.get('first_name'), str(user['id']))
    new_id = uuid.uuid4().hex
    plist.append({
        'id': new_id,
        'user_id': str(user['id']),
        'name': actor_name,
        'text': text,
        'reply_to': (body.reply_to or None),
        'ts': int(time.time()),
    })
    _save_news_comments(comments)
    # Раунд 6 §5.2: activity alerts релевантным (owner + прежние комментаторы); новости из
    # пайплайна не имеют user_id-автора → author_id=None.
    try:
        _emit_comment_activity_alerts(
            'news_comment', post_id, new_id, str(user['id']), actor_name,
            f"{actor_name} прокомментировал новость", _news_post_title(post_id),
            _comment_alert_recipients(user['id'], prior_ids))
    except Exception:
        pass
    return {"comments": plist}


@app.get("/api/feed/news/{post_id}/comments")
def get_news_comments(post_id: str, user: dict = Depends(get_current_user)):
    return {"comments": _load_news_comments().get(post_id, [])}


@app.delete("/api/feed/news/{post_id}/comments/{comment_id}")
def delete_news_comment(post_id: str, comment_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    comments = _load_news_comments()
    plist = comments.get(post_id, [])
    comment = next((c for c in plist if c.get('id') == comment_id), None)
    if not comment:
        raise HTTPException(404, "Комментарий не найден")
    if str(comment.get('user_id')) != str(user['id']) and role != 'owner':
        raise HTTPException(403, "Можно удалить только свой комментарий")
    comments[post_id] = [c for c in plist if c.get('id') != comment_id]
    _save_news_comments(comments)
    return {"comments": comments[post_id]}


class FeedReadBody(BaseModel):
    tab: str  # "news" | "photos" | "info"


@app.post("/api/feed/read")
def mark_feed_read(body: FeedReadBody, user: dict = Depends(get_current_user)):
    if body.tab not in ('news', 'photos', 'info'):
        raise HTTPException(400, "tab должен быть news/photos/info")
    reads = _load_feed_reads()
    urec = reads.setdefault(str(user['id']), {})
    urec[f'last_{body.tab}_read_at'] = int(time.time())
    _save_feed_reads(reads)
    return {"ok": True, "tab": body.tab, "read_at": urec[f'last_{body.tab}_read_at']}


@app.get("/api/feed/unread")
def get_feed_unread(user: dict = Depends(get_current_user)):
    """Счётчики НЕПРОЧИТАННОГО (не общее число). Новость непрочитана, если она
    опубликована позже отметки ИЛИ получила новый комментарий позже отметки. Фото —
    по ts. Инфо — по погодным/др. записям (пока по кол-ву новее отметки нет ts-поля →
    считаем 0, если механизм появится). >99 фронт покажет как «99+»."""
    uid = str(user['id'])
    urec = _load_feed_reads().get(uid, {})
    news_read = urec.get('last_news_read_at', 0)
    photos_read = urec.get('last_photos_read_at', 0)

    news_unread = 0
    if os.path.exists(NEWS_FEED_FILE):
        try:
            with open(NEWS_FEED_FILE, encoding='utf-8') as f:
                feed = json.load(f)
        except Exception:
            feed = []
        comments = _load_news_comments()
        for post in feed:
            created = post.get('created', 0) or 0
            pc = comments.get(post['id'], [])
            last_c = max((c.get('ts', 0) for c in pc), default=0)
            if created > news_read or last_c > news_read:
                news_unread += 1

    photos_unread = 0
    try:
        for p in _load_photo_meta():
            if (p.get('ts', 0) or 0) > photos_read:
                photos_unread += 1
    except Exception:
        pass

    return {"news": news_unread, "photos": photos_unread, "info": 0}


# ---------- Photo feed ----------
# Хранение: файлы на диске + метадата в JSON. Любой сотрудник грузит фото с объекта,
# все видят общей лентой (без ролевых ограничений — как командный чат).
# moved to core/paths.py -- PHOTO_DIR
# moved to core/paths.py -- PHOTO_META_FILE
# moved to core/limits.py -- PHOTO_MAX_BYTES
# moved to core/limits.py -- PHOTO_MAX_COUNT
_photo_lock = __import__('threading').Lock()

os.makedirs(PHOTO_DIR, exist_ok=True)


def _load_photo_meta() -> list:
    return _safe_load_json(PHOTO_META_FILE, [])


def _save_photo_meta(items: list):
    with open(PHOTO_META_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False)


def _copy_checkin_photos_to_feed(rel_paths: list, prefix: str) -> list:
    """Копирует check-in фото (уже сохранены под CHECKIN_PHOTO_BASE) в PHOTO_DIR под
    новыми именами, возвращает список имён файлов для feed_photos.json. 24.07: фото
    старта/финиша смены теперь дублируются в общую фото-ленту — юзер явно попросил
    "чтоб фото начала и конца работ летели в ленту с фото"."""
    saved = []
    for i, rel in enumerate(rel_paths):
        src_path = os.path.join(CHECKIN_PHOTO_BASE, rel)
        if not os.path.exists(src_path):
            continue
        ext = os.path.splitext(rel)[1] or '.jpg'
        fname = f"{prefix}_{i}{ext}"
        with open(src_path, 'rb') as fsrc, open(os.path.join(PHOTO_DIR, fname), 'wb') as fdst:
            fdst.write(fsrc.read())
        saved.append(fname)
    return saved


def _upsert_checkin_feed_post(session: dict, kind: str, object_name: str, user_id, user_name: str):
    """kind: 'start' | 'finish'. Один пост на смену (session['id']) в фото-ленте — старт
    создаёт пост, финиш дописывает свои фото в тот же пост (не два отдельных поста).
    Каждое фото подписывается через _photo_captions (index -> подпись), отдельно от
    общей caption поста."""
    rel_paths = session.get('start_photos' if kind == 'start' else 'finish_photos') or []
    if not rel_paths:
        return
    prefix = f"checkin_{session['id']}_{kind}"
    new_files = _copy_checkin_photos_to_feed(rel_paths, prefix)
    if not new_files:
        return

    time_str = datetime.fromtimestamp(
        session['start_at'] if kind == 'start' else session['finish_at']
    ).strftime('%H:%M')
    label = ('Начало смены' if kind == 'start' else 'Конец смены') + f' · {time_str}'

    with _photo_lock:
        items = _load_photo_meta()
        post = next((p for p in items if p.get('checkin_session_id') == session['id']), None)
        if post:
            start_idx = len(post['files'])
            post['files'].extend(new_files)
            post.setdefault('photo_labels', {})
            for i, _f in enumerate(new_files):
                post['photo_labels'][str(start_idx + i)] = label
        else:
            post = {
                "id": uuid.uuid4().hex,
                "files": new_files,
                "ts": int(time.time()),
                "user_id": user_id,
                "name": user_name,
                "object_id": object_name,
                "caption": "",
                "checkin_session_id": session['id'],
                "photo_labels": {str(i): label for i in range(len(new_files))},
            }
            items.append(post)
        _save_photo_meta(items)


@app.get("/api/feed/photos")
def list_feed_photos(user: dict = Depends(get_current_user)):
    with _photo_lock:
        items = _load_photo_meta()
    photos = []
    for p in reversed(items):
        p = dict(p)
        p['comment_count'] = len(p.pop('comments', []))
        # 24.07: мультифото — старые записи (до этой правки) хранили один 'file',
        # новые хранят 'files' (список). Нормализуем на чтение, не трогаем сами
        # старые JSON-записи на диске (не нужно, чтение уже покрывает оба случая).
        if 'files' not in p:
            p['files'] = [p['file']] if p.get('file') else []
        photos.append(p)
    return {"photos": photos}


# moved to core/limits.py -- PHOTO_MAX_FILES


@app.post("/api/feed/photos")
async def upload_feed_photo(
    files: list[UploadFile] = File(...),
    object_id: str = Form(''),
    caption: str = Form(''),
    user: dict = Depends(get_current_user),
):
    if not files:
        raise HTTPException(400, "Нужно хотя бы одно фото")
    if len(files) > PHOTO_MAX_FILES:
        raise HTTPException(400, f"Максимум {PHOTO_MAX_FILES} фото за раз")

    photo_id = uuid.uuid4().hex
    saved_files = []
    for f in files:
        raw = await f.read()
        if len(raw) > PHOTO_MAX_BYTES:
            raise HTTPException(400, "Фото слишком большое (макс. 8 МБ на файл)")
        detected = sniff_image(raw)
        if not detected:
            raise HTTPException(400, "Все файлы должны быть изображениями")
        ext = _ALLOWED_IMAGE_MIME_EXT[detected]
        fname = f"{photo_id}_{len(saved_files)}.{ext}"
        with open(os.path.join(PHOTO_DIR, fname), 'wb') as out:
            out.write(raw)
        saved_files.append(fname)

    entry = {
        "id": photo_id,
        "files": saved_files,
        "ts": int(time.time()),
        "user_id": user['id'],
        "name": _sanitize_display_name(user.get('first_name'), str(user['id'])),
        "object_id": object_id.strip()[:100],
        "caption": caption.strip()[:300],
    }

    with _photo_lock:
        items = _load_photo_meta()
        items.append(entry)
        if len(items) > PHOTO_MAX_COUNT:
            for old in items[:-PHOTO_MAX_COUNT]:
                for old_fname in (old.get('files') or ([old['file']] if old.get('file') else [])):
                    old_path = os.path.join(PHOTO_DIR, old_fname)
                    if os.path.exists(old_path):
                        os.remove(old_path)
            items = items[-PHOTO_MAX_COUNT:]
        _save_photo_meta(items)

    return {"photo": entry}


class PhotoCommentBody(BaseModel):
    text: str


@app.post("/api/feed/photos/{photo_id}/comments")
def add_feed_photo_comment(photo_id: str, body: PhotoCommentBody, user: dict = Depends(get_current_user)):
    text = body.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Комментарий не может быть пустым")
    with _photo_lock:
        items = _load_photo_meta()
        entry = next((p for p in items if p['id'] == photo_id), None)
        if not entry:
            raise HTTPException(404, "Фото не найдено")
        prior_ids = {c.get('user_id') for c in entry.get('comments', [])}
        photo_author = entry.get('user_id')
        photo_object_id = entry.get('object_id', '')
        actor_name = _sanitize_display_name(user.get('first_name'), str(user['id']))
        new_id = uuid.uuid4().hex
        entry.setdefault('comments', []).append({
            'id': new_id,
            'user_id': str(user['id']),
            'name': actor_name,
            'text': text,
            'at': datetime.utcnow().isoformat(),
        })
        _save_photo_meta(items)
    # Раунд 6 §5.2: activity alerts (owner + прежние комментаторы + автор фото).
    try:
        obj_name = _resolve_object_name(photo_object_id)
        subtitle = f"Объект: {obj_name}" if obj_name else ''
        _emit_comment_activity_alerts(
            'photo_comment', photo_id, new_id, str(user['id']), actor_name,
            f"{actor_name} прокомментировал фото", subtitle,
            _comment_alert_recipients(user['id'], prior_ids, author_id=photo_author))
    except Exception:
        pass
    return {"comments": entry['comments']}


@app.get("/api/feed/photos/{photo_id}/comments")
def get_feed_photo_comments(photo_id: str, user: dict = Depends(get_current_user)):
    with _photo_lock:
        items = _load_photo_meta()
    entry = next((p for p in items if p['id'] == photo_id), None)
    if not entry:
        raise HTTPException(404, "Фото не найдено")
    return {"comments": entry.get('comments', [])}


@app.delete("/api/feed/photos/{photo_id}/comments/{comment_id}")
def delete_feed_photo_comment(photo_id: str, comment_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    with _photo_lock:
        items = _load_photo_meta()
        entry = next((p for p in items if p['id'] == photo_id), None)
        if not entry:
            raise HTTPException(404, "Фото не найдено")
        comments = entry.get('comments', [])
        comment = next((c for c in comments if c.get('id') == comment_id), None)
        if not comment:
            raise HTTPException(404, "Комментарий не найден")
        if str(comment.get('user_id')) != str(user['id']) and role != 'owner':
            raise HTTPException(403, "Можно удалить только свой комментарий")
        entry['comments'] = [c for c in comments if c.get('id') != comment_id]
        _save_photo_meta(items)
    return {"comments": entry['comments']}


# ---------- Раунд 6 §5: пересылка комментариев + in-app activity alerts ----------
# Base comment lifecycle (add/get/delete news+photo) уже есть из Раунда 5 — здесь только
# недостающее: серверная карточка-пересылка в чат и лёгкие in-app алерты о новых
# комментариях (НЕ critical_alerts — без telegram-пуша/ack, отдельный activity_alerts.json).
# moved to core/paths.py -- ACTIVITY_ALERTS_FILE


def _load_activity_alerts() -> list:
    return _safe_load_json(ACTIVITY_ALERTS_FILE, [])


def _save_activity_alerts(items: list):
    _atomic_write_json(ACTIVITY_ALERTS_FILE, items)


def _news_post_title(post_id: str) -> str:
    try:
        if os.path.exists(NEWS_FEED_FILE):
            with open(NEWS_FEED_FILE, encoding='utf-8') as f:
                for p in json.load(f):
                    if p.get('id') == post_id:
                        return p.get('title', '') or ''
    except Exception:
        pass
    return ''


def _resolve_object_name(object_id: str) -> str:
    if not object_id:
        return ''
    try:
        rows = _cached_get_used_range('Объекты')
        if rows:
            hdr = rows[0]
            for r in rows[1:]:
                row = dict(zip(hdr, r))
                if str(row.get('ID объекта', '')) == str(object_id):
                    return row.get('Объект', '') or str(object_id)
    except Exception:
        pass
    return str(object_id)


def _comment_alert_recipients(actor_id, prior_user_ids, author_id=None) -> set:
    """§5.2: релевантные получатели — Owner('ы) + кто уже комментировал + автор публикации
    (если есть user_id). НЕ все Worker. Автор нового комментария исключён."""
    recips = {str(uid) for uid, r in _load_roles().items() if r == 'owner'}
    recips |= {str(u) for u in prior_user_ids if u}
    if author_id:
        recips.add(str(author_id))
    recips.discard(str(actor_id))
    return recips


def _emit_comment_activity_alerts(kind, ref_id, comment_id, actor_id, actor_name,
                                   title, subtitle, recipients):
    """§5.2 идемпотентность: один comment_id не создаёт повторный alert одному получателю
    (повторный GET/добавление не плодит алерты)."""
    if not recipients:
        return
    items = _load_activity_alerts()
    existing = {(a.get('target_user_id'), a.get('comment_id')) for a in items}
    now = int(time.time())
    changed = False
    for uid in recipients:
        if (str(uid), comment_id) in existing:
            continue
        items.append({
            'id': uuid.uuid4().hex, 'target_user_id': str(uid), 'kind': kind,
            'ref_id': str(ref_id), 'comment_id': comment_id, 'actor_id': str(actor_id),
            'actor_name': actor_name, 'title': title, 'subtitle': subtitle,
            'created_at': now, 'read_at': None,
        })
        changed = True
    if changed:
        _save_activity_alerts(items)


class ActivityReadBody(BaseModel):
    kind: str
    ref_id: str


@app.post("/api/activity-alerts/read")
def mark_activity_alerts_read(body: ActivityReadBody, user: dict = Depends(get_current_user)):
    """§5.2/§5.3: после реального открытия конкретного обсуждения — пометить прочитанным."""
    items = _load_activity_alerts()
    now = int(time.time())
    changed = False
    for a in items:
        if (a.get('target_user_id') == str(user['id']) and a.get('kind') == body.kind
                and a.get('ref_id') == str(body.ref_id) and not a.get('read_at')):
            a['read_at'] = now
            changed = True
    if changed:
        _save_activity_alerts(items)
    return {"status": "ok"}


class CommentForwardBody(BaseModel):
    source_type: str  # 'news' | 'photo'
    source_id: str
    comment_id: str
    to_user_id: str | None = None
    thread_key: str | None = None


@app.post("/api/comments/forward")
def forward_comment(body: CommentForwardBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """§5.1: пересылка комментария в существующий чат (общий/личный/объект/дефект/потребность).
    Карточка строится СЕРВЕРНО из сохранённого комментария и заголовка новости/фото —
    тексту карточки от frontend не доверяем; существование источника валидируется."""
    if body.source_type == 'news':
        plist = _load_news_comments().get(body.source_id, [])
        comment = next((c for c in plist if c.get('id') == body.comment_id), None)
        if not comment:
            raise HTTPException(404, "Комментарий не найден")
        title = _news_post_title(body.source_id) or 'Новость'
        card = f"💬 Комментарий к новости\n«{title}»\n{comment.get('name', '')}:\n{comment.get('text', '')}"
    elif body.source_type == 'photo':
        with _photo_lock:
            items = _load_photo_meta()
        entry = next((p for p in items if p['id'] == body.source_id), None)
        if not entry:
            raise HTTPException(404, "Фото не найдено")
        comment = next((c for c in entry.get('comments', []) if c.get('id') == body.comment_id), None)
        if not comment:
            raise HTTPException(404, "Комментарий не найден")
        obj_name = _resolve_object_name(entry.get('object_id', '')) or 'без объекта'
        card = f"💬 Комментарий к фотографии\nОбъект: {obj_name}\n{comment.get('name', '')}:\n{comment.get('text', '')}"
    else:
        raise HTTPException(400, "Неизвестный тип источника")

    # Проверка доступа к цели — тот же гейт, что и обычная отправка сообщения.
    if body.thread_key:
        _check_thread_access(body.thread_key, str(user['id']), role)
    else:
        _reject_self_chat(user['id'], body.to_user_id)
        _validate_dm_recipient(body.to_user_id)
        thread_id = _chat_thread_id(user['id'], body.to_user_id)
        thread_meta = _load_chat_thread_meta()
        if thread_meta.get(thread_id, {}).get('closed') and role != 'owner':
            raise HTTPException(403, "Чат закрыт руководством")

    msg = {
        "id": uuid.uuid4().hex, "ts": int(time.time()), "user_id": user['id'],
        "name": user.get('first_name', str(user['id'])), "text": card,
        "to_user_id": body.to_user_id, "thread_key": body.thread_key,
        "forwarded_comment": {"source_type": body.source_type, "source_id": body.source_id,
                              "comment_id": body.comment_id},
    }
    with _chat_lock:
        messages = _load_chat()
        messages.append(msg)
        _save_chat(messages)
    return {"message": msg, "status": "ok"}


@app.get("/api/feed/photos/{photo_id}/file")
def get_feed_photo_file(photo_id: str, index: int = 0, user: dict = Depends(get_current_user)):
    with _photo_lock:
        items = _load_photo_meta()
    entry = next((p for p in items if p['id'] == photo_id), None)
    if not entry:
        raise HTTPException(404, "Фото не найдено")
    files = entry.get('files') or ([entry['file']] if entry.get('file') else [])
    if index < 0 or index >= len(files):
        raise HTTPException(404, "Файл не найден по этому индексу")
    path = os.path.join(PHOTO_DIR, files[index])
    if not os.path.exists(path):
        raise HTTPException(404, "Файл отсутствует")
    return FileResponse(path)


# ---------- Team Chat ----------
# Хранение: JSON-файл, последние 200 сообщений. Polling с фронта каждые 8 сек.
# Инстанс один, файл достаточен — без WebSocket и БД для простоты.
# moved to core/paths.py -- CHAT_FILE
# moved to core/paths.py -- CHAT_ARCHIVE_FILE
# moved to core/limits.py -- CHAT_MAX
_chat_lock = __import__('threading').Lock()


def _archive_chat_messages(messages: list):
    # 28.07: owner request -- удаление треда/сообщения не должно стирать историю
    # безвозвратно. Append-only архив на диске, отдельный от рабочего chat_messages.json
    # (тот же принцип, что закрытые Потребности архивируются в Google Sheets вместо
    # физического удаления).
    if not messages:
        return
    archive = _safe_load_json(CHAT_ARCHIVE_FILE, [])
    archive.extend(messages)
    # 30.07 (Release-аудит P1): plain open(w)+json.dump -> atomic. Вызывается изнутри
    # _save_chat, которая уже держит _chat_lock -- RMW-race закрыт, тут только crash-safety.
    _atomic_write_json(CHAT_ARCHIVE_FILE, archive)


def _load_chat() -> list:
    return _safe_load_json(CHAT_FILE, [])


def _save_chat(messages: list):
    # 28.07: owner request -- история чата должна сохраняться на сервере, не теряться
    # молча. Раньше messages[-CHAT_MAX:] отбрасывал всё, что не влезло в последние 200,
    # без следа. Теперь то, что вылетает за пределы CHAT_MAX, архивируется тем же
    # append-only архивом, что уже используется для явного удаления треда/сообщения.
    if len(messages) > CHAT_MAX:
        _archive_chat_messages(messages[:-CHAT_MAX])
        messages = messages[-CHAT_MAX:]
    # 30.07 (Release-аудит P1): plain open(w)+json.dump -> atomic. RMW-race уже
    # закрыт _chat_lock на всех call sites, тут только crash-safety записи.
    _atomic_write_json(CHAT_FILE, messages)


# moved to core/limits.py -- CHAT_RETENTION_SECONDS


def _purge_old_chat(messages: list) -> list:
    # 28.07: то же самое -- сообщения старше 7 дней архивируются, не стираются молча.
    cutoff = time.time() - CHAT_RETENTION_SECONDS
    keep = [m for m in messages if m.get('ts', 0) >= cutoff]
    expired = [m for m in messages if m.get('ts', 0) < cutoff]
    if expired:
        _archive_chat_messages(expired)
    return keep


# moved to core/paths.py -- CHAT_READS_FILE
def _load_reads() -> dict:
    return _safe_load_json(CHAT_READS_FILE, {})


def _save_reads(reads: dict):
    _atomic_write_json(CHAT_READS_FILE, reads)


# moved to core/paths.py -- CHAT_THREAD_META_FILE
def _load_chat_thread_meta() -> dict:
    return _safe_load_json(CHAT_THREAD_META_FILE, {})


def _save_chat_thread_meta(meta: dict):
    _atomic_write_json(CHAT_THREAD_META_FILE, meta)


# moved to core/paths.py -- CHAT_REACTIONS_FILE
# moved to core/constants.py -- CHAT_REACTION_OPTIONS


def _load_chat_reactions() -> list:
    """Phase 06: список {message_id,user_id,reaction,created_at}, а не словарь --
    один пользователь может оставить НЕСКОЛЬКО разных reaction на одно сообщение
    (👍 и 👀 одновременно), но не два одинаковых -- уникальность по (message_id,
    user_id, reaction), toggle снимает при повторном POST того же типа."""
    return _safe_load_json(CHAT_REACTIONS_FILE, [])


def _save_chat_reactions(reactions: list):
    _atomic_write_json(CHAT_REACTIONS_FILE, reactions)


def _reactions_summary_for_message(reactions: list, message_id: str, my_id: str) -> list:
    by_type = {}
    for r in reactions:
        if r['message_id'] != message_id:
            continue
        entry = by_type.setdefault(r['reaction'], {'reaction': r['reaction'], 'count': 0, 'mine': False})
        entry['count'] += 1
        if str(r['user_id']) == my_id:
            entry['mine'] = True
    return [by_type[e] for e in CHAT_REACTION_OPTIONS if e in by_type]


def _chat_thread_id(user_id: str, to_user_id: str | None) -> str:
    if not to_user_id:
        return 'group'
    return '-'.join(sorted([str(user_id), str(to_user_id)]))


def _reject_self_chat(user_id, to_user_id: str | None):
    """Phase 06 audit: self-DM was never explicitly blocked -- a buggy/replayed
    client sending to_user_id == own id would silently create a degenerate
    'uid-uid' thread. Group (to_user_id falsy) and obj:/mangel:/task: threads
    (thread_key path) are unaffected."""
    if to_user_id and str(to_user_id) == str(user_id):
        raise HTTPException(400, "Нельзя написать самому себе")


def _validate_dm_recipient(to_user_id: str | None):
    """DM targets must be active authorized users. A profile-only/revoked user
    must not become a new ghost thread target."""
    if not to_user_id:
        return
    roles = _load_roles()
    if str(to_user_id) not in roles:
        raise HTTPException(404, "Пользователь не найден или доступ отозван")


def _object_chat_participants(object_id: str) -> list:
    """03.08 (доп.раунд П2, реальный найденный баг): раньше ЛЮБОЕ назначение (даже
    pending/declined, даже вне периода) давало доступ к чату объекта -- полное
    несоответствие с can_access_object, которое уже требовало accepted+период.
    Теперь строго через has_active_object_access -- тот же критерий доступа
    одинаково для этапов/файлов/чата, не отдельная более слабая проверка."""
    roles = _load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    assignments = _load_assignments().get(object_id, [])
    candidate_ids = {str(a['user_id']) for a in assignments}
    today = _today_berlin_str()
    worker_ids = {uid for uid in candidate_ids if has_active_object_access(uid, object_id, today)}
    if owner_id:
        worker_ids.add(str(owner_id))
    return list(worker_ids)


def _mangel_chat_participants(ticket_id: str) -> list:
    roles = _load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    participants = {str(owner_id)} if owner_id else set()
    try:
        ticket = ml.get_ticket(ticket_id)
        if ticket.get('assigned_worker_id'):
            participants.add(str(ticket['assigned_worker_id']))
        if ticket.get('created_by'):
            participants.add(str(ticket['created_by']))
    except Exception:
        pass
    return list(participants)


def _task_chat_participants(task_id: str) -> list:
    roles = _load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    participants = {str(owner_id)} if owner_id else set()
    task = next((t for t in _load_tasks() if t['id'] == task_id), None)
    if task and task.get('from_user_id'):
        participants.add(str(task['from_user_id']))
    return list(participants)


def _check_thread_access(thread_id: str, uid: str, role: str):
    """obj:/mangel:/task: треды — доступ только участникам (не любой worker может
    писать в чужой чат). DM/group треды не проходят через эту проверку — там
    доступ регулируется самим thread_id (пара user_id) или ролью."""
    if thread_id.startswith('obj:'):
        object_id = thread_id[len('obj:'):]
        if uid not in _object_chat_participants(object_id) and role != 'owner':
            raise HTTPException(403, "Нет доступа к чату этого объекта")
    elif thread_id.startswith('mangel:'):
        ticket_id = thread_id[len('mangel:'):]
        if uid not in _mangel_chat_participants(ticket_id) and role != 'owner':
            raise HTTPException(403, "Нет доступа к чату этого тикета")
    elif thread_id.startswith('task:'):
        task_id = thread_id[len('task:'):]
        if uid not in _task_chat_participants(task_id) and role != 'owner':
            raise HTTPException(403, "Нет доступа к чату этой потребности")


def _thread_title(thread_key: str) -> str:
    if thread_key.startswith('obj:'):
        object_id = thread_key[len('obj:'):]
        try:
            rows = _cached_get_used_range('Объекты')
            if rows:
                hdr, data = rows[0], rows[1:]
                for r in data:
                    row = dict(zip(hdr, r))
                    if str(row.get('ID объекта', '')) == object_id:
                        return f"Объект: {row.get('Объект', object_id)}"
        except Exception:
            pass
        return f"Объект: {object_id}"
    if thread_key.startswith('mangel:'):
        ticket_id = thread_key[len('mangel:'):]
        try:
            ticket = ml.get_ticket(ticket_id)
            return f"Тикет: {ticket.get('object_id', ticket_id)}"
        except Exception:
            return f"Тикет: {ticket_id}"
    if thread_key.startswith('task:'):
        task_id = thread_key[len('task:'):]
        task = next((t for t in _load_tasks() if t['id'] == task_id), None)
        return f"Потребность: {task['title']}" if task else f"Потребность: {task_id}"
    return thread_key


@app.get("/api/chat/my_threads")
def get_my_chat_threads(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    uid = str(user['id'])
    messages = _load_chat()
    keys = {m['thread_key'] for m in messages if m.get('thread_key')}
    result = []
    for key in keys:
        try:
            _check_thread_access(key, uid, role)
        except HTTPException:
            continue
        thread_msgs = [m for m in messages if m.get('thread_key') == key]
        last = max(thread_msgs, key=lambda m: m['ts']) if thread_msgs else None
        result.append({
            "thread_key": key,
            "title": _thread_title(key),
            "last_ts": last['ts'] if last else 0,
            "last_preview": _message_preview(last),
        })
    result.sort(key=lambda t: t['last_ts'], reverse=True)
    return {"threads": result}


def _message_preview(msg: dict | None) -> str:
    if not msg:
        return ''
    if msg.get('text'):
        return msg['text']
    if msg.get('location'):
        return '📍 Геолокация'
    att = msg.get('attachment') or {}
    if (att.get('content_type') or '').startswith('audio'):
        return '🎤 Голосовое'
    if att:
        return '📎 Файл'
    return ''


# moved to core/constants.py -- THREAD_TYPE_BY_PREFIX


@app.get("/api/chat/threads")
def get_normalized_chat_threads(type: str = '', user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """Phase 06: normalized shape (id/type/title/avatar_url/subtitle/last_message/
    unread_count/muted/pinned/version) per docs/plan-phases/06-chat-hub-rebuild.md.
    Kept ALONGSIDE the legacy /api/chat/my_threads (not replacing it) -- no frontend
    UI reads this yet, the live Chat Hub still runs on the old endpoints, this is
    additive groundwork for the eventual frontend rebuild.
    `type` filter: GENERAL/DIRECT/OBJECT/DEFECT/TASK (spec's ChatThread.type enum,
    extended with TASK per the 5-tabs decision in docs/DECISIONS.md, 2026-07-28).
    Also fixes two real gaps found while building this: the old /api/chat/my_threads
    never included GENERAL or DIRECT threads at all (only obj:/mangel:/task:), so
    the frontend's "Общий чат"/DM previews in the thread list were always the
    static fallback text, never the actual last message -- see chat.js
    renderChatThreadList()'s _threadByKey('group') / _threadByKey(worker.user_id)
    calls, which could never match anything this endpoint's predecessor returned.
    No cursor/pagination -- CHAT_MAX caps total stored messages at 200 across ALL
    threads, so pagination has no real workload to justify yet; revisit if that
    cap is ever raised.
    """
    uid = str(user['id'])
    with _chat_lock:
        messages = _purge_old_chat(_load_chat())
        _save_chat(messages)
    reads = _load_reads()
    meta = _load_chat_thread_meta()
    profiles = _load_worker_profiles()
    roles = _load_roles()

    def _last_message_field(last):
        return {"text": _message_preview(last), "ts": last['ts'], "sender_id": str(last['user_id'])} if last else None

    threads = []

    if not type or type == 'GENERAL':
        group_msgs = [m for m in messages if not m.get('to_user_id') and not m.get('thread_key')]
        last = max(group_msgs, key=lambda m: m['ts']) if group_msgs else None
        unread = sum(1 for m in group_msgs if str(m.get('user_id')) != uid and m['ts'] > _thread_last_read(reads, uid, 'group'))
        prefs = _thread_user_prefs(meta, 'group', uid)
        threads.append({
            "id": "group", "type": "GENERAL", "title": "Общий чат", "avatar_url": None,
            "subtitle": _message_preview(last), "last_message": _last_message_field(last),
            "unread_count": unread, **prefs, "version": last['ts'] if last else 0,
        })

    if not type or type == 'DIRECT':
        for wuid in (set(roles.keys()) | set(profiles.keys())):
            if wuid == uid:
                continue
            dm_msgs = [m for m in messages if not m.get('thread_key') and (
                (str(m.get('user_id')) == uid and str(m.get('to_user_id')) == wuid) or
                (str(m.get('user_id')) == wuid and str(m.get('to_user_id')) == uid))]
            last = max(dm_msgs, key=lambda m: m['ts']) if dm_msgs else None
            thread_id = _chat_thread_id(uid, wuid)
            unread = sum(1 for m in dm_msgs if str(m.get('user_id')) != uid and m['ts'] > _thread_last_read(reads, uid, wuid))
            prefs = _thread_user_prefs(meta, thread_id, uid)
            p = profiles.get(wuid, {})
            last_seen = _last_seen.get(wuid)
            threads.append({
                "id": wuid, "type": "DIRECT",
                "title": _sanitize_display_name(p.get('name'), wuid),
                "avatar_url": f"/api/profile/{wuid}/avatar" if p.get('avatar') else None,
                "subtitle": _message_preview(last) or ('Владелец' if roles.get(wuid) == 'owner' else 'Работник'),
                "online": bool(last_seen and (time.time() - last_seen) < ONLINE_THRESHOLD_SECONDS),
                "last_message": _last_message_field(last),
                "unread_count": unread, **prefs, "version": last['ts'] if last else 0,
            })

    if not type or type in ('OBJECT', 'DEFECT', 'TASK'):
        keys = {m['thread_key'] for m in messages if m.get('thread_key')}
        for key in keys:
            ttype = next((v for p, v in THREAD_TYPE_BY_PREFIX.items() if key.startswith(p)), None)
            if not ttype or (type and type != ttype):
                continue
            try:
                _check_thread_access(key, uid, role)
            except HTTPException:
                continue
            thread_msgs = [m for m in messages if m.get('thread_key') == key]
            last = max(thread_msgs, key=lambda m: m['ts']) if thread_msgs else None
            unread = sum(1 for m in thread_msgs if str(m.get('user_id')) != uid and m['ts'] > _thread_last_read(reads, uid, key))
            prefs = _thread_user_prefs(meta, key, uid)
            threads.append({
                "id": key, "type": ttype, "title": _thread_title(key), "avatar_url": None,
                "subtitle": _message_preview(last), "last_message": _last_message_field(last),
                "unread_count": unread, **prefs, "version": last['ts'] if last else 0,
            })

    threads.sort(key=lambda t: t['last_message']['ts'] if t['last_message'] else 0, reverse=True)
    return {"threads": threads}


@app.get("/api/chat/messages")
def get_chat_messages(with_: str = '', thread_key: str = '', user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    with _chat_lock:
        messages = _purge_old_chat(_load_chat())
        _save_chat(messages)
    if thread_key:
        # 10.36: чат объекта (obj:OBJ-001) или дефекта (mangel:ticket_id) — сообщения
        # хранятся с явным полем thread_key, доступ только участникам.
        _check_thread_access(thread_key, str(user['id']), role)
        messages = [m for m in messages if m.get('thread_key') == thread_key]
    elif with_:
        # DM-тред: сообщения между мной и with_ в обе стороны
        me = str(user['id'])
        messages = [m for m in messages if
                    (str(m.get('user_id')) == me and str(m.get('to_user_id')) == with_) or
                    (str(m.get('user_id')) == with_ and str(m.get('to_user_id')) == me)]
    else:
        # Групповой тред: только сообщения без to_user_id (старые записи без ключа — тоже групповые)
        messages = [m for m in messages if not m.get('to_user_id') and not m.get('thread_key')]

    reactions = _load_chat_reactions()
    my_id = str(user['id'])
    for m in messages:
        m['reactions'] = _reactions_summary_for_message(reactions, m['id'], my_id)

    # 28.07: owner request -- статус прочтения в личном чате (DM). Собеседник уже
    # отмечает прочтение через существующий POST /api/chat/read (reads.json), просто
    # никогда не отдавался обратно отправителю. Только для DM (with_) -- групповой/
    # obj:/mangel: треды имеют много читателей, "прочитано" там неоднозначно, вне
    # скоупа этого запроса ("в личный чат").
    if with_:
        other_reads = _load_reads().get(with_, {})
        other_last_read = other_reads.get(my_id, 0) if isinstance(other_reads, dict) else int(other_reads or 0)
        for m in messages:
            if str(m.get('user_id')) == my_id:
                m['read_by_recipient'] = m.get('ts', 0) <= other_last_read

    return {"messages": messages}


def _thread_last_read(reads: dict, my_id: str, thread_key: str) -> int:
    """10.29 (Fable-аудит): reads.json теперь {user_id: {thread_id: ts}} вместо плоского
    {user_id: ts} — открытие одного треда больше не сбрасывает badge у остальных."""
    user_reads = reads.get(my_id, {})
    if isinstance(user_reads, (int, float)):
        # миграция со старого плоского формата — считаем это last_read для всех тредов сразу
        return int(user_reads)
    return int(user_reads.get(thread_key, 0))


@app.get("/api/chat/unread_count")
def get_unread_count(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """30.07 (Release-аудит Этап 5): раньше цикл вообще не учитывал thread_key
    (obj:/mangel:/task: треды) -- фильтровал только по to_user_id, поэтому любое
    сообщение с thread_key (thread_key истинный, to_user_id всегда None у таких
    сообщений) попадало в ветку "group" и считалось непрочитанным ДЛЯ ЛЮБОГО
    пользователя против его group-last-read, независимо от того, участник ли он
    вообще этого конкретного object/mangel/task-треда -- общий nav-badge был
    завышен и не гас после прочтения конкретного треда. Логика приведена к тому
    же паттерну, что уже верно работает в get_unread_by_thread ниже: явная
    проверка _check_thread_access для thread_key-сообщений + собственный ключ
    last-read на каждый thread_key (не смешивается с general group-веткой)."""
    with _chat_lock:
        messages = _load_chat()
        reads = _load_reads()
    meta = _load_chat_thread_meta()
    me = str(user['id'])
    count = 0
    for m in messages:
        if str(m.get('user_id')) == me:
            continue
        tkey = m.get('thread_key')
        if tkey:
            try:
                _check_thread_access(tkey, me, role)
            except HTTPException:
                continue
            thread_key = tkey
            prefs_id = tkey
        else:
            to_uid = m.get('to_user_id')
            if to_uid and str(to_uid) != me:
                continue  # чужой DM
            thread_key = 'group' if not to_uid else str(m['user_id'])
            prefs_id = thread_key if not to_uid else _chat_thread_id(me, thread_key)
        if m.get('ts', 0) <= _thread_last_read(reads, me, thread_key):
            continue
        if _thread_user_prefs(meta, prefs_id, me).get('muted'):
            continue
        count += 1
    return {"unread": count}


@app.get("/api/chat/unread_by_thread")
def get_unread_by_thread(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """10.14/10.29: разбивка непрочитанных по тредам для badge на каждой строке списка,
    per-thread last_read — открытие одного треда не сбрасывает счётчик у остальных.
    25.07: расширено на thread_key-треды (obj:/mangel:/task:) -- раньше badge считался
    только для group/DM веток, вкладки Объекты/Дефекты/Потребности в списке чатов не
    показывали unread вообще (не забыт badge в разметке -- сам подсчёт не доходил
    до этих сообщений, т.к. цикл ниже фильтровал только по to_user_id).
    28.07 (Phase 06): заглушённые (muted) треды исключены из счёта -- иначе mute-иконка
    во frontend была бы декоративной, а не реальным подавлением уведомлений. prefs_id
    для DM отличается от display-ключа thread_key (тот -- id собеседника, prefs хранятся
    под отсортированной парой _chat_thread_id, см. set_chat_thread_prefs) -- не перепутать.
    30.07 (Release-аудит Этап 5): та же thread_key/prefs/muted-логика теперь приведена
    в соответствие и в /api/chat/unread_count (общий nav-badge) выше -- раньше тот
    вообще не различал thread_key-треды (obj:/mangel:/task:) от group."""
    with _chat_lock:
        messages = _load_chat()
        reads = _load_reads()
    meta = _load_chat_thread_meta()
    me = str(user['id'])
    by_thread = {}
    for m in messages:
        if str(m.get('user_id')) == me:
            continue
        tkey = m.get('thread_key')
        if tkey:
            try:
                _check_thread_access(tkey, me, role)
            except HTTPException:
                continue
            thread_key = tkey
            prefs_id = tkey
        else:
            to_uid = m.get('to_user_id')
            if to_uid and str(to_uid) != me:
                continue  # чужой DM
            thread_key = 'group' if not to_uid else str(m['user_id'])
            prefs_id = thread_key if not to_uid else _chat_thread_id(me, thread_key)
        if m.get('ts', 0) <= _thread_last_read(reads, me, thread_key):
            continue
        if _thread_user_prefs(meta, prefs_id, me).get('muted'):
            continue
        by_thread[thread_key] = by_thread.get(thread_key, 0) + 1
    return {"unread_by_thread": by_thread}


@app.post("/api/chat/read")
def mark_chat_read(with_: str = '', thread_key: str = '', user: dict = Depends(get_current_user)):
    key = thread_key or ('group' if not with_ else with_)
    with _chat_lock:
        reads = _load_reads()
        my_id = str(user['id'])
        if not isinstance(reads.get(my_id), dict):
            reads[my_id] = {}
        reads[my_id][key] = int(time.time())
        _save_reads(reads)
    return {"ok": True}


# moved to core/paths.py -- CHAT_ATTACH_DIR
os.makedirs(CHAT_ATTACH_DIR, exist_ok=True)


@app.post("/api/chat/messages/attachment")
def post_chat_attachment(thread_key: str = Form(''), to_user_id: str = Form(''), file: UploadFile = File(...),
                          user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """Фото/файл-вложение в чат (10.27) — отдельный multipart endpoint, т.к. текстовые
    сообщения идут через простой JSON POST /api/chat/messages."""
    if thread_key:
        _check_thread_access(thread_key, str(user['id']), role)
    else:
        _reject_self_chat(user['id'], to_user_id or None)
        _validate_dm_recipient(to_user_id or None)
        thread_id = _chat_thread_id(user['id'], to_user_id or None)
        thread_meta = _load_chat_thread_meta()
        if thread_meta.get(thread_id, {}).get('closed') and role != 'owner':
            raise HTTPException(403, "Чат закрыт руководством")

    data = file.file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Файл слишком большой (макс. 8 МБ)")
    # 30.07 (Release-аудит P0): раньше расширение бралось из имени файла от клиента
    # без проверки содержимого -- любой файл (включая .html/.svg) сохранялся и позже
    # отдавался через FileResponse без nosniff, что выполнялось инлайн в WebView
    # (stored XSS). Теперь: magic-byte allowlist + расширение ТОЛЬКО из этой таблицы.
    sniffed = sniff_chat_attachment(data)
    if sniffed is None:
        raise HTTPException(400, "Недопустимый тип файла")
    _, ext = sniffed
    fname = f'{uuid.uuid4().hex}.{ext}'
    with open(os.path.join(CHAT_ATTACH_DIR, fname), 'wb') as f:
        f.write(data)

    msg = {
        "id": uuid.uuid4().hex,
        "ts": int(time.time()),
        "user_id": user['id'],
        "name": user.get('first_name', str(user['id'])),
        "text": '',
        "to_user_id": to_user_id or None,
        "thread_key": thread_key or None,
        "attachment": {"file": fname, "name": file.filename or fname, "content_type": file.content_type or ''},
    }
    with _chat_lock:
        messages = _load_chat()
        messages.append(msg)
        _save_chat(messages)
    return {"message": msg}


_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


def _transcribe_voice(path: str) -> str:
    model = _get_whisper()
    segments, _ = model.transcribe(path, language=None)
    return ' '.join(s.text.strip() for s in segments).strip()


# moved to core/limits.py -- TRANSCRIBE_MAX_BYTES
# moved to core/paths.py -- TRANSCRIBE_AUDIO_DIR
os.makedirs(TRANSCRIBE_AUDIO_DIR, exist_ok=True)


@app.post("/api/transcribe")
async def transcribe_voice_endpoint(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Голосовой ввод вне чата -- finish-shift wizard (что сделано/доп-работы/
    потребности), создание дефекта/потребности. Аудио хранится (не temp+delete) --
    транскрипция бывает кривой, юзер должен иметь возможность переслушать
    оригинал, не только доверять тексту. Хранится per-user подпапкой, отдаётся
    только владельцу файла или owner (см. GET /api/transcribe/{file_id}/audio)."""
    data = await file.read()
    if len(data) > TRANSCRIBE_MAX_BYTES:
        raise HTTPException(400, "Голосовое слишком большое (макс. 8 МБ)")
    if not data:
        raise HTTPException(400, "Пустой файл")
    # 30.07 (Release-аудит P0): было -- любой файл принимался (только size limit),
    # расширение бралось из клиентского filename без проверки. Magic-byte allowlist.
    detected = sniff_audio(data)
    if detected is None:
        raise HTTPException(400, "Недопустимый формат аудио")
    ext = f'.{_ALLOWED_AUDIO_MIME_EXT[detected]}'

    uid = str(user['id'])
    user_dir = os.path.join(TRANSCRIBE_AUDIO_DIR, uid)
    os.makedirs(user_dir, exist_ok=True)
    file_id = uuid.uuid4().hex
    fpath = os.path.join(user_dir, f'{file_id}{ext}')
    with open(fpath, 'wb') as f:
        f.write(data)

    try:
        raw_transcript = _transcribe_voice(fpath)
    except Exception as e:
        raise HTTPException(502, f"Не удалось распознать голосовое: {str(e)[:200]}")

    if not raw_transcript:
        raise HTTPException(422, "Не удалось разобрать речь в записи — попробуй ещё раз")

    return {
        "raw_transcript": raw_transcript,
        "status": "ok",
        "file_id": file_id,
        "audio_url": f"/api/transcribe/{file_id}/audio",
    }


@app.get("/api/transcribe/{file_id}/audio")
def get_transcribe_audio(file_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    safe_file_id = os.path.basename(file_id)
    if safe_file_id != file_id:
        raise HTTPException(404, "Файл не найден")
    uid = str(user['id'])
    search_dirs = [uid] if role != 'owner' else os.listdir(TRANSCRIBE_AUDIO_DIR) if os.path.isdir(TRANSCRIBE_AUDIO_DIR) else []
    for d in search_dirs:
        user_dir = os.path.join(TRANSCRIBE_AUDIO_DIR, os.path.basename(d))
        if not os.path.isdir(user_dir):
            continue
        for fname in os.listdir(user_dir):
            if fname.startswith(safe_file_id):
                return FileResponse(os.path.join(user_dir, fname))
    raise HTTPException(404, "Файл не найден")


@app.post("/api/chat/messages/voice")
async def post_chat_voice(thread_key: str = Form(''), to_user_id: str = Form(''), file: UploadFile = File(...),
                           user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    if thread_key:
        _check_thread_access(thread_key, str(user['id']), role)
    else:
        _reject_self_chat(user['id'], to_user_id or None)
        _validate_dm_recipient(to_user_id or None)
        thread_id = _chat_thread_id(user['id'], to_user_id or None)
        thread_meta = _load_chat_thread_meta()
        if thread_meta.get(thread_id, {}).get('closed') and role != 'owner':
            raise HTTPException(403, "Чат закрыт руководством")

    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Голосовое слишком большое (макс. 8 МБ)")
    # 30.07 (Release-аудит P0): magic-byte allowlist, расширение из таблицы а не
    # от клиента -- то же обоснование что и в post_chat_attachment выше.
    detected = sniff_audio(data)
    if detected is None:
        raise HTTPException(400, "Недопустимый формат аудио")
    fname = f'{uuid.uuid4().hex}.{_ALLOWED_AUDIO_MIME_EXT[detected]}'
    fpath = os.path.join(CHAT_ATTACH_DIR, fname)
    with open(fpath, 'wb') as f:
        f.write(data)

    try:
        transcript = _transcribe_voice(fpath)
    except Exception as e:
        transcript = ''
        print(f'WARNING: транскрипция голосового не удалась: {e}')

    msg = {
        "id": uuid.uuid4().hex,
        "ts": int(time.time()),
        "user_id": user['id'],
        "name": user.get('first_name', str(user['id'])),
        "text": '',
        "to_user_id": to_user_id or None,
        "thread_key": thread_key or None,
        "attachment": {"file": fname, "name": file.filename or fname, "content_type": file.content_type or 'audio/ogg'},
        "voice_transcript": transcript,
    }
    with _chat_lock:
        messages = _load_chat()
        messages.append(msg)
        _save_chat(messages)
    return {"message": msg}


class ExtractTaskBody(BaseModel):
    text: str
    object_id: str = ''


@app.post("/api/tasks/extract")
def extract_task_from_text(body: ExtractTaskBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """10.37: AI разбирает транскрипт голосового (или любой текст) и предлагает
    title/description для Потребности — НЕ создаёт заявку сама, только предлагает,
    подтверждение — отдельным POST /api/tasks с уже готовыми полями (юзер решил:
    голосовое остаётся в чате, извлечение — явное действие с подтверждением)."""
    if role == 'owner':
        raise HTTPException(403, "Потребности создают работники")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Пустой текст")

    system = (
        "Ты помощник, который извлекает из голосового сообщения строителя запрос на "
        "инструмент/материалы/защиту. Верни СТРОГО валидный JSON без пояснений: "
        '{"title": "короткое название (макс 60 символов)", "description": "детали, если есть"}. '
        'Если в тексте нет реального запроса на что-либо — верни {"title": "", "description": ""}.'
    )
    try:
        raw = _call_glm_json(system, text)
    except Exception as e:
        raise HTTPException(502, f"AI недоступен: {e}")

    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        raise HTTPException(502, "AI вернул не-JSON ответ")
    try:
        parsed = json.loads(m.group(0))
    except Exception:
        raise HTTPException(502, "Не удалось разобрать ответ AI")

    return {"title": parsed.get("title", "")[:200], "description": parsed.get("description", "")[:1000]}


@app.get("/api/chat/attachments/{fname}")
def get_chat_attachment(fname: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    # 30.07 (Release-аудит P0): basename -- fname раньше шёл в os.path.join без
    # проверки, что путь не выходит за пределы CHAT_ATTACH_DIR (owner-путь вообще
    # не имел проверки ниже, только non-owner ветка сверяла msg-принадлежность).
    safe_fname = os.path.basename(fname)
    if safe_fname != fname:
        raise HTTPException(404, "Файл не найден")
    path = os.path.join(CHAT_ATTACH_DIR, safe_fname)
    if not os.path.exists(path):
        raise HTTPException(404, "Файл не найден")
    if role != 'owner':
        # 30.07 (Release-аудит, IDOR): раньше бралось первое сообщение с этим файлом
        # и доступ проверялся только через to_user_id -- ломалось для обектовых/
        # дефектных/task-тредов (thread_key) и для файлов, пересланных в другой чат
        # (после пересылки на файл ссылаются несколько сообщений в разных тредах).
        # Теперь: доступ разрешён, если юзер имеет доступ хотя бы к одному сообщению
        # с этим файлом (через ту же _check_message_access, что и остальные эндпоинты).
        # 31.07 (Release-аудит П7): сообщения старше 7 дней уходят в CHAT_ARCHIVE_FILE
        # (_archive_chat_messages) -- вложение из архивного сообщения раньше не находилось
        # тут вообще (искали только активный _load_chat()), 404 даже для законного участника.
        messages = _load_chat() + _safe_load_json(CHAT_ARCHIVE_FILE, [])
        # attachment key is explicitly None for plain-text messages; `or {}` avoids
        # AttributeError from calling .get() on None (`.get('attachment', {})` only
        # uses the default when the key is ABSENT — not when it's present as None).
        candidates = [m for m in messages if (m.get('attachment') or {}).get('file') == safe_fname]
        if not candidates:
            raise HTTPException(404, "Файл не найден")
        uid = str(user['id'])
        allowed = False
        for msg in candidates:
            try:
                _check_message_access(msg, uid, role)
                allowed = True
                break
            except HTTPException:
                continue
        if not allowed:
            raise HTTPException(403, "Нет доступа к этому файлу")
    # 30.07 (Release-аудит P0): nosniff -- расширение теперь всегда из allowlist
    # (см. sniff_chat_attachment), но nosniff не даёт браузеру угадывать иначе,
    # даже для легаси-вложений, загруженных до этого фикса без magic-byte проверки.
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})


class ChatMessageBody(BaseModel):
    text: str = ''
    to_user_id: str | None = None
    thread_key: str | None = None
    reply_to_id: str | None = None
    location: dict | None = None


def _normalize_chat_location(raw: dict | None) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise HTTPException(400, "Некорректная геолокация")
    try:
        lat = float(raw.get('lat'))
        lon = float(raw.get('lon'))
    except (TypeError, ValueError):
        raise HTTPException(400, "Некорректная геолокация")
    if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(400, "Некорректная геолокация")
    normalized = {"lat": round(lat, 6), "lon": round(lon, 6)}
    if raw.get('accuracy') is not None:
        try:
            accuracy = float(raw.get('accuracy'))
        except (TypeError, ValueError):
            accuracy = None
        if accuracy is not None and math.isfinite(accuracy) and accuracy >= 0:
            normalized["accuracy"] = round(accuracy, 1)
    label = str(raw.get('label') or '').strip()
    if label:
        normalized["label"] = label[:80]
    return normalized


def _reply_snapshot(msg: dict) -> dict:
    """Компактный snapshot цитаты -- хранится в самом сообщении, а не резолвится
    заново из оригинала на каждый рендер, чтобы цитата не ломалась после удаления
    оригинала (пункт 3 задачи)."""
    return {
        "id": msg['id'],
        "name": msg.get('name', ''),
        "preview": _message_preview(msg)[:200],
    }


@app.post("/api/chat/messages")
def post_chat_message(body: ChatMessageBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    text = body.text.strip()
    location = _normalize_chat_location(body.location)
    if not text and not location:
        raise HTTPException(400, "Пустое сообщение")
    if len(text) > 1000:
        raise HTTPException(400, "Сообщение слишком длинное (макс. 1000 символов)")

    if body.thread_key:
        _check_thread_access(body.thread_key, str(user['id']), role)
    else:
        _reject_self_chat(user['id'], body.to_user_id)
        _validate_dm_recipient(body.to_user_id)
        thread_id = _chat_thread_id(user['id'], body.to_user_id)
        thread_meta = _load_chat_thread_meta()
        if thread_meta.get(thread_id, {}).get('closed') and role != 'owner':
            raise HTTPException(403, "Чат закрыт руководством")

    reply_snapshot = None
    if body.reply_to_id:
        with _chat_lock:
            source = next((m for m in _load_chat() if m['id'] == body.reply_to_id), None)
        if source is None:
            raise HTTPException(404, "Исходное сообщение не найдено")
        # Цитировать можно только сообщение из ТОГО ЖЕ треда/DM-пары, что и новое --
        # иначе можно было бы процитировать сообщение из чужого закрытого диалога,
        # просто зная его id (пункт 3 задачи: "нельзя цитировать чужой закрытый DM").
        if (source.get('thread_key') or None) != (body.thread_key or None):
            raise HTTPException(403, "Нельзя цитировать сообщение из другого чата")
        if not body.thread_key:
            source_thread = _chat_thread_id(source['user_id'], source.get('to_user_id'))
            new_thread = _chat_thread_id(user['id'], body.to_user_id)
            if source_thread != new_thread:
                raise HTTPException(403, "Нельзя цитировать сообщение из другого чата")
        reply_snapshot = _reply_snapshot(source)

    msg = {
        "id": uuid.uuid4().hex,
        "ts": int(time.time()),
        "user_id": user['id'],
        "name": user.get('first_name', str(user['id'])),
        "text": text,
        "to_user_id": body.to_user_id,
        "thread_key": body.thread_key,
        "location": location,
        "reply_to": reply_snapshot,
    }
    with _chat_lock:
        messages = _load_chat()
        messages.append(msg)
        _save_chat(messages)
    return {"message": msg}


@app.post("/api/chat/messages/{msg_id}/forward")
def forward_chat_message(msg_id: str, body: ChatMessageBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """Пересылка: копия текста/вложения исходного сообщения в новый чат-назначение,
    с отметкой forwarded_from. Вложение пересылается ссылкой на тот же файл на диске
    (не копия) -- безопасно, потому что раздача /api/chat/attachments/{fname} уже
    проверяет участие в треде ПО САМОМУ СООБЩЕНИЮ (main.py:3457-3463), а не по
    оригинальному, так что после пересылки новое сообщение само становится валидным
    источником доступа к файлу для участников нового треда."""
    uid = str(user['id'])
    with _chat_lock:
        source = next((m for m in _load_chat() if m['id'] == msg_id), None)
    if source is None:
        raise HTTPException(404, "Сообщение не найдено")
    _check_message_access(source, uid, role)

    if body.thread_key:
        _check_thread_access(body.thread_key, uid, role)
    else:
        _reject_self_chat(user['id'], body.to_user_id)
        _validate_dm_recipient(body.to_user_id)
        thread_id = _chat_thread_id(user['id'], body.to_user_id)
        thread_meta = _load_chat_thread_meta()
        if thread_meta.get(thread_id, {}).get('closed') and role != 'owner':
            raise HTTPException(403, "Чат закрыт руководством")

    if not source.get('text') and not source.get('attachment') and not source.get('location'):
        raise HTTPException(400, "Нечего пересылать")

    msg = {
        "id": uuid.uuid4().hex,
        "ts": int(time.time()),
        "user_id": user['id'],
        "name": user.get('first_name', str(user['id'])),
        "text": source.get('text', ''),
        "to_user_id": body.to_user_id,
        "thread_key": body.thread_key,
        "attachment": source.get('attachment'),
        "location": source.get('location'),
        "voice_transcript": source.get('voice_transcript'),
        "forwarded_from": source.get('name', ''),
    }
    with _chat_lock:
        messages = _load_chat()
        messages.append(msg)
        _save_chat(messages)
    return {"message": msg}

@app.delete("/api/chat/messages/{msg_id}")
def delete_chat_message(msg_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    with _chat_lock:
        messages = _load_chat()
        target = next((m for m in messages if m['id'] == msg_id), None)
        if target is None:
            raise HTTPException(404, 'Сообщение не найдено')
        if role != 'owner' and target['user_id'] != user['id']:
            raise HTTPException(403, 'Можно удалять только свои сообщения')
        messages = [m for m in messages if m['id'] != msg_id]
        _save_chat(messages)
    _archive_chat_messages([target])
    reactions = _load_chat_reactions()
    remaining = [r for r in reactions if r['message_id'] != msg_id]
    if len(remaining) != len(reactions):
        _save_chat_reactions(remaining)
    return {"status": "ok"}


@app.delete("/api/chat/threads")
def delete_chat_thread(thread_key: str = '', with_: str = '', user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    # 28.07: owner request -- удалить целый тред (DM с конкретным юзером или obj:/mangel:/
    # task: тред), пропадает у обеих сторон. История не теряется -- те же сообщения,
    # что _archive_chat_messages уже использует для отдельных удалённых сообщений.
    if not thread_key and not with_:
        raise HTTPException(400, "Укажи thread_key или with_")
    with _chat_lock:
        messages = _load_chat()
        if thread_key:
            to_delete = [m for m in messages if m.get('thread_key') == thread_key]
            remaining = [m for m in messages if m.get('thread_key') != thread_key]
        else:
            _reject_self_chat(user['id'], with_)
            _validate_dm_recipient(with_)
            target_thread_id = _chat_thread_id(user['id'], with_)
            to_delete = [
                m for m in messages
                if not m.get('thread_key')
                and _chat_thread_id(m.get('user_id'), m.get('to_user_id')) == target_thread_id
            ]
            deleted_ids = {m['id'] for m in to_delete}
            remaining = [m for m in messages if m['id'] not in deleted_ids]
        _save_chat(remaining)
    _archive_chat_messages(to_delete)
    deleted_ids = {m['id'] for m in to_delete}
    reactions = _load_chat_reactions()
    remaining_reactions = [r for r in reactions if r['message_id'] not in deleted_ids]
    if len(remaining_reactions) != len(reactions):
        _save_chat_reactions(remaining_reactions)
    return {"status": "ok", "deleted_count": len(to_delete)}


def _check_message_access(msg: dict, uid: str, role: str):
    thread_key = msg.get('thread_key')
    if thread_key:
        _check_thread_access(thread_key, uid, role)
        return
    thread_id = _chat_thread_id(msg['user_id'], msg.get('to_user_id'))
    if uid not in _chat_thread_participants(thread_id) and role != 'owner':
        raise HTTPException(403, "Нет доступа к этому сообщению")


class ChatReactionBody(BaseModel):
    reaction: str


@app.post("/api/chat/messages/{msg_id}/reactions")
def toggle_chat_reaction(msg_id: str, body: ChatReactionBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    if body.reaction not in CHAT_REACTION_OPTIONS:
        raise HTTPException(400, "Недопустимая реакция")
    uid = str(user['id'])
    with _chat_lock:
        messages = _load_chat()
        msg = next((m for m in messages if m['id'] == msg_id), None)
        if msg is None:
            raise HTTPException(404, "Сообщение не найдено")
        _check_message_access(msg, uid, role)

        reactions = _load_chat_reactions()
        existing = next((r for r in reactions if r['message_id'] == msg_id and str(r['user_id']) == uid and r['reaction'] == body.reaction), None)
        if existing:
            reactions.remove(existing)
        else:
            reactions.append({"message_id": msg_id, "user_id": uid, "reaction": body.reaction, "created_at": int(time.time())})
        _save_chat_reactions(reactions)
        summary = _reactions_summary_for_message(reactions, msg_id, uid)
    return {"reactions": summary}


class ChatThreadCloseBody(BaseModel):
    to_user_id: str | None = None


def _chat_thread_participants(thread_id: str) -> list:
    if thread_id == 'group':
        roles = _load_roles()
        return list(roles.keys())
    return thread_id.split('-')


# moved to core/constants.py -- DEFAULT_THREAD_PREFS


def _thread_user_prefs(meta: dict, thread_id: str, uid: str) -> dict:
    """Phase 06: mute/pin/archive — per-user (ThreadParticipant), не глобальные для
    треда, в отличие от closed/closed_at/closed_by (те owner-only, глобальные)."""
    prefs = meta.get(thread_id, {}).get('user_prefs', {}).get(uid)
    return {**DEFAULT_THREAD_PREFS, **prefs} if prefs else dict(DEFAULT_THREAD_PREFS)


class ChatThreadPrefsBody(BaseModel):
    to_user_id: str | None = None
    thread_key: str | None = None
    muted: bool | None = None
    pinned: bool | None = None
    archived: bool | None = None


@app.post("/api/chat/threads/prefs")
def set_chat_thread_prefs(body: ChatThreadPrefsBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """Per-user mute/pin/archive toggle. Real data layer (chat_thread_meta.json
    user_prefs) backing the Phase 06 spec's pin/mute/archive requirement -- see
    docs/plan-phases/06-chat-hub-rebuild.md ("не рисовать fake controls, сначала
    строить data layer"). No frontend UI wired to this yet."""
    uid = str(user['id'])
    if body.thread_key:
        _check_thread_access(body.thread_key, uid, role)
        thread_id = body.thread_key
    else:
        _reject_self_chat(user['id'], body.to_user_id)
        _validate_dm_recipient(body.to_user_id)
        thread_id = _chat_thread_id(user['id'], body.to_user_id)

    with _chat_lock:
        meta = _load_chat_thread_meta()
        thread_meta = meta.setdefault(thread_id, {})
        prefs_by_user = thread_meta.setdefault('user_prefs', {})
        current = {**DEFAULT_THREAD_PREFS, **prefs_by_user.get(uid, {})}
        if body.muted is not None:
            current['muted'] = body.muted
        if body.pinned is not None:
            current['pinned'] = body.pinned
        if body.archived is not None:
            current['archived'] = body.archived
        prefs_by_user[uid] = current
        _save_chat_thread_meta(meta)
    return {"status": "ok", "thread_id": thread_id, "prefs": current}


@app.post("/api/chat/threads/close")
def close_chat_thread(body: ChatThreadCloseBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    _reject_self_chat(user['id'], body.to_user_id)
    _validate_dm_recipient(body.to_user_id)
    thread_id = _chat_thread_id(user['id'], body.to_user_id)
    meta = _load_chat_thread_meta()
    # Phase 06: было meta[thread_id] = {...} -- полная перезапись стирала бы
    # user_prefs (mute/pin/archive), добавленные ниже. Мержим, не заменяем.
    thread_meta = meta.setdefault(thread_id, {})
    thread_meta['closed'] = True
    thread_meta['closed_at'] = int(time.time())
    thread_meta['closed_by'] = str(user['id'])
    _save_chat_thread_meta(meta)

    for uid in _chat_thread_participants(thread_id):
        if uid == str(user['id']):
            continue
        try:
            send_telegram_message(int(uid), "🔒 Чат закрыт руководством")
        except Exception:
            pass
    return {"status": "ok", "thread_id": thread_id}


@app.post("/api/chat/threads/reopen")
def reopen_chat_thread(body: ChatThreadCloseBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    _reject_self_chat(user['id'], body.to_user_id)
    _validate_dm_recipient(body.to_user_id)
    thread_id = _chat_thread_id(user['id'], body.to_user_id)
    meta = _load_chat_thread_meta()
    if thread_id in meta:
        meta[thread_id]['closed'] = False
        _save_chat_thread_meta(meta)
    return {"status": "ok", "thread_id": thread_id}


@app.get("/api/chat/threads/status")
def get_chat_thread_status(with_: str = '', user: dict = Depends(get_current_user)):
    thread_id = _chat_thread_id(user['id'], with_ or None)
    meta = _load_chat_thread_meta()
    return meta.get(thread_id, {'closed': False})


# ---------- AI Chat (GLM / Sonnet / Opus, переключаемо) ----------
# GLM — бесплатный, экономит лимиты (z.ai). Sonnet/Opus — через claude CLI по OAuth-подписке владельца.
# Доступ только для owner, rate limit 20 запросов/час.
# moved to core/paths.py -- AI_RATE_FILE
# moved to core/limits.py -- AI_RATE_LIMIT
# moved to core/limits.py -- AI_RATE_WINDOW

# moved to core/paths.py -- AI_MODEL_FILE
# moved to core/constants.py -- AI_MODELS
# moved to core/constants.py -- AI_MODEL_DEFAULT
CLAUDE_BIN = os.environ.get('CLAUDE_BIN', 'claude')

# 03.08 (ТЗ Задача 2, safe freeze): Owner AI (sonnet/opus) запускает `claude` CLI как
# полноценный subprocess с доступом ко всему /home/promonta/agent -- до отдельного
# unix-юзера/read-only checkout/sandbox (следующий раунд, НЕ этот) единственный
# безопасный default для production -- ВЫКЛЮЧЕНО. Owner может включить явно через env,
# осознанно принимая риск, пока sandbox не готов; deploy/production config НЕ должен
# сам проставлять true.
OWNER_AI_ENABLED = os.environ.get('OWNER_AI_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes')

# 03.08: subprocess получает ТОЛЬКО эти переменные, не полный os.environ -- claude CLI
# реально нужен PATH (найти бинарники node/git/etc), HOME (конфиг/кэш ~/.claude),
# ANTHROPIC_API_KEY если используется вместо OAuth-подписки (если её нет в окружении --
# claude CLI работает по уже сохранённому OAuth-токену в HOME, тоже ок). Полный
# os.environ до этого включал BOT_TOKEN/GLM_KEY/DATA_ROOT/все остальные секреты
# процесса -- subprocess их не использует и не должен их видеть.
# moved to core/constants.py -- _OWNER_AI_ENV_ALLOWLIST


def _owner_ai_subprocess_env() -> dict:
    return {k: os.environ[k] for k in _OWNER_AI_ENV_ALLOWLIST if k in os.environ}

AI_SYSTEM_PROMPT = (
    "Ты ИИ-ассистент строительной фирмы Promonta Multiservice UG (Chemnitz, Sachsen, Германия). "
    "Специализация: Trockenbau, Malerarbeiten, Spachtel Q2/Q3, Fliesen, Bodenbelag, WDVS/Fassade. "
    "Клиенты: Bauunternehmen, Hausverwaltungen, частные. "
    "Отвечай кратко и по делу. Внутренние ответы — на русском, тексты клиентам — на деловом немецком."
)


def _get_ai_model() -> str:
    if os.path.exists(AI_MODEL_FILE):
        with open(AI_MODEL_FILE, encoding='utf-8') as f:
            m = json.load(f).get('model', AI_MODEL_DEFAULT)
        if m in AI_MODELS:
            return m
    return AI_MODEL_DEFAULT


def _set_ai_model(model: str):
    if model not in AI_MODELS:
        raise HTTPException(400, f"Неизвестная модель. Доступно: {', '.join(AI_MODELS)}")
    with open(AI_MODEL_FILE, 'w', encoding='utf-8') as f:
        json.dump({'model': model}, f)


def _check_ai_rate(user_id: int, rate_file: str = None, limit: int = None):
    rate_file = rate_file or AI_RATE_FILE
    limit = limit if limit is not None else AI_RATE_LIMIT
    data = {}
    if os.path.exists(rate_file):
        with open(rate_file, encoding='utf-8') as f:
            data = json.load(f)

    uid = str(user_id)
    now = time.time()
    ud = data.get(uid, {"count": 0, "window_start": now})

    if now - ud["window_start"] >= AI_RATE_WINDOW:
        ud = {"count": 0, "window_start": now}

    if ud["count"] >= limit:
        remaining = int(AI_RATE_WINDOW - (now - ud["window_start"]))
        raise HTTPException(429, f"Лимит {limit} запросов/час исчерпан. Сброс через {remaining // 60} мин {remaining % 60} сек")

    ud["count"] += 1
    data[uid] = ud
    with open(rate_file, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def _call_glm(messages: list, system: str = None) -> str:
    glm_key = os.environ.get('GLM_KEY', '')
    if not glm_key:
        raise HTTPException(503, "GLM API не настроен (нет GLM_KEY)")

    payload = {
        "model": "glm-4.5-flash",
        "max_tokens": 1024,
        "system": system if system is not None else AI_SYSTEM_PROMPT,
        "messages": messages,
    }

    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = _urlreq.Request(
        'https://api.z.ai/api/anthropic/v1/messages',
        data=data,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'x-api-key': glm_key,
            'anthropic-version': '2023-06-01',
        }
    )
    try:
        with _urlreq.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return result['content'][0]['text']
    except _urlreq.HTTPError as e:
        err_body = e.read().decode('utf-8')
        raise HTTPException(502, f"GLM API ошибка: {err_body[:300]}")
    except Exception as e:
        raise HTTPException(502, f"GLM API недоступен: {str(e)[:200]}")


def _call_glm_json(system: str, user_text: str) -> str:
    glm_key = os.environ.get('GLM_KEY', '')
    if not glm_key:
        raise HTTPException(503, "GLM API не настроен (нет GLM_KEY)")
    payload = {
        "model": "glm-4.5-flash",
        "max_tokens": 512,
        "system": system,
        "messages": [{"role": "user", "content": user_text}],
    }
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = _urlreq.Request(
        'https://api.z.ai/api/anthropic/v1/messages',
        data=data,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'x-api-key': glm_key,
            'anthropic-version': '2023-06-01',
        }
    )
    with _urlreq.urlopen(req, timeout=45) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    return result['content'][0]['text']


def _messages_to_prompt(messages: list) -> str:
    """claude -p принимает один текстовый prompt, не chat-массив — сворачиваем историю в текст.
    Картинки (image content-блоки) в этом режиме не поддержаны — CLI не читает base64-вложения."""
    parts = [f"[SYSTEM]\n{AI_SYSTEM_PROMPT}"]
    for m in messages:
        role = m.get('role', 'user').upper()
        content = m.get('content')
        if isinstance(content, str):
            text = content
        else:
            text = ' '.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')
        parts.append(f"[{role}]\n{text}")
    return '\n\n'.join(parts)


_claude_cli_lock = __import__('threading').Lock()


def _call_claude_cli(messages: list, model: str) -> str:
    """owner-only agent chat -- полный контекст/permissions осознанно (владелец хочет,
    чтобы этот ассистент видел всё, что видит Claude Code сам). Lock -- не security-
    ограничение, а просто защита от нескольких параллельных 120-секундных subprocess
    (rate limit 20/час уже ограничивает частоту, но не одновременность)."""
    if not OWNER_AI_ENABLED:
        # 03.08 (ТЗ Задача 2): safe freeze -- пока не готов sandbox (отдельный unix-юзер +
        # read-only checkout, следующий раунд), subprocess НЕ запускается вообще.
        raise HTTPException(503, "Owner AI (Sonnet/Opus) временно отключён в production "
                                  "(OWNER_AI_ENABLED=false) -- доступен GLM-режим")
    prompt = _messages_to_prompt(messages)
    if not _claude_cli_lock.acquire(timeout=1):
        raise HTTPException(429, "Уже выполняется другой запрос к Claude — подожди и повтори")
    try:
        r = subprocess.run(
            [CLAUDE_BIN, '-p', '--model', model, prompt],
            cwd='/home/promonta/agent', capture_output=True, stdin=subprocess.DEVNULL,
            text=True, timeout=120, env=_owner_ai_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"Claude ({model}) не ответил за 120 сек")
    except Exception as e:
        raise HTTPException(502, f"Claude CLI недоступен: {str(e)[:200]}")
    finally:
        _claude_cli_lock.release()

    if r.returncode != 0:
        raise HTTPException(502, f"Claude CLI ошибка: {(r.stderr or '')[:300]}")

    reply = (r.stdout or '').strip()
    if not reply:
        raise HTTPException(502, "Claude вернул пустой ответ")
    return reply


def _call_ai(messages: list) -> str:
    model = _get_ai_model()
    if model == 'glm':
        return _call_glm(messages)
    return _call_claude_cli(messages, model)


class AiChatBody(BaseModel):
    messages: list


class AiModelBody(BaseModel):
    model: str


def _is_multimodal_content(content) -> bool:
    return isinstance(content, list)


@app.post("/api/ai-chat")
def ai_chat(body: AiChatBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    if role != 'owner':
        raise HTTPException(403, "Только для владельца")
    if not body.messages:
        raise HTTPException(400, "Нет сообщений")

    for msg in body.messages:
        if not isinstance(msg, dict) or msg.get('role') not in ('user', 'assistant'):
            raise HTTPException(400, "Неверный формат сообщений: {role, content} required")
        content = msg.get('content')
        if isinstance(content, str):
            if len(content) > 8000:
                raise HTTPException(400, "Сообщение слишком длинное")
        elif isinstance(content, list):
            # Мультимодальное сообщение (текст + фото) — Anthropic content-block формат.
            for block in content:
                if not isinstance(block, dict) or block.get('type') not in ('text', 'image'):
                    raise HTTPException(400, "Неверный формат content-блока")
        else:
            raise HTTPException(400, "content должен быть строкой или списком блоков")

    _check_ai_rate(user['id'])
    reply = _call_ai(body.messages)
    return {"reply": reply}


# ---------- AI Chat для worker (узкий, без бизнес-контекста) ----------
# Отдельно от owner-чата: GLM-only (не Claude CLI agent с полным доступом),
# system prompt не содержит имя фирмы/клиентов/финансов -- только общие
# строительные вопросы ("как штукатурить Q2", "как смешать грунтовку").
# Owner explicit decision (2026-07-27): worker не должен видеть чувствительные
# данные фирмы через AI, в отличие от owner-чата, который специально видит
# весь контекст.
# moved to core/paths.py -- WORKER_AI_RATE_FILE
# moved to core/limits.py -- WORKER_AI_RATE_LIMIT

WORKER_AI_SYSTEM_PROMPT = (
    "Ты помощник для строителей. Отвечай только на общие вопросы о строительных "
    "работах: технологии (Trockenbau, Malerarbeiten, Spachtel, Fliesen, Bodenbelag, "
    "WDVS/Fassade), материалы, инструменты, безопасность труда, нормативы. "
    "НЕ обсуждай: конкретные объекты, клиентов, бюджеты, финансы фирмы, зарплаты, "
    "внутренние данные компании -- у тебя нет доступа к этой информации и её не "
    "существует в этом разговоре. Если спросят про конкретный объект/клиента/деньги -- "
    "скажи, что это нужно уточнить у владельца. Отвечай кратко и по делу, на русском."
)


class WorkerAiChatBody(BaseModel):
    messages: list


@app.post("/api/ai-chat/worker")
def worker_ai_chat(body: WorkerAiChatBody, user: dict = Depends(get_current_user)):
    """Доступен всем authenticated (owner тоже может, но это worker-facing UI —
    не ограничиваем по роли, просто этот endpoint сам по себе узкий и безопасный
    для любого юзера, в отличие от /api/ai-chat который owner-only из-за
    Claude CLI agent access."""
    if not body.messages:
        raise HTTPException(400, "Нет сообщений")

    for msg in body.messages:
        if not isinstance(msg, dict) or msg.get('role') not in ('user', 'assistant'):
            raise HTTPException(400, "Неверный формат сообщений: {role, content} required")
        content = msg.get('content')
        if not isinstance(content, str):
            raise HTTPException(400, "content должен быть строкой (без фото/вложений в этом чате)")
        if len(content) > 4000:
            raise HTTPException(400, "Сообщение слишком длинное")

    _check_ai_rate(user['id'], rate_file=WORKER_AI_RATE_FILE, limit=WORKER_AI_RATE_LIMIT)
    reply = _call_glm(body.messages, system=WORKER_AI_SYSTEM_PROMPT)
    return {"reply": reply}


@app.get("/api/ai-model")
def get_ai_model(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    if role != 'owner':
        raise HTTPException(403, "Только для владельца")
    return {"model": _get_ai_model(), "available": list(AI_MODELS)}


@app.post("/api/ai-model")
def set_ai_model(body: AiModelBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    if role != 'owner':
        raise HTTPException(403, "Только для владельца")
    _set_ai_model(body.model)
    return {"model": body.model}


# moved to core/limits.py -- AI_UPLOAD_MAX_BYTES


@app.post("/api/ai-chat/upload")
async def ai_chat_upload(file: UploadFile = File(...), user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    if role != 'owner':
        raise HTTPException(403, "Только для владельца")

    raw = await file.read()
    if len(raw) > AI_UPLOAD_MAX_BYTES:
        raise HTTPException(400, "Файл слишком большой (макс. 8 МБ)")

    filename = file.filename or 'file'
    detected = sniff_image_or_pdf(raw)

    if detected in _ALLOWED_IMAGE_MIME_EXT:
        b64 = base64.b64encode(raw).decode('ascii')
        return {
            "kind": "image",
            "filename": filename,
            "block": {"type": "image", "source": {"type": "base64", "media_type": detected, "data": b64}},
        }

    if detected == 'application/pdf':
        try:
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(raw))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        except Exception as e:
            raise HTTPException(400, f"Не удалось прочитать PDF: {str(e)[:200]}")
        text = text[:12000]
        if not text.strip():
            raise HTTPException(400, "PDF не содержит извлекаемого текста (возможно скан-изображение)")
        return {"kind": "text", "filename": filename, "text": text}

    # Обычный текстовый файл
    try:
        text = raw.decode('utf-8', errors='ignore')[:12000]
    except Exception:
        raise HTTPException(400, "Не удалось прочитать файл как текст")
    if not text.strip():
        raise HTTPException(400, "Файл пуст или в неподдерживаемом формате")
    return {"kind": "text", "filename": filename, "text": text}


# ---------- Этапы объекта ----------
# 10.33: /api/objects/{id}/stages раньше дёргал objekte_lib.all_stages() напрямую —
# живой Google Sheets запрос на КАЖДЫЙ объект, каждый вызов. Home dashboard теперь
# грузит progress-ring параллельно для до 6 объектов разом (Promise.all) — это до
# 12 живых Sheets-запросов на одну загрузку Home, что провоцирует квота-сбои/HTTP 500.
# all_stages() читает один и тот же лист 'Этапы' целиком и фильтрует локально —
# значит можно закэшировать сырые строки листа через тот же _cached_get_used_range,
# который уже используют list_objects/get_alerts, и фильтровать по object_id из кэша.
def _cached_all_stages(object_id: str) -> list:
    o = _load_repo_objekte_lib()
    values = _cached_get_used_range('Этапы')
    if not values:
        return []
    headers = values[0]
    rows = []
    for i, r in enumerate(values[1:], start=2):
        if r and r[0].strip().upper() == object_id.strip().upper():
            d = o._row_to_dict(headers, r)
            d['_row'] = i
            rows.append(d)
    rows.sort(key=lambda d: int(d.get('№ этапа') or 0))
    return rows


@app.get("/api/objects/{object_id}/stages")
def get_stages(object_id: str, user: dict = Depends(get_current_user)):
    # 28.07: owner request -- любой воркер может просматривать этапы любого объекта
    # (не только назначенных), не требует can_access_object.
    return {"stages": _cached_all_stages(object_id)}


class NewStageBody(BaseModel):
    name: str
    description: str = ''


@app.post("/api/objects/{object_id}/stages")
def create_stage(object_id: str, body: NewStageBody, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    # 31.07 (Release-аудит П3): раньше любой авторизованный worker мог создать этап на
    # ЛЮБОМ объекте, не только назначенном -- require_object_access ограничивает записью
    # только для owner или worker с accepted-назначением на этот object_id (см.
    # can_access_object выше, тот же принцип что уже применён к другим stage-mutation
    # эндпоинтам этого файла).
    o = _load_repo_objekte_lib()
    if not body.name.strip():
        raise HTTPException(400, "Name erforderlich")
    num = o.add_stage(object_id, body.name.strip(), body.description.strip()[:2000])
    o.sync_current_stage(object_id)
    return {"stage_num": num}


class StageDescriptionBody(BaseModel):
    description: str


@app.patch("/api/objects/{object_id}/stages/{row_num}/description")
def update_stage_description_endpoint(object_id: str, row_num: int, body: StageDescriptionBody, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    # 31.07 (Release-аудит П3): не owner-only (сохраняем прежнее намерение -- любой
    # НАЗНАЧЕННЫЙ worker может редактировать), но require_object_access закрывает дыру,
    # когда worker без accepted-назначения на объект мог менять описание этапа на чужом.
    o = _load_repo_objekte_lib()
    try:
        o.update_stage_description(row_num, body.description.strip()[:2000])
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "ok"}


class StageStatusBody(BaseModel):
    status: str


@app.patch("/api/objects/{object_id}/stages/{row_num}")
def update_stage(object_id: str, row_num: int, body: StageStatusBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    o = _load_repo_objekte_lib()
    try:
        o.update_stage_status(row_num, body.status, business_today_str())  # 03.08 (ТЗ Задача 5): было date.today() (UTC)
    except ValueError as e:
        raise HTTPException(400, str(e))
    o.sync_current_stage(object_id)
    return {"status": "ok"}


@app.delete("/api/objects/{object_id}/stages/{row_num}")
def remove_stage(object_id: str, row_num: int, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    o = _load_repo_objekte_lib()
    try:
        o.delete_stage(object_id, row_num)
    except ValueError as e:
        raise HTTPException(404, str(e))
    o.sync_current_stage(object_id)
    return {"status": "ok"}


class StageSwapBody(BaseModel):
    row_num_b: int


@app.patch("/api/objects/{object_id}/stages/{row_num}/swap")
def swap_stage(object_id: str, row_num: int, body: StageSwapBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    o = _load_repo_objekte_lib()
    try:
        o.swap_stage_order(object_id, row_num, body.row_num_b)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok"}


# 29.07 v2 (feature freeze -- откат review/rework): /complete восстановлен, worker
# снова сам жмёт "Готово". Blocker остаётся, но НЕ меняет статус этапа -- отдельный
# badge поверх (см. /stages/{row}/blocker ниже).
@app.post("/api/objects/{object_id}/stages/{row_num}/complete")
def worker_complete_stage(object_id: str, row_num: int, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    o = _load_repo_objekte_lib()
    try:
        o.worker_complete_stage(object_id, row_num, str(user['id']), business_today_str())  # 03.08 (ТЗ Задача 5): было date.today() (UTC)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok"}


class StageBlockerBody(BaseModel):
    quick_reason: str = ''
    comment: str = ''
    photo_url: str = ''
    who_decides: str = ''
    expected_date: str = ''


@app.post("/api/objects/{object_id}/stages/{row_num}/blocker")
def set_stage_blocker(object_id: str, row_num: int, body: StageBlockerBody,
                       user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    # 29.07 v2: "Сообщить о проблеме" -- badge, НЕ статус этапа. Статус остаётся
    # предстоит/в процессе/готово независимо от наличия blocker.
    if not (body.quick_reason.strip() or body.comment.strip()):
        raise HTTPException(400, "Укажите причину")
    stage = _find_stage_by_row(object_id, row_num)
    stage_key = stage['ID строки этапа']

    def _mutate(store):
        return rl.set_stage_block_meta(
            store, stage_key, None, str(user['id']),
            quick_reason=body.quick_reason, comment=body.comment, photo_url=body.photo_url,
            who_decides=body.who_decides, expected_date=body.expected_date,
        )
    meta = update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)
    return {"status": "ok", "meta": meta}


@app.delete("/api/objects/{object_id}/stages/{row_num}/blocker")
def clear_stage_blocker(object_id: str, row_num: int, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    stage = _find_stage_by_row(object_id, row_num)
    stage_key = stage['ID строки этапа']

    def _mutate(store):
        rl.clear_stage_block_meta(store, stage_key)
        return {"status": "ok"}
    return update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)


# ---------- План работ (Roadmap) — 29.07, Этап 1 ----------
# Stage identity/order/status/description остаются в Google Sheets (objekte_lib.py) --
# roadmap_lib.py добавляет только то, чего там нет: чек-лист категорий/пунктов, заметки,
# и очередь запросов worker->owner на структурные изменения существующего этапа.
# 31.07 (Release-аудит П2): было `import roadmap_lib as rl` через глобальный sys.path --
# заменено на изолированный loader (см. _load_repo_roadmap_lib выше), гарантирующий
# repo-файл, не untracked-копию на диске сервера.
rl = _load_repo_roadmap_lib()


def _load_roadmap_store() -> dict:
    """Read-only helper -- ТОЛЬКО для GET-эндпоинтов ниже. Любая мутация store должна
    идти через update_json_transaction(rl.ROADMAP_FILE, ...), не через эту функцию +
    отдельный _atomic_write_json (та же read-modify-write гонка, что update_json_transaction
    существует чтобы закрыть -- см. его docstring выше)."""
    return _safe_load_json(rl.ROADMAP_FILE, rl._default_store())


def _load_stage_requests() -> list:
    """Read-only helper -- см. предупреждение у _load_roadmap_store() выше, тот же принцип."""
    return _safe_load_json(rl.STAGE_REQUESTS_FILE, rl._default_requests())


def _find_stage_by_row(object_id: str, row_num: int) -> dict:
    """Общая проверка для все roadmap-эндпоинтов ниже -- этап должен реально
    существовать и принадлежать этому объекту, иначе 404 (не создаём roadmap-данные
    для несуществующего/чужого этапа)."""
    o = _load_repo_objekte_lib()
    stages = o.all_stages(object_id)
    stage = next((s for s in stages if s['_row'] == row_num), None)
    if not stage:
        raise HTTPException(404, "Этап не найден")
    return stage


# moved to core/paths.py -- BLOCKER_PHOTO_DIR
os.makedirs(BLOCKER_PHOTO_DIR, exist_ok=True)


@app.post("/api/objects/{object_id}/blocker-photo")
async def upload_blocker_photo(object_id: str, file: UploadFile = File(...),
                                user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    # 29.07 (аудит): blocker sheet заявлял поле фото, но реального upload не было --
    # тот же паттерн, что и остальные фото-эндпоинты (sniff_image, размер-лимит).
    # photo_url -- относительный путь к get_blocker_photo ниже, не прямая файловая ссылка
    # (доступ к самому файлу тоже идёт через require_object_access, не голый static serve).
    raw = await file.read()
    if len(raw) > PHOTO_MAX_BYTES:
        raise HTTPException(400, "Фото слишком большое (макс. 8 МБ)")
    detected = sniff_image(raw)
    if not detected:
        raise HTTPException(400, "Файл должен быть изображением")
    ext = _ALLOWED_IMAGE_MIME_EXT[detected]
    fname = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(BLOCKER_PHOTO_DIR, fname), 'wb') as out:
        out.write(raw)
    return {"photo_url": f"/api/objects/{object_id}/blocker-photo/{fname}"}


@app.get("/api/objects/{object_id}/blocker-photo/{fname}")
def get_blocker_photo(object_id: str, fname: str, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    if '/' in fname or '..' in fname:
        raise HTTPException(400, "Некорректное имя файла")
    path = os.path.join(BLOCKER_PHOTO_DIR, fname)
    if not os.path.exists(path):
        raise HTTPException(404, "Файл отсутствует")
    from fastapi.responses import FileResponse
    return FileResponse(path)


@app.get("/api/objects/{object_id}/stages/{row_num}/roadmap")
def get_stage_roadmap(object_id: str, row_num: int, user: dict = Depends(get_current_user)):
    """Полный чек-лист (категории+пункты+прогресс) одного этапа одним запросом --
    не N+1 (ТЗ п.47). Доступ: та же политика, что у get_stages -- любой авторизованный
    воркер может просматривать (owner request 28.07), не только назначенный на объект."""
    stage = _find_stage_by_row(object_id, row_num)
    store = _load_roadmap_store()
    snapshot = rl.stage_snapshot(store, stage['ID строки этапа'])
    snapshot['stage'] = stage
    return snapshot


class RoadmapCategoryBody(BaseModel):
    title: str


@app.post("/api/objects/{object_id}/stages/{row_num}/roadmap/categories")
def create_roadmap_category(object_id: str, row_num: int, body: RoadmapCategoryBody,
                             user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    # 29.07: только owner меняет структуру (категории/reorder) -- worker-approval-flow
    # ниже касается delete/status-change СУЩЕСТВУЮЩЕГО этапа, не категорий/пунктов внутри
    # него (владелец не просил approval для этого уровня, только для самого этапа).
    stage = _find_stage_by_row(object_id, row_num)
    if not body.title.strip():
        raise HTTPException(400, "Название категории обязательно")
    # 29.07: read-modify-write под одним локом (update_json_transaction) -- та же гонка,
    # что уже закрыта для object photo upload/assign в этом файле (28.07, real bug found
    # by external audit). Два owner'а/два запроса одновременно не должны затирать
    # изменения друг друга в roadmap.json.
    return update_json_transaction(
        rl.ROADMAP_FILE, rl._default_store,
        lambda store: rl.new_category(store, stage['ID строки этапа'], body.title.strip()[:100]),
    )


@app.delete("/api/objects/{object_id}/stages/{row_num}/roadmap/categories/{category_id}")
def delete_roadmap_category(object_id: str, row_num: int, category_id: str,
                             user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    stage = _find_stage_by_row(object_id, row_num)
    stage_key = stage['ID строки этапа']

    def _mutate(store):
        has_items = any(i.get('category_id') == category_id for i in store['items'].get(stage_key, []))
        if has_items:
            raise HTTPException(400, "Нельзя удалить категорию с пунктами -- сначала перенесите или удалите их")
        if not rl.delete_category(store, stage_key, category_id):
            raise HTTPException(404, "Категория не найдена")
        return {"status": "ok"}

    return update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)


class RoadmapItemCreateBody(BaseModel):
    title: str
    category_id: str | None = None
    description: str = ''
    required: bool = True
    safety_critical: bool = False
    weight: int = 1


@app.post("/api/objects/{object_id}/stages/{row_num}/roadmap/items")
def create_roadmap_item(object_id: str, row_num: int, body: RoadmapItemCreateBody,
                         user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    stage = _find_stage_by_row(object_id, row_num)
    if not body.title.strip():
        raise HTTPException(400, "Название пункта обязательно")
    stage_key = stage['ID строки этапа']
    return update_json_transaction(
        rl.ROADMAP_FILE, rl._default_store,
        lambda store: rl.new_item(
            store, stage_key, body.title.strip()[:200], category_id=body.category_id,
            description=body.description.strip()[:1000], required=body.required,
            safety_critical=body.safety_critical, weight=body.weight,
        ),
    )


class RoadmapItemEditBody(BaseModel):
    title: str | None = None
    description: str | None = None
    required: bool | None = None
    safety_critical: bool | None = None
    weight: int | None = None
    category_id: str | None = None


@app.patch("/api/objects/{object_id}/stages/{row_num}/roadmap/items/{item_id}")
def edit_roadmap_item(object_id: str, row_num: int, item_id: str, body: RoadmapItemEditBody,
                       user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    stage = _find_stage_by_row(object_id, row_num)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    stage_key = stage['ID строки этапа']

    def _mutate(store):
        item = rl.edit_item(store, stage_key, item_id, **fields)
        if not item:
            raise HTTPException(404, "Пункт не найден")
        return item

    return update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)


@app.delete("/api/objects/{object_id}/stages/{row_num}/roadmap/items/{item_id}")
def delete_roadmap_item(object_id: str, row_num: int, item_id: str,
                         user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    stage = _find_stage_by_row(object_id, row_num)
    stage_key = stage['ID строки этапа']

    def _mutate(store):
        if not rl.delete_item(store, stage_key, item_id):
            raise HTTPException(404, "Пункт не найден")
        return {"status": "ok"}

    return update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)


# 29.07 v2 (feature freeze): checklist упрощён до open/done, никакого blocker на
# уровне пункта -- только простой toggle.
class RoadmapItemStatusBody(BaseModel):
    status: str


@app.post("/api/objects/{object_id}/stages/{row_num}/roadmap/items/{item_id}/status")
def update_roadmap_item_status(object_id: str, row_num: int, item_id: str, body: RoadmapItemStatusBody,
                                user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    stage = _find_stage_by_row(object_id, row_num)
    stage_key = stage['ID строки этапа']

    def _mutate(store):
        try:
            item = rl.update_item_status(store, stage_key, item_id, body.status, str(user['id']))
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not item:
            raise HTTPException(404, "Пункт не найден")
        return item

    return update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)


class RoadmapNoteBody(BaseModel):
    text: str
    item_id: str | None = None


@app.post("/api/objects/{object_id}/stages/{row_num}/roadmap/notes")
def create_roadmap_note(object_id: str, row_num: int, body: RoadmapNoteBody,
                         user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    stage = _find_stage_by_row(object_id, row_num)
    if not body.text.strip():
        raise HTTPException(400, "Текст заметки обязателен")
    profile = _get_worker_profile(user['id'])
    author_name = _sanitize_display_name(profile.get('name'), str(user['id']))
    stage_key = stage['ID строки этапа']
    return update_json_transaction(
        rl.ROADMAP_FILE, rl._default_store,
        lambda store: rl.new_note(store, stage_key, str(user['id']), author_name, body.text, item_id=body.item_id),
    )


@app.get("/api/objects/{object_id}/stages/{row_num}/roadmap/notes")
def list_roadmap_notes(object_id: str, row_num: int, item_id: str = '', user: dict = Depends(get_current_user)):
    # 30.07 (Release-аудит P1-6): нет require_object_access -- согласовано с
    # GET /api/objects/{object_id}/stages и GET .../roadmap (оба тоже открыты
    # любому авторизованному по документированному 28.07 owner-решению: "любой
    # worker может просматривать этапы/roadmap любого объекта"). POST на этот же
    # ресурс требует require_object_access -- писать может только назначенный,
    # читать может любой. Не меняем в рамках feature freeze.
    stage = _find_stage_by_row(object_id, row_num)
    store = _load_roadmap_store()
    notes = rl.stage_notes(store, stage['ID строки этапа'], item_id=item_id or None)
    return {"notes": sorted(notes, key=lambda n: n['created_at'])}


# ── Stage change requests -- worker→owner approval для delete/change-status этапа ──
# Owner decision (29.07): worker свободно создаёт этапы (как сейчас), но delete/смена
# статуса существующего этапа теперь идёт через запрос, который owner подтверждает --
# "через алерт", переиспользуем существующий critical_alerts push+ack механизм, не
# строим новый UI-канал.
class StageRequestBody(BaseModel):
    kind: str
    new_status: str = ''  # только для kind='change_status'


@app.post("/api/objects/{object_id}/stages/{row_num}/request")
def create_stage_request(object_id: str, row_num: int, body: StageRequestBody,
                          user: dict = Depends(get_current_user), role: str = Depends(get_role),
                          _: None = Depends(require_object_access)):
    o = _load_repo_objekte_lib()
    if role == 'owner':
        raise HTTPException(400, "Owner меняет этапы напрямую, без запроса")
    stage = _find_stage_by_row(object_id, row_num)
    if body.kind not in rl.REQUEST_KINDS:
        raise HTTPException(400, "Недопустимый тип запроса")
    payload = {}
    if body.kind == 'change_status':
        if body.new_status not in o.VALID_STAGE_STATUS:
            raise HTTPException(400, "Недопустимый статус")
        payload['new_status'] = body.new_status

    profile = _get_worker_profile(user['id'])
    requester_name = _sanitize_display_name(profile.get('name'), str(user['id']))
    stage_key = stage['ID строки этапа']
    req = update_json_transaction(
        rl.STAGE_REQUESTS_FILE, rl._default_requests,
        lambda requests: rl.new_stage_request(
            requests, object_id, stage_key, row_num, body.kind,
            str(user['id']), requester_name, payload=payload,
        ),
    )

    roles = _load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    if owner_id:
        kind_label = 'удаление этапа' if body.kind == 'delete_stage' else f"смену статуса на «{payload.get('new_status', '')}»"
        alert = _create_critical_alert(
            target_user_id=owner_id, kind='stage_request',
            title=f"{requester_name} просит {kind_label}",
            subtitle=stage.get('Название этапа', ''), ref_id=req['id'],
        )
        req['critical_alert_id'] = alert['id']

        def _attach_alert(requests):
            r = rl.find_stage_request(requests, req['id'])
            if r:
                r['critical_alert_id'] = alert['id']
            return r
        update_json_transaction(rl.STAGE_REQUESTS_FILE, rl._default_requests, _attach_alert)
    return req


@app.get("/api/objects/{object_id}/stages/requests")
def list_stage_requests(object_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    requests = _load_stage_requests()
    return {"requests": rl.pending_requests_for_object(requests, object_id)}


class StageRequestDecisionBody(BaseModel):
    approve: bool


@app.post("/api/objects/{object_id}/stages/requests/{request_id}/decide")
def decide_stage_request_endpoint(object_id: str, request_id: str, body: StageRequestDecisionBody,
                                   user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    o = _load_repo_objekte_lib()

    # Проверка существования/принадлежности -- read-only, до транзакции (тот же паттерн,
    # что _find_stage_by_row -- отдельно от самой мутации).
    existing = _load_stage_requests()
    pre_check = rl.find_stage_request(existing, request_id)
    if not pre_check or pre_check['object_id'] != object_id:
        raise HTTPException(404, "Запрос не найден")

    def _mutate(requests):
        decided = rl.decide_stage_request(requests, request_id, body.approve, str(user['id']))
        if not decided:
            raise HTTPException(400, "Запрос уже обработан")
        return decided

    decided = update_json_transaction(rl.STAGE_REQUESTS_FILE, rl._default_requests, _mutate)

    # Google Sheets запись -- НАМЕРЕННО вне JSON-лока выше (сетевой вызов, не должен
    # держать файловый лок дольше необходимого). Если статус запроса уже помечен approved,
    # но эта часть упадёт -- запрос не откатывается автоматически (best-effort, тот же
    # trade-off что и остальные Sheets-зеркала в этом файле), owner увидит ошибку и может
    # применить изменение вручную через обычный owner-only stage endpoint.
    if body.approve:
        try:
            if decided['kind'] == 'delete_stage':
                o.delete_stage(decided['object_id'], decided['stage_row'])
                o.sync_current_stage(decided['object_id'])
            elif decided['kind'] == 'change_status':
                o.update_stage_status(decided['stage_row'], decided['payload']['new_status'], business_today_str())  # 03.08 (ТЗ Задача 5): было date.today() (UTC)
                o.sync_current_stage(decided['object_id'])
        except ValueError as e:
            raise HTTPException(400, str(e))

    try:
        send_telegram_message(int(decided['requested_by']),
                               f"{'Одобрено' if body.approve else 'Отклонено'}: ваш запрос по этапу «{decided.get('stage_row')}»")
    except Exception:
        pass
    return decided


# ---------- Потребности (10.33) — worker → owner запросы (инструмент/материалы/защита) ----------
# moved to core/paths.py -- TASKS_FILE
def _load_tasks() -> list:
    return _safe_load_json(TASKS_FILE, [])


def _save_tasks(items: list):
    _atomic_write_json(TASKS_FILE, items)


# moved to core/constants.py -- TASK_PRIORITIES

# 27.07 (B7): категория запроса -- material/tool/ppe/access/other, отдельно от
# priority. Ключи латиницей (стабильный API contract), label для UI -- по месту рендера.
# moved to core/constants.py -- TASK_CATEGORIES


class TaskCreateBody(BaseModel):
    title: str
    description: str = ''
    object_id: str = ''
    priority: str = 'обычная'
    category: str = 'other'
    due_at: int | None = None


class TaskStatusBody(BaseModel):
    status: str


# 27.07 (B7): расширено с 3 до полного набора из плана (NEW/ACKNOWLEDGED/IN_PROGRESS/
# ORDERED/DELIVERED/DECLINED/CANCELLED) -- старые значения ('открыто','в работе','закрыто')
# сохранены как есть для обратной совместимости с уже существующими записями в tasks.json,
# новые статусы добавлены поверх, не переименовывая старые.
# moved to core/constants.py -- TASK_STATUSES


def _task_is_open(task: dict) -> bool:
    return task.get('status') not in ('закрыто', 'выдано', 'отклонено', 'cancelled')


def _normalize_task_due_at(raw_due_at) -> int | None:
    if raw_due_at in (None, ''):
        return None
    try:
        due_at = int(raw_due_at)
    except (TypeError, ValueError):
        raise HTTPException(400, "Некорректный срок задачи")
    if due_at <= 0:
        raise HTTPException(400, "Некорректный срок задачи")
    if due_at < int(time.time()) - 60:
        raise HTTPException(400, "Срок задачи не может быть в прошлом")
    return due_at


def _format_due_at(due_at: int) -> str:
    try:
        return datetime.fromtimestamp(int(due_at), business_now().tzinfo).strftime('%d.%m %H:%M')
    except Exception:
        return ''


def _overdue_task_alerts(now: int | None = None) -> list:
    now = int(time.time()) if now is None else int(now)
    result = []
    for task in _load_tasks():
        if not _task_is_open(task):
            continue
        try:
            due_at = int(task.get('due_at') or 0)
        except (TypeError, ValueError):
            continue
        if due_at <= 0 or due_at > now:
            continue
        title = (task.get('title') or 'Потребность')[:80]
        parts = []
        if task.get('object_id'):
            parts.append(str(task.get('object_id')))
        due_label = _format_due_at(due_at)
        if due_label:
            parts.append(f'срок {due_label}')
        if task.get('from_name') or task.get('from_user_id'):
            parts.append(f"запросил {task.get('from_name') or task.get('from_user_id')}")
        result.append({
            'id': f'task-overdue-{task.get("id", "")}',
            'type': 'red',
            'role_filter': 'owner',
            'title': f'Просрочена потребность: {title}',
            'subtitle': ' · '.join(parts),
            'at': due_at,
            'task_id': task.get('id', ''),
            'task_overdue': True,
        })
    return result


@app.get("/api/tasks")
def list_tasks(object_id: str = '', user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    # 03.08 (ТЗ Задача 4): worker с object_id должен иметь активный доступ к этому
    # конкретному объекту -- раньше ЛЮБОЙ whitelisted worker мог передать чужой
    # object_id и увидеть командную видимость Потребностей объекта, на который его
    # никогда не назначали (get_current_user проверяет только whitelist, не привязку
    # к объекту). Запрос БЕЗ object_id не трогаем -- он и так уже сужен до "только
    # свои" двумя строками ниже, никакой object-level дыры там нет.
    if object_id and role != 'owner' and not has_active_object_access(str(user['id']), object_id):
        raise HTTPException(403, "Нет доступа к этому объекту")

    items = _load_tasks()
    # 25.07: object_id передан -- worker смотрит вкладку Потребности ВНУТРИ конкретного
    # объекта, там нужна командная видимость (как в чате объекта), не только свои заявки.
    # Без object_id -- это глобальный экран Потребности, там worker видит только свои
    # (иначе он видит чужие материальные запросы по всем объектам сразу, что не нужно).
    if role != 'owner' and not object_id:
        items = [t for t in items if str(t.get('from_user_id')) == str(user['id'])]
    if object_id:
        items = [t for t in items if t.get('object_id') == object_id]
    return {"tasks": sorted(items, key=lambda t: (t.get('priority') != 'срочно', -t.get('created_at', 0)))}


@app.post("/api/tasks")
def create_task(body: TaskCreateBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    if role == 'owner':
        raise HTTPException(403, "Потребности создают работники")
    if not body.title.strip():
        raise HTTPException(400, "Название обязательно")
    if not body.object_id.strip():
        raise HTTPException(400, "Объект обязателен")
    # 03.08 (ТЗ Задача 4): worker может создать потребность только на объекте, к
    # которому у него активный доступ -- раньше object_id принимался как есть без
    # проверки, worker мог создать заявку (видимую всей команде объекта) на объект,
    # к которому вообще не назначен.
    if not has_active_object_access(str(user['id']), body.object_id.strip()):
        raise HTTPException(403, "Нет доступа к этому объекту")
    priority = body.priority.strip() or 'обычная'
    if priority not in TASK_PRIORITIES:
        raise HTTPException(400, "Недопустимый приоритет")
    category = body.category.strip() or 'other'
    if category not in TASK_CATEGORIES:
        raise HTTPException(400, "Недопустимая категория")
    due_at = _normalize_task_due_at(body.due_at)
    roles = _load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    profile = _get_worker_profile(user['id'])
    task = {
        'id': uuid.uuid4().hex,
        'type': 'request',
        'from_user_id': str(user['id']),
        'from_name': _sanitize_display_name(profile.get('name'), str(user['id'])),
        'to_user_id': owner_id,
        'object_id': body.object_id.strip(),
        'title': body.title.strip()[:200],
        'description': body.description.strip()[:1000],
        'priority': priority,
        'category': category,
        'status': 'открыто',
        'created_at': int(time.time()),
        'due_at': due_at,
        'closed_at': None,
    }
    with _lock_for(TASKS_FILE):
        items = _load_tasks()
        items.append(task)
        _save_tasks(items)
    if owner_id:
        try:
            urgent_prefix = "🔴 СРОЧНО! " if priority == 'срочно' else "📋 "
            send_telegram_message(int(owner_id), f"{urgent_prefix}Новая потребность от {task['from_name']}: {task['title']}")
        except Exception:
            pass
    return task


@app.patch("/api/tasks/{task_id}")
def update_task_status(task_id: str, body: TaskStatusBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    if body.status not in TASK_STATUSES:
        raise HTTPException(400, "Недопустимый статус")

    with _lock_for(TASKS_FILE):
        items = _load_tasks()
        task = next((t for t in items if t['id'] == task_id), None)
        if not task:
            raise HTTPException(404, "Потребность не найдена")
        prev_status = task.get('status')
        task['status'] = body.status
        if body.status == 'закрыто':
            task['closed_at'] = int(time.time())
        else:
            task['closed_at'] = None
        _save_tasks(items)

    # 04.08 (Раунд 3, задача 5.2): РАНЬШЕ закрытая потребность удалялась из JSON
    # (архив только в Sheets) -- из-за этого экран Потребности не мог показать
    # счётчик "Выполнены N" и фильтр "Выполненные". Теперь закрытые ОСТАЮТСЯ в JSON
    # со статусом 'закрыто'+closed_at (фронт по умолчанию показывает только активные),
    # архив в Sheets сохраняется best-effort, но только при ПЕРВОМ закрытии
    # (prev_status != 'закрыто'), чтобы не дублировать строки при повторном PATCH.
    if body.status == 'закрыто' and prev_status != 'закрыто':
        try:
            o = _load_repo_objekte_lib()
            from datetime import datetime
            created_str = datetime.fromtimestamp(task.get('created_at', 0)).strftime('%Y-%m-%d %H:%M') if task.get('created_at') else ''
            closed_str = datetime.fromtimestamp(task['closed_at']).strftime('%Y-%m-%d %H:%M')
            o.append_row_safe('Потребности', [
                task.get('id', ''), task.get('object_id', ''), task.get('title', ''),
                task.get('description', ''), task.get('category', ''), task.get('priority', ''),
                task.get('from_name', task.get('from_user_id', '')), created_str, closed_str,
            ])
        except Exception as e:
            print(f'WARNING: не удалось заархивировать потребность {task_id} в Sheets: {e}')
    return task


# ---------- Mängelmanagement — Фаза 3 ----------
# 30.07 (Release-аудит P1): было `import mangel_lib as ml` -- обычный import
# зависит от глобального sys.path (см. _load_repo_mangel_lib выше). Изолированная
# загрузка по точному пути, ml остаётся module-level именем как раньше -- все
# вызовы ml.xxx() ниже по файлу не меняются.
ml = _load_repo_mangel_lib()

# moved to core/paths.py -- MANGEL_PHOTO_DIR


class MangelStatusBody(BaseModel):
    status: str


class MangelCommentBody(BaseModel):
    text: str


def require_mangel_access(ticket_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """28.07: owner request -- любой воркер видит/комментирует дефект любого объекта,
    не только назначенный. Резолвит только существование тикета, не access-проверку."""
    try:
        ml.get_ticket(ticket_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


def _enrich_mangel_tickets_with_author(tickets: list) -> list:
    # 28.07: owner request -- "фиксация кто добавил дефект" уже была на бэкенде
    # (created_by в mangel_lib), но фронтенд её не показывал -- не было имени,
    # только сырой user_id. Резолвим здесь, а не в mangel_lib.py (тот файл живёт
    # вне git-репо, прямые prod-правки там рискованны -- см. HANDOFF).
    profiles = _load_worker_profiles()
    for t in tickets:
        created_by = t.get('created_by')
        if created_by:
            t['created_by_name'] = _sanitize_display_name(profiles.get(str(created_by), {}).get('name'), str(created_by))
        # 04.08 (Раунд 3, задача 3.1/4): резолвим имя ответственного (назначенного)
        # работника, чтобы UI показывал "Ответственный: Иван", а не сырой user_id.
        assigned = t.get('assigned_worker_id')
        if assigned:
            t['assigned_worker_name'] = _sanitize_display_name(profiles.get(str(assigned), {}).get('name'), str(assigned))
    return tickets


@app.get("/api/mangel")
def get_mangel_list(object_id: str = '', user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    # 28.07: owner request -- любой воркер видит дефекты любого объекта, не только
    # назначенного. Раньше worker без object_id получал только дефекты своих объектов.
    tickets = _enrich_mangel_tickets_with_author(ml.list_tickets(object_id or None))
    return {"tickets": tickets, "total": len(tickets)}


@app.get("/api/mangel/counts")
def get_mangel_counts(user: dict = Depends(get_current_user)):
    return ml.count_by_status()


@app.get("/api/mangel/{ticket_id}")
def get_mangel_ticket(ticket_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_mangel_access)):
    try:
        return _enrich_mangel_tickets_with_author([ml.get_ticket(ticket_id)])[0]
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/api/mangel")
async def create_mangel_ticket(
    object_id: str = Form(''),
    description: str = Form(''),
    assigned_worker_id: str = Form(''),
    file: UploadFile = File(None),
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
):
    # 28.07: owner request -- любой воркер может добавить дефект на любом объекте.
    if not description.strip():
        raise HTTPException(400, "Описание обязательно")

    photo_paths: list = []
    if file and file.filename:
        raw = await file.read()
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(400, "Фото слишком большое (макс. 8 МБ)")
        detected = sniff_image(raw)
        if not detected:
            raise HTTPException(400, "Файл должен быть изображением")
        ext = _ALLOWED_IMAGE_MIME_EXT[detected]
        photo_id = __import__('uuid').uuid4().hex
        fname = f"mangel_{photo_id}.{ext}"
        with open(os.path.join(MANGEL_PHOTO_DIR, fname), 'wb') as f_out:
            f_out.write(raw)
        photo_paths.append(fname)

    ticket = ml.create_ticket(
        object_id=object_id.strip()[:100],
        description=description.strip()[:500],
        created_by=str(user['id']),
        photo_paths=photo_paths,
        assigned_worker_id=assigned_worker_id.strip() if role == 'owner' else '',
    )
    # 22.07: зеркало в Google Sheets (лист "Дефекты") — юзер хочет видеть дефекты в таблице,
    # так же как объекты. JSON остаётся источником правды приложения, Sheets — только для просмотра;
    # сбой записи в Sheets НЕ должен ронять создание тикета (как и остальные Sheets-интеграции).
    try:
        o = _load_repo_objekte_lib()
        o.append_row_safe('Дефекты', [
            ticket.get('id', ''),
            ticket.get('object_id', ''),
            ticket.get('description', ''),
            ticket.get('status', ''),
            datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
        ])
    except Exception as e:
        print(f'WARNING: mangel-create Sheets mirror failed for ticket {ticket.get("id")}: {e}')
    return ticket


@app.get("/api/mangel/photos/{fname}/file")
def get_mangel_photo_file(fname: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    # Mängel-фото хранятся в той же feed_photos/, но без записи в feed_photos.json —
    # отдаём по basename имени файла (не по id, как feed), с защитой от path traversal.
    safe_name = os.path.basename(fname)
    if safe_name != fname or not safe_name.startswith('mangel_'):
        raise HTTPException(404, "Файл отсутствует")
    if role != 'owner':
        owning_ticket = next((t for t in ml.list_tickets(None) if safe_name in t.get('photo_paths', [])), None)
        if not owning_ticket or not can_access_object(user, role, owning_ticket.get('object_id', '')):
            raise HTTPException(403, "Нет доступа к этому файлу")
    path = os.path.join(PHOTO_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(404, "Файл отсутствует")
    return FileResponse(path)


@app.patch("/api/mangel/{ticket_id}/status")
def update_mangel_status(ticket_id: str, body: MangelStatusBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    try:
        result = ml.update_status(ticket_id, body.status)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    # 22.07: зеркалим смену статуса в Sheets тоже (та же best-effort защита, не роняем запрос)
    try:
        o = _load_repo_objekte_lib()
        rows = o.get_used_range('Дефекты')
        if rows:
            for i, row in enumerate(rows[1:], start=2):
                if row and row[0] == ticket_id:
                    o.update_range(f'Дефекты!D{i}:D{i}', [[body.status]])
                    break
    except Exception as e:
        print(f'WARNING: mangel-status Sheets mirror failed for ticket {ticket_id}: {e}')
    return result


@app.post("/api/mangel/{ticket_id}/comments")
def add_mangel_comment(ticket_id: str, body: MangelCommentBody, user: dict = Depends(get_current_user), _: None = Depends(require_mangel_access)):
    if not body.text.strip():
        raise HTTPException(400, "Текст комментария обязателен")
    try:
        return ml.add_comment(ticket_id, str(user['id']), body.text.strip()[:500],
                               name=user.get('first_name', str(user['id'])))
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/mangel/{ticket_id}")
def delete_mangel_ticket(ticket_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    # 04.08 (Раунд 3, задача 3.3): Owner-only мягкое удаление дефекта. Тикет
    # исчезает из рабочих списков (list/get фильтруют deleted_at), но остаётся
    # на диске с меткой -- фото/чат/audit не трогаем. Идемпотентно.
    try:
        ml.soft_delete_ticket(ticket_id, str(user['id']))
    except KeyError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "id": ticket_id}


@app.get("/api/mangel/{ticket_id}/comments")
def get_mangel_comments(ticket_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_mangel_access)):
    try:
        ticket = ml.get_ticket(ticket_id)
        return {"comments": ticket.get('comments', [])}
    except KeyError as e:
        raise HTTPException(404, str(e))


# ---------- Фотоотчёт старт/финиш смены — Фаза 4a ----------
# moved to core/paths.py -- CHECKIN_PHOTO_BASE
# moved to core/paths.py -- CHECKIN_META_FILE
# moved to core/limits.py -- CHECKIN_MAX_BYTES
_checkin_lock = __import__('threading').Lock()

# 10.40: idempotency-key для checkin start/finish — при плохой связи на объекте
# worker может не увидеть ответ и повторить запрос; без этого второй запрос либо
# создаёт дубль сессии, либо возвращает пугающую 409/400 ошибку на успешное действие.
# Кэш в памяти (не переживает restart) — приемлемо, ключ живёт секунды/минуты, не дни.
_idempotency_cache = {}  # key -> (timestamp, response_dict)
# moved to core/limits.py -- _IDEMPOTENCY_TTL


def _idempotency_get(key: str):
    if not key:
        return None
    entry = _idempotency_cache.get(key)
    if not entry:
        return None
    ts, response = entry
    if time.time() - ts > _IDEMPOTENCY_TTL:
        _idempotency_cache.pop(key, None)
        return None
    return response


def _idempotency_save(key: str, response: dict):
    if not key:
        return
    now = time.time()
    _idempotency_cache[key] = (now, response)
    # чистка старых ключей — кэш не должен расти бесконечно на активном сервере
    stale = [k for k, (ts, _) in _idempotency_cache.items() if now - ts > _IDEMPOTENCY_TTL]
    for k in stale:
        _idempotency_cache.pop(k, None)

os.makedirs(CHECKIN_PHOTO_BASE, exist_ok=True)


# ── Finish projector outbox ──────────────────────────────────────────────────
# Guarantees that a DailyPlan execution update is never silently lost when a crash
# occurs between the checkin_meta write and the daily_plan_store write.

def _outbox_load() -> dict:
    return _safe_load_json(FINISH_OUTBOX_FILE, {})


def _outbox_save(outbox: dict) -> None:
    _atomic_write_json(FINISH_OUTBOX_FILE, outbox)


# Round 1.2 follow-up (owner P0 finding): the original state machine was
# pending -> applied | failed, and startup retry only ever looked at "pending"
# -- once an event became "failed" it was permanently stuck (no automatic path
# back to being retried). New state machine: pending -> retrying -> applied |
# dead_letter, with attempt_count. Both "pending" and "retrying" are retried on
# every startup; after OUTBOX_MAX_ATTEMPTS failures the event becomes
# "dead_letter" and must surface in owner diagnostics (RED) for manual handling
# -- never silently dropped, never silently retried forever either.
OUTBOX_MAX_ATTEMPTS = 10


def _outbox_write_pending(session_id: str, plan_id: str, plan_version: int,
                          worker_id: str, date_str: str, object_id: str,
                          item_results: list) -> None:
    with _finish_outbox_lock:
        outbox = _outbox_load()
        outbox[session_id] = {
            "state": "pending",
            "plan_id": plan_id,
            "plan_version": plan_version,
            "worker_id": str(worker_id),
            "date": date_str,
            "object_id": object_id,
            "item_results": item_results,
            "created_at": time.time(),
            "last_attempt_at": None,
            "attempt_count": 0,
            "error": None,
        }
        _outbox_save(outbox)


def _outbox_mark_applied(session_id: str) -> None:
    with _finish_outbox_lock:
        outbox = _outbox_load()
        if session_id in outbox:
            outbox[session_id]["state"] = "applied"
            outbox[session_id]["applied_at"] = time.time()
            _outbox_save(outbox)


def _outbox_mark_failed(session_id: str, error: str) -> None:
    """Records a failed attempt. Stays retryable ("retrying") until
    OUTBOX_MAX_ATTEMPTS is reached, then becomes a permanent "dead_letter" --
    at that point only manual owner intervention (fixing the underlying data
    issue, then a manual re-trigger) should touch it again."""
    with _finish_outbox_lock:
        outbox = _outbox_load()
        if session_id in outbox:
            evt = outbox[session_id]
            evt["attempt_count"] = evt.get("attempt_count", 0) + 1
            evt["error"] = error[:500]
            evt["last_attempt_at"] = time.time()
            if evt["attempt_count"] >= OUTBOX_MAX_ATTEMPTS:
                evt["state"] = "dead_letter"
            else:
                evt["state"] = "retrying"
            _outbox_save(outbox)


def _retry_pending_outbox_events() -> int:
    """Called at startup to apply any pending/retrying finish-projection events.
    dead_letter events are intentionally NOT retried automatically -- they need
    manual owner review (surfaced via diagnostics, see _outbox_dead_letter_count).
    Returns count of successfully applied events."""
    with _finish_outbox_lock:
        outbox = _outbox_load()
    retried = 0
    for session_id, evt in list(outbox.items()):
        if evt.get("state") not in ("pending", "retrying"):
            continue
        try:
            dpl.apply_daily_execution(
                session_id=session_id,
                daily_plan_id=evt["plan_id"],
                plan_version=int(evt.get("plan_version") or 0),
                worker_id=str(evt["worker_id"]),
                date_str=evt["date"],
                object_id=evt["object_id"],
                item_results=evt.get("item_results") or [],
            )
            _outbox_mark_applied(session_id)
            _clear_pending_execution_report(session_id)
            retried += 1
        except Exception as e:
            _outbox_mark_failed(session_id, str(e))
    return retried


def _outbox_dead_letter_count() -> int:
    """Owner diagnostics: count of finish-projection events that exhausted all
    retry attempts and need manual review. A non-zero count means a completed
    shift's DailyExecution was never recorded and needs a human to look."""
    outbox = _outbox_load()
    return sum(1 for evt in outbox.values() if evt.get("state") == "dead_letter")


def _clear_pending_execution_report(session_id: str) -> None:
    """Once a finish-projection event is successfully applied (either inline in
    checkin_finish or via startup retry), clear the raw report we stashed on the
    checkin_meta session as a crash-window safety net -- it's done its job, no
    need to keep the raw JSON blob around forever."""
    with _checkin_lock:
        items = _load_checkin_meta()
        session = next((i for i in items if i.get('id') == session_id), None)
        if session and session.get('pending_execution_report'):
            session['pending_execution_report'] = None
            _save_checkin_meta(items)


def _reconcile_missing_outbox_events() -> int:
    """Startup reconciliation (owner P0 finding): a finished checkin session can
    have pending_execution_report set (the crash-window fix above) but no
    corresponding outbox event at all, if the process died between the
    checkin_meta commit and the _outbox_write_pending call in checkin_finish.
    Without this, such a session's DailyExecution is silently lost forever --
    nothing would ever retry it, because _retry_pending_outbox_events only
    looks at events that already exist in the outbox. This scans finished
    sessions for that exact gap and reconstructs the missing outbox entry so
    the normal pending/retrying machinery picks it up on this same startup.
    Returns count of reconstructed events."""
    items = _load_checkin_meta()
    outbox = _outbox_load()
    reconciled = 0
    for session in items:
        if session.get('finish_at') is None:
            continue
        report_raw = session.get('pending_execution_report')
        if not report_raw:
            continue
        session_id = session.get('id')
        if session_id in outbox:
            continue  # outbox event already exists (normal path or already reconciled)
        try:
            rpt = json.loads(report_raw)
        except Exception as e:
            print(f'WARNING: reconcile — session {session_id} has unparseable pending_execution_report: {e}')
            continue
        plan_id = rpt.get('plan_id', '') or session.get('daily_plan_id', '')
        plan_ver = int(rpt.get('plan_version', 0) or session.get('daily_plan_version', 0) or 0)
        item_results = rpt.get('item_results') or []
        if not (plan_id and isinstance(item_results, list) and item_results):
            continue
        _outbox_write_pending(
            session_id=session_id, plan_id=plan_id, plan_version=plan_ver,
            worker_id=str(session['user_id']), date_str=session['date'],
            object_id=session['object_id'], item_results=item_results,
        )
        reconciled += 1
        print(f'[startup] Reconciled missing outbox event for session {session_id} (crash-window recovery)')
    return reconciled


def _load_checkin_meta() -> list:
    return _safe_load_json(CHECKIN_META_FILE, [])


def _save_checkin_meta(items: list):
    # 30.07 (Release-аудит P1): было plain open(w)+json.dump -- crash посреди записи
    # (systemctl restart, OOM-kill) обрезал бы главный стор смен/GPS/фото. RMW-race
    # уже закрыт _checkin_lock на всех call sites, здесь только crash-safety записи.
    _atomic_write_json(CHECKIN_META_FILE, items)


async def _save_checkin_photos(files: list, object_id: str, date_str: str) -> list:
    # 30.07 (Release-аудит P0): object_id на /api/checkin/start приходит от клиента
    # (Form-параметр), раньше обрезался только по длине (.strip()[:100]), без защиты
    # от '../' -- потенциальный path traversal при записи фото. os.path.basename
    # схлопывает любые сегменты пути в один компонент (тот же приём, что уже
    # используется для fname/file_id в других upload/serving endpoints).
    object_id = os.path.basename(object_id) or 'unknown'
    day_dir = os.path.join(CHECKIN_PHOTO_BASE, object_id, date_str)
    os.makedirs(day_dir, exist_ok=True)
    saved = []
    for file in files:
        raw = await file.read()
        if len(raw) > CHECKIN_MAX_BYTES:
            continue
        detected = sniff_image(raw)
        if not detected:
            continue
        ext = _ALLOWED_IMAGE_MIME_EXT[detected]
        fname = f"{uuid.uuid4().hex}.{ext}"
        with open(os.path.join(day_dir, fname), 'wb') as f:
            f.write(raw)
        saved.append(os.path.join(object_id, date_str, fname))
    return saved


def _cleanup_checkin_photo_files(relative_paths: list) -> None:
    """03.08: удаляет файлы, сохранённые _save_checkin_photos() ТЕКУЩЕГО неуспешного
    запроса (когда итоговое количество валидных фото < 2) -- не оставляет orphan-файлы
    на диске без ссылки в metadata. Не трогает фото прошлых успешных запросов -- те
    приходят отдельным списком путей, никогда не пересекаются с этим вызовом."""
    for rel_path in relative_paths:
        # os.path.basename на каждом сегменте -- та же defense-in-depth привычка,
        # что и при сохранении (rel_path здесь свой же вывод _save_checkin_photos,
        # но не доверяем этому неявно на случай будущих изменений вызывающего кода).
        abs_path = os.path.join(CHECKIN_PHOTO_BASE, rel_path)
        try:
            os.remove(abs_path)
        except OSError:
            pass


def _get_active_assignment_for_checkin(user_id: str, object_id: str, today: str) -> str:
    """Единая проверка для /api/checkin/start (30.07, аудит п.5) -- owner вызывающий
    код не проверяет вообще (owner проходит can_access_object безусловно), эта функция
    только для worker-пути. Возвращает assignment_id при успехе, иначе бросает 403
    с конкретным сообщением (pending/declined/вне периода/нет назначения -- разные
    тексты, не один общий "нет доступа"). Backward compat: назначение без 'status'
    трактуется как accepted (_assignment_status), без date_from/date_to -- не блокируется.

    03.08: критерий "успех" здесь ТОТ ЖЕ, что has_active_object_access() (accepted +
    сегодня внутри [date_from, date_to] либо период не задан) -- не дублирующая
    независимая проверка дат, просто эта функция дополнительно резолвит конкретный
    assignment_id и даёт разные сообщения об ошибке (pending/declined/вне периода),
    чего bool-helper намеренно не делает."""
    candidates = [a for a in _load_assignments().get(object_id, []) if str(a.get('user_id')) == str(user_id)]
    if not candidates:
        raise HTTPException(403, "У вас нет принятого назначения на этот объект")

    # Если есть хоть одно accepted в периоде -- оно и есть искомое (наиболее частый путь).
    accepted = [a for a in candidates if _assignment_status(a) == 'accepted']
    for a in accepted:
        d_from, d_to = a.get('date_from', ''), a.get('date_to', '')
        if not (d_from and d_to):
            return a.get('id', '')
        if d_from <= today <= d_to:
            return a.get('id', '')
    if accepted:
        # Есть accepted, но ни один не покрывает today датами -- сообщаем по ближайшему.
        a = accepted[0]
        d_from, d_to = a.get('date_from', ''), a.get('date_to', '')
        if today < d_from:
            raise HTTPException(403, f"Смена доступна с {d_from}")
        raise HTTPException(403, f"Период назначения завершён {d_to}")

    if any(_assignment_status(a) == 'pending' for a in candidates):
        raise HTTPException(403, "Сначала подтвердите назначение")
    if any(_assignment_status(a) == 'declined' for a in candidates):
        raise HTTPException(403, "Назначение отклонено")
    raise HTTPException(403, "У вас нет принятого назначения на этот объект")


@app.post("/api/checkin/start")
async def checkin_start(
    object_id: str = Form(''),
    lat: str = Form(''),
    lon: str = Form(''),
    stage_name: str = Form(''),
    files: list[UploadFile] = File(default=[]),
    daily_plan_id: str = Form(''),
    daily_plan_version: str = Form(''),
    daily_plan_acceptance_id: str = Form(''),
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
    idempotency_key: str = Header(default='', alias='Idempotency-Key'),
):
    cached = _idempotency_get(idempotency_key)
    if cached is not None:
        return cached

    if not object_id.strip():
        raise HTTPException(400, "object_id обязателен")
    if not lat.strip() or not lon.strip():
        raise HTTPException(400, "Включи геолокацию, чтобы начать смену")
    # 03.08: Europe/Berlin, не UTC сервера -- проверка периода назначения
    # (_get_active_assignment_for_checkin ниже) должна сверяться с той же датой, что
    # реально "сегодня" по местному времени, иначе вечером/ночью Berlin worker мог бы
    # получить доступ на день раньше/позже реального начала/конца периода.
    date_str = _today_berlin_str()

    # 30.07 (аудит п.5): единая проверка ДО сохранения фото/создания сессии -- нельзя
    # сначала записать файлы, а потом вернуть 403. Owner не назначается вообще
    # (can_access_object пропускает owner безусловно), для него assignment_id пуст.
    assignment_id = ''
    if role == 'owner':
        if not can_access_object(user, role, object_id.strip()):
            raise HTTPException(403, "Нет доступа к этому объекту")
    else:
        assignment_id = _get_active_assignment_for_checkin(str(user['id']), object_id.strip(), date_str)

    # Server-trust validation for optional DailyPlan linkage at Start
    _dp_id_clean = daily_plan_id.strip()
    _dp_session_plan_id = None
    _dp_session_plan_version = None
    _dp_session_acceptance_id = None
    if _dp_id_clean:
        _dp_at_start = dpl.get_plan(_dp_id_clean)
        if not _dp_at_start:
            raise HTTPException(400, f"daily_plan_id {_dp_id_clean!r} не найден")
        _wid_str = str(user['id'])
        if _wid_str not in [str(w) for w in _dp_at_start.get('assigned_worker_ids', [])]:
            raise HTTPException(403, "Этот план не назначен вам")
        if _dp_at_start.get('object_id') != object_id.strip():
            raise HTTPException(400, "daily_plan_id объект не совпадает с объектом смены")
        if _dp_at_start.get('date') != date_str:
            raise HTTPException(400, "daily_plan_id дата не совпадает с сегодняшней датой")
        _dp_acc_clean = daily_plan_acceptance_id.strip()
        if not _dp_acc_clean:
            raise HTTPException(400, "Сначала примите план дня")
        _dp_store = dpl.get_store_snapshot()
        _acc = _dp_store["acceptances"].get(_dp_acc_clean)
        if not _acc:
            raise HTTPException(400, f"acceptance_id {_dp_acc_clean!r} не найден")
        if str(_acc.get("worker_id")) != _wid_str:
            raise HTTPException(403, "acceptance_id принадлежит другому работнику")
        if _acc.get("daily_plan_id") != _dp_id_clean:
            raise HTTPException(400, "acceptance_id принадлежит другому плану")
        _snapshot = _acc.get("accepted_context_snapshot") or {}
        if _snapshot:
            if _wid_str not in [str(w) for w in _snapshot.get("assigned_worker_ids", [])]:
                raise HTTPException(403, "Вы не назначены на принятую версию плана")
            if _snapshot.get("object_id") != object_id.strip():
                raise HTTPException(400, "Принятый план относится к другому объекту")
            if _snapshot.get("date") != date_str:
                raise HTTPException(400, "Принятый план относится к другой дате")
        _dp_session_plan_id = _dp_id_clean
        _dp_session_plan_version = str(_acc.get("plan_version") or _snapshot.get("plan_version") or _dp_at_start.get("version") or '')
        _dp_session_acceptance_id = _dp_acc_clean

    with _checkin_lock:
        # 10.29 (Fable-аудит): раньше можно было создать сколько угодно параллельных
        # "стартов" смены — часы потом считались некорректно.
        existing = _load_checkin_meta()
        open_session = next((i for i in existing
                              if str(i.get('user_id')) == str(user['id']) and i.get('finish_at') is None), None)
        if open_session:
            raise HTTPException(409, f"У вас уже есть незавершённая смена на объекте {open_session['object_id']} — сначала завершите её")

    photo_paths = await _save_checkin_photos(files, object_id.strip()[:100], date_str)

    entry = {
        "id": uuid.uuid4().hex,
        "object_id": object_id.strip()[:100],
        "assignment_id": assignment_id,
        "date": date_str,
        "user_id": user['id'],
        "start_at": int(time.time()),
        "start_photos": photo_paths,
        "start_lat": lat,
        "start_lon": lon,
        "start_gps_suspect": _gps_suspect(lat, lon),
        "stage_name": (stage_name.strip()[:200] if isinstance(stage_name, str) else '') or None,
        "daily_plan_id": _dp_session_plan_id,
        "daily_plan_version": _dp_session_plan_version,
        "daily_plan_acceptance_id": _dp_session_acceptance_id,
        "finish_at": None,
        "finish_photos": [],
        "finish_lat": None,
        "finish_lon": None,
        "finish_gps_suspect": None,
        "pause_started_at": None,
        "pause_accumulated_seconds": 0,
    }
    with _checkin_lock:
        items = _load_checkin_meta()
        # Повторная проверка внутри финального лока — на случай гонки между двумя
        # параллельными checkin_start запросами (TOCTOU между первой проверкой и этой записью).
        open_session = next((i for i in items
                              if str(i.get('user_id')) == str(user['id']) and i.get('finish_at') is None), None)
        if open_session:
            raise HTTPException(409, f"У вас уже есть незавершённая смена на объекте {open_session['object_id']} — сначала завершите её")
        items.append(entry)
        _save_checkin_meta(items)

    if photo_paths:
        try:
            profiles = _load_worker_profiles()
            worker_name = _sanitize_display_name(profiles.get(str(user['id']), {}).get('name'), str(user['id']))
            rows = _cached_get_used_range('Объекты')
            object_name = entry['object_id']
            if rows:
                header, data = rows[0], rows[1:]
                for r in data:
                    obj = dict(zip(header, r))
                    if str(obj.get('ID объекта', '')) == entry['object_id']:
                        object_name = obj.get('Объект', entry['object_id'])
                        break
            _upsert_checkin_feed_post(entry, 'start', object_name, user['id'], worker_name)
        except Exception as e:
            print(f'WARNING: checkin-start feed post failed: {e}')

    _idempotency_save(idempotency_key, entry)
    return entry


@app.post("/api/checkin/{session_id}/pause")
def checkin_pause(session_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """Тоггл паузы во время активной смены (24.07) — тап 'Пауза' фиксирует момент
    начала, повторный тап 'Продолжить' добавляет прошедшее время в накопленную паузу.
    Клиент подставляет накопленные минуты как default в анкету при Финише, юзер может
    доправить вручную если нужно."""
    with _checkin_lock:
        items = _load_checkin_meta()
        session = next((i for i in items if i.get('id') == session_id), None)
        if not session:
            raise HTTPException(404, "Сессия check-in не найдена")
        if role != 'owner' and str(session.get('user_id')) != str(user['id']):
            raise HTTPException(403, "Нельзя управлять чужой сменой")
        if session.get('finish_at') is not None:
            raise HTTPException(400, "Смена уже завершена")

        now = int(time.time())
        if session.get('pause_started_at'):
            # Продолжить — закрываем текущий отрезок паузы, добавляем в накопленное
            elapsed = max(0, now - session['pause_started_at'])
            session['pause_accumulated_seconds'] = session.get('pause_accumulated_seconds', 0) + elapsed
            session['pause_started_at'] = None
            paused = False
        else:
            # Пауза — фиксируем момент начала
            session['pause_started_at'] = now
            paused = True
        _save_checkin_meta(items)

    return {
        "paused": paused,
        "pause_accumulated_seconds": session['pause_accumulated_seconds'],
        "pause_accumulated_minutes": round(session['pause_accumulated_seconds'] / 60),
    }


@app.post("/api/checkin/{session_id}/finish")
async def checkin_finish(
    session_id: str,
    lat: str = Form(''),
    lon: str = Form(''),
    done_summary: str = Form(''),
    extra_work: str = Form(''),
    extra_works: str = Form(''),
    needs: str = Form(''),
    defects: str = Form(''),
    next_day_needs: str = Form(''),
    pause_minutes: int = Form(0),
    voice_note_file_id: str = Form(''),
    daily_plan_report: str = Form(''),
    files: list[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
    idempotency_key: str = Header(default='', alias='Idempotency-Key'),
):
    """27.07 (B3, finish-shift wizard): extra_works/needs/defects — JSON-массивы
    структурированных пунктов из wizard-шагов 3-4 (описание/зона/время/согласование
    для доп-работ; категория+текст для потребностей/дефектов). extra_work (str) --
    старое одиночное текстовое поле, оставлено для обратной совместимости с
    checkin_manual и старым фронтендом, если он ещё где-то шлёт этот формат;
    новый wizard шлёт extra_works, extra_work остаётся пустым. Ни Need ни Mangel
    не создаются автоматически -- это только сохраняет данные в сессию, реальное
    создание тикетов делает отдельный подтверждающий вызов с фронтенда после
    показа сводки юзеру (см. wizard Step 6)."""
    cached = _idempotency_get(idempotency_key)
    if cached is not None:
        return cached

    def _parse_json_list(raw: str, field_name: str) -> list:
        if not raw.strip():
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            raise HTTPException(400, f"{field_name}: некорректный JSON")
        if not isinstance(parsed, list):
            raise HTTPException(400, f"{field_name}: ожидался список")
        return parsed

    extra_works_list = _parse_json_list(extra_works, 'extra_works')
    needs_list = _parse_json_list(needs, 'needs')
    defects_list = _parse_json_list(defects, 'defects')

    if not lat.strip() or not lon.strip():
        raise HTTPException(400, "Включи геолокацию, чтобы завершить смену")

    with _checkin_lock:
        items = _load_checkin_meta()
        session = next((i for i in items if i.get('id') == session_id), None)
        if not session:
            raise HTTPException(404, "Сессия check-in не найдена")
        if role != 'owner' and str(session.get('user_id')) != str(user['id']):
            raise HTTPException(403, "Нельзя завершить чужую смену")
        if session['finish_at'] is not None:
            raise HTTPException(400, "Смена уже завершена")
        object_id, date_str = session['object_id'], session['date']

    if len(files) < 2:
        raise HTTPException(400, "Прикрепите минимум 2 фото выполненной работы")

    # Сохранение фото (I/O, await) — вне лока, как и в checkin_start. Раньше await стоял
    # внутри with _checkin_lock: — второй параллельный check-in-запрос (частый сценарий,
    # два работника жмут "Финиш" в конце смены одновременно) блокировал event loop навсегда.
    #
    # 03.08 (реальный найденный баг): len(files) < 2 проверяет ПЕРЕДАННОЕ количество,
    # не РЕАЛЬНО СОХРАНЁННОЕ -- _save_checkin_photos() молча пропускает (continue)
    # битые/слишком большие/не-изображение файлы, ничего не бросая. Раньше finish_at
    # мог записаться после отправки 2 файлов, из которых 0-1 реально сохранились.
    # Теперь: сохраняем, считаем РЕАЛЬНО сохранённые, при недостатке -- удаляем файлы
    # ИМЕННО этого неуспешного запроса (не трогаем фото прошлых успешных попыток) и
    # 400 ДО захвата _checkin_lock -- session['finish_at'] не пишется вообще.
    photo_paths = await _save_checkin_photos(files, object_id, date_str)
    if len(photo_paths) < 2:
        _cleanup_checkin_photo_files(photo_paths)
        raise HTTPException(400, "Для завершения смены необходимо минимум 2 корректных фото")

    with _checkin_lock:
        items = _load_checkin_meta()
        session = next((i for i in items if i.get('id') == session_id), None)
        if not session:
            raise HTTPException(404, "Сессия check-in не найдена")
        if session['finish_at'] is not None:
            raise HTTPException(400, "Смена уже завершена")
        session['finish_at'] = int(time.time())
        session['finish_photos'] = photo_paths
        session['finish_lat'] = lat
        session['finish_lon'] = lon
        session['finish_gps_suspect'] = _gps_suspect(lat, lon)
        # 10.31: опрос конца дня — всё опционально, worker не обязан заполнять,
        # если для следующего дня ничего готовить не нужно.
        session['done_summary'] = done_summary.strip()[:1000] or None
        session['extra_work'] = extra_work.strip()[:1000] or None
        session['extra_works'] = extra_works_list or None
        session['needs'] = needs_list or None
        session['defects'] = defects_list or None
        session['next_day_needs'] = next_day_needs.strip()[:1000] or None
        # 28.07: owner request -- голосовое "что сделано" должно быть прослушиваемо
        # владельцем, не только видно транскриптом. file_id уже создан/сохранён
        # раньше через /api/transcribe (тот же поток что и для распознавания) --
        # тут просто привязываем его к сессии смены. os.path.basename на всякий
        # случай -- та же защита от path traversal, что и в get_transcribe_audio.
        vnf = os.path.basename(voice_note_file_id.strip()) if voice_note_file_id.strip() else ''
        session['voice_note_file_id'] = vnf or None
        # 24.07: если воркер финиширует смену прямо во время активной паузы (забыл нажать
        # "Продолжить") — закрываем её здесь же, не оставляем pause_started_at висеть
        # в завершённой сессии.
        if session.get('pause_started_at'):
            elapsed = max(0, int(time.time()) - session['pause_started_at'])
            session['pause_accumulated_seconds'] = session.get('pause_accumulated_seconds', 0) + elapsed
            session['pause_started_at'] = None
        session['pause_minutes'] = max(0, int(pause_minutes or 0))
        # P0 fix (owner review): persist the raw execution report INSIDE the same
        # checkin_meta write that commits finish_at -- previously daily_plan_report
        # only existed as a request Form parameter, never durably stored anywhere
        # until the outbox write a few lines below. A crash between this save and
        # that outbox write meant the report was permanently lost: finish_at=true,
        # photos saved, but no outbox event and no way to reconstruct item_results
        # from checkin_meta.json alone (there was nothing to reconstruct FROM).
        # Now it's part of this one atomic write -- reconciliation on startup can
        # find a finished session with pending_execution_report set and no
        # outbox event, and rebuild the outbox entry from it (see
        # _reconcile_missing_outbox_events below).
        session['pending_execution_report'] = daily_plan_report.strip() or None
        _save_checkin_meta(items)

    # Apply daily plan execution report via durable outbox.
    # Outbox event is written AFTER checkin_meta is committed and BEFORE apply_daily_execution,
    # so a crash between these two leaves a pending event retried on startup.
    if daily_plan_report.strip():
        try:
            rpt = json.loads(daily_plan_report)
            plan_id = rpt.get('plan_id', '') or session.get('daily_plan_id', '')
            plan_ver = int(rpt.get('plan_version', 0) or session.get('daily_plan_version', 0) or 0)
            item_results = rpt.get('item_results') or []
            if plan_id and isinstance(item_results, list) and item_results:
                # Round 1.2 #2: validate against the worker's IMMUTABLE accepted
                # context snapshot, not the live (possibly since-mutated-by-Sheets-
                # edit) plan fields. A later update_plan_fields() call (object/date/
                # worker/stage change) must never invalidate an already-accepted,
                # already-started shift's Finish -- the accepted snapshot is the
                # trusted historical truth for this comparison, not current plan state.
                _worker_id_str = str(session['user_id'])
                _acceptance_id = session.get('daily_plan_acceptance_id') or ''
                _snapshot = None
                if _acceptance_id:
                    _dp_store = dpl.get_store_snapshot()
                    _acc = _dp_store["acceptances"].get(_acceptance_id)
                    if _acc and str(_acc.get('worker_id')) == _worker_id_str and _acc.get('daily_plan_id') == plan_id:
                        _snapshot = _acc.get('accepted_context_snapshot')
                if _snapshot:
                    # Trusted path: compare against what THIS worker actually accepted.
                    if _worker_id_str not in [str(w) for w in _snapshot.get('assigned_worker_ids', [])]:
                        print(f'WARNING: finish plan_id {plan_id} worker not in accepted snapshot — skipping execution')
                        plan_id = ''
                    elif _snapshot.get('object_id') != object_id:
                        print(f'WARNING: finish plan_id {plan_id} object mismatch vs accepted snapshot — skipping execution')
                        plan_id = ''
                    elif _snapshot.get('date') != date_str:
                        print(f'WARNING: finish plan_id {plan_id} date mismatch vs accepted snapshot — skipping execution')
                        plan_id = ''
                else:
                    # Backward-compat fallback: no acceptance_id on this session, or
                    # the acceptance predates round 1.2 (no snapshot stored yet).
                    # Conservative choice: fall back to the live plan fields exactly
                    # as before -- cannot fabricate a historical snapshot that was
                    # never recorded. This preserves pre-1.2 behavior for old sessions
                    # instead of silently skipping execution for them.
                    _plan_obj = dpl.get_plan(plan_id)
                    if _plan_obj:
                        if _worker_id_str not in [str(w) for w in _plan_obj.get('assigned_worker_ids', [])]:
                            print(f'WARNING: finish plan_id {plan_id} worker not assigned — skipping execution')
                            plan_id = ''
                        elif _plan_obj.get('object_id') != object_id:
                            print(f'WARNING: finish plan_id {plan_id} object mismatch — skipping execution')
                            plan_id = ''
                        elif _plan_obj.get('date') != date_str:
                            print(f'WARNING: finish plan_id {plan_id} date mismatch — skipping execution')
                            plan_id = ''
                if plan_id:
                    # Write outbox event before applying (durable, crash-safe)
                    _outbox_write_pending(session_id, plan_id, plan_ver,
                                          str(session['user_id']), date_str, object_id, item_results)
                    try:
                        dpl.apply_daily_execution(
                            session_id=session_id,
                            daily_plan_id=plan_id,
                            plan_version=plan_ver,
                            worker_id=str(session['user_id']),
                            date_str=date_str,
                            object_id=object_id,
                            item_results=item_results,
                        )
                        _outbox_mark_applied(session_id)
                        _clear_pending_execution_report(session_id)
                        # Auto-record productivity observations from execution
                        try:
                            plan_obj = dpl.get_plan(plan_id)
                            shift_hours = max(0.0, (session['finish_at'] - session.get('start_at', session['finish_at'])) / 3600.0)
                            if plan_obj and shift_hours > 0:
                                dpl.auto_record_execution_productivity(
                                    session_id=session_id,
                                    worker_id=str(session['user_id']),
                                    plan=plan_obj,
                                    item_results=item_results,
                                    shift_hours=shift_hours,
                                )
                        except Exception as _pe:
                            print(f'WARNING: auto_record_execution_productivity failed: {_pe}')
                    except Exception as _ae:
                        _outbox_mark_failed(session_id, str(_ae))
                        print(f'WARNING: apply_daily_execution failed (event pending in outbox): {_ae}')
        except Exception as e:
            print(f'WARNING: apply_daily_execution failed: {e}')

    _write_zeiterfassung_row(session, object_id, session['user_id'])

    if photo_paths:
        try:
            profiles = _load_worker_profiles()
            worker_name = _sanitize_display_name(profiles.get(str(session['user_id']), {}).get('name'), str(session['user_id']))
            rows = _cached_get_used_range('Объекты')
            object_name = object_id
            if rows:
                header, data = rows[0], rows[1:]
                for r in data:
                    obj = dict(zip(header, r))
                    if str(obj.get('ID объекта', '')) == object_id:
                        object_name = obj.get('Объект', object_id)
                        break
            _upsert_checkin_feed_post(session, 'finish', object_name, session['user_id'], worker_name)
        except Exception as e:
            print(f'WARNING: checkin-finish feed post failed: {e}')

    extra_work_summary = _extra_works_summary_text(session)
    if extra_work_summary or next_day_needs.strip():
        # Owner получает пуш только если worker реально что-то указал — не спамим
        # при пустом опроснике. 24.07: extra_work (доп-работы вне плана) теперь тоже
        # шлётся — раньше уходила только в Zeiterfassung sheet, owner мог её пропустить
        # без захода в таблицу. Нужно для billing: если заказчик попросил доп-работу на
        # месте, а её не заметили — компании не доплатят, хотя воркеру платят за время.
        # 27.07: extra_work_summary теперь может прийти из structured extra_works[]
        # (wizard), не только из старого одиночного текстового поля.
        roles = _load_roles()
        owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
        if owner_id:
            if extra_work_summary:
                try:
                    send_telegram_message(int(owner_id),
                        f"⚠️ Доп-работы вне плана ({object_id}): {extra_work_summary[:300]}")
                except Exception:
                    pass
            if next_day_needs.strip():
                try:
                    send_telegram_message(int(owner_id),
                        f"📋 На завтра нужно ({object_id}): {next_day_needs.strip()[:300]}")
                except Exception:
                    pass
    _idempotency_save(idempotency_key, session)
    return session


@app.get("/api/workers/{target_user_id}/calendar")
def get_worker_calendar(target_user_id: str, year: int, month: int,
                         user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """10.30 + 21.07: owner выбирает профиль worker'а и видит availability (доступные/недоступные/
    отработанные дни). Worker может смотреть ТОЛЬКО свой собственный календарь тем же способом —
    permission проверяется здесь на backend (не только скрытием кнопки в UI, см. ChatGPT-аудит 21.07),
    не декоратором require_owner, т.к. worker имеет легитимный доступ к своим же данным."""
    if role != 'owner' and str(user['id']) != str(target_user_id):
        raise HTTPException(403, "Можно смотреть только свой календарь")
    month_prefix = f'{year:04d}-{month:02d}'

    abwesenheit = [e for e in _load_abwesenheit() if str(e['user_id']) == target_user_id]
    unavailable_dates = set()
    for e in abwesenheit:
        if e.get('status') == 'rejected':
            continue  # отклонённая заявка не блокирует день
        d = datetime.strptime(e['date_from'], '%Y-%m-%d')
        end = datetime.strptime(e['date_to'], '%Y-%m-%d')
        while d <= end:
            ds = d.strftime('%Y-%m-%d')
            if ds.startswith(month_prefix):
                unavailable_dates.add(ds)
            d += timedelta(days=1)

    checkins = [c for c in _load_checkin_meta()
                if str(c.get('user_id')) == target_user_id and c.get('date', '').startswith(month_prefix)]
    worked_dates = sorted(set(c['date'] for c in checkins))

    # 22.07: 4-е состояние — назначен на объект в эти даты (bubble-assign date_from/date_to).
    # Одобренный отпуск теперь физически блокирует новое назначение (см. assign_user), но старые
    # назначения (созданные до этого фикса) могут пересекаться — недоступен побеждает по приоритету.
    assigned_dates = set()
    for oid, lst in _load_assignments().items():
        for a in lst:
            if a.get('user_id') != target_user_id or not a.get('date_from') or not a.get('date_to'):
                continue
            d = datetime.strptime(a['date_from'], '%Y-%m-%d')
            end = datetime.strptime(a['date_to'], '%Y-%m-%d')
            while d <= end:
                ds = d.strftime('%Y-%m-%d')
                if ds.startswith(month_prefix):
                    assigned_dates.add(ds)
                d += timedelta(days=1)
    assigned_dates -= unavailable_dates  # приоритет: недоступен важнее назначения

    return {
        "unavailable_dates": sorted(unavailable_dates),
        "worked_dates": worked_dates,
        "assigned_dates": sorted(assigned_dates),
    }


def _worker_period_stats(target_id: str, date_from: str, date_to: str) -> dict:
    """Раунд 5 §13: агрегаты по периоду [date_from, date_to] включительно (Europe/Berlin,
    строковые ISO-даты сравниваются лексикографически). days_worked = уникальные дни со
    сменами (активная смена считается один раз, не дублируется), total_hours учитывает
    паузы через _hours_from_session, sick/vacation — одобренные отсутствия, пересекающие
    период. Средн. за день = total_hours / days_worked."""
    sessions = [s for s in _load_checkin_meta()
                if str(s.get('user_id')) == str(target_id)
                and date_from <= s.get('date', '') <= date_to]
    worked_dates = sorted(set(s['date'] for s in sessions if s.get('date')))
    total_hours = round(sum(_hours_from_session(s) for s in sessions), 2)
    days_worked = len(worked_dates)
    avg = round(total_hours / days_worked, 2) if days_worked else 0.0

    d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    sick_days = vacation_days = 0
    for e in _load_abwesenheit():
        if str(e.get('user_id')) != str(target_id) or e.get('status') != 'approved':
            continue
        e1 = datetime.strptime(e['date_from'], '%Y-%m-%d').date()
        e2 = datetime.strptime(e.get('date_to') or e['date_from'], '%Y-%m-%d').date()
        lo, hi = max(e1, d_from), min(e2, d_to)
        if lo > hi:
            continue
        days = (hi - lo).days + 1
        if e.get('reason') == 'Krankheit':
            sick_days += days
        elif e.get('reason') == 'Urlaub':
            vacation_days += days

    return {
        'date_from': date_from, 'date_to': date_to,
        'days_worked': days_worked, 'total_hours': total_hours,
        'avg_per_day': avg, 'sick_days': sick_days, 'vacation_days': vacation_days,
        'worked_dates': worked_dates,
    }


@app.get("/api/workers/{target_user_id}/calendar-stats")
def get_worker_calendar_stats(target_user_id: str, date_from: str, date_to: str,
                              user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """Раунд 5 §13: статистика работника за произвольный период (Неделя/Месяц/3 месяца/
    свой период). Owner видит любого, Worker — только себя (проверка на backend)."""
    if role != 'owner' and str(user['id']) != str(target_user_id):
        raise HTTPException(403, "Можно смотреть только свою статистику")
    for d in (date_from, date_to):
        try:
            datetime.strptime(d, '%Y-%m-%d')
        except (ValueError, TypeError):
            raise HTTPException(400, "date_from/date_to должны быть YYYY-MM-DD")
    if date_from > date_to:
        raise HTTPException(400, "date_from не может быть позже date_to")
    stats = _worker_period_stats(target_user_id, date_from, date_to)
    profile = _get_worker_profile(target_user_id)
    stats['name'] = _sanitize_display_name(profile.get('name'), str(target_user_id))
    return stats


@app.get("/api/checkin/stundenzettel")
def export_stundenzettel(user_id: str = '', year: int = 0, month: int = 0,
                          date_from: str = '', date_to: str = '',
                          user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """10.29 (Fable-аудит, идея): экспорт табеля рабочего времени — в Германии
    учёт рабочего времени обязателен по решению BAG (2022). CSV, открывается
    в Excel/LibreOffice — не тащим Node-PDF-пайплайн ради одного отчёта."""
    target_id = user_id or str(user['id'])
    if target_id != str(user['id']) and role != 'owner':
        raise HTTPException(403, "Можно выгружать только свой табель")
    # Раунд 5 §13: произвольный период date_from/date_to (Неделя/Месяц/3 месяца/свой).
    # Обратная совместимость: без диапазона — месяц year/month (старый вызов из UI).
    if date_from and date_to:
        for d in (date_from, date_to):
            try:
                datetime.strptime(d, '%Y-%m-%d')
            except ValueError:
                raise HTTPException(400, "date_from/date_to должны быть YYYY-MM-DD")
        if date_from > date_to:
            raise HTTPException(400, "date_from не может быть позже date_to")
        period_label = f'{date_from}_{date_to}'
        sessions = [s for s in _load_checkin_meta()
                    if str(s.get('user_id')) == target_id and date_from <= s.get('date', '') <= date_to]
    else:
        if not year or not month:
            now = business_now()
            year, month = now.year, now.month
        month_prefix = f'{year:04d}-{month:02d}'
        period_label = month_prefix
        sessions = [s for s in _load_checkin_meta()
                    if str(s.get('user_id')) == target_id and s.get('date', '').startswith(month_prefix)]

    import io
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';', lineterminator='\n')
    writer.writerow(['Дата', 'Объект', 'Начало', 'Конец', 'Пауза (мин)', 'Часы', 'Тип'])
    for s in sorted(sessions, key=lambda x: x.get('date', '')):
        kind = 'Ручной ввод' if s.get('manual_entry') else 'Фото-чекин'
        if s.get('manual_entry'):
            start, finish = s.get('start_time', ''), s.get('end_time', '')
        else:
            start = datetime.fromtimestamp(s['start_at']).strftime('%H:%M') if s.get('start_at') else ''
            finish = datetime.fromtimestamp(s['finish_at']).strftime('%H:%M') if s.get('finish_at') else 'не завершено'
        hours = round(_hours_from_session(s), 2)
        pause = int(s.get('pause_minutes') or 0)
        writer.writerow([_csv_safe(s.get('date', '')), _csv_safe(s.get('object_id', '')), start, finish, pause, hours, kind])

    total_hours = round(sum(_hours_from_session(s) for s in sessions), 2)
    writer.writerow(['', '', '', '', '', total_hours, 'ИТОГО'])

    csv_content = buf.getvalue()
    # Раунд 6 §2.4: имя файла с реальным именем работника (если заполнено), не Telegram ID.
    _prof = _get_worker_profile(target_id)
    _disp = _sanitize_display_name(_prof.get('name'), '')
    if _disp and _disp != str(target_id):
        _safe_name = re.sub(r'[^0-9A-Za-zА-Яа-яЁё]+', '_', _disp).strip('_') or str(target_id)
    else:
        _safe_name = str(target_id)
    filename = f'Stundenzettel_{_safe_name}_{period_label}.csv'
    # Content-Disposition должен быть latin-1-safe (Starlette кодирует заголовки в latin-1),
    # поэтому кириллическое имя отдаём через RFC 5987 filename* (UTF-8, percent-encoded), а в
    # ASCII-fallback filename — только латиница/цифры (кириллица → '_').
    ascii_name = re.sub(r'[^0-9A-Za-z._-]+', '_', filename).strip('_') or 'Stundenzettel.csv'
    if not ascii_name.endswith('.csv'):
        ascii_name += '.csv'
    encoded_name = quote(filename)
    from fastapi.responses import Response
    return Response(
        content='\ufeff' + csv_content,  # BOM — Excel корректно определяет UTF-8
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}"}
    )


@app.get("/api/checkin")
def list_checkins(object_id: str = '', date: str = '', user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    items = _load_checkin_meta()
    if role != 'owner':
        # 10.29 (Fable-аудит): раньше worker видел GPS-координаты старта/финиша
        # смены ВСЕХ коллег — только свои сессии.
        items = [i for i in items if str(i.get('user_id')) == str(user['id'])]
    if object_id:
        items = [i for i in items if i['object_id'] == object_id]
    if date:
        items = [i for i in items if i['date'] == date]
    # 28.07: voice_note_file_id -- отдаём готовый audio_url, фронтенду не нужно самому
    # собирать путь (тот же паттерн, что /api/transcribe уже возвращает при записи).
    for i in items:
        if i.get('voice_note_file_id'):
            i['voice_note_audio_url'] = f"/api/transcribe/{i['voice_note_file_id']}/audio"
    return {"sessions": items}


@app.get("/api/checkin/{session_id}/photo/{which}/{index}")
def get_checkin_photo(session_id: str, which: str, index: int, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    items = _load_checkin_meta()
    session = next((i for i in items if i.get('id') == session_id), None)
    if not session:
        raise HTTPException(404, "Сессия не найдена")
    if role != 'owner' and str(session.get('user_id')) != str(user['id']):
        raise HTTPException(403, "Нет доступа к фото этой смены")
    key = 'start_photos' if which == 'start' else 'finish_photos'
    photos = session.get(key, [])
    if index < 0 or index >= len(photos):
        raise HTTPException(404, "Фото не найдено")
    path = os.path.join(CHECKIN_PHOTO_BASE, photos[index])
    if not os.path.exists(path):
        raise HTTPException(404, "Файл отсутствует")
    from fastapi.responses import FileResponse
    return FileResponse(path)


# ---------- Zeiterfassung (ручной ввод времени, референс "Neue Zeit") — Фаза 4a ----------
class ZeiterfassungBody(BaseModel):
    object_id: str
    art: str = "Arbeitszeit"
    date: str
    start_time: str
    end_time: str
    pause_minutes: int = 0
    description: str = ''
    mitarbeiter_user_id: str | None = None  # owner может внести за другого работника


@app.post("/api/checkin/manual")
def checkin_manual(body: ZeiterfassungBody, user: dict = Depends(get_current_user), role: str = Depends(get_role),
                    idempotency_key: str = Header(default='', alias='Idempotency-Key')):
    target_user_id = body.mitarbeiter_user_id if (role == 'owner' and body.mitarbeiter_user_id) else str(user['id'])
    entry = {
        "id": uuid.uuid4().hex,
        "object_id": body.object_id.strip()[:100],
        "date": body.date,
        "user_id": target_user_id,
        "art": body.art,
        "start_time": body.start_time,
        "end_time": body.end_time,
        "pause_minutes": body.pause_minutes,
        "description": body.description.strip()[:500],
        "manual_entry": True,
        "created_at": int(time.time()),
    }
    with _checkin_lock:
        items = _load_checkin_meta()
        items.append(entry)
        _save_checkin_meta(items)
    _write_zeiterfassung_row(entry, entry['object_id'], target_user_id)
    _idempotency_save(idempotency_key, entry)
    return entry


# ---------- AI-анализ фотоотчёта — Фаза 4b ----------
# Технический нюанс: _call_claude_cli() работает через "claude -p <text>" субпроцесс и
# НЕ читает image-контент-блоки (см. _messages_to_prompt — картинки отбрасываются).
# Реальный multimodal-путь в этом кодбейсе — GLM через HTTP API (_call_glm),
# который принимает Anthropic-совместимый messages-формат с image-блоками как есть.
# Поэтому анализ фото идёт через GLM напрямую, а не через "существующий _call_claude_cli".

def _image_block_from_file(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    ext = path.rsplit('.', 1)[-1].lower()
    media_type = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}.get(ext, 'image/jpeg')
    with open(path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}


def _call_glm_vision(system_prompt: str, image_paths: list, text_prompt: str) -> str:
    content = []
    for p in image_paths:
        block = _image_block_from_file(os.path.join(CHECKIN_PHOTO_BASE, p))
        if block:
            content.append(block)
    content.append({"type": "text", "text": text_prompt})

    glm_key = os.environ.get('GLM_KEY', '')
    if not glm_key:
        raise HTTPException(503, "GLM API не настроен (нет GLM_KEY)")

    payload = {
        "model": "glm-4.5-flash",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [{"role": "user", "content": content}],
    }
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = _urlreq.Request(
        'https://api.z.ai/api/anthropic/v1/messages',
        data=data, method='POST',
        headers={'Content-Type': 'application/json', 'x-api-key': glm_key, 'anthropic-version': '2023-06-01'},
    )
    try:
        with _urlreq.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return result['content'][0]['text']
    except _urlreq.HTTPError as e:
        raise HTTPException(502, f"GLM API ошибка: {e.read().decode('utf-8')[:300]}")
    except Exception as e:
        raise HTTPException(502, f"GLM недоступен: {str(e)[:200]}")


def _get_checkin_session(session_id: str, user_id=None, role=None) -> dict:
    items = _load_checkin_meta()
    session = next((i for i in items if i.get('id') == session_id), None)
    if not session:
        raise HTTPException(404, "Сессия не найдена")
    if role is not None and role != 'owner' and str(session.get('user_id')) != str(user_id):
        raise HTTPException(403, "Нет доступа к этой смене")
    if not session.get('finish_photos'):
        raise HTTPException(400, "Смена ещё не завершена — нет финишных фото для сравнения")
    return session


def _save_checkin_analysis(session_id: str, key: str, value):
    items = _load_checkin_meta()
    for i in items:
        if i.get('id') == session_id:
            i.setdefault('analysis', {})[key] = value
            _save_checkin_meta(items)
            return
    raise HTTPException(404, "Сессия не найдена")


@app.post("/api/checkin/{session_id}/analyze-progress")
def analyze_checkin_progress(session_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    session = _get_checkin_session(session_id, user['id'], role)
    _check_ai_rate(user['id'])
    result = _call_glm_vision(
        "Ты — опытный прораб на стройке. Сравниваешь фото 'до' и 'после' работ на одном участке "
        "объекта. Кратко (2-4 предложения, по-русски) опиши: какой прогресс виден, что изменилось, "
        "выглядит ли работа завершённой или частично сделанной.",
        session['start_photos'] + session['finish_photos'],
        "Вот фото начала смены, затем фото конца смены. Сравни прогресс работ.",
    )
    _save_checkin_analysis(session_id, 'progress', result)
    return {"analysis": result}


@app.post("/api/checkin/{session_id}/analyze-materials")
def analyze_checkin_materials(session_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    session = _get_checkin_session(session_id, user['id'], role)
    _check_ai_rate(user['id'])
    result = _call_glm_vision(
        "Ты — сметчик на стройке. По фото оцениваешь примерный расход строительных материалов "
        "(мешки, паллеты, упаковки — что видно в кадре). Дай краткую (2-3 предложения, по-русски) "
        "оценку расхода материала. Это ПРЕДЛОЖЕНИЕ для владельца на проверку, не финальная цифра — "
        "явно укажи, что оценка приблизительная по фото.",
        session['start_photos'] + session['finish_photos'],
        "Оцени примерный расход материала по этим фото (начало и конец смены).",
    )
    _save_checkin_analysis(session_id, 'materials', result)
    return {"analysis": result, "note": "Предложение на проверку владельцем — бюджет объекта не изменён автоматически."}


@app.post("/api/checkin/{session_id}/analyze-defects")
def analyze_checkin_defects(session_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    session = _get_checkin_session(session_id, user['id'], role)
    _check_ai_rate(user['id'])
    result = _call_glm_vision(
        "Ты — инспектор качества на стройке. Смотришь на фото участка работ и ищешь видимые дефекты: "
        "трещины, протечки, неровности, брак. Ответь СТРОГО в формате: первая строка 'ДЕФЕКТ: да' или "
        "'ДЕФЕКТ: нет', затем если да — короткое описание дефекта на русском (1-2 предложения).",
        session['finish_photos'],
        "Есть ли видимые дефекты на этом фото?",
    )
    has_defect = result.strip().upper().startswith('ДЕФЕКТ: ДА') or result.strip().upper().startswith('ДЕФЕКТ:ДА')
    ticket = None
    if has_defect:
        description = result.split('\n', 1)[1].strip() if '\n' in result else 'Дефект обнаружен AI-анализом'
        # 30.07 (Release-аудит P1): убран локальный import mangel_lib as ml -- module-level
        # ml уже загружен через _load_repo_mangel_lib() выше, повторный обычный import
        # был бы тем же риском резолва в untracked-копию, что мы только что закрыли.
        ticket = ml.create_ticket(
            object_id=session['object_id'],
            description=description[:500],
            created_by=str(user['id']),
            photo_paths=session['finish_photos'][:1],
            created_by_ai=True,
        )
    _save_checkin_analysis(session_id, 'defects', result)
    return {"analysis": result, "ticket_created": ticket}


# ---------- Critical Alerts — persisted, с deadline/comment/photo (Фаза 10.16) ----------
# moved to core/paths.py -- CRITICAL_ALERTS_FILE
# moved to core/paths.py -- CRITICAL_ALERT_PHOTO_DIR
os.makedirs(CRITICAL_ALERT_PHOTO_DIR, exist_ok=True)


def _load_critical_alerts() -> list:
    return _safe_load_json(CRITICAL_ALERTS_FILE, [])


def _save_critical_alerts(items: list):
    _atomic_write_json(CRITICAL_ALERTS_FILE, items)


def _create_critical_alert(target_user_id: str, kind: str, title: str, ref_id: str = '',
                            subtitle: str = '', deadline_at: int | None = None) -> dict:
    """Создаёт persisted критический алерт + пуш + авто-чат-тред (владельцы + назначенный worker)."""
    alert = {
        "id": uuid.uuid4().hex,
        "target_user_id": str(target_user_id),
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "ref_id": ref_id,
        "created_at": int(time.time()),
        "deadline_at": deadline_at,
        "acknowledged_at": None,
        "comment": None,
        "resolution": None,  # 'yes' | 'no' — ответ на "вопрос решён?"
        "resolution_note": None,
        "resolution_photos": [],
    }
    items = _load_critical_alerts()
    items.append(alert)
    _save_critical_alerts(items)

    roles = _load_roles()
    owner_ids = [uid for uid, r in roles.items() if r == 'owner']
    thread_id = _chat_thread_id(target_user_id, owner_ids[0] if owner_ids else None) \
        if owner_ids else 'group'
    _ensure_critical_alert_chat(alert, thread_id, owner_ids)

    try:
        send_telegram_message(int(target_user_id), f"🔴 {title}")
    except Exception:
        pass
    return alert


def _ensure_critical_alert_chat(alert: dict, thread_id: str, owner_ids: list):
    """Авто-сообщение в тред алерта — создаётся независимо от того, ответит ли worker."""
    msg = {
        "id": uuid.uuid4().hex,
        "ts": int(time.time()),
        "user_id": "system",
        "name": "Система",
        "text": f"🔴 Критический алерт: {alert['title']}",
        "to_user_id": None if thread_id == 'group' else thread_id,
        "critical_alert_id": alert['id'],
    }
    with _chat_lock:
        messages = _load_chat()
        messages.append(msg)
        _save_chat(messages)


class CriticalAlertAckBody(BaseModel):
    comment: str = ''


@app.post("/api/critical-alerts/{alert_id}/ack")
def ack_critical_alert(alert_id: str, body: CriticalAlertAckBody, user: dict = Depends(get_current_user)):
    items = _load_critical_alerts()
    alert = next((a for a in items if a['id'] == alert_id), None)
    if not alert:
        raise HTTPException(404, "Алерт не найден")
    if alert['target_user_id'] != str(user['id']):
        raise HTTPException(403, "Не ваш алерт")
    alert['acknowledged_at'] = int(time.time())
    alert['comment'] = body.comment.strip()[:500] or None
    _save_critical_alerts(items)

    if alert['comment']:
        roles = _load_roles()
        owner_ids = [uid for uid, r in roles.items() if r == 'owner']
        thread_id = _chat_thread_id(alert['target_user_id'], owner_ids[0] if owner_ids else None) \
            if owner_ids else 'group'
        msg = {
            "id": uuid.uuid4().hex, "ts": int(time.time()), "user_id": user['id'],
            "name": user.get('first_name', str(user['id'])), "text": alert['comment'],
            "to_user_id": None if thread_id == 'group' else thread_id,
            "critical_alert_id": alert['id'],
        }
        with _chat_lock:
            messages = _load_chat()
            messages.append(msg)
            _save_chat(messages)
    return alert


@app.post("/api/critical-alerts/{alert_id}/resolve")
def resolve_critical_alert(alert_id: str, resolution: str = Form(...), note: str = Form(''),
                            files: list[UploadFile] = File(default=[]),
                            user: dict = Depends(get_current_user)):
    if resolution not in ('yes', 'no'):
        raise HTTPException(400, "resolution должен быть yes или no")
    items = _load_critical_alerts()
    alert = next((a for a in items if a['id'] == alert_id), None)
    if not alert:
        raise HTTPException(404, "Алерт не найден")
    if alert['target_user_id'] != str(user['id']):
        raise HTTPException(403, "Не ваш алерт")

    alert['resolution'] = resolution
    alert['resolution_note'] = note.strip()[:500] or None

    saved_photos = []
    if resolution == 'yes' and files:
        # 30.07 (Release-аудит P1-8): basename на write-стороне для согласованности
        # с read-стороной (GET .../photo/{filename} уже санитирует). alert_id уже
        # проверен по _load_critical_alerts()+ownership выше, практическая
        # эксплуатируемость низкая (id -- server-generated uuid), но раз паттерн
        # есть на чтении -- должен быть и на записи.
        alert_dir = os.path.join(CRITICAL_ALERT_PHOTO_DIR, os.path.basename(alert_id))
        os.makedirs(alert_dir, exist_ok=True)
        for f in files:
            data = f.file.read()
            if len(data) > 8 * 1024 * 1024:
                raise HTTPException(400, "Файл слишком большой (макс. 8 МБ)")
            detected = sniff_image(data)
            if not detected:
                raise HTTPException(400, "Файл должен быть изображением")
            ext = '.' + _ALLOWED_IMAGE_MIME_EXT[detected]
            fname = f"{uuid.uuid4().hex}{ext}"
            with open(os.path.join(alert_dir, fname), 'wb') as out:
                out.write(data)
            saved_photos.append(fname)
    alert['resolution_photos'] = saved_photos
    _save_critical_alerts(items)

    roles = _load_roles()
    owner_ids = [uid for uid, r in roles.items() if r == 'owner']
    thread_id = _chat_thread_id(alert['target_user_id'], owner_ids[0] if owner_ids else None) \
        if owner_ids else 'group'
    text = f"Вопрос решён: {'да' if resolution == 'yes' else 'нет'}"
    if note:
        text += f"\n{note}"
    if saved_photos:
        text += f"\n📷 {len(saved_photos)} фото"
    msg = {
        "id": uuid.uuid4().hex, "ts": int(time.time()), "user_id": user['id'],
        "name": user.get('first_name', str(user['id'])), "text": text,
        "to_user_id": None if thread_id == 'group' else thread_id,
        "critical_alert_id": alert['id'],
    }
    with _chat_lock:
        messages = _load_chat()
        messages.append(msg)
        _save_chat(messages)
    return alert


@app.get("/api/critical-alerts/{alert_id}/photo/{filename}")
def get_critical_alert_photo(alert_id: str, filename: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    # path traversal: alert_id/filename идут из URL напрямую в os.path.join без
    # проверки против known-хранимых значений (в отличие от object documents/chat
    # attachments, которые матчат fname против JSON-store перед сборкой пути) --
    # basename() режет любой ../ компонент до склейки.
    safe_alert_id = os.path.basename(alert_id)
    safe_filename = os.path.basename(filename)
    if safe_alert_id != alert_id or safe_filename != filename:
        raise HTTPException(404, "Фото не найдено")
    path = os.path.join(CRITICAL_ALERT_PHOTO_DIR, safe_alert_id, safe_filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Фото не найдено")
    if role != 'owner':
        alert = next((a for a in _load_critical_alerts() if a['id'] == alert_id), None)
        if not alert or alert['target_user_id'] != str(user['id']):
            raise HTTPException(403, "Нет доступа к этому фото")
    return FileResponse(path)


@app.get("/api/critical-alerts/pending")
def list_pending_critical_alerts(user: dict = Depends(get_current_user)):
    """Polling endpoint для глобального попапа — только непрочитанные алерты текущего юзера."""
    items = [a for a in _load_critical_alerts()
             if a['target_user_id'] == str(user['id']) and not a.get('acknowledged_at')]
    return {"alerts": items}


class CriticalAlertCreateBody(BaseModel):
    target_user_id: str
    title: str
    subtitle: str = ''
    deadline_minutes: int | None = None


@app.post("/api/critical-alerts")
def create_critical_alert_endpoint(body: CriticalAlertCreateBody, user: dict = Depends(get_current_user),
                                    _: None = Depends(require_owner)):
    deadline_at = int(time.time()) + body.deadline_minutes * 60 if body.deadline_minutes else None
    return _create_critical_alert(
        target_user_id=body.target_user_id, kind='manual', title=body.title,
        subtitle=body.subtitle, deadline_at=deadline_at,
    )


# ---------- Abwesenheit — Фаза 5 (календарь отсутствий работников) ----------
# moved to core/paths.py -- ABWESENHEIT_FILE
# moved to core/constants.py -- ABWESENHEIT_REASONS


def _load_abwesenheit() -> list:
    return _safe_load_json(ABWESENHEIT_FILE, [])


def _save_abwesenheit(items: list):
    _atomic_write_json(ABWESENHEIT_FILE, items)


class AbwesenheitBody(BaseModel):
    date_from: str
    date_to: str | None = None
    reason: str
    note: str = ''
    start_time: str | None = None
    end_time: str | None = None


def _notify_owner_abwesenheit_pending(entry: dict):
    """Критический алерт owner'у при новой заявке на отсутствие (10.15)."""
    roles = _load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    if not owner_id:
        return
    text = (f"🔴 Заявка на отсутствие: {entry['name']}\n"
            f"{entry['date_from']} — {entry['date_to']} · {entry['reason']}\n"
            f"{entry['note'] or ''}\n\nПодтвердите или отклоните в приложении.")
    try:
        send_telegram_message(owner_id, text)
    except Exception:
        pass  # best-effort — не блокировать создание записи


def _notify_worker_abwesenheit_decision(entry: dict):
    """Push worker'у после решения owner'а по заявке (10.15)."""
    status_text = 'одобрена' if entry['status'] == 'approved' else 'не одобрена'
    text = (f"{'✅' if entry['status'] == 'approved' else '❌'} Ваша заявка на отсутствие "
            f"{status_text} руководством\n{entry['date_from']} — {entry['date_to']}")
    try:
        send_telegram_message(int(entry['user_id']), text)
    except Exception:
        pass


def _validate_date_str(date_str: str, field_name: str = 'дата'):
    """Валидация формата YYYY-MM-DD — без этого кривая дата от клиента доходит
    до calendar.monthrange()/сравнений строк и валит эндпоинт 500 вместо 400 (10.29)."""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        raise HTTPException(400, f"Некорректный формат {field_name}: {date_str!r} (ожидается YYYY-MM-DD)")


def _month_end(date_str: str) -> str:
    import calendar
    try:
        y, m, _ = (int(x) for x in date_str.split('-'))
        if not (1 <= m <= 12):
            raise ValueError
    except (ValueError, AttributeError):
        raise HTTPException(400, f"Некорректная дата: {date_str}")
    last_day = calendar.monthrange(y, m)[1]
    return f'{y:04d}-{m:02d}-{last_day:02d}'


@app.post("/api/abwesenheit")
def create_abwesenheit(body: AbwesenheitBody, user: dict = Depends(get_current_user)):
    if body.reason not in ABWESENHEIT_REASONS:
        raise HTTPException(400, f"Недопустимая причина: {body.reason}")
    _validate_date_str(body.date_from, 'date_from')
    if body.date_to:
        _validate_date_str(body.date_to, 'date_to')
        if body.date_to < body.date_from:
            raise HTTPException(400, "date_to не может быть раньше date_from")
    # 10.25: "не знаю сколько буду болеть" — date_to не указан, ставим временно до конца
    # месяца (видимость в календаре), open_ended=true — worker сам закрывает досрочно
    # через PATCH .../close, когда поправится, owner тоже может закрыть/продлить.
    open_ended = not body.date_to
    date_to = body.date_to or _month_end(body.date_from)
    entry = {
        "id": uuid.uuid4().hex,
        "user_id": str(user['id']),
        "name": user.get('first_name', str(user['id'])),
        "date_from": body.date_from,
        "date_to": date_to,
        "open_ended": open_ended,
        "reason": body.reason,
        "note": body.note.strip()[:300],
        "start_time": body.start_time,
        "end_time": body.end_time,
        "created_at": int(time.time()),
        "status": "pending",
    }
    items = _load_abwesenheit()
    items.append(entry)
    _save_abwesenheit(items)
    _notify_owner_abwesenheit_pending(entry)
    return entry


@app.patch("/api/abwesenheit/{entry_id}/close")
def close_abwesenheit(entry_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """Worker закрывает открытую запись досрочно ('поправился раньше'), owner может закрыть любую."""
    items = _load_abwesenheit()
    entry = next((i for i in items if i['id'] == entry_id), None)
    if not entry:
        raise HTTPException(404, "Запись не найдена")
    if entry['user_id'] != str(user['id']) and role != 'owner':
        raise HTTPException(403, "Можно закрывать только свои записи")
    entry['date_to'] = business_today_str()
    entry['open_ended'] = False
    _save_abwesenheit(items)
    return entry


class AbwesenheitStatusBody(BaseModel):
    status: str


@app.patch("/api/abwesenheit/{entry_id}/status")
def update_abwesenheit_status(entry_id: str, body: AbwesenheitStatusBody,
                               user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    if body.status not in ('approved', 'rejected'):
        raise HTTPException(400, "status должен быть approved или rejected")
    items = _load_abwesenheit()
    entry = next((i for i in items if i['id'] == entry_id), None)
    if not entry:
        raise HTTPException(404, "Запись не найдена")
    entry['status'] = body.status
    _save_abwesenheit(items)
    _notify_worker_abwesenheit_decision(entry)
    _create_critical_alert(
        target_user_id=entry['user_id'],
        kind='abwesenheit_decision',
        title=f"Отсутствие {entry['date_from']}—{entry['date_to']}: "
              f"{'одобрено' if body.status == 'approved' else 'не одобрено'}",
        ref_id=entry['id'],
    )
    return entry


def _auto_close_expired_open_ended_abwesenheit():
    """10.29 (Fable-аудит): open_ended заявка без ручного закрытия молча висела
    до конца месяца без уведомления. Ленивая проверка при каждом GET (не отдельный
    systemd timer) — закрывает просроченные и пушит worker'у + owner'у."""
    today_str = business_today_str()
    items = _load_abwesenheit()
    expired = [i for i in items if i.get('open_ended') and i['date_to'] < today_str]
    if not expired:
        return
    for entry in expired:
        entry['open_ended'] = False
    _save_abwesenheit(items)

    roles = _load_roles()
    owner_ids = [uid for uid, r in roles.items() if r == 'owner']
    for entry in expired:
        text = (f"⏰ Заявка на отсутствие автоматически закрыта (истёк месяц)\n"
                f"{entry['date_from']} — {entry['date_to']} · {entry.get('name', entry['user_id'])}")
        try:
            send_telegram_message(int(entry['user_id']), text)
        except Exception:
            pass
        for owner_id in owner_ids:
            try:
                send_telegram_message(owner_id, text)
            except Exception:
                pass


@app.get("/api/abwesenheit")
def list_my_abwesenheit(user: dict = Depends(get_current_user)):
    _auto_close_expired_open_ended_abwesenheit()
    items = [i for i in _load_abwesenheit() if i['user_id'] == str(user['id'])]
    for e in items:
        e.setdefault('status', 'pending')
    return {"entries": items}


# 31.07 (доп.раунд, П2): reason убран из публичного набора -- свободная строка,
# может содержать мед./личные детали не хуже note (изначально П5 прошлого раунда
# скрыл только note, оставив reason по ошибке).
# moved to core/constants.py -- ABWESENHEIT_PUBLIC_FIELDS


@app.get("/api/abwesenheit/all")
def list_all_abwesenheit(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    # 28.07: owner request -- воркер тоже может смотреть общий календарь команды
    # (view-only). Approve/reject остаются отдельно защищены require_owner на
    # /api/abwesenheit/{id}/status -- этот endpoint только читает список.
    # 31.07 (Release-аудит П5): owner и сам автор записи видят все поля (включая
    # свободный комментарий note, потенциально мед. детали), другие Worker -- только
    # безопасные поля (имя/даты/общий статус). Свою полную запись Worker всё равно
    # видит через GET /api/abwesenheit (list_my_abwesenheit), не этот endpoint.
    _auto_close_expired_open_ended_abwesenheit()
    my_id = str(user['id'])
    entries = _load_abwesenheit()
    result = []
    for e in entries:
        e.setdefault('status', 'pending')
        if role == 'owner' or e.get('user_id') == my_id:
            result.append(e)
        else:
            result.append({k: e.get(k) for k in ABWESENHEIT_PUBLIC_FIELDS})
    return {"entries": result}


@app.delete("/api/abwesenheit/{entry_id}")
def delete_abwesenheit(entry_id: str, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    items = _load_abwesenheit()
    entry = next((i for i in items if i['id'] == entry_id), None)
    if not entry:
        raise HTTPException(404, "Запись не найдена")
    if entry['user_id'] != str(user['id']) and role != 'owner':
        raise HTTPException(403, "Можно удалять только свои записи")
    items = [i for i in items if i['id'] != entry_id]
    _save_abwesenheit(items)
    return {"status": "ok"}


# ── DailyPlan routes (Round 1 — Production Control) ────────────────────────

@app.get("/api/daily-plan/today")
def daily_plan_today(
    worker_id_param: str = Query('', alias='worker_id'),
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
):
    """Работник видит свой план на сегодня (или сообщение «нет плана»).
    Owner может смотреть план за любого worker: ?worker_id=<id>."""
    today = business_today_str()
    if role == 'owner' and worker_id_param:
        worker_id = worker_id_param
    else:
        worker_id = str(user['id'])

    plan = dpl.get_today_plan_for_worker(worker_id, today)
    if not plan:
        return {"has_plan": False, "date": today}

    carryovers = dpl.get_carryovers_for_worker(worker_id, today)
    acceptance = dpl.get_acceptance(plan["id"], worker_id)
    amendments = dpl.get_pending_amendments(plan["id"], worker_id)

    # Если план принят — отдаём snapshot принятой версии, не текущий Sheet
    if acceptance:
        accepted_items = dpl.get_accepted_snapshot(plan["id"], worker_id)
    else:
        accepted_items = plan["items"]

    return {
        "has_plan": True,
        "plan": {
            "id": plan["id"],
            "object_id": plan["object_id"],
            "stage_key": plan["stage_key"],
            "date": plan["date"],
            "status": plan["status"],
            "version": plan["version"],
            "items": accepted_items,
            "published_at": plan.get("published_at"),
        },
        "acceptance": acceptance,
        "pending_amendments": amendments,
        "carryovers": carryovers,
        "date": today,
    }


@app.post("/api/daily-plan/{plan_id}/accept")
def daily_plan_accept(
    plan_id: str,
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
):
    """Работник принимает план: «ПЛАН ПОНЯТЕН — БЕРУ В РАБОТУ»."""
    if role == 'owner':
        raise HTTPException(403, "Owner не принимает план как работник")
    plan = dpl.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "План не найден")
    # Статус-гейт живёт в dpl.accept_plan() (включая 'accepted' для multi-worker
    # планов, где один работник уже принял) -- не дублировать его здесь со
    # старым списком статусов, которые расходятся с библиотекой.

    try:
        acceptance = dpl.accept_plan(plan_id, plan["version"], str(user['id']))
    except PermissionError:
        raise HTTPException(403, "Вы не назначены на этот план")
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"status": "accepted", "acceptance": acceptance}


@app.post("/api/daily-plan/{plan_id}/amendments/{amendment_id}/accept")
def daily_plan_accept_amendment(
    plan_id: str,
    amendment_id: str,
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
):
    """Работник подтверждает Amendment после Start."""
    if role == 'owner':
        raise HTTPException(403, "Owner не подтверждает Amendment как работник")
    try:
        amendment = dpl.acknowledge_amendment(plan_id, amendment_id, str(user['id']))
    except KeyError:
        raise HTTPException(404, "Amendment не найден")
    except PermissionError:
        raise HTTPException(403, "Вы не назначены на этот план")

    return {"status": "acknowledged", "amendment": amendment}


_PLAN_BLOCKER_REASON_LABELS = {
    'material_missing': 'нет материалов',
    'tool_missing': 'нет инструмента',
    'access_denied': 'нет доступа на объект',
    'safety_concern': 'проблема безопасности',
    'weather': 'погодные условия',
    'coordinator_missing': 'нет ответственного лица',
    'other': 'другое',
}


class PlanBlockerBody(BaseModel):
    reason_code: str
    comment: str = ''


@app.post("/api/daily-plan/{plan_id}/blocker")
def daily_plan_report_blocker(
    plan_id: str,
    body: PlanBlockerBody,
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
):
    """Работник сообщает о препятствии при утреннем принятии — «ЕСТЬ ПРЕПЯТСТВИЕ».
    Сохраняет причину + отправляет critical alert владельцу."""
    if role == 'owner':
        raise HTTPException(403, "Owner не сообщает о препятствии как работник")
    plan = dpl.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "План не найден")
    if str(user['id']) not in [str(w) for w in plan.get('assigned_worker_ids', [])]:
        raise HTTPException(403, "Вы не назначены на этот план")
    if body.reason_code not in _PLAN_BLOCKER_REASON_LABELS:
        raise HTTPException(400, f"Недопустимый reason_code. Допустимые: {list(_PLAN_BLOCKER_REASON_LABELS)}")

    blocker = dpl.record_blocker(plan_id, str(user['id']), body.reason_code, body.comment.strip()[:500])

    roles = _load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    if owner_id:
        profiles = _load_worker_profiles()
        worker_name = _sanitize_display_name(
            profiles.get(str(user['id']), {}).get('name'), str(user['id'])
        )
        reason_label = _PLAN_BLOCKER_REASON_LABELS.get(body.reason_code, body.reason_code)
        _create_critical_alert(
            target_user_id=owner_id,
            kind='plan_blocker',
            title=f"{worker_name} не может начать — {reason_label}",
            subtitle=body.comment[:100] if body.comment else '',
            ref_id=plan_id,
        )

    return {"status": "recorded", "blocker": blocker}


@app.get("/api/daily-plan/owner/today")
def daily_plan_owner_today(
    _: None = Depends(require_owner),
    user: dict = Depends(get_current_user),
):
    """Owner Контроль дня — unified DTO. Собирается из local DailyPlan store + checkin_meta.
    Без N+1 Sheets-вызовов: все Sheets-данные приходят через plan_sync_state.json (кэш).
    """
    today = business_today_str()
    plans = dpl.get_pending_plans_for_owner_today(today)

    checkin_items = _load_checkin_meta()
    # Item 9: key sessions on (worker_id, object_id) not worker_id alone -- a
    # worker with two same-day shifts on different objects must not have one
    # session silently overwrite the other in this dict.
    active_sessions = {
        (str(s["user_id"]), str(s.get("object_id", ""))): s for s in checkin_items
        if s.get("date") == today and s.get("finish_at") is None
    }
    finished_sessions = {
        (str(s["user_id"]), str(s.get("object_id", ""))): s for s in checkin_items
        if s.get("date") == today and s.get("finish_at") is not None
    }

    rows = []
    for plan in plans:
        for worker_id in plan.get("assigned_worker_ids", []):
            wid = str(worker_id)
            skey = (wid, str(plan.get("object_id", "")))
            acceptance = dpl.get_acceptance(plan["id"], wid)
            amendments = dpl.get_pending_amendments(plan["id"], wid)
            execution = None
            session = finished_sessions.get(skey) or active_sessions.get(skey)
            if session and session.get("finish_at"):
                execution = dpl.get_execution(session["id"])
            carryovers = dpl.get_carryovers_for_worker(wid, today)

            plan_status_label = _daily_plan_status_label(plan, acceptance, amendments)
            shift_status = _checkin_shift_status(skey, active_sessions, finished_sessions)

            plan_blockers = dpl.get_blockers_for_plan(plan["id"])
            risk_level = _compute_risk_level(carryovers, amendments, plan_blockers, execution)
            row = {
                "plan_id": plan["id"],
                "worker_id": wid,
                "object_id": plan["object_id"],
                "date": today,
                "plan_summary": {
                    "stage_key": plan["stage_key"],
                    "item_count": len(plan["items"]),
                    "version": plan["version"],
                },
                "plan_status": plan["status"],
                "plan_status_label": plan_status_label,
                "acceptance": {
                    "accepted_at": acceptance["accepted_at"] if acceptance else None,
                    "plan_version": acceptance["plan_version"] if acceptance else None,
                } if acceptance else None,
                "shift_status": shift_status,
                "pending_amendments_count": len(amendments),
                "carryover_count": len(carryovers),
                "execution_summary": _execution_summary(execution) if execution else None,
                "risk_level": risk_level,
            }
            rows.append(row)

    total = len(rows)
    accepted = sum(1 for r in rows if r["acceptance"] is not None)
    working = sum(1 for r in rows if r["shift_status"] == "working")
    finished = sum(1 for r in rows if r["shift_status"] == "finished")
    carryover_count = sum(1 for r in rows if r["carryover_count"] > 0)

    return {
        "date": today,
        "summary": {
            "total_plans": total,
            "accepted": accepted,
            "working": working,
            "finished": finished,
            "has_carryovers": carryover_count,
        },
        "rows": rows,
    }


@app.get("/api/daily-plan/object/{object_id}")
def daily_plan_object(
    object_id: str,
    date_from: str = '',
    date_to: str = '',
    _: None = Depends(require_owner),
):
    """Планы объекта за диапазон дат (для матрицы объекта)."""
    today = business_today_str()
    df = date_from or today
    dt = date_to or today

    store = dpl.get_store_snapshot()
    plans = [
        p for p in store["daily_plans"].values()
        if p["object_id"] == object_id and df <= p["date"] <= dt
    ]
    plans.sort(key=lambda p: p["date"])

    result = []
    for plan in plans:
        result.append({
            "id": plan["id"],
            "date": plan["date"],
            "stage_key": plan["stage_key"],
            "status": plan["status"],
            "version": plan["version"],
            "item_count": len(plan["items"]),
            "assigned_worker_ids": plan["assigned_worker_ids"],
        })
    return {"object_id": object_id, "date_from": df, "date_to": dt, "plans": result}


class DailyPlanItemIn(BaseModel):
    id: str = ''
    sequence: int = 0
    title: str
    objective: str = ''
    planned_quantity: float | None = None
    unit: str = ''
    time_estimate_hours: float | None = None
    work_type_id: str | None = None
    required_tools: list = []
    required_materials: list = []


class DailyPlanIn(BaseModel):
    object_id: str
    stage_key: str
    date: str
    assigned_worker_ids: list
    items: list[DailyPlanItemIn]
    publish: bool = False


@app.post("/api/daily-plan")
def daily_plan_create(
    body: DailyPlanIn,
    user: dict = Depends(get_current_user),
    _: None = Depends(require_owner),
):
    """Owner создаёт/публикует DailyPlan (вручную, без Sheets-синка)."""
    items = []
    for i, item in enumerate(body.items):
        item_id = item.id or uuid.uuid4().hex
        items.append({
            "id": item_id,
            "sequence": item.sequence or i + 1,
            "title": item.title,
            "objective": item.objective,
            "planned_quantity": item.planned_quantity,
            "unit": item.unit,
            "time_estimate_hours": item.time_estimate_hours,
            "work_type_id": item.work_type_id,
            "required_tools": item.required_tools,
            "required_materials": item.required_materials,
        })

    plan = dpl.create_plan(
        object_id=body.object_id,
        stage_key=body.stage_key,
        date_str=body.date,
        assigned_worker_ids=body.assigned_worker_ids,
        items=items,
        created_by=str(user['id']),
    )

    if body.publish:
        plan = dpl.publish_plan(plan["id"], str(user['id']))

    return plan


@app.get("/api/daily-plan/{plan_id}")
def daily_plan_get(
    plan_id: str,
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
):
    """Полный план с версиями, принятием, amendments."""
    plan = dpl.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "План не найден")

    worker_id = str(user['id'])
    if role != 'owner' and worker_id not in [str(w) for w in plan["assigned_worker_ids"]]:
        raise HTTPException(403, "Нет доступа к этому плану")

    acceptance = dpl.get_acceptance(plan_id, worker_id) if role != 'owner' else None
    amendments = dpl.get_pending_amendments(plan_id)
    versions = dpl.get_plan_versions(plan_id)

    return {
        "plan": plan,
        "versions": versions,
        "acceptance": acceptance,
        "pending_amendments": amendments,
    }


@app.get("/api/productivity/workers/{target_user_id}")
def get_worker_productivity_api(
    target_user_id: str,
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
):
    """Производительность работника. Работник видит только свою, owner — любого."""
    if role != 'owner' and str(user['id']) != target_user_id:
        raise HTTPException(403, "Можно смотреть только свою производительность")
    data = dpl.get_worker_productivity(target_user_id)
    return data or {"aggregates": {}, "observations": []}


@app.post("/api/productivity/workers/{target_user_id}/baseline")
def set_worker_baseline(
    target_user_id: str,
    work_type_id: str,
    baseline: float,
    _: None = Depends(require_owner),
):
    """Owner устанавливает manual_baseline_factor (prior) для работника × вид работ."""
    if baseline <= 0:
        raise HTTPException(400, "baseline должен быть > 0")
    agg = dpl.set_manual_baseline(target_user_id, work_type_id, baseline)
    return agg


# ── DailyPlan helpers (private) ──────────────────────────────────────────────

def _daily_plan_status_label(plan: dict, acceptance: dict | None, amendments: list) -> str:
    if not plan:
        return "NO_PLAN"
    s = plan["status"]
    if s == "draft":
        return "DRAFT"
    if s == "published" and not acceptance:
        return "NOT_ACCEPTED"
    if s == "amendment_pending":
        return "AMENDMENT_PENDING"
    if s == "accepted":
        return "ACCEPTED"
    if s == "completed":
        return "COMPLETED"
    return s.upper()


def _checkin_shift_status(session_key, active: dict, finished: dict) -> str:
    """session_key: (worker_id, object_id) tuple (item 9) — matches active/finished dicts."""
    if session_key in active:
        s = active[session_key]
        if s.get("pause_started_at"):
            return "paused"
        return "working"
    if session_key in finished:
        return "finished"
    return "not_started"


def _execution_summary(execution: dict | None) -> dict | None:
    if not execution:
        return None
    results = execution.get("item_results", [])
    done = sum(1 for r in results if r.get("status") == "done")
    partial = sum(1 for r in results if r.get("status") == "partial")
    not_done = sum(1 for r in results if r.get("status") == "not_done")
    blocked = sum(1 for r in results if r.get("status") == "blocked")
    return {
        "done": done,
        "partial": partial,
        "not_done": not_done,
        "blocked": blocked,
        "total": len(results),
    }


def _compute_risk_level(
    carryovers: list,
    amendments: list,
    blockers_for_plan: list,
    execution: dict | None,
    predicted_finish_date: str | None = None,
    contract_finish_date: str | None = None,
    internal_target_date: str | None = None,
) -> str:
    """GREEN / YELLOW / ORANGE / RED per spec risk model.

    RED:    predicted_finish_date > contract_finish_date (confirmed schedule breach)
    ORANGE: blocker or blocked execution item; OR internal_target threatened with carryovers
    YELLOW: pending amendment or carryover without a RED/ORANGE condition
    GREEN:  none of the above
    """
    has_blocker = bool(blockers_for_plan)
    blocked_in_exec = execution and any(
        r.get("status") == "blocked"
        for r in execution.get("item_results", [])
    )
    # RED: predicted delivery is past the contract deadline
    if predicted_finish_date and contract_finish_date:
        try:
            if predicted_finish_date > contract_finish_date:
                return "red"
        except Exception:
            pass
    if has_blocker or blocked_in_exec:
        # ORANGE: also escalate when internal target is threatened with carryovers
        return "orange"
    if internal_target_date and carryovers and predicted_finish_date:
        try:
            if predicted_finish_date > internal_target_date:
                return "orange"
        except Exception:
            pass
    if amendments:
        return "yellow"
    if carryovers:
        return "yellow"
    return "green"


# ── Owner matrix + replan routes (Round 4) ──────────────────────────────────

@app.get("/api/daily-plan/owner/matrix")
def daily_plan_owner_matrix(
    date_from: str = '',
    date_to: str = '',
    object_id: str = '',
    _: None = Depends(require_owner),
):
    """Мульти-объектная матрица плана/факта за диапазон дат.
    date_from/date_to: YYYY-MM-DD. object_id: фильтр по объекту (необязательно)."""
    today = business_today_str()
    df = date_from or today
    dt = date_to or today

    store = dpl.get_store_snapshot()
    plans = list(store["daily_plans"].values())
    if object_id:
        plans = [p for p in plans if p["object_id"] == object_id]
    plans = [p for p in plans if df <= p["date"] <= dt]
    plans.sort(key=lambda p: (p["date"], p["object_id"]))

    rows = []
    for plan in plans:
        plan_id = plan["id"]
        acceptance_list = [
            a for a in store["acceptances"].values()
            if a.get("daily_plan_id") == plan_id
        ]
        executions = [
            e for e in store["executions"].values()
            if e.get("plan_id") == plan_id
        ]
        carryovers = [
            c for c in store["carryovers"].values()
            if c.get("source_plan_id") == plan_id
        ]
        # Per item 8: amendments have no object_id/status field of their own —
        # resolve via daily_plan_id, and use the pending-amendment semantics
        # already implemented in get_pending_amendments (not-acked-by-all).
        amendments = [
            a for a in dpl.get_pending_amendments(plan_id)
        ]
        rows.append({
            "plan_id": plan_id,
            "date": plan["date"],
            "object_id": plan["object_id"],
            "stage_key": plan["stage_key"],
            "status": plan["status"],
            "version": plan["version"],
            "assigned_worker_count": len(plan.get("assigned_worker_ids", [])),
            "accepted_count": len(acceptance_list),
            "item_count": len(plan["items"]),
            "execution_count": len(executions),
            "carryover_count": len(carryovers),
            "pending_amendment_count": len(amendments),
        })

    return {
        "date_from": df,
        "date_to": dt,
        "object_id": object_id or None,
        "rows": rows,
        "total": len(rows),
    }


class ReplanRequestBody(BaseModel):
    notes: str = ''


@app.post("/api/daily-plan/replan/{object_id}")
def daily_plan_replan(
    object_id: str,
    body: ReplanRequestBody = ReplanRequestBody(),
    _: None = Depends(require_owner),
):
    """Лёгкая оценка рисков объекта + рекомендации по перепланированию.
    Не изменяет данные — только читает и возвращает risk-summary."""
    today = business_today_str()
    store = dpl.get_store_snapshot()

    plans = [p for p in store["daily_plans"].values() if p["object_id"] == object_id]
    plans.sort(key=lambda p: p["date"])

    if not plans:
        return {"object_id": object_id, "risk_level": "green", "issues": [], "recommendations": []}

    issues = []
    open_carryovers = [
        c for c in store["carryovers"].values()
        if c.get("object_id") == object_id and c.get("status") != "applied"
    ]
    if open_carryovers:
        issues.append({
            "type": "open_carryovers",
            "count": len(open_carryovers),
            "description": f"Есть незакрытые переносы ({len(open_carryovers)} ед.)",
        })

    plans_with_blockers = []
    for plan in plans:
        plan_blockers = [
            b for b in store.get("blockers", {}).values()
            if b.get("daily_plan_id") == plan["id"]
        ]
        if plan_blockers:
            plans_with_blockers.append({"plan_id": plan["id"], "date": plan["date"],
                                         "blocker_count": len(plan_blockers)})
    if plans_with_blockers:
        issues.append({
            "type": "blockers",
            "count": len(plans_with_blockers),
            "description": f"Зафиксированы препятствия на {len(plans_with_blockers)} дн.",
            "detail": plans_with_blockers,
        })

    # Item 8: amendments have no object_id/status field — resolve via the
    # object's plans -> daily_plan_id chain instead, using the existing
    # not-acked-by-all semantics in get_pending_amendments().
    pending_amendments = [
        a for plan in plans for a in dpl.get_pending_amendments(plan["id"])
    ]
    if pending_amendments:
        issues.append({
            "type": "pending_amendments",
            "count": len(pending_amendments),
            "description": f"Неподтверждённые изменения плана ({len(pending_amendments)})",
        })

    # Item 10: use the shared 4-tier risk function instead of an independent
    # inline 3-tier calc (which had no RED tier and could drift from owner/today's
    # logic). RED stays unreachable here until a caller supplies
    # predicted_finish_date/contract_finish_date -- no contract-date source exists
    # yet in this codebase; adding one is out of scope for a Round 1 bug fix.
    risk_level = _compute_risk_level(
        carryovers=open_carryovers,
        amendments=pending_amendments,
        blockers_for_plan=plans_with_blockers,
        execution=None,
    )

    recommendations = []
    if open_carryovers:
        recommendations.append("Пересмотрите план на следующие рабочие дни с учётом открытых переносов.")
    if plans_with_blockers:
        recommendations.append("Устраните препятствия (материалы/доступ) до следующей смены.")
    if pending_amendments:
        recommendations.append("Убедитесь, что работники подтвердили внесённые изменения.")

    return {
        "object_id": object_id,
        "risk_level": risk_level,
        "issues": issues,
        "recommendations": recommendations,
        "plan_count": len(plans),
        "open_carryover_count": len(open_carryovers),
    }


# ── Contract ingestion routes (Round 5 — Drive scope gated) ─────────────────

# moved to core/constants.py -- _EMPTY_CONTRACT_STORE


def _load_contract_store() -> dict:
    """Item 14: routed through the existing safe-store mechanism (CRITICAL_JSON_PATHS
    already includes CONTRACT_INGEST_STATE_FILE) instead of a raw json.load() that
    silently wiped the contract list on any corruption."""
    return _safe_load_json(CONTRACT_INGEST_STATE_FILE, {"contracts": {}})


def _save_contract_store(data: dict) -> None:
    tmp = CONTRACT_INGEST_STATE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONTRACT_INGEST_STATE_FILE)


@app.get("/api/contracts")
def list_contracts(_: None = Depends(require_owner)):
    """Список договоров и их статус обработки.
    DRIVE_SCOPE_REQUIRED: без CONTRACTS_DRIVE_FOLDER_ID ingestion не запускается."""
    store = _load_contract_store()
    contracts = list(store["contracts"].values())
    contracts.sort(key=lambda c: c.get("ingested_at", 0), reverse=True)
    return {
        "drive_configured": bool(CONTRACTS_DRIVE_FOLDER_ID),
        "drive_scope_status": "DRIVE_SCOPE_REQUIRED" if not CONTRACTS_DRIVE_FOLDER_ID else "configured",
        "total": len(contracts),
        "contracts": [
            {
                "id": c["id"],
                "file_name": c.get("file_name", ""),
                "status": c.get("status", "unknown"),
                "ingested_at": c.get("ingested_at"),
                "approved_at": c.get("approved_at"),
                "rejected_at": c.get("rejected_at"),
                "error": c.get("error"),
                "has_draft_plan": bool(c.get("project_plan_draft")),
            }
            for c in contracts
        ],
    }


@app.get("/api/contracts/{contract_id}")
def get_contract(
    contract_id: str,
    _: None = Depends(require_owner),
):
    """Полный договор с извлечёнными фактами и черновиком плана."""
    store = _load_contract_store()
    contract = store["contracts"].get(contract_id)
    if not contract:
        raise HTTPException(404, "Договор не найден")
    return contract


class ContractReviewBody(BaseModel):
    notes: str = ''


@app.post("/api/contracts/{contract_id}/approve")
def approve_contract(
    contract_id: str,
    body: ContractReviewBody = ContractReviewBody(),
    user: dict = Depends(get_current_user),
    _: None = Depends(require_owner),
):
    """Owner утверждает черновик плана из договора (УТВЕРДИТЬ).
    После утверждения project_plan_draft становится publishable для работников."""
    with _CONTRACT_INGEST_LOCK:
        store = _load_contract_store()
        contract = store["contracts"].get(contract_id)
        if not contract:
            raise HTTPException(404, "Договор не найден")
        if contract.get("status") not in ("ingested", "needs_manual_review"):
            raise HTTPException(400, f"Договор в статусе '{contract['status']}' не может быть утверждён")
        if not contract.get("project_plan_draft"):
            raise HTTPException(400, "Нет черновика плана для утверждения")
        contract["status"] = "approved"
        contract["approved_at"] = time.time()
        contract["approved_by"] = str(user['id'])
        contract["review_notes"] = body.notes.strip()[:1000]
        _save_contract_store(store)
    return {"status": "approved", "contract_id": contract_id}


@app.post("/api/contracts/{contract_id}/reject")
def reject_contract(
    contract_id: str,
    body: ContractReviewBody = ContractReviewBody(),
    user: dict = Depends(get_current_user),
    _: None = Depends(require_owner),
):
    """Owner отклоняет черновик плана (ОТКЛОНИТЬ)."""
    with _CONTRACT_INGEST_LOCK:
        store = _load_contract_store()
        contract = store["contracts"].get(contract_id)
        if not contract:
            raise HTTPException(404, "Договор не найден")
        if contract.get("status") == "approved":
            raise HTTPException(400, "Утверждённый договор нельзя отклонить без отмены")
        contract["status"] = "rejected"
        contract["rejected_at"] = time.time()
        contract["rejected_by"] = str(user['id'])
        contract["review_notes"] = body.notes.strip()[:1000]
        _save_contract_store(store)
    return {"status": "rejected", "contract_id": contract_id}


@app.post("/api/contracts/ingest")
def trigger_contract_ingest(
    _: None = Depends(require_owner),
):
    """Ручной триггер перепроверки Drive-папки.
    DRIVE_SCOPE_REQUIRED: если CONTRACTS_DRIVE_FOLDER_ID не задан — 503."""
    if not CONTRACTS_DRIVE_FOLDER_ID:
        raise HTTPException(503, "DRIVE_SCOPE_REQUIRED: задайте CONTRACTS_DRIVE_FOLDER_ID в env")
    return {
        "status": "trigger_sent",
        "message": "Синхронизация с Drive будет выполнена при следующем запуске plan_sync / contract_ingest.py",
        "folder_id": CONTRACTS_DRIVE_FOLDER_ID,
    }


# 31.07 (Release-аудит П4): регистрация критичных сторов -- в самом конце модуля,
# после того как все _FILE-константы (включая rl.ROADMAP_FILE/rl.STAGE_REQUESTS_FILE,
# доступные только после _load_repo_roadmap_lib() выше) уже определены. Порча этих
# файлов не должна тихо деградировать к default (см. _safe_load_json/update_json_transaction).
CRITICAL_JSON_PATHS.update({
    ROLES_FILE,
    OBJECT_ASSIGNMENTS_FILE,
    CHECKIN_META_FILE,
    CHAT_FILE,
    CHAT_ARCHIVE_FILE,
    ABWESENHEIT_FILE,
    WORKER_PROFILES_FILE,
    TASKS_FILE,
    CRITICAL_ALERTS_FILE,
    rl.ROADMAP_FILE,
    rl.STAGE_REQUESTS_FILE,
    DAILY_PLAN_STORE_FILE,
    FINISH_OUTBOX_FILE,
    OBJECT_INFO_FILE,
    OBJECT_IMAGES_FILE,
    WORK_CALENDAR_FILE,
    CHAT_THREAD_META_FILE,
    CONTRACT_INGEST_STATE_FILE,
})
