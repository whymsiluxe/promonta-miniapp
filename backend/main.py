#!/usr/bin/env python3
"""Promonta Mini App — FastAPI backend. Фаза 2 плана: скелет + initData-auth + roles.
Запуск: uvicorn main:app --host 127.0.0.1 --port 8001
"""
import copy
import csv
import hashlib
import hmac
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import base64
import magic
from pydantic import BaseModel

sys.path.insert(0, '/home/promonta/agent')

BOT_TOKEN = os.environ['BOT_TOKEN']
ROLES_FILE = '/home/promonta/agent/miniapp/roles.json'
INIT_DATA_MAX_AGE = 3600  # секунд — Telegram initData считается протухшим через час

app = FastAPI(title="Promonta Mini App", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://web.telegram.org"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

AUDIT_FILE = '/home/promonta/agent/miniapp/audit.log'
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

    if request.method in ("POST", "PATCH", "DELETE") and response.status_code < 400:
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


_json_locks: dict = {}
_json_locks_guard = __import__('threading').Lock()


def _lock_for(path: str):
    """Один threading.Lock на файл — гонки read-modify-write между конкурентными
    запросами (напр. owner подтверждает заявку в момент, когда worker её закрывает)
    иначе тихо теряют одно из двух изменений (10.29 — Fable-аудит)."""
    with _json_locks_guard:
        if path not in _json_locks:
            _json_locks[path] = __import__('threading').Lock()
        return _json_locks[path]


def _atomic_write_json(path: str, data, ensure_ascii: bool = False):
    """Пишет во временный файл + os.replace — процесс, упавший посреди записи
    (напр. systemctl restart), не оставляет обрезанный JSON, который потом валит
    json.load на старте всех эндпоинтов, читающих этот стор (10.29).

    ВАЖНО: сам по себе не защищает от read-modify-write гонки -- если код делает
    `data = _safe_load_json(path, default); data[k] = v; _atomic_write_json(path, data)`,
    лок захватывается только на сам _atomic_write_json, ЧТЕНИЕ происходит СНАРУЖИ лока.
    Два параллельных запроса могут оба прочитать одинаковую версию до того как первый
    успеет записать -- второй молча затирает изменения первого. Для любого места, где
    read-modify-write должен быть атомарным (не просто "запись не оставит corrupt файл"),
    используй update_json_transaction() ниже, не _safe_load_json+_atomic_write_json
    по отдельности (28.07, real bug found by external audit, ТЗ п.5)."""
    with _lock_for(path):
        tmp_path = f'{path}.tmp-{os.getpid()}'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii)
        os.replace(tmp_path, path)


def update_json_transaction(path: str, default, mutator):
    """Read-modify-write под ОДНИМ захватом лока -- закрывает гонку, которую
    _atomic_write_json сам по себе не решает (см. комментарий выше). mutator получает
    текущую структуру (или default, если файла нет/битый), мутирует её IN-PLACE
    (list.append/dict[k]=v — не return нового объекта, чтобы не плодить два разных
    паттерна использования) и может опционально вернуть значение для вызывающего кода.
    НЕ вызывать _atomic_write_json изнутри mutator -- тот же _lock_for(path) не
    reentrant, будет deadlock (threading.Lock, не RLock)."""
    with _lock_for(path):
        if not os.path.exists(path):
            data = default() if callable(default) else copy.deepcopy(default)
        else:
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                print(f'ERROR: {path} corrupt JSON in transaction, falling back to default')
                data = default() if callable(default) else copy.deepcopy(default)
        result = mutator(data)
        tmp_path = f'{path}.tmp-{os.getpid()}'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_path, path)
        return result



