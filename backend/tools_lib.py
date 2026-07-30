#!/usr/bin/env python3
"""Учёт инструмента — отдельная Google Sheet, не связана с Objekte&Kosten."""
import json, time, urllib.request, urllib.parse
from datetime import datetime

SHEETS_CRED = '/home/promonta/agent/.sheets.json'
SHEET_ID = '1m1PDEPs8ZUc1WhKXzThlAilwIlzIVaQaxzPEn1_JDrs'
TOOLS_TAB = 'Лист1'
HISTORY_TAB = 'История'

HEADERS = ['Серийный #', 'Название Инструмента', 'Категория', 'Кто взял', 'У кого взял',
           'Дата возврата', 'Статус', 'Обьект/Адрес', 'ID держателя']
# 22.07: ID держателя (колонка I) — telegram user_id того, кто реально оформил checkout сам
# (не когда owner вручную вписывает произвольное имя в 'Кто взял' — тогда ID неизвестен и
# остаётся пустым). Нужен чтобы avatar держателя на карточке инструмента был кликабельным
# (openUserCard(userId)) — раньше было только имя-строка, не user_id.

# 30.07 (Инструменты cleanup): зеркало RAW_STATUS_MAP из frontend tools.js -- та же
# конвенция "пустой/нераспознанный статус = free", используется backend'ом для
# проверки "инструмент уже выдан" перед checkout (раньше этой проверки не было явно).
RAW_STATUS_MAP = {'на объекте': 'in-use', 'зарезервирован': 'reserved', 'в ремонте': 'repair', 'не найден': 'missing'}


def mapped_status(tool: dict) -> str:
    raw = (tool.get('Статус') or '').strip().lower()
    return RAW_STATUS_MAP.get(raw, 'free')

_token_cache = {'token': None, 'expires_at': 0}


def _token():
    if _token_cache['token'] and time.time() < _token_cache['expires_at'] - 60:
        return _token_cache['token']
    c = json.load(open(SHEETS_CRED))
    b = urllib.parse.urlencode({'client_id': c['client_id'], 'client_secret': c['client_secret'],
                                'refresh_token': c['refresh_token'], 'grant_type': 'refresh_token'}).encode()
    r = json.load(urllib.request.urlopen('https://oauth2.googleapis.com/token', b, timeout=20))
    _token_cache['token'] = r['access_token']
    _token_cache['expires_at'] = time.time() + r.get('expires_in', 3600)
    return r['access_token']


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


def _row_to_dict(row):
    row = list(row) + [''] * (len(HEADERS) - len(row))
    return dict(zip(HEADERS, row))


def list_tools():
    """Все инструменты с непустым серийным # и названием (пропускает мусорные пустые строки)."""
    values = get_values(f'{TOOLS_TAB}!A2:I1000')
    tools = []
    for row in values:
        d = _row_to_dict(row)
        if d['Серийный #'].strip() and d['Название Инструмента'].strip():
            tools.append(d)
    return tools


def find_tool_row(serial):
    """1-based номер строки (с учётом заголовка в строке 1) или None."""
    values = get_values(f'{TOOLS_TAB}!A2:I1000')
    target = str(serial).strip()
    for i, row in enumerate(values, start=2):
        d = _row_to_dict(row)
        if d['Серийный #'].strip() == target:
            return i
    return None


def get_tool(serial):
    """Строка инструмента как dict (для проверки текущего держателя перед возвратом) или None."""
    values = get_values(f'{TOOLS_TAB}!A2:I1000')
    target = str(serial).strip()
    for row in values:
        d = _row_to_dict(row)
        if d['Серийный #'].strip() == target:
            return d
    return None


def checkout_tool(serial, holder, object_name, changed_by, holder_id=''):
    """Работник/владелец берёт инструмент — статус На объекте, пишет holder+object, лог в Историю.
    holder_id — telegram user_id worker'а, если checkout делает он сам (не owner вручную)."""
    row_num = find_tool_row(serial)
    if row_num is None:
        raise ValueError(f'инструмент {serial} не найден')
    update_range(f'{TOOLS_TAB}!D{row_num}:I{row_num}', [[holder, '', '', 'На объекте', object_name, holder_id or '']])
    append_row_safe(HISTORY_TAB, [datetime.now().isoformat(timespec='seconds'), serial,
                             f'Выдана {holder} → {object_name}', changed_by])


def return_tool(serial, changed_by):
    """30.07 (Инструменты-редизайн, п.11): настоящий возврат -- отдельно от checkout_tool,
    т.к. checkout с пустыми holder/object_name всё равно писал holder_id текущего юзера
    (реальный найденный баг: "возврат" молча делал юзера держателем свободного инструмента).
    Очищает Кто взял/ID держателя/Обьект-Адрес, статус -> Свободен."""
    row_num = find_tool_row(serial)
    if row_num is None:
        raise ValueError(f'инструмент {serial} не найден')
    update_range(f'{TOOLS_TAB}!D{row_num}:I{row_num}', [['', '', '', '', '', '']])
    append_row_safe(HISTORY_TAB, [datetime.now().isoformat(timespec='seconds'), serial,
                             'Возвращён', changed_by])


def update_tool_status(serial, status, holder, object_name, changed_by, holder_id=''):
    """Владелец правит статус/держателя вручную (возврат, ремонт, исправление ошибки работника).
    holder_id пустой по умолчанию — owner вписывает имя текстом, реальный user_id неизвестен,
    avatar в этом случае остаётся некликабельным (нет ID для openUserCard)."""
    row_num = find_tool_row(serial)
    if row_num is None:
        raise ValueError(f'инструмент {serial} не найден')
    update_range(f'{TOOLS_TAB}!D{row_num}:I{row_num}',
                 [[holder or '', '', '', status, object_name or '', holder_id or '']])
    append_row_safe(HISTORY_TAB, [datetime.now().isoformat(timespec='seconds'), serial,
                             f'Владелец изменил: статус={status}, кто={holder or "-"}, объект={object_name or "-"}',
                             changed_by])


def add_tool(name, category, changed_by):
    values = get_values(f'{TOOLS_TAB}!A2:A1000')
    existing = [int(r[0]) for r in values if r and r[0].strip().isdigit()]
    next_serial = max(existing) + 1 if existing else 1
    append_row_safe(TOOLS_TAB, [str(next_serial), name, category, '', '', '', 'Свободен', '', ''])
    append_row_safe(HISTORY_TAB, [datetime.now().isoformat(timespec='seconds'), str(next_serial),
                             f'Добавлен новый инструмент: {name} ({category})', changed_by])
    return next_serial


def tool_history(serial):
    values = get_values(f'{HISTORY_TAB}!A2:D5000')
    target = str(serial).strip()
    rows = [{'date': r[0], 'serial': r[1], 'text': r[2], 'by': r[3] if len(r) > 3 else ''}
           for r in values if len(r) >= 3 and r[1].strip() == target]
    rows.sort(key=lambda r: r['date'], reverse=True)
    return rows


def append_row_safe(sheet_name, row):
    """Безопасная запись — Sheets :append сдвигает данные если строки разной длины."""
    values = get_values(f'{sheet_name}!A1:Z10000')
    next_row_num = len(values) + 1
    col_count = len(row)
    end_col = chr(ord('A') + col_count - 1) if col_count <= 26 else 'Z'
    update_range(f'{sheet_name}!A{next_row_num}:{end_col}{next_row_num}', [row])
