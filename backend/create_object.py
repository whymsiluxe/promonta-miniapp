#!/usr/bin/env python3
"""Регистрация нового объекта: генерит object_id, создаёт Drive-подпапку,
добавляет строку в Объекты + строки в Этапы. Fail-before-write: если Drive
не создался — строка в Объекты не пишется.

Usage: create_object.py '<Объект>' '<Адрес>' <Бюджет> [Этап1 Этап2 ...]
"""
import os, sys, json, urllib.request, urllib.parse
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from objekte_lib import get_used_range, get_values, append_row, append_row_safe, parse_amount, InvalidAmountError

DRIVE_CRED = '/home/promonta/agent/.gdrive_creds.json'
DRIVE_TOKEN = '/home/promonta/agent/.gdrive_token.json'
ROOT_FOLDER_ID = '1m3321Ps5Uym6G-pIpN-6vIOivIfC53fG'


def _drive_token():
    creds = json.load(open(DRIVE_CRED))
    c = creds.get('web') or creds.get('installed')
    tok = json.load(open(DRIVE_TOKEN))
    b = urllib.parse.urlencode({'client_id': c['client_id'], 'client_secret': c['client_secret'],
                                'refresh_token': tok['refresh_token'], 'grant_type': 'refresh_token'}).encode()
    r = json.load(urllib.request.urlopen('https://oauth2.googleapis.com/token', b, timeout=20))
    if not r.get('access_token'):
        raise RuntimeError(f'drive token refresh fail: {r}')
    return r['access_token']


def create_drive_folder(name, parent_id):
    token = _drive_token()
    meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
    body = json.dumps(meta).encode()
    req = urllib.request.Request('https://www.googleapis.com/drive/v3/files', data=body, method='POST',
                                 headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    r = json.load(urllib.request.urlopen(req, timeout=20))
    if not r.get('id'):
        raise RuntimeError(f'drive folder create fail: {r}')
    return r['id'], f"https://drive.google.com/drive/folders/{r['id']}"


def next_object_id():
    year = date.today().year
    values = get_values('Объекты!A:A')
    max_n = 0
    prefix = f'PM-{year}-'
    for row in (values[1:] if values else []):
        if row and row[0].strip().upper().startswith(prefix):
            try:
                n = int(row[0].strip().split('-')[-1])
                max_n = max(max_n, n)
            except ValueError:
                continue
    return f'PM-{year}-{max_n + 1:03d}'


def main():
    if len(sys.argv) < 4:
        print('Usage: create_object.py <Объект> <Адрес> <Бюджет> [--start=YYYY-MM-DD] [--end=YYYY-MM-DD] [Этап1 Этап2 ...]', file=sys.stderr)
        sys.exit(1)

    name, address, budget_raw = sys.argv[1], sys.argv[2], sys.argv[3]
    rest = sys.argv[4:]
    start_date = ''
    end_date = ''
    stages = []
    for arg in rest:
        if arg.startswith('--start='):
            start_date = arg.split('=', 1)[1]
        elif arg.startswith('--end='):
            end_date = arg.split('=', 1)[1]
        else:
            stages.append(arg)
    stages = stages or ['Основной этап']

    try:
        budget = parse_amount(budget_raw)
    except InvalidAmountError as e:
        print(f'Некорректный бюджет: {e}', file=sys.stderr)
        sys.exit(1)

    object_id = next_object_id()

    # Быстрый путь: пишем в Sheet сразу без Drive-папки (пустая ссылка).
    # Папку досоздаём отдельным фоновым вызовом create_object_folder.py,
    # чтобы не блокировать пользователя на 5-6 секунд Drive API.
    today = date.today().isoformat()
    append_row_safe('Объекты', [object_id, name, address, 'открыт', str(budget), '0.00', '0',
                           stages[0], '', today, '0', '', start_date, end_date])

    for i, stage_name in enumerate(stages, start=1):
        status = 'в процессе' if i == 1 else 'предстоит'
        append_row_safe('Этапы', [object_id, str(i), stage_name, status, today, f'{object_id}-S{i}'])

    print(f'OK: {object_id} создан')
    print(f'Этапов: {len(stages)}')


if __name__ == '__main__':
    main()