def _safe_load_json(path: str, default):
    """Единая точка для всех _load_* сторов -- corrupt JSON (диск full / kill -9
    посреди записи, до _atomic_write_json или на старых файлах без него) не должен
    ронять запрос 500-кой, деградируем к default с явным логом. Раньше только
    roles.json имел эту защиту, 17 других _load_* падали с необработанным
    JSONDecodeError на первом же corrupt-файле."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f'ERROR: {path} corrupt JSON, falling back to default: {default!r}')
        return default


_ALLOWED_IMAGE_MIME_EXT = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/gif': 'gif',
}


def sniff_image(raw: bytes) -> str | None:
    """Content-Type из клиента (file.content_type) -- заголовок, который клиент
    присылает сам, ничего не проверяя по факту (spoofable: переименовать .exe в
    .jpg с Content-Type: image/jpeg проходило раньше без вопросов). Смотрит
    реальные magic bytes через libmagic, возвращает канонический MIME из
    allowlist или None, если это не один из 4 разрешённых форматов изображений
    -- вызывающий код решает как реагировать (обычно HTTPException 400)."""
    detected = magic.from_buffer(raw, mime=True)
    return detected if detected in _ALLOWED_IMAGE_MIME_EXT else None


def sniff_image_or_pdf(raw: bytes) -> str | None:
    """Как sniff_image(), плюс PDF -- для endpoints, что принимают либо
    изображение, либо документ (object documents, AI attachments)."""
    detected = magic.from_buffer(raw, mime=True)
    if detected in _ALLOWED_IMAGE_MIME_EXT or detected == 'application/pdf':
        return detected
    return None


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


NOTIFIED_USERS_FILE = '/home/promonta/agent/miniapp/notified_users.json'


NOTIFIED_USERS_TTL = 7 * 86400  # 7 дней — потом можно напомнить owner'у снова (10.29)


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
ONLINE_THRESHOLD_SECONDS = 5 * 60


def get_current_user(x_telegram_init_data: str = Header(...)) -> dict:
    user = validate_init_data(x_telegram_init_data)
    # Whitelist (Фаза 10.1): доступ только тем, кого владелец явно добавил в roles.json —
    # раньше любой Telegram user_id молча получал worker-права по умолчанию (см. get_role ниже).
    roles = _load_roles()
    if str(user['id']) not in roles:
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


def can_access_object(user: dict, role: str, object_id: str) -> bool:
    """owner видит/управляет всем; worker -- только объекты, на которые назначен
    (object_assignments.json). Единая точка правды для object-scoped routes --
    раньше большинство из них проверяли только get_current_user (авторизован ли
    вообще), не было ли это чужим объектом."""
    if role == 'owner':
        return True
    assignments = _load_assignments()
    return any(str(a.get('user_id')) == str(user['id']) for a in assignments.get(str(object_id), []))


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
    pending = sorted(set(notified.keys()) - set(roles.keys()))
    return {
        "roles": [{"user_id": uid, "role": r,
                   "name": _sanitize_display_name(profiles.get(uid, {}).get('name'), uid)}
                  for uid, r in roles.items()],
        "pending": [{"user_id": uid,
                     "name": _sanitize_display_name(profiles.get(uid, {}).get('name'), uid)}
                    for uid in pending],
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


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/me")
def me(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    return {"user_id": user['id'], "name": user.get('first_name'), "role": role}


# ---------- Workers list (для bubble-assign, Фаза 2 → доделано в Фазе 3) ----------
@app.get("/api/workers")
def list_workers(user: dict = Depends(get_current_user)):
    roles = _load_roles()
    profiles = _load_worker_profiles()
    # объединяем ключи из roles.json (явные роли) и worker_profiles.json (кто уже
    # проходил онбординг-квиз, но мог не попасть в roles.json явно) — иначе воркеры,
    # заполнившие анкету, но не добавленные владельцем в roles.json, не видны в списке
    all_ids = set(roles.keys()) | set(profiles.keys())
    workers = []
    for uid in all_ids:
        p = profiles.get(uid, {})
        last_seen = _last_seen.get(uid)
        workers.append({
            'user_id': uid,
            'role': roles.get(uid, 'worker'),
            'name': _sanitize_display_name(p.get('name'), uid),
            'skills': p.get('skills', []),
            'quiz_completed': p.get('quiz_completed', False),
            'online': bool(last_seen and (time.time() - last_seen) < ONLINE_THRESHOLD_SECONDS),
        })
    return {'workers': workers}


# ---------- Профиль работника: навыки + онбординг-квиз (Фаза 2/8) ----------
WORKER_PROFILES_FILE = '/home/promonta/agent/miniapp/worker_profiles.json'
SKILL_OPTIONS = [
    "Штукатурка", "Малярные работы", "Электрика", "Кровля", "Фасад",
    "Сантехника", "Плитка", "Демонтаж", "Гипсокартон (сухая стройка)",
    "Стяжка пола / бетонные работы", "Утепление / изоляция", "Каменная кладка",
    "Столярные / плотницкие работы", "Сварочные работы", "Отопление / вентиляция",
    "Ландшафт / благоустройство территории", "Малярные работы фасада",
    "Монтаж окон и дверей", "Кровельная жесть / водостоки", "Строительные леса",
]


def _load_worker_profiles() -> dict:
    return _safe_load_json(WORKER_PROFILES_FILE, {})


def _save_worker_profiles(profiles: dict):
    _atomic_write_json(WORKER_PROFILES_FILE, profiles)


def _get_worker_profile(user_id) -> dict:
    profiles = _load_worker_profiles()
    return profiles.get(str(user_id), {"skills": [], "quiz_completed": False})


_INVISIBLE_FILLER_CHARS = (
    'ᅟᅠㅤﾠ'  # Hangul choseong/jungseong filler + halfwidth filler —
                                 # популярный трюк для "невидимого" имени в Telegram
)


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
    return {"user_id": user['id'], "skill_options": SKILL_OPTIONS, **profile}


@app.get("/api/users/{target_id}/card")
def get_user_card(target_id: str, user: dict = Depends(get_current_user)):
    """Публичная карточка (10.10) — доступна любому авторизованному пользователю,
    в отличие от /api/profile/stats (там чужой профиль видит только owner).
    Только неконфиденциальные поля: имя, роль, навыки. Без часов/истории объектов/бюджета."""
    roles = _load_roles()
    if target_id not in roles:
        raise HTTPException(404, "Пользователь не найден")
    profile = _get_worker_profile(target_id)
    has_avatar = bool(profile.get('avatar'))
    return {
        "user_id": target_id,
        "name": _sanitize_display_name(profile.get('name'), target_id),
        "role": roles[target_id],
        "skills": profile.get('skills', []),
        "has_avatar": has_avatar,
    }


class ProfileUpdateBody(BaseModel):
    name: str | None = None  # 24.07: ручное имя — нужно, когда Telegram first_name
    # пуст/скрыт/состоит из невидимых символов (self-heal в get_my_profile не может
    # исцелиться нечем в этом случае).
    skills: list[str] | None = None
    quiz_completed: bool | None = None
    pants_size: str | None = None
    shirt_size: str | None = None
    shoe_size: str | None = None
    birthday: str | None = None  # YYYY-MM-DD, только месяц/день значимы (10.31)


@app.patch("/api/profile/me")
def update_my_profile(body: ProfileUpdateBody, user: dict = Depends(get_current_user)):
    profiles = _load_worker_profiles()
    key = str(user['id'])
    profile = profiles.get(key, {"skills": [], "quiz_completed": False})
    updates = body.dict(exclude_unset=True)
    if 'name' in updates:
        cleaned = _sanitize_display_name(updates['name'], '')
        if not cleaned:
            raise HTTPException(400, "Имя не должно быть пустым")
        updates['name'] = cleaned[:100]
    profile.update(updates)
    profiles[key] = profile
    _save_worker_profiles(profiles)
    return profile


# ---------- Фаза 8: аватар + агрегированная статистика профиля ----------
AVATAR_DIR = '/home/promonta/agent/miniapp/avatars'
AVATAR_MAX_BYTES = 4 * 1024 * 1024
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
        import objekte_lib as o
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
    from datetime import date, timedelta
    target = user_id if (role == 'owner' and user_id) else str(user['id'])
    sessions = [s for s in _load_checkin_meta() if str(s.get('user_id')) == target]

    # 21.07: owner смотрит СВОЙ профиль (без ?user_id=) — не отмечает check-in физически,
    # личные часы всегда пусты. Вместо этого — агрегат "часы по каждому работнику за неделю".
    team_hours = None
    if role == 'owner' and not user_id:
        roles = _load_roles()
        worker_ids = [uid for uid, r in roles.items() if r == 'worker']
        profiles_map = _load_worker_profiles()
        today0 = date.today()
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
        today0 = date.today()
        days = []
        for i in range(29, -1, -1):
            d = today0 - timedelta(days=i)
            iso = d.isoformat()
            hours = sum(_hours_from_session(s) for s in sessions if s.get('date') == iso)
            days.append({'date': iso, 'hours': round(hours, 2)})
        period_data = {'kind': 'heatmap', 'days': days, 'total_hours': round(sum(d['hours'] for d in days), 1)}
    elif period in ('3months', 'year'):
        weeks_back = 13 if period == '3months' else 52
        today0 = date.today()
        buckets = []
        for i in range(weeks_back - 1, -1, -1):
            week_end = today0 - timedelta(days=i * 7)
            week_start = week_end - timedelta(days=6)
            hours = sum(_hours_from_session(s) for s in sessions
                        if week_start.isoformat() <= s.get('date', '') <= week_end.isoformat())
            buckets.append({'label': week_start.isoformat(), 'hours': round(hours, 2)})
        period_data = {'kind': 'bar', 'buckets': buckets, 'total_hours': round(sum(b['hours'] for b in buckets), 1)}

    # 7 кругов дней недели: последние 7 дней, часы на день
    today = date.today()
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
    return {
        'user_id': target,
        'name': _sanitize_display_name(
            profile.get('name') or (user.get('first_name') if target == str(user['id']) else None),
            target,
        ),
        'role': _load_roles().get(target, 'worker'),
        'skills': profile.get('skills', []),
        'sizes': {
            'pants': profile.get('pants_size', ''),
            'shirt': profile.get('shirt_size', ''),
            'shoe': profile.get('shoe_size', ''),
        },
        'has_avatar': bool(profile.get('avatar')),
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


# ---------- Назначения работников на объекты (Фаза 2c, восстановлено после инцидента Фазы 3) ----------
OBJECT_ASSIGNMENTS_FILE = '/home/promonta/agent/miniapp/object_assignments.json'
OBJECT_IMAGES_FILE = '/home/promonta/agent/miniapp/object_images.json'
OBJECT_PHOTO_DIR = '/home/promonta/agent/miniapp/object_photos'


def _load_assignments() -> dict:
    return _safe_load_json(OBJECT_ASSIGNMENTS_FILE, {})


def _save_assignments(assignments: dict):
    _atomic_write_json(OBJECT_ASSIGNMENTS_FILE, assignments)


def _load_object_images() -> dict:
    return _safe_load_json(OBJECT_IMAGES_FILE, {})


def _save_object_images(images: dict):
    _atomic_write_json(OBJECT_IMAGES_FILE, images)


OBJECT_PHOTO_MAX = 8  # разумный потолок для carousel, не безлимит


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
    images = _load_object_images()
    photos = images.get(object_id) or []
    if not photos or index < 0 or index >= len(photos):
        raise HTTPException(404, "Фото не загружено")
    path = os.path.join(OBJECT_PHOTO_DIR, photos[index])
    if not os.path.exists(path):
        raise HTTPException(404, "Файл отсутствует")
    return FileResponse(path)


_sheets_cache: dict = {}
SHEETS_CACHE_TTL = 45  # секунд — list_objects/get_alerts дёргались синхронно на Google Sheets
                        # на каждый запрос, блокируя event loop на время RTT (10.29, Fable-аудит)


def _cached_get_used_range(tab_name: str):
    now = time.time()
    cached = _sheets_cache.get(tab_name)
    if cached and now - cached[0] < SHEETS_CACHE_TTL:
        return cached[1]
    import objekte_lib as o
    rows = o.get_used_range(tab_name)
    _sheets_cache[tab_name] = (now, rows)
    return rows


BUDGET_FIELDS = ['Бюджет (EUR)', 'Потрачено (EUR)', 'потрачено в % от бюджета']


@app.get("/api/objects")
def list_objects(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    rows = _cached_get_used_range('Объекты')
    if not rows:
        return {"objects": []}
    header, data = rows[0], rows[1:]
    assignments = _load_assignments()
    profiles = _load_worker_profiles()
    images = _load_object_images()

    def _user_info(uid: str) -> dict:
        p = profiles.get(str(uid), {})
        return {"user_id": str(uid), "name": _sanitize_display_name(p.get('name'), str(uid))}

    objects = []
    for r in data:
        obj = dict(zip(header, r))
        oid = str(obj.get('ID объекта', ''))
        obj['assigned_users'] = [_user_info(a['user_id']) for a in assignments.get(oid, [])]
        obj['photo_count'] = len(images.get(oid) or [])
        if role != 'owner':
            # 10.5: бюджет — финансовая информация, работнику видеть не должен.
            for f in BUDGET_FIELDS:
                obj.pop(f, None)
        objects.append(obj)
    return {"objects": objects}


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
            names[str(obj.get('ID объекта', ''))] = obj.get('Название', '') or obj.get('Адрес', '')

    result = []
    for oid, lst in assignments.items():
        for a in lst:
            if a.get('user_id') != uid:
                continue
            result.append({
                "object_id": oid,
                "object_name": names.get(oid, oid),
                "stage_id": a.get('stage_id', ''),
                "date_from": a.get('date_from', ''),
                "date_to": a.get('date_to', ''),
                "assigned_at": a.get('assigned_at', ''),
            })
    result.sort(key=lambda r: r['date_from'] or '', reverse=True)
    return {"assignments": result}


class AssignBody(BaseModel):
    user_id: str
    stage_id: str = ''
    date_from: str = ''
    date_to: str = ''


def _dates_overlap(a_from: str, a_to: str, b_from: str, b_to: str) -> bool:
    if not (a_from and a_to and b_from and b_to):
        return False
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
        already = any(
            a['user_id'] == str(body.user_id) and a.get('stage_id', '') == body.stage_id
            for a in assignments[key]
        )
        if already:
            return
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
        for other_oid, other_list in assignments.items():
            if other_oid == key:
                continue
            for a in other_list:
                if a['user_id'] != str(body.user_id):
                    continue
                if _dates_overlap(body.date_from, body.date_to, a.get('date_from', ''), a.get('date_to', '')):
                    raise HTTPException(
                        409,
                        f"Этот работник уже назначен на объект {other_oid} "
                        f"на период {a.get('date_from')} — {a.get('date_to')}"
                    )
        assignments[key].append({
            'user_id': str(body.user_id),
            'stage_id': body.stage_id,
            'date_from': body.date_from,
            'date_to': body.date_to,
            'assigned_at': datetime.utcnow().isoformat()
        })

    update_json_transaction(OBJECT_ASSIGNMENTS_FILE, {}, _mutator)
    return {"status": "ok"}


@app.delete("/api/objects/{object_id}/assign/{user_id}")
def unassign_user(object_id: str, user_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    key = str(object_id)

    def _mutator(assignments):
        if key in assignments:
            assignments[key] = [a for a in assignments[key] if a['user_id'] != str(user_id)]

    update_json_transaction(OBJECT_ASSIGNMENTS_FILE, {}, _mutator)
    return {"status": "ok"}


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

    working_now = []
    finished_today = []
    for s in today_sessions:
        entry = {
            "user_id": str(s['user_id']),
            "worker_name": _worker_name(s['user_id']),
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

    # "Назначен сегодня, но не начал" -- assignment date_from/date_to охватывает today,
    # и юзер ни разу не появился в today_sessions (ни работает, ни уже закончил).
    assignments = _load_assignments()
    not_started = []
    seen_uids = set()
    for oid, lst in assignments.items():
        for a in lst:
            uid = str(a.get('user_id', ''))
            if not uid or uid in working_uids or uid in finished_uids or uid in seen_uids:
                continue
            date_from, date_to = a.get('date_from', ''), a.get('date_to', '')
            if date_from and date_to and date_from <= today <= date_to:
                seen_uids.add(uid)
                not_started.append({
                    "user_id": uid,
                    "worker_name": _worker_name(uid),
                    "object_id": oid,
                    "object_name": object_names.get(oid, oid),
                })

    return {
        "date": today,
        "working_now": working_now,
        "not_started": not_started,
        "finished_today": finished_today,
    }


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
                pct_raw = obj.get('потрачено в % от бюджета') or obj.get('Потрачено %') or '0'
                try:
                    pct = float(pct_raw)
                except ValueError:
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
        import tools_lib as tl
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


ALERT_DISMISSALS_FILE = '/home/promonta/agent/miniapp/alert_dismissals.json'
ALERT_DISMISS_TTL = 24 * 3600


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
    import tools_lib as tl
    return {"tools": tl.list_tools()}


@app.get("/api/tools/{serial}/history")
def tool_history(serial: str, user: dict = Depends(get_current_user)):
    import tools_lib as tl
    return {"history": tl.tool_history(serial)}


class CheckoutBody(BaseModel):
    holder: str
    object_name: str


@app.patch("/api/tools/{serial}/checkout")
def checkout_tool(serial: str, body: CheckoutBody, user: dict = Depends(get_current_user)):
    import tools_lib as tl
    try:
        # 22.07: worker сам оформляет checkout — user['id'] это и есть реальный держатель,
        # пишем как holder_id чтобы avatar на карточке инструмента был кликабельным (openUserCard).
        tl.checkout_tool(serial, body.holder, body.object_name, user.get('first_name', str(user['id'])),
                          holder_id=str(user['id']))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "ok"}


class ToolUpdateBody(BaseModel):
    status: str
    holder: str = ''
    object_name: str = ''


@app.patch("/api/tools/{serial}")
def update_tool(serial: str, body: ToolUpdateBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    import tools_lib as tl
    try:
        tl.update_tool_status(serial, body.status, body.holder, body.object_name, user.get('first_name', str(user['id'])))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "ok"}


class NewToolBody(BaseModel):
    name: str
    category: str


@app.post("/api/tools")
def create_tool(body: NewToolBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    import tools_lib as tl
    serial = tl.add_tool(body.name, body.category, user.get('first_name', str(user['id'])))
    return {"serial": serial}


# ---------- Angebot generator ----------
import subprocess
import uuid
import urllib.request as _urlreq
from fastapi.responses import FileResponse


def send_telegram_message(chat_id, text):
    """sendMessage через Bot API — тем же стандартно-библиотечным путём, что send_pdf_to_chat."""
    body = json.dumps({'chat_id': chat_id, 'text': text}).encode()
    req = _urlreq.Request(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
        data=body, method='POST',
        headers={'Content-Type': 'application/json'}
    )
    _urlreq.urlopen(req, timeout=10)


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


ANGEBOT_SCRIPT = '/home/promonta/agent/miniapp/angebot_free.js'
ANGEBOT_OUT_DIR = '/home/promonta/agent/miniapp/angebote'
os.makedirs(ANGEBOT_OUT_DIR, exist_ok=True)


def require_angebot_access(role: str = Depends(get_role)):
    if role not in ('owner', 'manager'):
        raise HTTPException(403, "только owner/manager могут создавать Angebot")


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

    config_path = f'/tmp/{uuid.uuid4().hex}.json'
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False)

    try:
        result = subprocess.run(['node', ANGEBOT_SCRIPT, config_path],
                               capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise HTTPException(500, f'PDF-Generierung fehlgeschlagen: {result.stderr[-500:]}')
    finally:
        os.remove(config_path)

    filename = f"Angebot_{body.kunde.name.replace(' ', '_')}.pdf"
    send_pdf_to_chat(user['id'], out_path, filename, f'Angebot für {body.kunde.name}')
    return FileResponse(out_path, media_type='application/pdf', filename=filename)


# ---------- Aufgaben (tasks) ----------
@app.get("/api/objects/{object_id}/tasks")
def get_tasks(object_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    import objekte_lib as o
    return {"tasks": o.list_tasks(object_id)}


class TaskBody(BaseModel):
    text: str


@app.post("/api/objects/{object_id}/tasks")
def create_task(object_id: str, body: TaskBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    import objekte_lib as o
    if not body.text.strip():
        raise HTTPException(400, "Текст не может быть пустым")
    task_id = o.add_task(object_id, body.text.strip(), user.get('first_name', str(user['id'])))
    return {"task_id": task_id}


@app.patch("/api/tasks/{task_id}/complete")
def complete_task(task_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    import objekte_lib as o
    try:
        o.complete_task(task_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "ok"}


# ---------- Инфо объекта (24.07, Step 3): work-items + документы ----------
OBJECT_INFO_FILE = '/home/promonta/agent/miniapp/object_info.json'
OBJECT_DOC_DIR = '/home/promonta/agent/miniapp/object_documents'
os.makedirs(OBJECT_DOC_DIR, exist_ok=True)


def _load_object_info() -> dict:
    return _safe_load_json(OBJECT_INFO_FILE, {})


def _save_object_info(data: dict):
    _atomic_write_json(OBJECT_INFO_FILE, data)


def _object_info_entry(object_id: str) -> dict:
    data = _load_object_info()
    return data.get(object_id, {"items": [], "documents": [], "description": ""})


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
    data = _load_object_info()
    entry = data.setdefault(object_id, {"items": [], "documents": [], "description": ""})
    entry["description"] = body.description.strip()[:2000]
    _save_object_info(data)
    return {"description": entry["description"]}


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
    data = _load_object_info()
    entry = data.setdefault(object_id, {"items": [], "documents": []})
    entry.setdefault("items", []).append(item)
    _save_object_info(data)
    return {"item": item}


@app.delete("/api/objects/{object_id}/info-items/{item_id}")
def delete_object_info_item(object_id: str, item_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    data = _load_object_info()
    entry = data.get(object_id)
    if not entry:
        raise HTTPException(404, "Не найдено")
    before = len(entry.get("items", []))
    entry["items"] = [i for i in entry.get("items", []) if i["id"] != item_id]
    if len(entry["items"]) == before:
        raise HTTPException(404, "Не найдено")
    _save_object_info(data)
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
    data = _load_object_info()
    entry = data.setdefault(object_id, {"items": [], "documents": []})
    entry.setdefault("documents", []).append(doc)
    _save_object_info(data)
    return {"document": doc}


@app.delete("/api/objects/{object_id}/documents/{doc_id}")
def delete_object_document(object_id: str, doc_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    data = _load_object_info()
    entry = data.get(object_id)
    if not entry:
        raise HTTPException(404, "Не найдено")
    doc = next((d for d in entry.get("documents", []) if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(404, "Не найдено")
    entry["documents"] = [d for d in entry.get("documents", []) if d["id"] != doc_id]
    _save_object_info(data)
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
    args = ['python3', '/home/promonta/agent/create_object.py', body.name, body.adresse, body.budget]
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
            ['python3', '/home/promonta/agent/create_object_folder.py', object_id, body.name],
            capture_output=True, text=True, timeout=30
        )

    return {"result": result.stdout.strip(), "object_id": object_id}


class StatusBody(BaseModel):
    status: str


VALID_OBJECT_STATUSES = {'В работе', 'Пауза', 'Завершён'}


@app.patch("/api/objects/{object_id}/status")
def update_object_status(object_id: str, body: StatusBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    if body.status not in VALID_OBJECT_STATUSES:
        raise HTTPException(400, f'Недопустимый статус: {body.status}')
    import objekte_lib as o
    try:
        o.update_object_field(object_id, 'Статус', body.status)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "ok"}


# ---------- Rechnung generator ----------
RECHNUNG_SCRIPT = '/home/promonta/agent/miniapp/rechnung.js'
RECHNUNG_OUT_DIR = '/home/promonta/agent/miniapp/rechnungen'
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

    config_path = f'/tmp/{uuid.uuid4().hex}.json'
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False)

    try:
        result = subprocess.run(['node', RECHNUNG_SCRIPT, config_path],
                               capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise HTTPException(500, f'PDF-Generierung fehlgeschlagen: {result.stderr[-500:]}')
    finally:
        os.remove(config_path)

    filename = f"Rechnung_{body.kunde.name.replace(' ', '_')}.pdf"
    send_pdf_to_chat(user['id'], out_path, filename, f'{body.nummer} — {body.kunde.name}')
    return FileResponse(out_path, media_type='application/pdf', filename=filename)


# ---------- Weather feed ----------
WEATHER_FEED_FILE = '/home/promonta/agent/.weather_feed.json'


WEATHER_REACTIONS_FILE = '/home/promonta/agent/miniapp/weather_reactions.json'
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
NEWS_REACTIONS_FILE = '/home/promonta/agent/miniapp/news_reactions.json'
# {post_id: {user_id: "like"|"dislike"}} — по одной реакции на пост от юзера, апдейт при повторном клике.
NEWS_READS_FILE = '/home/promonta/agent/miniapp/news_reads.json'
# {user_id: {category: read_count}} — накопитель для будущей адаптивной фильтрации ленты под интересы.


def _load_news_reactions() -> dict:
    return _safe_load_json(NEWS_REACTIONS_FILE, {})


def _save_news_reactions(data: dict):
    _atomic_write_json(NEWS_REACTIONS_FILE, data)


def _load_news_reads() -> dict:
    return _safe_load_json(NEWS_READS_FILE, {})


def _save_news_reads(data: dict):
    _atomic_write_json(NEWS_READS_FILE, data)


BIRTHDAY_ALERTS_FILE = '/home/promonta/agent/miniapp/birthday_alerts.json' 

def _load_birthday_alerts() -> list:
    return _safe_load_json(BIRTHDAY_ALERTS_FILE, [])


def _save_birthday_alerts(items: list):
    _atomic_write_json(BIRTHDAY_ALERTS_FILE, items)


def _check_upcoming_birthdays():
    """10.31: за 2 дня до дня рождения worker'а — критический алерт owner'у +
    инфо-запись в ленту для всех (видно в суб-табе "Инфо"). Ленивая проверка при
    заходе на GET /api/feed/birthdays — не отдельный systemd timer, раз в сутки
    достаточно, а миниапп открывают каждый день."""
    profiles = _load_worker_profiles()
    today = datetime.utcnow().date()
    target_date = today + timedelta(days=2)
    alerts = _load_birthday_alerts()
    already_alerted = {(a['user_id'], a['year']) for a in alerts}

    for uid, profile in profiles.items():
        bday = profile.get('birthday')
        if not bday:
            continue
        try:
            bd = datetime.strptime(bday, '%Y-%m-%d').date()
        except ValueError:
            continue
        if (bd.month, bd.day) != (target_date.month, target_date.day):
            continue
        if (uid, target_date.year) in already_alerted:
            continue

        name = _sanitize_display_name(profile.get('name'), uid)
        entry = {
            'user_id': uid, 'name': name, 'year': target_date.year,
            'date': target_date.strftime('%Y-%m-%d'), 'created_at': int(time.time()),
        }
        alerts.append(entry)

        try:
            _create_critical_alert(
                target_user_id=next((o for o, r in _load_roles().items() if r == 'owner'), uid),
                kind='birthday',
                title=f'🎂 У {name} день рождения через 2 дня',
                ref_id=uid,
            )
        except Exception:
            pass

    _save_birthday_alerts(alerts)


@app.get("/api/feed/birthdays")
def get_birthday_feed(user: dict = Depends(get_current_user)):
    _check_upcoming_birthdays()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    upcoming = [a for a in _load_birthday_alerts() if a['date'] >= today]
    return {"birthdays": upcoming}


@app.get("/api/feed/news")
def get_news_feed(user: dict = Depends(get_current_user)):
    if not os.path.exists(NEWS_FEED_FILE):
        return {"feed": []}
    with open(NEWS_FEED_FILE, encoding='utf-8') as f:
        feed = json.load(f)
    reactions = _load_news_reactions()
    uid = str(user['id'])
    for post in feed:
        post['my_reaction'] = reactions.get(post['id'], {}).get(uid)

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


# ---------- Photo feed ----------
# Хранение: файлы на диске + метадата в JSON. Любой сотрудник грузит фото с объекта,
# все видят общей лентой (без ролевых ограничений — как командный чат).
PHOTO_DIR = '/home/promonta/agent/miniapp/feed_photos'
PHOTO_META_FILE = '/home/promonta/agent/miniapp/feed_photos.json'
PHOTO_MAX_BYTES = 8 * 1024 * 1024  # 8 МБ
PHOTO_MAX_COUNT = 300  # старые фото (и файлы) обрезаются сверху этого лимита
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


PHOTO_MAX_FILES = 10  # разумный потолок на пост, не архитектурное ограничение


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
        entry.setdefault('comments', []).append({
            'id': uuid.uuid4().hex,
            'user_id': str(user['id']),
            'name': user.get('first_name', str(user['id'])),
            'text': text,
            'at': datetime.utcnow().isoformat(),
        })
        _save_photo_meta(items)
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
CHAT_FILE = '/home/promonta/agent/miniapp/chat_messages.json'
CHAT_ARCHIVE_FILE = '/home/promonta/agent/miniapp/chat_messages_archive.json'
CHAT_MAX = 200
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
    with open(CHAT_ARCHIVE_FILE, 'w', encoding='utf-8') as f:
        json.dump(archive, f, ensure_ascii=False)


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
    with open(CHAT_FILE, 'w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False)


CHAT_RETENTION_SECONDS = 7 * 24 * 3600  # 7 дней — сообщения старше удаляются автоматически


def _purge_old_chat(messages: list) -> list:
    # 28.07: то же самое -- сообщения старше 7 дней архивируются, не стираются молча.
    cutoff = time.time() - CHAT_RETENTION_SECONDS
    keep = [m for m in messages if m.get('ts', 0) >= cutoff]
    expired = [m for m in messages if m.get('ts', 0) < cutoff]
    if expired:
        _archive_chat_messages(expired)
    return keep


CHAT_READS_FILE = '/home/promonta/agent/miniapp/chat_reads.json'


def _load_reads() -> dict:
    return _safe_load_json(CHAT_READS_FILE, {})


def _save_reads(reads: dict):
    _atomic_write_json(CHAT_READS_FILE, reads)


CHAT_THREAD_META_FILE = '/home/promonta/agent/miniapp/chat_thread_meta.json'


def _load_chat_thread_meta() -> dict:
    return _safe_load_json(CHAT_THREAD_META_FILE, {})


def _save_chat_thread_meta(meta: dict):
    _atomic_write_json(CHAT_THREAD_META_FILE, meta)


CHAT_REACTIONS_FILE = '/home/promonta/agent/miniapp/chat_reactions.json'
CHAT_REACTION_OPTIONS = ['👍', '✅', '👀', '❗']


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


def _object_chat_participants(object_id: str) -> list:
    roles = _load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    assignments = _load_assignments().get(object_id, [])
    worker_ids = {str(a['user_id']) for a in assignments}
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
            "last_preview": (last.get('text') or ('🎤 Голосовое' if last.get('attachment', {}).get('content_type', '').startswith('audio') else '📎 Файл') if last else ''),
        })
    result.sort(key=lambda t: t['last_ts'], reverse=True)
    return {"threads": result}


def _message_preview(msg: dict | None) -> str:
    if not msg:
        return ''
    if msg.get('text'):
        return msg['text']
    att = msg.get('attachment') or {}
    if (att.get('content_type') or '').startswith('audio'):
        return '🎤 Голосовое'
    if att:
        return '📎 Файл'
    return ''


THREAD_TYPE_BY_PREFIX = {'obj:': 'OBJECT', 'mangel:': 'DEFECT', 'task:': 'TASK'}


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
def get_unread_count(user: dict = Depends(get_current_user)):
    with _chat_lock:
        messages = _load_chat()
        reads = _load_reads()
    me = str(user['id'])
    count = 0
    for m in messages:
        if str(m.get('user_id')) == me:
            continue
        to_uid = m.get('to_user_id')
        if to_uid and str(to_uid) != me:
            continue  # чужой DM
        thread_key = 'group' if not to_uid else str(m['user_id'])
        if m.get('ts', 0) > _thread_last_read(reads, me, thread_key):
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
    Аналогичный fix НЕ внесён в /api/chat/unread_count (общий nav-badge): тот вообще
    не различает thread_key-треды (obj:/mangel:/task:) от group -- отдельный, более
    старый и более рискованный для правки баг, задокументирован отдельно, не в этом проходе."""
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


