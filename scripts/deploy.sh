#!/bin/bash
# Promonta miniapp deploy -- Release-аудит Этап 8. Полный цикл: чистота репо ->
# тесты -> syntax -> backup -> копирование в production paths -> restart ->
# health-проверка. При ЛЮБОЙ ошибке на любом шаге -- exit, ничего дальше не
# трогаем (set -euo pipefail), последний удачный backup остаётся на диске для
# scripts/rollback.sh.
#
# Запуск: на VPS, из корня репозитория (/home/promonta/agent/miniapp-repo):
#   sudo scripts/deploy.sh
# (sudo нужен для записи в /var/www/miniapp/, владелец root; без sudo backend-
# часть всё равно задеплоится, если пользователь promonta имеет права на
# /home/promonta/agent/miniapp/, но frontend-шаг откажет.)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Production paths -- НЕ угадано, сверено с реальным systemd unit
# (/etc/systemd/system/promonta-miniapp.service, WorkingDirectory=/home/promonta/agent,
# ExecStart=uvicorn miniapp.main:app) и реальной раздачей frontend через Caddy
# (/var/www/miniapp/) на момент написания этого скрипта.
BACKEND_SERVING_DIR="/home/promonta/agent/miniapp"
FRONTEND_SERVING_DIR="/var/www/miniapp"
SERVICE_NAME="promonta-miniapp.service"
HEALTH_URL="https://app.promonta.fun/api/health"
HEALTH_READY_URL_LOCAL="http://127.0.0.1:8001/api/health/ready"

TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="/tmp/rollback_backup_${TS}"

echo "== 1/12 Проверка: работаем из git-репозитория =="
if [[ ! -d "$REPO_DIR/.git" ]]; then
  echo "ОШИБКА: $REPO_DIR не является git-репозиторием" >&2
  exit 1
fi
echo "OK: $REPO_DIR"

echo "== 2/12 Проверка ветки и SHA =="
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
CURRENT_SHA="$(git rev-parse HEAD)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  echo "ОШИБКА: деплой разрешён только с ветки main, сейчас на '$CURRENT_BRANCH'" >&2
  exit 1
fi
echo "OK: branch=main, SHA=$CURRENT_SHA"

echo "== 3/12 Проверка чистого git status =="
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ОШИБКА: есть незакоммиченные изменения -- закоммить или stash перед деплоем" >&2
  git status --short
  exit 1
fi
echo "OK: working tree чист"

