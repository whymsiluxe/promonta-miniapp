# Promonta Mini App — Audit Master Plan (Phase file)

PHASE B part 1 — Worker shift flows (start/active/finish wizard/voice/dashboard/object-card-for-owner). Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE B — Product flows (Worker/Owner core scenarios)

Источники: ТЗ1 §2-10, ТЗ2 §30-32, §44.

### B1. Старт смены
Статус: **Было уже почти полностью реализовано, +stage picker добавлен (commit eae17cb, 2026-07-27).** Проверка кода показала: single/multi-object autoselect уже есть (`_openWorkerObjectPicker`), GPS+фото required уже есть (Фаза 01, A2/A3), нельзя начать на чужом объекте / вторую смену — уже было. Owner подтвердил добавить недостающее: выбор этапа из полного списка этапов объекта. Добавлено `_openStagePickerThenStart()` между выбором объекта и стартом — грузит `GET /api/objects/{id}/stages`, показывает picker со скипом, не блокирует старт если этапов нет/запрос упал. Backend: `checkin_start` принимает опциональный `stage_name`, сохраняет в entry.

### B2. Активная смена
Статус: **FIXED (commit 4e592e1, 2026-07-27).** Owner решение: и расширенная Home CTA (уже была), и панель внутри существующего `stages-view` (не отдельный full-screen view — переиспользует object-detail shell). `#active-shift-panel` показывается когда `refreshCheckinButtons()` находит открытую сессию: live-таймер (один setInterval на всё приложение, explicit guard от дублирования при повторных вызовах `refreshCheckinButtons`, учитывает `pause_accumulated_seconds`), GPS-статус (проверка `navigator.geolocation` наличия, не polling `getCurrentPosition` каждую секунду — не тратит батарею), quick actions: Чат/Потребность/Дефект (переиспользуют существующие кнопки/switchView).

**Осознанно НЕ сделано**: quick action "Фото" — `checkin-photo-input` жёстко завязан на `_checkinPendingAction` ('start'|'finish'), нет режима "просто прикрепить фото посреди смены", backend endpoint для этого не существует — не стал строить полу-рабочую кнопку. **Geo-в-чат** — owner explicit decision отложить, новая фича без backend поддержки, вне скоупа этого прохода.

### B3. Finish shift — пошаговый wizard
Статус: **FIXED, полностью (commits 4376123 backend + 8bbf03d frontend, 2026-07-27).** Owner решение: делать весь wizard сразу по плану (не поэтапно), structured extra_works хранить сразу (не текстом).

Backend: `checkin_finish` принимает `extra_works`/`needs`/`defects` как JSON-encoded списки (опциональные Form-поля, старый `extra_work: str` работает как раньше для обратной совместимости с `checkin_manual`/старыми клиентами). Ни один список не создаёт Need/Mangel тикеты автоматически — только сохраняется в session, реальное создание — отдельный подтверждённый вызов с фронтенда после успешного finish. `_extra_works_summary_text()` сериализует список в текст для Zeiterfassung Sheets/Telegram push (не показывает сырой JSON бухгалтерии/owner).

Frontend: новый `frontend/js/finish-wizard.js` (отдельно от checkin.js), новый `#finish-wizard-modal` (не переиспользует `checkin-preview-modal` — тот остался для start-shift). 6 шагов реализованы по плану: фото (мин 2) → что сделано (текст+voice через `/api/transcribe` из B4) → доп.работы (structured list, каждый пункт с описанием/зоной/временем/чекбоксом согласования, свой voice-button) → потребности (категории materials/tool/ppe/access/other) + дефекты (оба list, ничего не создаётся до подтверждения) → гео финиша (обязательна, retry на отказ) → сводка + submit (finish → затем по одному POST /api/tasks на каждый Need и POST /api/mangel на каждый Defect, best-effort — сбой создания тикета не откатывает уже успешный finish).

Оба входа в finish (checkin.js `checkin-finish-btn`, worker-checkin-fab.js `checkin-status-finish-btn`) переключены на `openFinishShiftWizard()`, старый photo-picker flow для finish больше не используется (start остался нетронут).

**Не сделано в этом проходе**: AI-структуризация voice-транскрипта доп-работ в несколько пунктов автоматически (voice сейчас просто дописывает текст в текущее редактируемое поле, worker добавляет по одному пункту вручную) — план упоминал это как желательное, не обязательное. Фото-вложения к Need/Defect, созданным через wizard — не реализовано (spec подразумевал, wizard создаёт их только текстом).

### B4. Voice input + AI transcription
Статус: **Backend FIXED (commit 823a08d), frontend NOT STARTED.**

`POST /api/transcribe` создан (owner explicit decision: отдельный endpoint, не переиспользовать chat-voice). Переиспользует существующую `_transcribe_voice()`. Response: `{raw_transcript, status, file_id, audio_url}`.

**Owner explicit correction во время разработки**: изначальный план предполагал temp-file (транскрибировать → удалить), но owner сказал хранить аудио постоянно — "транскрибация может быть хуёвой", юзер должен мочь переслушать оригинал, не только доверять тексту. Реализовано: аудио хранится в `transcribe_audio/{user_id}/{file_id}.ext`, отдельный `GET /api/transcribe/{file_id}/audio` для playback (worker — только свои записи, owner — любые, `file_id` basename-sanitized).

**Не сделано в этом проходе** (backend-only per B4 scope): frontend reusable voice-input component (idle/recording/recorded/transcribing/ready/error states + record/stop/cancel/re-record/use-text buttons), wiring в finish-shift шаги 2-4/создание дефекта/потребности. `cleaned_text`/AI-структуризация текста в пункты — тоже не реализовано, только `raw_transcript`. Это отдельная frontend-задача, требует brainstorm UI перед стартом (см. B1-B3 — тот же subject, owner попросил brainstorm экранов сначала).

### B5. Dashboard владельца — добавить блоки (не переписывать с нуля)
Кто сейчас работает (worker/объект/start time/duration/чат). Кто не начал смену (worker/объект/этап/напомнить). Alerts (critical/просроченные задачи/новые дефекты/потребности). Просроченные задачи → alerts с переходом. Смены сегодня (начаты/завершены/активные/с проблемами).

### B6. Object card для owner — центр управления
Внутри карточки/страницы объекта собрать: общая инфо, адрес, статус, назначенные workers, этапы, сегодняшние смены, история смен, фото до/после, задачи+просроченные, потребности, дефекты, документы, чат объекта, бюджет (owner-only), история действий. Для worker — урезанная версия (адрес/что делать/этапы/документы/чат/свои needs-defects). См. также PHASE F (карточка-превью в списке) и Object Detail IA (PHASE C).

