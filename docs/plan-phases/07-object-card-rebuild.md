# Promonta Mini App — Audit Master Plan (Phase file)

PHASE F — Object Card full rebuild. Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE F — Object Card rebuild

Источник: ТЗ4 (полное, все 26 разделов получены) + ТЗ2 §27-29.

Референс: ski-resort card (hero photo, weather island top-center, worker avatars overlap bottom-left, status pill bottom-right, dots, title, address, stages strip). Композицию переносим буквально, содержание — реальные данные объекта.

### Текущее дублирование, которое нужно убрать (уже частично закрыто в v3, commit `cea952e` — проверить актуальное состояние перед повтором)
Бюджет/статус/этап не должны повторяться. Не должно быть: status editor в preview, "Текущий этап" строкой если этап уже в нижнем блоке, второй progress bar, кнопки Documents в preview, ссылки Defects в обычной карточке, множество chips.

### Нормализованный DTO (frontend не зависит от сырых Sheets-колонок)
```json
{
  "id": "OBJ-001", "name": "...", "address": "...", "maps_url": "...",
  "start_date": "2026-07-22", "status": "IN_PROGRESS", "status_label": "В работе",
  "photos": [{"url":"...", "alt":"..."}],
  "weather": {"temperature": 18, "condition": "Дождь", "icon": "rain"},
  "workers": [{"id":"...", "name":"...", "avatar_url":"..."}],
  "stages": [{"id":"...", "title":"Демонтаж", "status":"DONE"}]
}
```
Backend уже возвращает `Дата старта`/`Дата окончания` из Sheets (подтверждено прошлой сессией, `GET /api/objects` делает `dict(zip(header,r))`, ничего не фильтрует) — просто не рендерилось, теперь используем. Weather — существующий `GET /api/feed/weather` (cron-populated `.weather_feed.json`, matched by object name), кешировать через `_objWeatherByName`, НЕ делать N+1 запрос на карточку. Stages — НЕ дёргать `/api/objects/{id}/stages` per-card (N+1), только `Текущий этап` строка из list response для превью; полный DONE/ACTIVE/NEXT timeline — в Object Detail (PHASE B6/C).

Компонент: `frontend/js/components/object-card.js`, `frontend/css/components/object-card.css`. Без inline onclick/style.

Layout: photo (aspect ~4:3, cover, branded SVG fallback без stock-фото) → gradient (верх легче для weather, низ плотнее для avatars/status) → carousel dots (только если photos.length>1, swipe+drag, counter, index сохраняется) → weather island (absolute top-center, темный charcoal/forest bg, blur ок, LOADING/LOADED/ERROR states, скрыть если нет координат — не делать frontend geocoding с ключом в клиенте) → workers overlap (max 3 + `+N`, первый 54-58px, остальные 42-48px, overlap 12-18px, ivory border, тап → worker preview/direct chat с stopPropagation, не открывает объект) → status pill (bottom-right, полупрозрачный тёмный, text+icon не только цвет, IN_PROGRESS=forest/PAUSED=brass/ATTENTION=oxblood/COMPLETED=muted) → title (26-30px/700, center, max 2 строки) → address (кликабельно → Google Maps через `https://www.google.com/maps/search/?api=1&query=<encoded>`, Telegram.openLink, "Адрес не указан" если нет) → start date (Europe/Berlin display, скрыть если нет, никогда не показывать null/ISO raw) → stages strip (max 3 видимых: done/active/next, ivory pill background, тап → Object Detail Этапы, не редактировать в карточке; если нет этапов — "Этапы не добавлены").

Бюджет: по умолчанию НЕ показывать (референс не содержит). Максимум один compact secondary indicator под датой, owner-only, feature-flaggable.

Interactive zones раздельны с stopPropagation: address→Maps, avatar→worker/chat, `+N`→team sheet, stages→Detail/Work, photo→viewer, остальное→Object Detail (сохранить scroll+photo index при Back).

Performance: batch workers data, stages вместе с DTO или batch, weather cached TTL 15-30min, lazy-load images, preload только следующий фото в активной карусели, responsive image sizes, не грузить full-res оригинал в маленькую карточку.

Тесты: unit (DTO adapter, status label, stages DONE/ACTIVE/NEXT selection, avatar fallback, Maps URL encoding, date formatting, weather unavailable, no-budget-duplication) + component (status ровно один раз, stage не дублируется, max 3 avatars+N, weather island скрывается без данных) + Playwright E2E (22 шага из ТЗ4 §21) + visual regression (16 сценариев из ТЗ4 §22, worker vs owner version).

---

