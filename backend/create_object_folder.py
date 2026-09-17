#!/usr/bin/env python3
"""Фоновая досоздание Drive-папки для уже зарегистрированного объекта.
Вызывается отдельно от create_object.py, чтобы не блокировать пользователя.
Usage: create_object_folder.py <object_id> <name>
"""
import os, sys, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from objekte_lib import find_object_row, update_object_field

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


def main():
    if len(sys.argv) < 3:
        print('Usage: create_object_folder.py <object_id> <name>', file=sys.stderr)
        sys.exit(1)

    object_id, name = sys.argv[1], sys.argv[2]

    if find_object_row(object_id) is None:
        print(f'Объект {object_id} не найден в Sheet, папку не создаю', file=sys.stderr)
        sys.exit(1)

    folder_id, folder_url = create_drive_folder(f'{object_id} — {name}', ROOT_FOLDER_ID)
    update_object_field(object_id, 'Папка на Drive', folder_url)
    print(f'OK: папка создана для {object_id}: {folder_url}')


if __name__ == '__main__':
    main()
