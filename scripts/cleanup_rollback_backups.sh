#!/bin/bash
# Release-аудит Этап 9: retention для /tmp/rollback_backup_* (deploy-time backups,
# НЕ пользовательские данные -- те защищены отдельным ежедневным promonta-backup.timer,
# см. docs/BACKUP_AND_RECOVERY.md). Оставляет последние N (по умолчанию 5), удаляет
# остальные. Безопасно запускать вручную или добавить в cron -- ничего кроме
# /tmp/rollback_backup_* не трогает.
#
# Использование: scripts/cleanup_rollback_backups.sh [keep_count]
set -euo pipefail

KEEP="${1:-5}"

mapfile -t BACKUPS < <(ls -dt /tmp/rollback_backup_* 2>/dev/null || true)
TOTAL="${#BACKUPS[@]}"

if [[ "$TOTAL" -le "$KEEP" ]]; then
  echo "Найдено $TOTAL backup(ов), храним $KEEP -- удалять нечего."
  exit 0
fi

TO_DELETE=("${BACKUPS[@]:$KEEP}")
echo "Найдено $TOTAL backup(ов), храним $KEEP самых свежих, удаляем ${#TO_DELETE[@]}:"
for dir in "${TO_DELETE[@]}"; do
  echo "  $dir"
  rm -rf "$dir"
done
echo "Готово."