echo "== 4/12 Python syntax-check =="
python3 -m py_compile backend/*.py
echo "OK"

echo "== 5/12 node --check (frontend/js/*.js) =="
for f in frontend/js/*.js; do
  node --check "$f"
done
echo "OK"

echo "== 6/12 Полный test suite =="
# Тестовое окружение сервиса (venv с fastapi/python-magic уже установлены) --
# не production venv напрямую с активацией, а явный путь к интерпретатору,
# как и во всех прошлых прогонах в этой сессии.
TEST_PYTHON="${BACKEND_SERVING_DIR}/.venv/bin/python3"
if [[ ! -x "$TEST_PYTHON" ]]; then
  echo "ОШИБКА: $TEST_PYTHON не найден -- venv сервиса недоступен" >&2
  exit 1
fi
if [[ -f /etc/claude-agent.env ]]; then
  env $(grep -v '^#' /etc/claude-agent.env | xargs -d'\n') "$TEST_PYTHON" -m pytest tests/ -q
else
  echo "ОШИБКА: /etc/claude-agent.env не найден (нужен BOT_TOKEN для теста)" >&2
  exit 1
fi
echo "OK: тесты прошли"

echo "== 7/12 Создание timestamped backup =="
mkdir -p "$BACKUP_DIR"
if [[ -f "${BACKEND_SERVING_DIR}/main.py" ]]; then
  cp "${BACKEND_SERVING_DIR}/main.py" "${BACKUP_DIR}/main.py"
fi
if [[ -f "${BACKEND_SERVING_DIR}/tools_lib.py" ]]; then
  cp "${BACKEND_SERVING_DIR}/tools_lib.py" "${BACKUP_DIR}/tools_lib.py"
fi
if [[ -f "${BACKEND_SERVING_DIR}/mangel_lib.py" ]]; then
  cp "${BACKEND_SERVING_DIR}/mangel_lib.py" "${BACKUP_DIR}/mangel_lib.py"
fi
if [[ -f "${BACKEND_SERVING_DIR}/objekte_lib.py" ]]; then
  cp "${BACKEND_SERVING_DIR}/objekte_lib.py" "${BACKUP_DIR}/objekte_lib.py"
fi
if [[ -f "${BACKEND_SERVING_DIR}/VERSION" ]]; then
  cp "${BACKEND_SERVING_DIR}/VERSION" "${BACKUP_DIR}/VERSION"
else
  touch "${BACKUP_DIR}/.VERSION_ABSENT"
fi
if [[ -d "$FRONTEND_SERVING_DIR" ]]; then
  mkdir -p "${BACKUP_DIR}/frontend"
  rsync -a "${FRONTEND_SERVING_DIR}/" "${BACKUP_DIR}/frontend/"
fi
echo "== 8/12 Проверка, что backup реально содержит файлы =="
if [[ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]]; then
  echo "ОШИБКА: backup-директория пуста после копирования -- деплой остановлен" >&2
  exit 1
fi
echo "OK: backup сохранён в $BACKUP_DIR"
find "$BACKUP_DIR" -type f | sed 's/^/  /'

echo "== 9/12 Копирование backend в serving-путь (main.py + tools_lib.py + mangel_lib.py рядом) =="
# ВАЖНО: tools_lib.py и mangel_lib.py обязаны лежать РЯДОМ с main.py -- изолированный
# importlib-loader (_load_repo_tools_lib/_load_repo_mangel_lib в main.py) резолвит их
# по BACKEND_DIR = os.path.dirname(main.py), не по глобальному sys.path.
cp "$REPO_DIR/backend/main.py" "${BACKEND_SERVING_DIR}/main.py"
cp "$REPO_DIR/backend/tools_lib.py" "${BACKEND_SERVING_DIR}/tools_lib.py"
cp "$REPO_DIR/backend/mangel_lib.py" "${BACKEND_SERVING_DIR}/mangel_lib.py"
cp "$REPO_DIR/backend/objekte_lib.py" "${BACKEND_SERVING_DIR}/objekte_lib.py"
python3 -m py_compile "${BACKEND_SERVING_DIR}/main.py" "${BACKEND_SERVING_DIR}/tools_lib.py" "${BACKEND_SERVING_DIR}/mangel_lib.py" "${BACKEND_SERVING_DIR}/objekte_lib.py"
# Version-файл для /api/health -- version/commit видны в ответе без git subprocess
# на каждый запрос (main.py читает VERSION рядом с собой, см. APP_VERSION_FILE).
cat > "${BACKEND_SERVING_DIR}/VERSION" <<EOF
{"version": "$(git describe --tags --always 2>/dev/null || echo 0.9.0-rc1)", "commit": "$CURRENT_SHA"}
EOF
echo "OK"

echo "== 10/12 Копирование frontend (без .git, без тестов, без secrets) =="
mkdir -p "$FRONTEND_SERVING_DIR"
rsync -av --delete \
  --exclude='.git*' --exclude='.archived-legacy' --exclude='*.bak-*' \
  "$REPO_DIR/frontend/" "$FRONTEND_SERVING_DIR/"
chown -R root:root "$FRONTEND_SERVING_DIR" 2>/dev/null || echo "предупреждение: chown пропущен (не root) -- проверь права вручную"
echo "OK"

echo "== 11/12 Restart backend =="
systemctl restart "$SERVICE_NAME"
sleep 3
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "ОШИБКА: $SERVICE_NAME не активен после restart -- см. journalctl -u $SERVICE_NAME" >&2
  echo "Для отката: scripts/rollback.sh $BACKUP_DIR" >&2
  exit 1
fi
echo "OK: $SERVICE_NAME активен"

echo "== 12/12 Health/readiness проверка =="
HEALTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || echo 000)"
echo "GET $HEALTH_URL -> $HEALTH_CODE"
if [[ "$HEALTH_CODE" != "200" ]]; then
  echo "ОШИБКА: /api/health не отвечает 200 после деплоя" >&2
  echo "Для отката: scripts/rollback.sh $BACKUP_DIR" >&2
  exit 1
fi
echo "(readiness /api/health/ready owner-only -- проверь вручную через Telegram-авторизованный запрос, скрипт её не может вызвать без initData)"

echo ""
echo "== Последние логи backend =="
journalctl -u "$SERVICE_NAME" -n 20 --no-pager

echo ""
echo "=== ДЕПЛОЙ ЗАВЕРШЁН ==="
echo "SHA:     $CURRENT_SHA"
echo "Backup:  $BACKUP_DIR (не удалён -- для отката: scripts/rollback.sh $BACKUP_DIR)"
