# Promonta Mini App — Audit Master Plan (Phase file)

PHASE H part 2 — Test infrastructure, E2E flows, visual regression, endpoint audit table, docs update. Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE H (continued) — Tests, docs, endpoint audit

### Test infrastructure
Playwright + mock Telegram WebApp API. Viewports: iPhone 13 mini/15 Pro/15 Pro Max, Android 360×800/412×915, Telegram Desktop narrow. Telegram host overlay simulation (Dynamic Island/Close/Back/menu/safe area/keyboard) — bounding rect assertions, ни один элемент не пересекает reserved zones.

Обязательные E2E flows: Home, Objects, Photo feed, Chat, Object chat, Tasks, Needs (worker+owner), Profile, Radio — конкретные шаги см. ТЗ2 §52.

Visual regression baselines — список экранов см. ТЗ2 §53. Desktop Chromium screenshots ≠ доказательство iOS Telegram — physical tests помечать `REQUIRED — NOT YET VERIFIED` или `VERIFIED ON DEVICE: device/iOS/Telegram version/date`.

### Backend endpoint audit table
Для каждого из ~93-106 routes: METHOD/PATH/HANDLER/AUTH/ROLE/RESOURCE SCOPE/READS/WRITES/EXTERNAL SIDE EFFECTS/ERROR BEHAVIOUR/TEST COVERAGE/RISK. Существующий TODO.md REC-3 уже это требует — не дублировать, использовать эту секцию как выполнение REC-3.

### Документация
Обновить: README.md, docs/{PROJECT_STATE,TODO,API,ROLES_AND_PERMISSIONS,SECURITY,UI_UX}.md — **известный факт для исправления**: PROJECT_STATE.md утверждает `fix/security-reliability-p1` "not merged", но `git log main..origin/fix/security-reliability-p1` пустой = уже смёржено, документ устарел, поправить в рамках этой фазы.

Создать `docs/audit/*` (14 файлов, список см. ТЗ2 §59) для дефектов формата ID/Severity/Status/Screenshot symptom/Affected screen/files/functions/Code evidence/Root cause/Impact/Reproduction/Safe fix/Automated test/Physical test/Migration/Rollback. Severity P0-P4 по критериям ТЗ2 §59.

Добавить `scripts/smoke.sh` — не существует.

Минимальные тесты, явно запрошенные владельцем: backend auth, worker не может открыть unassigned object, finish shift требует 2 фото, finish shift требует location, chat attachment сохраняет thread_key, `/api/transcribe` существует (или задокументировать реальный путь — см. B4), XSS-sensitive render functions экранируют значения.

---

## Продуктовая философия (не actionable, ориентир для решений)

Worker: "Пришёл на объект, начал смену, сделал работу, быстро голосом отчитался, приложил фото, сообщил проблемы." Owner: "Вижу кто где работает, кто не начал, где просрочено, где нужны материалы, где дефекты, где тревога, могу быстро принять решение." Не красота ради красоты — рабочий/компактный/понятный/мобильный/одной рукой/большие кнопки для строителя/плотная инфо для владельца.

Финальный acceptance (весь план): worker завершает смену 30-60 сек; finish shift невозможен без 2 фото + geo; start shift невозможен без geo; голос заполняет отчёт/доп.работы/потребности/дефекты; owner видит "кто работает"/"кто не начал" на dashboard; просрочка → alerts; вся инфа объекта в одной карточке для owner; API безопасен по ролям и объектам; чаты не смешивают контексты.

---

## Порядок выполнения (согласовано с owner)

1. **PHASE A (Security P0)** — начинаем здесь.
2. PHASE B (Product flows) — параллельно/следом, многое пересекается с A (finish-shift backend = A2-A4).
3. PHASE C (Telegram UI/Navigation).
4. PHASE D (Design System V2).
5. PHASE E (Chat Hub).
6. PHASE F (Object Card).
7. PHASE G (Radio Player).
8. PHASE H (Architecture/Tests/Docs) — частично идёт параллельно всем фазам (тесты пишутся вместе с фичей, не в конце).

Каждая фаза — отдельные коммиты, маленькие логические блоки, `py_compile`+`node --check` после каждого, обновление этого файла статусами по мере выполнения.
