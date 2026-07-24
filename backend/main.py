#!/usr/bin/env python3
"""Promonta Mini App — FastAPI backend. Фаза 2 плана: скелет + initData-auth + roles.
Запуск: uvicorn main:app --host 127.0.0.1 --port 8001
"""
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
from pydantic import BaseModel

sys.path.insert(0, '/home/promonta/agent')

BOT_TOKEN = os.environ['BOT_TOKEN']
ROLES_FILE = '/home/promonta/agent/miniapp/roles.json'
INIT_DATA_MAX_AGE = 3600  # секунд — Telegram initData считается протухшим через час

app = FastAPI(title="Promonta Mini App")
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
    body_bytes = b""
    if request.method in ("POST", "PATCH", "DELETE"):
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
        if not auth_date or time.time() - int(auth_date) > INIT_DATA_MAX_AGE:
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
    json.load на старте всех эндпоинтов, читающих этот стор (10.29)."""
    with _lock_for(path):
        tmp_path = f'{path}.tmp-{os.getpid()}'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii)
        os.replace(tmp_path, path)


def _load_roles() -> dict:
    if not os.path.exists(ROLES_FILE):
        return {}
    return json.load(open(ROLES_FILE))


def _save_roles(roles: dict):
    _atomic_write_json(ROLES_FILE, roles)


NOTIFIED_USERS_FILE = '/home/promonta/agent/miniapp/notified_users.json'


NOTIFIED_USERS_TTL = 7 * 86400  # 7 дней — потом можно напомнить owner'у снова (10.29)


def _load_notified_users() -> dict:
    if not os.path.exists(NOTIFIED_USERS_FILE):
        return {}
    raw = json.load(open(NOTIFIED_USERS_FILE))
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
    if not os.path.exists(WORKER_PROFILES_FILE):
        return {}
    return json.load(open(WORKER_PROFILES_FILE, encoding='utf-8'))


def _save_worker_profiles(profiles: dict):
    _atomic_write_json(WORKER_PROFILES_FILE, profiles)


def _get_worker_profile(user_id) -> dict:
    profiles = _load_worker_profiles()
    return profiles.get(str(user_id), {"skills": [], "quiz_completed": False})


_INVISIBLE_FILLER_CHARS = (
    'ᅟᅠㅤﾠ'  # Hangul choseong/jungseong filler + halfwidth filler —
                                 # популярный трюк для "невидимого" имени в Telegram
)


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
    content_type = file.content_type or ''
    if not content_type.startswith('image/'):
        raise HTTPException(400, "Файл должен быть изображением")
    raw = await file.read()
    if len(raw) > AVATAR_MAX_BYTES:
        raise HTTPException(400, "Аватар слишком большой (макс. 4 МБ)")
    ext = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}.get(content_type, 'jpg')
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
        extra_work = session.get('extra_work') or ''

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


def _load_assignments() -> dict:
    if not os.path.exists(OBJECT_ASSIGNMENTS_FILE):
        return {}
    return json.load(open(OBJECT_ASSIGNMENTS_FILE, encoding='utf-8'))


def _save_assignments(assignments: dict):
    _atomic_write_json(OBJECT_ASSIGNMENTS_FILE, assignments)


def _load_object_images() -> dict:
    if not os.path.exists(OBJECT_IMAGES_FILE):
        return {}
    return json.load(open(OBJECT_IMAGES_FILE, encoding='utf-8'))


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
        obj['image_path'] = images.get(oid)
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
    assignments = _load_assignments()
    key = str(object_id)
    if key not in assignments:
        assignments[key] = []
    already = any(
        a['user_id'] == str(body.user_id) and a.get('stage_id', '') == body.stage_id
        for a in assignments[key]
    )
    if not already:
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
        _save_assignments(assignments)
    return {"status": "ok"}


@app.delete("/api/objects/{object_id}/assign/{user_id}")
def unassign_user(object_id: str, user_id: str, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    assignments = _load_assignments()
    key = str(object_id)
    if key in assignments:
        assignments[key] = [a for a in assignments[key] if a['user_id'] != str(user_id)]
        _save_assignments(assignments)
    return {"status": "ok"}


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
    return {"alerts": filtered, "count": len(filtered)}


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
def get_tasks(object_id: str, user: dict = Depends(get_current_user)):
    import objekte_lib as o
    return {"tasks": o.list_tasks(object_id)}


class TaskBody(BaseModel):
    text: str


@app.post("/api/objects/{object_id}/tasks")
def create_task(object_id: str, body: TaskBody, user: dict = Depends(get_current_user)):
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
    if not os.path.exists(OBJECT_INFO_FILE):
        return {}
    return json.load(open(OBJECT_INFO_FILE))


def _save_object_info(data: dict):
    _atomic_write_json(OBJECT_INFO_FILE, data)


def _object_info_entry(object_id: str) -> dict:
    data = _load_object_info()
    return data.get(object_id, {"items": [], "documents": []})


@app.get("/api/objects/{object_id}/info-items")
def get_object_info_items(object_id: str, user: dict = Depends(get_current_user)):
    return {"items": _object_info_entry(object_id).get("items", [])}


class InfoItemBody(BaseModel):
    text: str
    qty: str = ''


@app.post("/api/objects/{object_id}/info-items")
def create_object_info_item(object_id: str, body: InfoItemBody, user: dict = Depends(get_current_user)):
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
def get_object_documents(object_id: str, user: dict = Depends(get_current_user)):
    return {"documents": _object_info_entry(object_id).get("documents", [])}


@app.post("/api/objects/{object_id}/documents")
async def upload_object_document(object_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content_type = file.content_type or ''
    allowed = content_type.startswith('image/') or content_type == 'application/pdf'
    if not allowed:
        raise HTTPException(400, "Разрешены только изображения и PDF")
    data_bytes = await file.read()
    if len(data_bytes) > 8 * 1024 * 1024:
        raise HTTPException(400, "Файл слишком большой (макс. 8 МБ)")
    ext = os.path.splitext(file.filename or '')[1] or '.bin'
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
def get_object_document_file(object_id: str, fname: str, user: dict = Depends(get_current_user)):
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
    if not os.path.exists(WEATHER_REACTIONS_FILE):
        return {}
    with open(WEATHER_REACTIONS_FILE, encoding='utf-8') as f:
        return json.load(f)


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
    if not os.path.exists(NEWS_REACTIONS_FILE):
        return {}
    with open(NEWS_REACTIONS_FILE, encoding='utf-8') as f:
        return json.load(f)


def _save_news_reactions(data: dict):
    _atomic_write_json(NEWS_REACTIONS_FILE, data)


def _load_news_reads() -> dict:
    if not os.path.exists(NEWS_READS_FILE):
        return {}
    with open(NEWS_READS_FILE, encoding='utf-8') as f:
        return json.load(f)


def _save_news_reads(data: dict):
    _atomic_write_json(NEWS_READS_FILE, data)


BIRTHDAY_ALERTS_FILE = '/home/promonta/agent/miniapp/birthday_alerts.json' 

def _load_birthday_alerts() -> list:
    if not os.path.exists(BIRTHDAY_ALERTS_FILE):
        return []
    with open(BIRTHDAY_ALERTS_FILE, encoding='utf-8') as f:
        return json.load(f)


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
    if not os.path.exists(PHOTO_META_FILE):
        return []
    with open(PHOTO_META_FILE, encoding='utf-8') as f:
        return json.load(f)


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
        content_type = f.content_type or ''
        if not content_type.startswith('image/'):
            raise HTTPException(400, "Все файлы должны быть изображениями")
        raw = await f.read()
        if len(raw) > PHOTO_MAX_BYTES:
            raise HTTPException(400, "Фото слишком большое (макс. 8 МБ на файл)")
        ext = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif'}.get(content_type, 'jpg')
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
CHAT_MAX = 200
_chat_lock = __import__('threading').Lock()


def _load_chat() -> list:
    if not os.path.exists(CHAT_FILE):
        return []
    with open(CHAT_FILE, encoding='utf-8') as f:
        return json.load(f)


def _save_chat(messages: list):
    with open(CHAT_FILE, 'w', encoding='utf-8') as f:
        json.dump(messages[-CHAT_MAX:], f, ensure_ascii=False)


CHAT_RETENTION_SECONDS = 7 * 24 * 3600  # 7 дней — сообщения старше удаляются автоматически


def _purge_old_chat(messages: list) -> list:
    cutoff = time.time() - CHAT_RETENTION_SECONDS
    return [m for m in messages if m.get('ts', 0) >= cutoff]


CHAT_READS_FILE = '/home/promonta/agent/miniapp/chat_reads.json'


def _load_reads() -> dict:
    if not os.path.exists(CHAT_READS_FILE):
        return {}
    with open(CHAT_READS_FILE, encoding='utf-8') as f:
        return json.load(f)


def _save_reads(reads: dict):
    _atomic_write_json(CHAT_READS_FILE, reads)


CHAT_THREAD_META_FILE = '/home/promonta/agent/miniapp/chat_thread_meta.json'


def _load_chat_thread_meta() -> dict:
    if not os.path.exists(CHAT_THREAD_META_FILE):
        return {}
    with open(CHAT_THREAD_META_FILE, encoding='utf-8') as f:
        return json.load(f)


def _save_chat_thread_meta(meta: dict):
    _atomic_write_json(CHAT_THREAD_META_FILE, meta)


def _chat_thread_id(user_id: str, to_user_id: str | None) -> str:
    if not to_user_id:
        return 'group'
    return '-'.join(sorted([str(user_id), str(to_user_id)]))


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
def get_unread_by_thread(user: dict = Depends(get_current_user)):
    """10.14/10.29: разбивка непрочитанных по тредам для badge на каждой строке списка,
    per-thread last_read — открытие одного треда не сбрасывает счётчик у остальных."""
    with _chat_lock:
        messages = _load_chat()
        reads = _load_reads()
    me = str(user['id'])
    by_thread = {}
    for m in messages:
        if str(m.get('user_id')) == me:
            continue
        to_uid = m.get('to_user_id')
        if to_uid and str(to_uid) != me:
            continue  # чужой DM
        thread_key = 'group' if not to_uid else str(m['user_id'])
        if m.get('ts', 0) <= _thread_last_read(reads, me, thread_key):
            continue
        by_thread[thread_key] = by_thread.get(thread_key, 0) + 1
    return {"unread_by_thread": by_thread}


@app.post("/api/chat/read")
def mark_chat_read(with_: str = '', user: dict = Depends(get_current_user)):
    thread_key = 'group' if not with_ else with_
    with _chat_lock:
        reads = _load_reads()
        my_id = str(user['id'])
        if not isinstance(reads.get(my_id), dict):
            reads[my_id] = {}
        reads[my_id][thread_key] = int(time.time())
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


@app.post("/api/chat/messages/voice")
async def post_chat_voice(thread_key: str = Form(''), to_user_id: str = Form(''), file: UploadFile = File(...),
                           user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    if thread_key:
        _check_thread_access(thread_key, str(user['id']), role)
    else:
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
    return {"status": "ok"}


class ChatThreadCloseBody(BaseModel):
    to_user_id: str | None = None


def _chat_thread_participants(thread_id: str) -> list:
    if thread_id == 'group':
        roles = _load_roles()
        return list(roles.keys())
    return thread_id.split('-')


@app.post("/api/chat/threads/close")
def close_chat_thread(body: ChatThreadCloseBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    thread_id = _chat_thread_id(user['id'], body.to_user_id)
    meta = _load_chat_thread_meta()
    meta[thread_id] = {'closed': True, 'closed_at': int(time.time()), 'closed_by': str(user['id'])}
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


def _check_ai_rate(user_id: int):
    data = {}
    if os.path.exists(AI_RATE_FILE):
        with open(AI_RATE_FILE, encoding='utf-8') as f:
            data = json.load(f)

    uid = str(user_id)
    now = time.time()
    ud = data.get(uid, {"count": 0, "window_start": now})

    if now - ud["window_start"] >= AI_RATE_WINDOW:
        ud = {"count": 0, "window_start": now}

    if ud["count"] >= AI_RATE_LIMIT:
        remaining = int(AI_RATE_WINDOW - (now - ud["window_start"]))
        raise HTTPException(429, f"Лимит {AI_RATE_LIMIT} запросов/час исчерпан. Сброс через {remaining // 60} мин {remaining % 60} сек")

    ud["count"] += 1
    data[uid] = ud
    with open(AI_RATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def _call_glm(messages: list) -> str:
    glm_key = os.environ.get('GLM_KEY', '')
    if not glm_key:
        raise HTTPException(503, "GLM API не настроен (нет GLM_KEY)")

    payload = {
        "model": "glm-4.5-flash",
        "max_tokens": 1024,
        "system": AI_SYSTEM_PROMPT,
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


def _call_claude_cli(messages: list, model: str) -> str:
    prompt = _messages_to_prompt(messages)
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

    content_type = file.content_type or ''
    filename = file.filename or 'file'

    if content_type.startswith('image/'):
        b64 = base64.b64encode(raw).decode('ascii')
        media_type = content_type if content_type in ('image/jpeg', 'image/png', 'image/gif', 'image/webp') else 'image/jpeg'
        return {
            "kind": "image",
            "filename": filename,
            "block": {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
        }

    if content_type == 'application/pdf' or filename.lower().endswith('.pdf'):
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
    return {"stages": _cached_all_stages(object_id)}


class NewStageBody(BaseModel):
    name: str


@app.post("/api/objects/{object_id}/stages")
def create_stage(object_id: str, body: NewStageBody, user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
    import objekte_lib as o
    if not body.name.strip():
        raise HTTPException(400, "Name erforderlich")
    num = o.add_stage(object_id, body.name.strip())
    o.sync_current_stage(object_id)
    return {"stage_num": num}


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


# ---------- Потребности (10.33) — worker → owner запросы (инструмент/материалы/защита) ----------
TASKS_FILE = '/home/promonta/agent/miniapp/tasks.json'


def _load_tasks() -> list:
    if not os.path.exists(TASKS_FILE):
        return []
    with open(TASKS_FILE, encoding='utf-8') as f:
        return json.load(f)


def _save_tasks(items: list):
    _atomic_write_json(TASKS_FILE, items)


class TaskCreateBody(BaseModel):
    title: str
    description: str = ''
    object_id: str = ''


class TaskStatusBody(BaseModel):
    status: str


TASK_STATUSES = ('открыто', 'в работе', 'закрыто')


@app.get("/api/tasks")
def list_tasks(object_id: str = '', user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    items = _load_tasks()
    if role != 'owner':
        items = [t for t in items if str(t.get('from_user_id')) == str(user['id'])]
    if object_id:
        items = [t for t in items if t.get('object_id') == object_id]
    return {"tasks": sorted(items, key=lambda t: t.get('created_at', 0), reverse=True)}


@app.post("/api/tasks")
def create_task(body: TaskCreateBody, user: dict = Depends(get_current_user), role: str = Depends(get_role)):
    if role == 'owner':
        raise HTTPException(403, "Потребности создают работники")
    if not body.title.strip():
        raise HTTPException(400, "Название обязательно")
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
        'status': 'открыто',
        'created_at': int(time.time()),
        'closed_at': None,
    }
    items.append(task)
    _save_tasks(items)
    if owner_id:
        try:
            send_telegram_message(int(owner_id), f"📋 Новая потребность от {task['from_name']}: {task['title']}")
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
    _save_tasks(items)
    return task


# ---------- Mängelmanagement — Фаза 3 ----------
import mangel_lib as ml

MANGEL_PHOTO_DIR = '/home/promonta/agent/miniapp/feed_photos'  # переиспользуем feed_photos/


class MangelStatusBody(BaseModel):
    status: str


class MangelCommentBody(BaseModel):
    text: str


@app.get("/api/mangel")
def get_mangel_list(object_id: str = '', user: dict = Depends(get_current_user)):
    tickets = ml.list_tickets(object_id or None)
    return {"tickets": tickets, "total": len(tickets)}


@app.get("/api/mangel/counts")
def get_mangel_counts(user: dict = Depends(get_current_user)):
    return ml.count_by_status()


@app.get("/api/mangel/{ticket_id}")
def get_mangel_ticket(ticket_id: str, user: dict = Depends(get_current_user)):
    try:
        return ml.get_ticket(ticket_id)
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
    if not description.strip():
        raise HTTPException(400, "Описание обязательно")

    photo_paths: list = []
    if file and file.filename:
        content_type = file.content_type or ''
        if not content_type.startswith('image/'):
            raise HTTPException(400, "Файл должен быть изображением")
        raw = await file.read()
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(400, "Фото слишком большое (макс. 8 МБ)")
        ext = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}.get(content_type, 'jpg')
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
    except Exception:
        pass
    return ticket


@app.get("/api/mangel/photos/{fname}/file")
def get_mangel_photo_file(fname: str, user: dict = Depends(get_current_user)):
    # Mängel-фото хранятся в той же feed_photos/, но без записи в feed_photos.json —
    # отдаём по basename имени файла (не по id, как feed), с защитой от path traversal.
    safe_name = os.path.basename(fname)
    if safe_name != fname or not safe_name.startswith('mangel_'):
        raise HTTPException(404, "Файл отсутствует")
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
    except Exception:
        pass
    return result


@app.post("/api/mangel/{ticket_id}/comments")
def add_mangel_comment(ticket_id: str, body: MangelCommentBody, user: dict = Depends(get_current_user)):
    if not body.text.strip():
        raise HTTPException(400, "Текст комментария обязателен")
    try:
        return ml.add_comment(ticket_id, str(user['id']), body.text.strip()[:500],
                               name=user.get('first_name', str(user['id'])))
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/mangel/{ticket_id}/comments")
def get_mangel_comments(ticket_id: str, user: dict = Depends(get_current_user)):
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
    if not os.path.exists(CHECKIN_META_FILE):
        return []
    with open(CHECKIN_META_FILE, encoding='utf-8') as f:
        return json.load(f)


def _save_checkin_meta(items: list):
    with open(CHECKIN_META_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False)


async def _save_checkin_photos(files: list, object_id: str, date_str: str) -> list:
    day_dir = os.path.join(CHECKIN_PHOTO_BASE, object_id, date_str)
    os.makedirs(day_dir, exist_ok=True)
    saved = []
    for file in files:
        content_type = file.content_type or ''
        if not content_type.startswith('image/'):
            continue
        raw = await file.read()
        if len(raw) > CHECKIN_MAX_BYTES:
            continue
        ext = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}.get(content_type, 'jpg')
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
    files: list[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
    idempotency_key: str = Header(default='', alias='Idempotency-Key'),
):
    cached = _idempotency_get(idempotency_key)
    if cached is not None:
        return cached

    if not object_id.strip():
        raise HTTPException(400, "object_id обязателен")
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
        "finish_at": None,
        "finish_photos": [],
        "finish_lat": None,
        "finish_lon": None,
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
    next_day_needs: str = Form(''),
    pause_minutes: int = Form(0),
    files: list[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
    role: str = Depends(get_role),
    idempotency_key: str = Header(default='', alias='Idempotency-Key'),
):
    cached = _idempotency_get(idempotency_key)
    if cached is not None:
        return cached

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
        # 10.31: опрос конца дня — всё опционально, worker не обязан заполнять,
        # если для следующего дня ничего готовить не нужно.
        session['done_summary'] = done_summary.strip()[:1000] or None
        session['extra_work'] = extra_work.strip()[:1000] or None
        session['next_day_needs'] = next_day_needs.strip()[:1000] or None
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

    if extra_work.strip() or next_day_needs.strip():
        # Owner получает пуш только если worker реально что-то указал — не спамим
        # при пустом опроснике. 24.07: extra_work (доп-работы вне плана) теперь тоже
        # шлётся — раньше уходила только в Zeiterfassung sheet, owner мог её пропустить
        # без захода в таблицу. Нужно для billing: если заказчик попросил доп-работу на
        # месте, а её не заметили — компании не доплатят, хотя воркеру платят за время.
        roles = _load_roles()
        owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
        if owner_id:
            if extra_work.strip():
                try:
                    send_telegram_message(int(owner_id),
                        f"⚠️ Доп-работы вне плана ({object_id}): {extra_work.strip()[:300]}")
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

    rows = ['Дата;Объект;Начало;Конец;Пауза (мин);Часы;Тип']
    for s in sorted(sessions, key=lambda x: x.get('date', '')):
        kind = 'Ручной ввод' if s.get('manual_entry') else 'Фото-чекин'
        if s.get('manual_entry'):
            start, finish = s.get('start_time', ''), s.get('end_time', '')
        else:
            start = datetime.fromtimestamp(s['start_at']).strftime('%H:%M') if s.get('start_at') else ''
            finish = datetime.fromtimestamp(s['finish_at']).strftime('%H:%M') if s.get('finish_at') else 'не завершено'
        hours = round(_hours_from_session(s), 2)
        pause = int(s.get('pause_minutes') or 0)
        rows.append(f"{s.get('date','')};{s.get('object_id','')};{start};{finish};{pause};{hours};{kind}")

    total_hours = round(sum(_hours_from_session(s) for s in sessions), 2)
    rows.append(f';;;;;{total_hours};ИТОГО')

    csv_content = '\n'.join(rows)
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
    if not os.path.exists(CRITICAL_ALERTS_FILE):
        return []
    with open(CRITICAL_ALERTS_FILE, encoding='utf-8') as f:
        return json.load(f)


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
            content_type = f.content_type or ''
            if not content_type.startswith('image/'):
                raise HTTPException(400, "Файл должен быть изображением")
            data = f.file.read()
            if len(data) > 8 * 1024 * 1024:
                raise HTTPException(400, "Файл слишком большой (макс. 8 МБ)")
            ext = os.path.splitext(f.filename or '')[1] or '.jpg'
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
    path = os.path.join(CRITICAL_ALERT_PHOTO_DIR, alert_id, filename)
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
    if not os.path.exists(ABWESENHEIT_FILE):
        return []
    with open(ABWESENHEIT_FILE, encoding='utf-8') as f:
        return json.load(f)


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
def list_all_abwesenheit(user: dict = Depends(get_current_user), _: None = Depends(require_owner)):
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
