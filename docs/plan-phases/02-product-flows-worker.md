# Promonta Mini App — Audit Master Plan (Phase file)

PHASE B part 1 — Worker shift flows (start/active/finish wizard/voice/dashboard/object-card-for-owner). Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE B — Product flows (Worker/Owner core scenarios)

Источники: ТЗ1 §2-10, ТЗ2 §30-32, §44.

### B1. Старт смены
Одна кнопка "Начать смену" если один объект сегодня; выбор только из назначенных, если несколько. GPS + фото "до начала" обязательны (см. A2/A3-аналог для старта). Нельзя начать на чужом объекте, нельзя начать вторую смену при активной. Сохранять object_id/worker_id/start_time/start_location/start_photo(s)/stage.

### B2. Активная смена — отдельный экран
Объект, адрес, этап, таймер, статус GPS, быстрые действия: фото/чат объекта/потребность/дефект/отправить геолокацию в чат/завершить смену. Геолокация в чат — координаты видны только участникам соответствующего чата/объекта.

### B3. Finish shift — пошаговый wizard
Step 1 Фото (мин. 2, см. A3) → Step 2 Что сделано (текст + голос + AI-транскрипт, редактируемый, не auto-send) → Step 3 Доп. работы (Нет/Добавить, голос, AI может структурировать в пункты, каждый editable: описание/зона/время/нужно ли согласование) → Step 4 Потребности/проблемы (категории: материалы/инструмент/СИЗ/доступ/дефект/другое, не создавать Need/Mangel автоматически без подтверждения) → Step 5 Геолокация финиша (обязательна, см. A2) → Step 6 Сводка + отправка.

Backend finish endpoint принимает структурированные поля: `work_summary`, `extra_works[]`, `needs[]`, `defects[]`, `blockers`, `finish_photos[]`, `finish_location`. Проверяет: активная смена есть, object_id из смены не с клиента (A4), доступ, мин. 2 фото (A3), finish location (A2). Атомарная запись.

### B4. Voice input + AI transcription
Статус: **Backend FIXED (commit 823a08d), frontend NOT STARTED.**

`POST /api/transcribe` создан (owner explicit decision: отдельный endpoint, не переиспользовать chat-voice). Переиспользует существующую `_transcribe_voice()`. Response: `{raw_transcript, status, file_id, audio_url}`.

**Owner explicit correction во время разработки**: изначальный план предполагал temp-file (транскрибировать → удалить), но owner сказал хранить аудио постоянно — "транскрибация может быть хуёвой", юзер должен мочь переслушать оригинал, не только доверять тексту. Реализовано: аудио хранится в `transcribe_audio/{user_id}/{file_id}.ext`, отдельный `GET /api/transcribe/{file_id}/audio` для playback (worker — только свои записи, owner — любые, `file_id` basename-sanitized).

**Не сделано в этом проходе** (backend-only per B4 scope): frontend reusable voice-input component (idle/recording/recorded/transcribing/ready/error states + record/stop/cancel/re-record/use-text buttons), wiring в finish-shift шаги 2-4/создание дефекта/потребности. `cleaned_text`/AI-структуризация текста в пункты — тоже не реализовано, только `raw_transcript`. Это отдельная frontend-задача, требует brainstorm UI перед стартом (см. B1-B3 — тот же subject, owner попросил brainstorm экранов сначала).

### B5. Dashboard владельца — добавить блоки (не переписывать с нуля)
Кто сейчас работает (worker/объект/start time/duration/чат). Кто не начал смену (worker/объект/этап/напомнить). Alerts (critical/просроченные задачи/новые дефекты/потребности). Просроченные задачи → alerts с переходом. Смены сегодня (начаты/завершены/активные/с проблемами).

### B6. Object card для owner — центр управления
Внутри карточки/страницы объекта собрать: общая инфо, адрес, статус, назначенные workers, этапы, сегодняшние смены, история смен, фото до/после, задачи+просроченные, потребности, дефекты, документы, чат объекта, бюджет (owner-only), история действий. Для worker — урезанная версия (адрес/что делать/этапы/документы/чат/свои needs-defects). См. также PHASE F (карточка-превью в списке) и Object Detail IA (PHASE C).

