# Backup и восстановление

Дата: 2026-07-31. Проверено на живом сервере, не с чужих слов.

## Source of truth

Вся бизнес-логика приложения хранится в двух местах:

1. **Google Sheets** — объекты, этапы, инструменты (через `objekte_lib.py`/
   `tools_lib.py`, OAuth refresh_token). Google Sheets — это отдельный источник
   правды, у Google своя защита от потери данных (version history), но
   `refresh_token` (`/home/promonta/agent/.sheets.json`) — единая точка отказа
   для доступа к нему из приложения.
2. **JSON-файлы на диске сервера** (`/home/promonta/agent/miniapp/*.json`) —
   всё остальное: роли, назначения, смены (`checkin_meta.json`), чат, дефекты
   (`mangel_tickets.json`), отсутствия, задачи/потребности, alerts, roadmap.
   Здесь на диске — единственная копия, ничего не зеркалируется во внешний
   сервис (кроме best-effort Sheets-mirror для некоторых записей, см.
   `docs/RELEASE_AUDIT.md`).

## Где хранится

| Что | Путь | В backup? |
|---|---|---|
| JSON-сторы (роли/смены/чат/дефекты/...) | `/home/promonta/agent/miniapp/*.json` | Да |
| Загруженные фото/документы/голосовые | `/home/promonta/agent/miniapp/{object_photos,chat_attachments,checkin_photos,avatars,object_documents,transcribe_audio,blocker_photos,critical_alert_photos}` | Да (внутри `agent_*.tgz`) |
| Медиа для frontend (иконки инструментов и т.п.) | `/var/www/miniapp/media/` | **Нет** — не в текущем backup-скрипте, но это статичные generated-ассеты, воспроизводимые из репозитория/промптов, не пользовательские данные |
| Google OAuth credentials | `/home/promonta/agent/.sheets.json` | Да, отдельным архивом `secrets_*.tgz` |
| Telegram bot token и прочие secrets | `/etc/claude-agent.env` | Да, `secrets_*.tgz` |
| Код приложения | Git-репозиторий (`backend/`, `frontend/`) | Да — GitHub, не нуждается в отдельном файловом backup |
| audit.log (журнал запросов) | `/home/promonta/agent/miniapp/audit.log` | Да (внутри `agent_*.tgz`) |

## Что попадает в backup

Существующий `promonta-backup.service`/`.timer` (systemd, ежедневно 03:00,
`/home/promonta/agent/backup.sh`):

- `tar czf agent_<timestamp>.tgz` — весь `/home/promonta/agent` (кроме
  `.venv`/`__pycache__`/`node_modules`), включает все JSON-сторы, все
  загруженные файлы, `audit.log`.
- `tar czf secrets_<timestamp>.tgz` — отдельно `/etc/claude-agent.env` и
  `/home/promonta/agent/.sheets.json`.
- Хранится последние 14 копий каждого архива локально в `/home/promonta/backups/`,
  старые удаляются автоматически.
- Симлинки `agent_latest.tgz`/`secrets_latest.tgz` — Mac-сторона периодически
  тянет их и кладёт в iCloud (внешняя копия вне сервера).
- Дополнительно запускает `sheet_export.py` (экспорт Google Sheets данных).

## Что НЕ попадает в backup

- `/var/www/miniapp/media/` — сгенерированные статичные ассеты (иконки
  инструментов/объектов), не пользовательские данные, воспроизводимы.
- Само содержимое Google Sheets (у Google своя защита, `sheet_export.py`
  делает локальный снепшот, но это не полноценный restore-путь для Sheets).
- `/tmp/rollback_backup_*` — deploy-time backups (см. `scripts/rollback.sh`),
  временные, не для восстановления пользовательских данных.
- Логи systemd journal (`journalctl`) — не архивируются отдельно, `journalctl
  --disk-usage` на момент написания — 1.4G, растёт со временем (см. "disk space" ниже).

## Как восстановить

### Полное восстановление после потери сервера

1. Поднять новый VPS, установить те же системные пакеты (Python 3.12, Node.js,
   libmagic1, ffmpeg для транскрипции).
2. Распаковать самый свежий `agent_latest.tgz` в `/home/promonta/`.
3. Распаковать `secrets_latest.tgz` — восстановит `/etc/claude-agent.env` и
   `.sheets.json`.
4. `git clone` репозитория в `/home/promonta/agent/miniapp-repo`.
5. Создать venv (`python3 -m venv /home/promonta/agent/miniapp/.venv`), поставить
   `backend/requirements.txt`.
6. Настроить systemd unit (`/etc/systemd/system/promonta-miniapp.service`),
   Caddy/nginx для frontend (см. `docs/DEPLOYMENT.md`).
7. Запустить `scripts/deploy.sh` (после проверки, что все JSON-сторы на месте —
   деплой сам их не трогает, только код).

### Восстановление одного повреждённого JSON-файла

Начиная с этой сессии (см. `docs/RELEASE_AUDIT.md`, Этап 2) все критичные
JSON-сторы (`checkin_meta.json`, `chat_messages.json`, `chat_messages_archive.json`,
`mangel_tickets.json` и остальные через `_atomic_write_json`) пишутся атомарно —
`open(...,'w')+json.dump` напрямую больше не используется на этих файлах, значит
обрезанный файл посреди записи (crash/kill -9) практически исключён. Если всё же
`_safe_load_json` встретит невалидный JSON — приложение **не падает**, деградирует
к дефолтному значению (`{}`/`[]`) и пишет `ERROR: {path} corrupt JSON, falling
back to default` в лог. Это значит на практике: при повреждении файла приложение
продолжит работать, но с "чистого листа" по этому конкретному стору.