CHAT_ATTACH_DIR = '/home/promonta/agent/miniapp/chat_attachments'
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
        thread_id = _chat_thread_id(user['id'], to_user_id or None)
        thread_meta = _load_chat_thread_meta()
        if thread_meta.get(thread_id, {}).get('closed') and role != 'owner':
            raise HTTPException(403, "Чат закрыт руководством")

    ext = os.path.splitext(file.filename or '')[1] or '.bin'
    fname = f'{uuid.uuid4().hex}{ext}'
    data = file.file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Файл слишком большой (макс. 8 МБ)")
    with open(os.path.join(CHAT_ATTACH_DIR, fname), 'wb') as f:
        f.write(data)

    msg = {
        "id": uuid.uuid4().hex,
        "ts": int(time.time()),
        "user_id": user['id'],
        "name": user.get('first_name', str(user['id'])),
        "text": '',
        "to_user_id": to_user_id or None,
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


TRANSCRIBE_MAX_BYTES = 8 * 1024 * 1024
TRANSCRIBE_AUDIO_DIR = '/home/promonta/agent/miniapp/transcribe_audio'
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

    uid = str(user['id'])
    user_dir = os.path.join(TRANSCRIBE_AUDIO_DIR, uid)
    os.makedirs(user_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or '')[1] or '.ogg'
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
        thread_id = _chat_thread_id(user['id'], to_user_id or None)
        thread_meta = _load_chat_thread_meta()
        if thread_meta.get(thread_id, {}).get('closed') and role != 'owner':
            raise HTTPException(403, "Чат закрыт руководством")

    ext = os.path.splitext(file.filename or '')[1] or '.ogg'
    fname = f'{uuid.uuid4().hex}{ext}'
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Голосовое слишком большое (макс. 8 МБ)")
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
    path = os.path.join(CHAT_ATTACH_DIR, fname)
    if not os.path.exists(path):
        raise HTTPException(404, "Файл не найден")
    if role != 'owner':
        # 10.29 (Fable-аудит, IDOR): fname — uuid, но раньше отдавался любому
        # авторизованному без проверки, что он участник треда с этим вложением.
        messages = _load_chat()
        msg = next((m for m in messages if m.get('attachment', {}).get('file') == fname), None)
        if not msg:
            raise HTTPException(404, "Файл не найден")
        thread_id = _chat_thread_id(msg['user_id'], msg.get('to_user_id'))
        if str(user['id']) not in _chat_thread_participants(thread_id):
            raise HTTPException(403, "Нет доступа к этому файлу")
    return FileResponse(path)


class ChatMessageBody(BaseModel):
    text: str
    to_user_id: str | None = None
    thread_key: str | None = None


@app.post("/api/chat/messages")
def post_chat_message(body: ChatMessageBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Пустое сообщение")
    if len(text) > 1000:
        raise HTTPException(400, "Сообщение слишком длинное (макс. 1000 символов)")

    if body.thread_key:
        _check_thread_access(body.thread_key, str(user['id']), role)
    else:
        _reject_self_chat(user['id'], body.to_user_id)
        thread_id = _chat_thread_id(user['id'], body.to_user_id)
        thread_meta = _load_chat_thread_meta()
        if thread_meta.get(thread_id, {}).get('closed') and role != 'owner':
            raise HTTPException(403, "Чат закрыт руководством")

    msg = {
        "id": uuid.uuid4().hex,
        "ts": int(time.time()),
        "user_id": user['id'],
        "name": user.get('first_name', str(user['id'])),
        "text": text,
        "to_user_id": body.to_user_id,
        "thread_key": body.thread_key,
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
            to_delete = [m for m in messages if not m.get('thread_key') and (
                (str(m.get('user_id')) == with_) or (str(m.get('to_user_id')) == with_)
            )]
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


DEFAULT_THREAD_PREFS = {'muted': False, 'pinned': False, 'archived': False}


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
AI_RATE_FILE = '/home/promonta/agent/miniapp/ai_chat_rate.json'
AI_RATE_LIMIT = 20
AI_RATE_WINDOW = 3600

AI_MODEL_FILE = '/home/promonta/agent/miniapp/ai_model.json'
AI_MODELS = ('glm', 'sonnet', 'opus')
AI_MODEL_DEFAULT = 'glm'
CLAUDE_BIN = os.environ.get('CLAUDE_BIN', 'claude')

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
    prompt = _messages_to_prompt(messages)
    if not _claude_cli_lock.acquire(timeout=1):
        raise HTTPException(429, "Уже выполняется другой запрос к Claude — подожди и повтори")
    try:
        r = subprocess.run(
            [CLAUDE_BIN, '-p', '--dangerously-skip-permissions', '--model', model, prompt],
            cwd='/home/promonta/agent', capture_output=True, stdin=subprocess.DEVNULL,
            text=True, timeout=120, env={**os.environ},
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
WORKER_AI_RATE_FILE = '/home/promonta/agent/miniapp/worker_ai_chat_rate.json'
WORKER_AI_RATE_LIMIT = 15

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


AI_UPLOAD_MAX_BYTES = 8 * 1024 * 1024  # 8 МБ


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
    import objekte_lib as o
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
def create_stage(object_id: str, body: NewStageBody, user: dict = Depends(get_current_user)):
    # 28.07: owner request -- любой воркер может добавлять этап на любом объекте
    # (не только owner, не только назначенным на объект)
    import objekte_lib as o
    if not body.name.strip():
        raise HTTPException(400, "Name erforderlich")
    num = o.add_stage(object_id, body.name.strip(), body.description.strip()[:2000])
    o.sync_current_stage(object_id)
    return {"stage_num": num}


class StageDescriptionBody(BaseModel):
    description: str


@app.patch("/api/objects/{object_id}/stages/{row_num}/description")
def update_stage_description_endpoint(object_id: str, row_num: int, body: StageDescriptionBody, user: dict = Depends(get_current_user)):
    # 28.07: roadmap-этапы -- owner request "чтоб работник знал что ему делать" (список
    # подзадач текстом внутри развёрнутого этапа). Любая роль может редактировать (тот же
    # принцип, что уже применён к созданию/просмотру этапов сегодня -- не owner-only).
    import objekte_lib as o
    try:
        o.update_stage_description(row_num, body.description.strip()[:2000])
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "ok"}


class StageStatusBody(BaseModel):
    status: str


@app.patch("/api/objects/{object_id}/stages/{row_num}")
def update_stage(object_id: str, row_num: int, body: StageStatusBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    import objekte_lib as o
    from datetime import date
    try:
        o.update_stage_status(row_num, body.status, date.today().isoformat())
    except ValueError as e:
        raise HTTPException(400, str(e))
    o.sync_current_stage(object_id)
    return {"status": "ok"}


@app.delete("/api/objects/{object_id}/stages/{row_num}")
def remove_stage(object_id: str, row_num: int, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    import objekte_lib as o
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
    import objekte_lib as o
    try:
        o.swap_stage_order(object_id, row_num, body.row_num_b)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok"}


@app.post("/api/objects/{object_id}/stages/{row_num}/complete")
def worker_complete_stage(object_id: str, row_num: int, user: dict = Depends(get_current_user), _: None = Depends(require_object_access)):
    import objekte_lib as o
    from datetime import date
    try:
        o.worker_complete_stage(object_id, row_num, str(user['id']), date.today().isoformat())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok"}


# ---------- Потребности (10.33) — worker → owner запросы (инструмент/материалы/защита) ----------
TASKS_FILE = '/home/promonta/agent/miniapp/tasks.json'


def _load_tasks() -> list:
    return _safe_load_json(TASKS_FILE, [])


def _save_tasks(items: list):
    _atomic_write_json(TASKS_FILE, items)


TASK_PRIORITIES = ('обычная', 'срочно')

# 27.07 (B7): категория запроса -- material/tool/ppe/access/other, отдельно от
# priority. Ключи латиницей (стабильный API contract), label для UI -- по месту рендера.
TASK_CATEGORIES = ('materials', 'tool', 'ppe', 'access', 'other')


class TaskCreateBody(BaseModel):
    title: str
    description: str = ''
    object_id: str = ''
    priority: str = 'обычная'
    category: str = 'other'


class TaskStatusBody(BaseModel):
    status: str


# 27.07 (B7): расширено с 3 до полного набора из плана (NEW/ACKNOWLEDGED/IN_PROGRESS/
# ORDERED/DELIVERED/DECLINED/CANCELLED) -- старые значения ('открыто','в работе','закрыто')
# сохранены как есть для обратной совместимости с уже существующими записями в tasks.json,
# новые статусы добавлены поверх, не переименовывая старые.
TASK_STATUSES = ('открыто', 'в работе', 'закрыто', 'принято', 'заказано', 'выдано', 'отклонено')


@app.get("/api/tasks")
def list_tasks(object_id: str = '', user: dict = Depends(get_current_user), role: str = Depends(get_role)):
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
    priority = body.priority.strip() or 'обычная'
    if priority not in TASK_PRIORITIES:
        raise HTTPException(400, "Недопустимый приоритет")
    category = body.category.strip() or 'other'
    if category not in TASK_CATEGORIES:
        raise HTTPException(400, "Недопустимая категория")
    roles = _load_roles()
    owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
    profile = _get_worker_profile(user['id'])
    items = _load_tasks()
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
        'closed_at': None,
    }
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
    items = _load_tasks()
    task = next((t for t in items if t['id'] == task_id), None)
    if not task:
        raise HTTPException(404, "Потребность не найдена")
    task['status'] = body.status
    if body.status == 'закрыто':
        task['closed_at'] = int(time.time())
        # 28.07: owner request -- закрытые потребности не засорять основной список,
        # но не терять данные -- архивируем строкой в Google Sheet ("Потребности"
        # вкладка, тот же SHEET_ID что Объекты/Дефекты/Zeiterfassung), затем убираем
        # из рабочего JSON. Экспорт best-effort -- сбой Sheets API не должен блокировать
        # закрытие потребности воркеру/owner (тот же паттерн что _write_zeiterfassung_row).
        try:
            import objekte_lib as o
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
        items = [t for t in items if t['id'] != task_id]
        _save_tasks(items)
        return task
    _save_tasks(items)
    return task


# ---------- Mängelmanagement — Фаза 3 ----------
import mangel_lib as ml

MANGEL_PHOTO_DIR = '/home/promonta/agent/miniapp/feed_photos'  # переиспользуем feed_photos/


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
        import objekte_lib as o
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
        import objekte_lib as o
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


@app.get("/api/mangel/{ticket_id}/comments")
def get_mangel_comments(ticket_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_mangel_access)):
    try:
        ticket = ml.get_ticket(ticket_id)
        return {"comments": ticket.get('comments', [])}
    except KeyError as e:
        raise HTTPException(404, str(e))


# ---------- Фотоотчёт старт/финиш смены — Фаза 4a ----------
CHECKIN_PHOTO_BASE = '/home/promonta/agent/miniapp/checkin_photos'
CHECKIN_META_FILE = '/home/promonta/agent/miniapp/checkin_meta.json'
CHECKIN_MAX_BYTES = 8 * 1024 * 1024
_checkin_lock = __import__('threading').Lock()

# 10.40: idempotency-key для checkin start/finish — при плохой связи на объекте
# worker может не увидеть ответ и повторить запрос; без этого второй запрос либо
# создаёт дубль сессии, либо возвращает пугающую 409/400 ошибку на успешное действие.
# Кэш в памяти (не переживает restart) — приемлемо, ключ живёт секунды/минуты, не дни.
_idempotency_cache = {}  # key -> (timestamp, response_dict)
_IDEMPOTENCY_TTL = 600  # 10 минут


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


def _load_checkin_meta() -> list:
    return _safe_load_json(CHECKIN_META_FILE, [])


def _save_checkin_meta(items: list):
    with open(CHECKIN_META_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False)


async def _save_checkin_photos(files: list, object_id: str, date_str: str) -> list:
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


@app.post("/api/checkin/start")
async def checkin_start(
    object_id: str = Form(''),
    lat: str = Form(''),
    lon: str = Form(''),
    stage_name: str = Form(''),
    files: list[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
    idempotency_key: str = Header(default='', alias='Idempotency-Key'),
):
    cached = _idempotency_get(idempotency_key)
    if cached is not None:
        return cached

    if not object_id.strip():
        raise HTTPException(400, "object_id обязателен")
    if not lat.strip() or not lon.strip():
        raise HTTPException(400, "Включи геолокацию, чтобы начать смену")
    date_str = datetime.now().strftime('%Y-%m-%d')

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
        "date": date_str,
        "user_id": user['id'],
        "start_at": int(time.time()),
        "start_photos": photo_paths,
        "start_lat": lat,
        "start_lon": lon,
        "start_gps_suspect": _gps_suspect(lat, lon),
        "stage_name": stage_name.strip()[:200] or None,
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
        session = next((i for i in items if i['id'] == session_id), None)
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
        session = next((i for i in items if i['id'] == session_id), None)
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
    photo_paths = await _save_checkin_photos(files, object_id, date_str)

    with _checkin_lock:
        items = _load_checkin_meta()
        session = next((i for i in items if i['id'] == session_id), None)
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
        _save_checkin_meta(items)

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


@app.get("/api/checkin/stundenzettel")
def export_stundenzettel(user_id: str = '', year: int = 0, month: int = 0,
                          user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    """10.29 (Fable-аудит, идея): экспорт табеля рабочего времени — в Германии
    учёт рабочего времени обязателен по решению BAG (2022). CSV, открывается
    в Excel/LibreOffice — не тащим Node-PDF-пайплайн ради одного отчёта."""
    target_id = user_id or str(user['id'])
    if target_id != str(user['id']) and role != 'owner':
        raise HTTPException(403, "Можно выгружать только свой табель")
    if not year or not month:
        now = datetime.utcnow()
        year, month = now.year, now.month
    month_prefix = f'{year:04d}-{month:02d}'

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
    filename = f'Stundenzettel_{target_id}_{month_prefix}.csv'
    from fastapi.responses import Response
    return Response(
        content='\ufeff' + csv_content,  # BOM — Excel корректно определяет UTF-8
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
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
    session = next((i for i in items if i['id'] == session_id), None)
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
    session = next((i for i in items if i['id'] == session_id), None)
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
        if i['id'] == session_id:
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
        import mangel_lib as ml
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
CRITICAL_ALERTS_FILE = '/home/promonta/agent/miniapp/critical_alerts.json'
CRITICAL_ALERT_PHOTO_DIR = '/home/promonta/agent/miniapp/critical_alert_photos'
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
        alert_dir = os.path.join(CRITICAL_ALERT_PHOTO_DIR, alert_id)
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
ABWESENHEIT_FILE = '/home/promonta/agent/miniapp/abwesenheit.json'
ABWESENHEIT_REASONS = ('Krankheit', 'Urlaub', 'Sonstiges')


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
    entry['date_to'] = datetime.utcnow().strftime('%Y-%m-%d')
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
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
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


@app.get("/api/abwesenheit/all")
def list_all_abwesenheit(user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    # 28.07: owner request -- воркер тоже может смотреть общий календарь команды
    # (view-only). Approve/reject остаются отдельно защищены require_owner на
    # /api/abwesenheit/{id}/status -- этот endpoint только читает список.
    _auto_close_expired_open_ended_abwesenheit()
    entries = _load_abwesenheit()
    for e in entries:
        e.setdefault('status', 'pending')
    return {"entries": entries}


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
