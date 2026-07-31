#!/usr/bin/env python3
"""Общие функции для учёта объектов/расходов/этапов в Google Sheet."""
import json, os, re, secrets, tempfile, time, urllib.request, urllib.parse
from decimal import Decimal, InvalidOperation
from datetime import datetime, date

SHEETS_CRED = '/home/promonta/agent/.sheets.json'
SHEET_ID = '14CXpSaW9ErmViK09zAh09X52EUmEJjnkxGUSmW3Z9sA'
STATE_FILE = '/home/promonta/agent/.objekte_alert_state.json'
TG_API = 'https://api.telegram.org/bot'

VALID_DB_CATEGORIES = {'Material', 'Subunternehmer', 'Arbeitskosten', 'Transport', 'Sonstiges'}
# 29.07 v2 (новый спек -- feature freeze): откат 7 статусов обратно на 3. Полный
# review/rework workflow и STAGE_TRANSITIONS были реализованы в этой же сессии по
# предыдущей версии ТЗ, затем эта версия явно потребовала упростить обратно --
# "не реализовывать: готов к началу/на проверке/на доработке/семь статусов/Owner
# approval". compatibility mapping ниже страхует на случай, если где-то в данных уже
# успел записаться один из 4 промежуточных статусов (miniapp тестировался против mock
# API, реальный Google Sheet этой правкой не трогался -- но на всякий случай).
VALID_STAGE_STATUS = {'предстоит', 'в процессе', 'готово'}

# Статусы, которые могли записаться при более ранней версии этой же сессии (или любые
# внешние/экспериментальные значения) -- читаются как один из 3 канонических.
_STAGE_STATUS_COMPAT = {
    'не начат': 'предстоит', 'not_started': 'предстоит', 'ready': 'предстоит',
    'ready_to_start': 'предстоит', 'готово к началу': 'предстоит',
    'in_progress': 'в процессе', 'blocked': 'в процессе', 'заблокирован': 'в процессе',
    'pending_review': 'в процессе', 'review': 'в процессе', 'на проверке': 'в процессе',
    'rework': 'в процессе', 'на доработке': 'в процессе',
    'completed': 'готово', 'done': 'готово',
}


def normalize_stage_status(raw: str) -> str:
    """Читает статус этапа как один из 3 канонических значений -- старые/промежуточные
    записи не пропадают и не ломают отображение, просто схлопываются в ближайший смысл."""
    if raw in VALID_STAGE_STATUS:
        return raw
    return _STAGE_STATUS_COMPAT.get(raw, 'предстоит')

_token_cache = {'token': None, 'expires_at': 0}


class InvalidAmountError(ValueError):
    pass


# ---------- OAuth / low-level Sheets I/O ----------

def _token():
    """Кэширует access token — раньше рефрешился на КАЖДЫЙ вызов, что стало
    узким местом при многопользовательском доступе из Mini App."""
    if _token_cache['token'] and time.time() < _token_cache['expires_at'] - 60:
        return _token_cache['token']
    c = json.load(open(SHEETS_CRED))
    b = urllib.parse.urlencode({'client_id': c['client_id'], 'client_secret': c['client_secret'],
                                'refresh_token': c['refresh_token'], 'grant_type': 'refresh_token'}).encode()
    r = json.load(urllib.request.urlopen('https://oauth2.googleapis.com/token', b, timeout=20))
    _token_cache['token'] = r['access_token']
    _token_cache['expires_at'] = time.time() + r.get('expires_in', 3600)
    return r['access_token']


def get_used_range(tab_name):
    """Читает реально занятый диапазон вкладки через grid metadata,
    без хардкод-потолка строк. Фоллбэк на A1:Z2000 при сбое metadata-запроса."""
    t = _token()
    try:
        req = urllib.request.Request(
            f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?fields=sheets(properties(title,gridProperties))',
            headers={'Authorization': f'Bearer {t}'})
        meta = json.load(urllib.request.urlopen(req, timeout=20))
        grid = None
        for s in meta['sheets']:
            if s['properties']['title'] == tab_name:
                grid = s['properties']['gridProperties']
                break
        if grid is None:
            raise KeyError(f'вкладка {tab_name!r} не найдена')
        last_row = grid.get('rowCount', 2000)
        last_col = grid.get('columnCount', 26)
    except Exception as e:
        print(f'WARNING: get_used_range metadata fail для {tab_name}: {e}, фоллбэк A1:Z2000')
        last_row, last_col = 2000, 26

    end_col = chr(ord('A') + min(last_col, 26) - 1)
    rng = f'{tab_name}!A1:{end_col}{last_row}'
    rng_enc = urllib.parse.quote(rng, safe='')
    req = urllib.request.Request(f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{rng_enc}',
                                 headers={'Authorization': f'Bearer {t}'})
    return json.load(urllib.request.urlopen(req, timeout=20)).get('values', [])