**Если это произошло:**
1. Проверить логи (`journalctl -u promonta-miniapp -n 100`) на предмет
   `corrupt JSON` — определить какой именно файл и когда.
2. Найти самый свежий backup ДО момента повреждения: `ls -t
   /home/promonta/backups/agent_*.tgz`.
3. Распаковать во временную директорию, найти конкретный JSON-файл внутри
   `agent/miniapp/`, сравнить его временную метку с моментом повреждения.
4. Скопировать восстановленный файл на прод, перезапустить сервис.
5. Данные, записанные МЕЖДУ последним backup и моментом повреждения, будут
   потеряны — это ограничение ежедневного (не непрерывного) backup.

### Восстановление одного файла загрузки (фото/документ)

Аналогично — распаковать нужный `agent_*.tgz`, найти файл по пути внутри
соответствующей директории (`object_photos/`, `chat_attachments/` и т.д.),
скопировать обратно. Ссылки на файл в JSON-сторе (например `object_images.json`)
восстанавливать отдельно не нужно, если сам JSON не был повреждён — они хранят
только имя файла, не содержимое.

## Как проверить восстановление

Не полагаться на "backup существует" — раз в месяц (рекомендация, конкретный
интервал: **OWNER DECISION REQUIRED**) вручную:

1. Скопировать последний `agent_latest.tgz` на любую тестовую машину (не прод).
2. Распаковать, проверить `python3 -c "import json; json.load(open('checkin_meta.json'))"`
   на нескольких ключевых JSON-файлах — валидный JSON, разумный размер (не 0 байт).
3. Открыть 1-2 файла из `object_photos`/`chat_attachments` — убедиться, что
   это реально валидные изображения, не обрезанные.

## Срок хранения backup

- Локально на сервере: последние 14 ежедневных копий (~2 недели), старше —
  удаляются автоматически скриптом.
- В iCloud (через Mac-синхронизацию): срок хранения **OWNER DECISION REQUIRED**
  — на момент написания не задокументирована политика ротации на стороне iCloud.

## Кто имеет доступ

- SSH-доступ к серверу — root/`promonta` пользователь, только через ключ
  (`~/.ssh/promonta_hetzner` на стороне владельца/агента).
- Backup-архивы на диске сервера читаемы всеми, у кого есть доступ к
  `/home/promonta/backups/` — та же граница доступа, что и SSH к серверу в целом.
- iCloud-копия — только владелец Apple ID, под которым синхронизируется Mac.

## Что делать при повреждении JSON

См. "Восстановление одного повреждённого JSON-файла" выше. Коротко: приложение
само не падает (деградирует к дефолту + логирует), но данные до момента
последнего backup нужно восстанавливать вручную из архива.

## Что делать при потере Google Sheets OAuth

Если `refresh_token` в `.sheets.json` истёк/отозван:

1. Приложение продолжит работать для всего, что НЕ зависит от Sheets (чат,
   отсутствия, назначения, дефекты, инструменты хранятся в JSON, не в Sheets —
   но список объектов/этапов через `objekte_lib.py` и каталог инструментов
   через `tools_lib.py` перестанут отвечать).
2. Владелец должен заново пройти OAuth-flow для получения нового refresh_token
   (Google Cloud Console, тот же проект/client_id что использовался раньше).
3. Заменить `.sheets.json` новым токеном, перезапустить сервис.
4. `secrets_*.tgz` в backup содержит СТАРЫЙ токен на момент backup — если он
   уже истёк, backup не поможет восстановить доступ, только даёт историческую
   копию для справки.

## Что делать при заполнении диска

На момент этого документа: `df -h /` показывает 24% использовано (8.6G из 38G) —
не критично, но нужно следить за ростом:

- `checkin_photos/` — крупнейшая директория загрузок (35M на момент проверки,
  растёт с каждой сменой с фото). Естественный рост, ретеншен-политика для
  старых фото смен **OWNER DECISION REQUIRED** (сейчас хранятся бессрочно).
- `journalctl` — 1.4G архивных логов на момент проверки. systemd-journald по
  умолчанию имеет свой SystemMaxUse лимит (проверить `journalctl
  --disk-usage` периодически); если не настроен явно — может расти
  неограниченно. Рекомендация: `journalctl --vacuum-time=90d` вручную или
  через systemd-journald.conf, если место станет проблемой.
- `/tmp/rollback_backup_*` — deploy-time backups НЕ удаляются автоматически
  ни `scripts/deploy.sh`, ни `scripts/rollback.sh` (осознанное решение —
  всегда должен быть путь для отката). Требует периодической ручной очистки
  старых копий (`ls -t /tmp/rollback_backup_* | tail -n +6 | xargs rm -rf`
  вручную, оставляя последние 5, если место закончится) — retention-политика
  для них **OWNER DECISION REQUIRED**, сейчас не автоматизирована.
- `.bak-*` файлы в serving-путях (`/home/promonta/agent/miniapp/*.bak-*`) —
  на момент проверки 75 файлов, накопленных за прошлые ручные деплои. Не
  влияют на работу приложения, но занимают место и путают при навигации по
  директории. Кандидат на ручную чистку, не автоматизировано.
