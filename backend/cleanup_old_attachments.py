#!/usr/bin/env python3
"""Удаляет файлы вложений старше RETENTION_DAYS из папок chat_attachments/
critical_alert_photos/checkin_photos — без этого лимита папки растут бесконечно
(10.29, Fable-аудит). Запускается по systemd timer раз в сутки."""
import os
import time

RETENTION_DAYS = 90
CUTOFF = time.time() - RETENTION_DAYS * 86400

DIRS = [
    '/home/promonta/agent/miniapp/chat_attachments',
    '/home/promonta/agent/miniapp/critical_alert_photos',
    '/home/promonta/agent/miniapp/checkin_photos',
]


def cleanup_dir(path):
    if not os.path.isdir(path):
        return 0
    removed = 0
    for root, dirs, files in os.walk(path):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                if os.path.getmtime(fpath) < CUTOFF:
                    os.remove(fpath)
                    removed += 1
            except OSError:
                continue
    return removed


def main():
    total = 0
    for d in DIRS:
        n = cleanup_dir(d)
        total += n
        if n:
            print(f'{d}: removed {n} files older than {RETENTION_DAYS}d')
    if not total:
        print('OK: nothing to clean')


if __name__ == '__main__':
    main()