def get_values(rng):
    t = _token()
    rng_enc = urllib.parse.quote(rng, safe='')
    req = urllib.request.Request(f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{rng_enc}',
                                 headers={'Authorization': f'Bearer {t}'})
    return json.load(urllib.request.urlopen(req, timeout=20)).get('values', [])


def append_row(sheet_name, row):
    t = _token()
    rng_enc = urllib.parse.quote(f'{sheet_name}!A:Z', safe='')
    req = urllib.request.Request(
        f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{rng_enc}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS',
        data=json.dumps({'values': [row]}).encode(), method='POST',
        headers={'Authorization': f'Bearer {t}', 'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=20)


def update_range(rng, values):
    t = _token()
    rng_enc = urllib.parse.quote(rng, safe='')
    req = urllib.request.Request(
        f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{rng_enc}?valueInputOption=USER_ENTERED',
        data=json.dumps({'values': values}).encode(), method='PUT',
        headers={'Authorization': f'Bearer {t}', 'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=20)


def send_telegram(text):
    token = os.environ.get('BOT_TOKEN')
    allowed = os.environ.get('ALLOWED_CHAT', '')
    if not token or not allowed:
        return
    for chat in [x.strip() for x in allowed.split(',') if x.strip()]:
        try:
            urllib.request.urlopen(f'{TG_API}{token}/sendMessage',
                urllib.parse.urlencode({'chat_id': chat, 'text': text}).encode(), timeout=15)
        except Exception:
            pass


# ---------- atomic local state ----------

def atomic_write_json(path, data):
    dir_ = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix='.tmp_', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def load_alert_state():
    try:
        return json.load(open(STATE_FILE, encoding='utf-8'))
    except Exception:
        return {}


def save_alert_state(state):
    atomic_write_json(STATE_FILE, state)


# ---------- safe amount parsing ----------

def parse_amount(raw):
    """EU-форматы (1.234,56 / 1234,56 / 1234.56 / 1234), с/без €/EUR.
    Кидает InvalidAmountError с понятным сообщением, никогда не роняет вызывающего молча."""
    if raw is None:
        raise InvalidAmountError('пусто')
    s = str(raw).strip().replace('€', '').replace('EUR', '').strip()
    if not s:
        raise InvalidAmountError('пусто')

    has_dot, has_comma = '.' in s, ',' in s
    if has_dot and has_comma:
        if s.rindex(',') > s.rindex('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif has_comma:
        s = s.replace(',', '.')

    s = re.sub(r'[^\d.\-]', '', s)
    try:
        value = Decimal(s)
    except InvalidOperation:
        raise InvalidAmountError(f'не число: {raw}')
    return value.quantize(Decimal('0.01'))


def _demo():
    cases = {
        '1.234,56': Decimal('1234.56'),
        '1234,56': Decimal('1234.56'),
        '1234.56': Decimal('1234.56'),
        '1234': Decimal('1234.00'),
        '1.234,56€': Decimal('1234.56'),
        '1,234.56': Decimal('1234.56'),
    }
    for raw, expected in cases.items():
        got = parse_amount(raw)
        assert got == expected, f'{raw} -> {got}, ожидалось {expected}'
    try:
        parse_amount('abc')
        assert False, 'должно было упасть'
    except InvalidAmountError:
        pass
    print('parse_amount: все кейсы OK')


# ---------- object_id-based lookups ----------

def _row_to_dict(headers, row):
    row = list(row) + [''] * (len(headers) - len(row))
    return dict(zip(headers, row))


def find_object_row(object_id):
    """1-based номер строки в Объекты (с учётом заголовка) или None."""
    values = get_used_range('Объекты')
    if not values:
        return None
    target = object_id.strip().upper()
    for i, row in enumerate(values[1:], start=2):
        if row and row[0].strip().upper() == target:
            return i
    return None


def get_object(object_id):
    values = get_used_range('Объекты')
    if not values:
        return None
    headers = values[0]
    target = object_id.strip().upper()
    for row in values[1:]:
        if row and row[0].strip().upper() == target:
            return _row_to_dict(headers, row)
    return None


def resolve_object_id(ref):
    """Точное совпадение по ID, иначе однозначный поиск по имени (подстрока).
    None если не найдено или неоднозначно — тогда просим уточнить, не гадаем."""
    if not ref:
        return None
    ref = ref.strip()
    values = get_used_range('Объекты')
    if not values:
        return None
    headers = values[0]
    ref_upper = ref.upper()
    for row in values[1:]:
        if row and row[0].strip().upper() == ref_upper:
            return row[0].strip().upper()
    ref_lower = ref.lower()
    matches = [row[0].strip() for row in values[1:] if len(row) > 1 and ref_lower in row[1].lower()]
    matches = list(dict.fromkeys(matches))
    return matches[0] if len(matches) == 1 else None


def update_object_field(object_id, field_name, value):
    values = get_used_range('Объекты')
    headers = values[0]
    row_num = find_object_row(object_id)
    if row_num is None:
        raise ValueError(f'объект {object_id} не найден')
    col_idx = headers.index(field_name)
    col_letter = chr(ord('A') + col_idx)
    update_range(f'Объекты!{col_letter}{row_num}:{col_letter}{row_num}', [[value]])


# ---------- expense id / idempotency ----------

def next_expense_id():
    now = datetime.now()
    return f'EXP-{now:%Y%m%d}-{now:%H%M%S}-{secrets.token_hex(2)}'


def is_duplicate_event(source_event_id):
    if not source_event_id:
        return False
    values = get_used_range('Расходы')
    if not values:
        return False
    headers = values[0]
    if 'ID события (идемпотентность)' not in headers:
        return False
    j_idx = headers.index('ID события (идемпотентность)')
    for row in values[1:]:
        if len(row) > j_idx and row[j_idx] == source_event_id:
            return True
    return False


def append_expense(object_id, object_name, raw_category, db_category, amount, note, source,
                   expense_id, source_event_id=''):
    if db_category not in VALID_DB_CATEGORIES:
        db_category = 'Sonstiges'
    from datetime import date
    row = [date.today().isoformat(), object_id, object_name, raw_category, db_category,
           str(amount), note or '', source, expense_id, source_event_id or '']
    append_row_safe('Расходы', row)


# ---------- budget recompute ----------

def recompute_objekt(object_id):
    """Пересчитать Потрачено/% бюджета для объекта, ключ — object_id (не имя)."""
    row_num = find_object_row(object_id)
    if row_num is None:
        return

    obj_values = get_used_range('Объекты')
    headers = obj_values[0]
    obj_row = obj_values[row_num - 1]
    obj = _row_to_dict(headers, obj_row)

    expenses = get_used_range('Расходы')
    exp_headers = expenses[0] if expenses else []
    b_idx = exp_headers.index('ID объекта') if 'ID объекта' in exp_headers else 1
    f_idx = exp_headers.index('Сумма (EUR)') if 'Сумма (EUR)' in exp_headers else 5

    target = object_id.strip().upper()
    total = Decimal('0')
    for row in (expenses[1:] if expenses else []):
        if len(row) > b_idx and row[b_idx].strip().upper() == target:
            try:
                total += parse_amount(row[f_idx]) if len(row) > f_idx else Decimal('0')
            except InvalidAmountError:
                continue  # кривая строка не должна ронять пересчёт остальных

    budget_raw = obj.get('Бюджет (EUR)', '')
    try:
        budget = parse_amount(budget_raw) if budget_raw else None
    except InvalidAmountError:
        budget = None

    pct = float(total / budget * 100) if budget else None

    f_col = chr(ord('A') + headers.index('Потрачено (EUR)'))
    g_col = chr(ord('A') + headers.index('% бюджета'))
    update_range(f'Объекты!{f_col}{row_num}:{g_col}{row_num}',
                 [[float(total), round(pct, 1) if pct is not None else '']])


def check_budget_threshold(object_id, thresholds=(90, 60)):
    """Проверяет пороги, шлёт Telegram при первом пересечении, пишет K.
    thresholds по убыванию — сработает только высший достигнутый в этом прогоне."""
    obj = get_object(object_id)
    if not obj:
        return
    try:
        pct = float(obj.get('% бюджета') or 0)
    except ValueError:
        pct = 0

    state = load_alert_state()
    last_alerted = int(state.get(object_id, 0) or 0)

    for threshold in thresholds:
        if pct >= threshold and last_alerted < threshold:
            send_telegram(
                f'⚠️ Объект {object_id} ({obj.get("Объект","")}): '
                f'{pct:.0f}% бюджета израсходовано '
                f'({obj.get("Потрачено (EUR)","")}€ из {obj.get("Бюджет (EUR)","")}€).')
            state[object_id] = threshold
            update_object_field(object_id, 'Последнее уведомление %', threshold)
            save_alert_state(state)
            return


# ---------- stages ----------

def find_stage_row(object_id, stage_ref):
    """Возвращает (row_num, row_dict) по названию этапа (подстрока, регистронезависимо) или по номеру."""
    values = get_used_range('Этапы')
    if not values:
        return None
    headers = values[0]
    target_obj = object_id.strip().upper()
    stage_ref_l = str(stage_ref).strip().lower()
    for i, row in enumerate(values[1:], start=2):
        d = _row_to_dict(headers, row)
        if d.get('ID объекта', '').strip().upper() != target_obj:
            continue
        if stage_ref_l == d.get('№ этапа', '').strip() or stage_ref_l in d.get('Название этапа', '').lower():
            return i, d
    return None


def update_stage_status(row_num, new_status, date_str):
    if new_status not in VALID_STAGE_STATUS:
        raise ValueError(f'недопустимый статус: {new_status}')
    values = get_used_range('Этапы')
    headers = values[0]
    d_col = chr(ord('A') + headers.index('Статус'))
    e_col = chr(ord('A') + headers.index('Дата'))
    update_range(f'Этапы!{d_col}{row_num}:{e_col}{row_num}', [[new_status, date_str]])


def current_stage(object_id):
    values = get_used_range('Этапы')
    if not values:
        return 'не начат'
    headers = values[0]
    rows = [_row_to_dict(headers, r) for r in values[1:]
           if r and r[0].strip().upper() == object_id.strip().upper()]
    if not rows:
        return 'не начат'
    rows.sort(key=lambda d: int(d.get('№ этапа') or 0))
    for d in rows:
        if normalize_stage_status(d.get('Статус', '')) == 'в процессе':
            return d.get('Название этапа', '')
    done = [d for d in rows if normalize_stage_status(d.get('Статус', '')) == 'готово']
    if done:
        return done[-1].get('Название этапа', '')
    return 'не начат'


def sync_current_stage(object_id):
    stage = current_stage(object_id)
    update_object_field(object_id, 'Текущий этап', stage)


def all_stages(object_id):
    values = get_used_range('Этапы')
    if not values:
        return []
    headers = values[0]
    rows = []
    for i, r in enumerate(values[1:], start=2):
        if r and r[0].strip().upper() == object_id.strip().upper():
            d = _row_to_dict(headers, r)
            d['_row'] = i
            rows.append(d)
    rows.sort(key=lambda d: int(d.get('№ этапа') or 0))
    return rows


def all_stages_grouped():
    """28.07 (external audit ТЗ п.20): batch-версия all_stages() -- читает 'Этапы'
    ОДИН раз (не по разу на каждый object_id, как было бы при N+1 вызовов all_stages
    в цикле по списку объектов) и группирует локально в Python. Используется списком
    объектов (list_objects), где нужна краткая roadmap-сводка на каждой карточке."""
    values = get_used_range('Этапы')
    grouped = {}
    if not values:
        return grouped
    headers = values[0]
    for i, r in enumerate(values[1:], start=2):
        if not r or not r[0].strip():
            continue
        oid = r[0].strip().upper()
        d = _row_to_dict(headers, r)
        d['_row'] = i
        grouped.setdefault(oid, []).append(d)
    for oid in grouped:
        grouped[oid].sort(key=lambda d: int(d.get('№ этапа') or 0))
    return grouped


def add_stage(object_id, stage_name, description=''):
    from datetime import date
    existing = all_stages(object_id)
    next_num = max([int(s.get('№ этапа') or 0) for s in existing], default=0) + 1
    append_row_safe('Этапы', [object_id, str(next_num), stage_name, 'предстоит', '', f'{object_id}-S{next_num}', description])
    return next_num


def update_stage_description(row_num, description):
    values = get_used_range('Этапы')
    if not values or row_num < 2 or row_num > len(values):
        raise ValueError('этап не найден')
    update_range(f'Этапы!G{row_num}:G{row_num}', [[description]])


def delete_stage(object_id, row_num):
    values = get_used_range('Этапы')
    if not values or row_num < 2 or row_num > len(values):
        raise ValueError('этап не найден')
    row = values[row_num - 1]
    if not row or row[0].strip().upper() != object_id.strip().upper():
        raise ValueError('этап не принадлежит этому объекту')
    update_range(f'Этапы!A{row_num}:G{row_num}', [[''] * 7])


def swap_stage_order(object_id, row_num_a, row_num_b):
    """24.07 Step 6: меняет местами значения '№ этапа' у двух строк -- физические
    строки листа не переставляются (нет такого примитива у Sheets API без полного
    reload диапазона), сортировка all_stages()/current_stage() и так идёт по этому
    числовому полю, так что swap значений достаточен для видимого reorder."""
    values = get_used_range('Этапы')
    if not values:
        raise ValueError('этап не найден')
    for row_num in (row_num_a, row_num_b):
        if row_num < 2 or row_num > len(values):
            raise ValueError('этап не найден')
    row_a = values[row_num_a - 1]
    row_b = values[row_num_b - 1]
    if not row_a or row_a[0].strip().upper() != object_id.strip().upper():
        raise ValueError('этап не принадлежит этому объекту')
    if not row_b or row_b[0].strip().upper() != object_id.strip().upper():
        raise ValueError('этап не принадлежит этому объекту')
    headers = values[0]
    num_idx = headers.index('№ этапа')
    num_col = chr(ord('A') + num_idx)
    num_a, num_b = row_a[num_idx], row_b[num_idx]
    update_range(f'Этапы!{num_col}{row_num_a}:{num_col}{row_num_a}', [[num_b]])
    update_range(f'Этапы!{num_col}{row_num_b}:{num_col}{row_num_b}', [[num_a]])


def worker_complete_stage(object_id, row_num, worker_user_id, date_str):
    """24.07 Step 6, восстановлено 29.07 v2 (feature freeze -- откат review/rework):
    worker отмечает ГОТОВЫМ только текущий этап своего объекта, owner-only
    update_stage_status остаётся единственным способом менять что-либо ещё."""
    stage = current_stage(object_id)
    values = get_used_range('Этапы')
    if not values or row_num < 2 or row_num > len(values):
        raise ValueError('этап не найден')
    row = values[row_num - 1]
    if not row or row[0].strip().upper() != object_id.strip().upper():
        raise ValueError('этап не принадлежит этому объекту')
    headers = values[0]
    d = _row_to_dict(headers, row)
    if d.get('Название этапа', '') != stage:
        raise ValueError('это не текущий этап объекта')
    update_stage_status(row_num, 'готово', date_str)
    sync_current_stage(object_id)


if __name__ == '__main__':
    _demo()


# ---------- Aufgaben (tasks) ----------
import secrets as _secrets

def next_task_id():
    return f'TASK-{_secrets.token_hex(4)}'


def list_tasks(object_id):
    values = get_used_range('Aufgaben')
    if not values:
        return []
    headers = values[0]
    target = object_id.strip().upper()
    return [_row_to_dict(headers, r) for r in values[1:]
           if r and len(r) > 1 and r[1].strip().upper() == target]


def add_task(object_id, text, created_by):
    task_id = next_task_id()
    today = date.today().isoformat()
    append_row_safe('Aufgaben', [task_id, object_id, text, 'offen', created_by, today])
    return task_id


def find_task_row(task_id):
    values = get_used_range('Aufgaben')
    if not values:
        return None
    target = task_id.strip().upper()
    for i, row in enumerate(values[1:], start=2):
        if row and row[0].strip().upper() == target:
            return i
    return None


def complete_task(task_id):
    row_num = find_task_row(task_id)
    if row_num is None:
        raise ValueError(f'Aufgabe {task_id} nicht gefunden')
    update_range(f'Aufgaben!D{row_num}:D{row_num}', [['erledigt']])


def append_row_safe(sheet_name, row):
    """Пишет строку по явно вычисленному номеру, минуя Sheets :append —
    у :append баг: если существующие строки короче ширины заголовка,
    он неправильно вычисляет якорь и сдвигает новые данные вбок.
    Использует лёгкий get_values(колонка A) вместо get_used_range —
    без отдельного metadata-запроса, вдвое быстрее."""
    col_a = get_values(f'{sheet_name}!A:A')
    next_row_num = len(col_a) + 1
    col_count = len(row)
    end_col = chr(ord('A') + col_count - 1) if col_count <= 26 else 'Z'
    update_range(f'{sheet_name}!A{next_row_num}:{end_col}{next_row_num}', [row])
