#!/bin/bash
# Promonta miniapp rollback -- Release-аудит Этап 8. Восстанавливает production
# файлы из backup, созданного scripts/deploy.sh (/tmp/rollback_backup_<timestamp>/).
#
# Запуск: sudo scripts/rollback.sh /tmp/rollback_backup_20260730_153917
set -euo pipefail

BACKEND_SERVING_DIR="/home/promonta/agent/miniapp"
FRONTEND_SERVING_DIR="/var/www/miniapp"
SERVICE_NAME="promonta-miniapp.service"
HEALTH_URL="https://app.promonta.fun/api/health"

BACKUP_DIR="${1:-}"
if [[ -z "$BACKUP_DIR" ]]; then
  echo "Использование: $0 <путь-к-backup-директории>" >&2
  echo "Доступные backup'ы:" >&2
  ls -dt /tmp/rollback_backup_* 2>/dev/null | sed 's/^/  /' >&2
  exit 1
fi

echo "== 1/6 Валидация backup-директории =="
if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "ОШИБКА: $BACKUP_DIR не существует" >&2
  exit 1
fi
if [[ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]]; then
  echo "ОШИБКА: $BACKUP_DIR пуст -- нечего восстанавливать" >&2
  exit 1
fi
if [[ ! -f "$BACKUP_DIR/main.py" ]]; then
  echo "ОШИБКА: $BACKUP_DIR/main.py отсутствует -- это не похоже на backup от deploy.sh" >&2
  exit 1
fi
echo "OK: $BACKUP_DIR содержит:"
find "$BACKUP_DIR" -type f | sed 's/^/  /'

echo "== 2/6 Syntax-check backup перед восстановлением =="
python3 -m py_compile "$BACKUP_DIR/main.py"
if [[ -f "$BACKUP_DIR/tools_lib.py" ]]; then
  python3 -m py_compile "$BACKUP_DIR/tools_lib.py"
fi
if [[ -f "$BACKUP_DIR/mangel_lib.py" ]]; then
  python3 -m py_compile "$BACKUP_DIR/mangel_lib.py"
fi
if [[ -f "$BACKUP_DIR/objekte_lib.py" ]]; then
  python3 -m py_compile "$BACKUP_DIR/objekte_lib.py"
fi
echo "OK"

echo "== 3/6 Восстановление backend =="
cp "$BACKUP_DIR/main.py" "${BACKEND_SERVING_DIR}/main.py"
if [[ -f "$BACKUP_DIR/tools_lib.py" ]]; then
  cp "$BACKUP_DIR/tools_lib.py" "${BACKEND_SERVING_DIR}/tools_lib.py"
fi
if [[ -f "$BACKUP_DIR/mangel_lib.py" ]]; then
  cp "$BACKUP_DIR/mangel_lib.py" "${BACKEND_SERVING_DIR}/mangel_lib.py"
fi
if [[ -f "$BACKUP_DIR/objekte_lib.py" ]]; then
  cp "$BACKUP_DIR/objekte_lib.py" "${BACKEND_SERVING_DIR}/objekte_lib.py"
fi
# VERSION -- симметрично deploy.sh: backup либо содержит старый VERSION (сценарий A,
# восстановить), либо маркер .VERSION_ABSENT (сценарий B, файла до deploy не было --
# удалить тот, что создал деплой, чтобы /api/health не показывал отменённый SHA).
if [[ -f "$BACKUP_DIR/VERSION" ]]; then
  cp "$BACKUP_DIR/VERSION" "${BACKEND_SERVING_DIR}/VERSION"
elif [[ -f "$BACKUP_DIR/.VERSION_ABSENT" ]]; then
  rm -f "${BACKEND_SERVING_DIR}/VERSION"
fi
echo "OK"

echo "== 4/6 Восстановление frontend (если было в backup) =="
if [[ -d "$BACKUP_DIR/frontend" ]]; then
  rsync -a --delete "$BACKUP_DIR/frontend/" "${FRONTEND_SERVING_DIR}/"
  chown -R root:root "$FRONTEND_SERVING_DIR" 2>/dev/null || echo "предупреждение: chown пропущен (не root)"
  echo "OK"
else
  echo "(в этом backup не было frontend -- пропущено)"
fi

echo "== 5/6 Restart backend =="
systemctl restart "$SERVICE_NAME"
sleep 3
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "ОШИБКА: $SERVICE_NAME не активен после restart даже после отката -- требуется ручное вмешательство" >&2
  journalctl -u "$SERVICE_NAME" -n 30 --no-pager
  exit 1
fi
echo "OK: $SERVICE_NAME активен"

echo "== 6/6 Health-проверка =="
HEALTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || echo 000)"
echo "GET $HEALTH_URL -> $HEALTH_CODE"
if [[ "$HEALTH_CODE" != "200" ]]; then
  echo "ПРЕДУПРЕЖДЕНИЕ: /api/health не отвечает 200 даже после отката -- нужна ручная диагностика" >&2
fi

echo ""
echo "=== ОТКАТ ЗАВЕРШЁН ==="
echo "Backup НЕ удалён (на случай если понадобится снова): $BACKUP_DIR"
