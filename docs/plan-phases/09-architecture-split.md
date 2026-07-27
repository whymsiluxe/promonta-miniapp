# Promonta Mini App — Audit Master Plan (Phase file)

PHASE H part 1 — Backend/frontend architecture split, API client, UI states, offline queue. Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE H — Frontend/Backend Architecture, Tests, Docs

Источники: ТЗ1 §13-14, ТЗ2 §36-39, §51-56.

### Backend split (модульный монолит, НЕ микросервисы)
`backend/main.py` — 4027 строк, полностью монолитный (подтверждено). Порядок extraction: permissions → storage → shifts → files → chat → objects → assignments → defects → needs → documents → AI. Целевая структура — см. ТЗ2 §56 (`app/core/{config,auth,permissions,errors,logging,time,ids}.py`, `app/storage/{base,json_storage,transactions,schemas}.py`, `app/modules/{users,objects,assignments,work_items,needs,defects,shifts,chat,documents,notifications,ai}/`, `app/integrations/{telegram,google_sheets,file_storage,pdf,ai_provider}.py`). Router не должен одновременно открывать JSON + решать permissions + subprocess + Google + Telegram + files + business logic.

### Frontend split
`frontend/app.html` — 4000 строк. Извлекать по компоненту с regression tests, не одним махом. Целевая структура — см. ТЗ2 §36 (`css/{tokens,base,layout,components,screens/*}.css`, `js/core/{api,router,navigation,lifecycle,telegram-viewport,state,events}.js`, `js/components/*`, `js/screens/*`).

### API client
Единый клиент: timeout, AbortController, Telegram initData, expired session handling ("Сессия Telegram истекла..." без infinite retry loop), FormData, retries, request dedup, idempotency для non-idempotent mutations, offline errors, error code mapping. Unified error contract: `{"error":{"code":"...","message":"...","request_id":"..."}}`.

### UI states
Каждый screen: initial loading/refreshing/loaded/empty/mutation pending/partial failure/full failure/offline/retry. Reusable: Skeleton/EmptyState/ErrorState/OfflineState/InlineLoader/Toast/RetryButton.

### Offline queue (минимум для start/finish shift, message, Need, Defect, photos)
IndexedDB не только localStorage. States: LOCAL/QUEUED/SENDING/SENT/FAILED/CONFLICT. Persistent idempotency key, manual+auto retry с backoff, visible status, success только после backend confirmation. Не обязательно всё сразу — один working slice архитектуры достаточно на первый проход.

