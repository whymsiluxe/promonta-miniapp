# Roles and permissions

Two roles: `owner`, `worker`. Source: `roles.json` on the VPS, `{telegram_user_id: "owner"|"worker"}`.

## Enforcement mechanism (verified by reading `main.py`)

```python
def get_current_user(x_telegram_init_data: str = Header(...)) -> dict:
    user = validate_init_data(x_telegram_init_data)
    roles = _load_roles()
    if str(user['id']) not in roles:
        _notify_owner_new_user(user, roles)
        raise HTTPException(403, "Доступ не предоставлен. Обратитесь к владельцу.")
    return user

def get_role(user: dict = Depends(get_current_user)) -> str:
    return _load_roles().get(str(user['id']), 'worker')

def require_owner(role: str = Depends(get_role)):
    if role != 'owner':
        raise HTTPException(403, "owner only")
```

**Correction to prior institutional memory**: an earlier internal note (`server-structure.md`, dated 2026-07-15) says unknown Telegram IDs "default to worker". That is **no longer accurate** — a whitelist gate was added since (commented in code as "Фаза 10.1"): any Telegram ID not present in `roles.json` now gets an outright **403**, plus a Telegram notification to the owner. `get_role()`'s `worker` fallback is dead code in practice for unknown users — it only matters for IDs that *are* whitelisted but somehow missing a role value, which shouldn't happen given how roles are written.

Every route requires `Depends(get_current_user)` (confirmed: this is the sole entry point, no route bypasses it based on the grep pass done in this recovery — see [API.md](API.md) for the full route list). Owner-only routes additionally require `Depends(require_owner)`.

## Owner-only routes (verified via grep for `Depends(require_owner)`, 19 matches)

```
GET    /api/roles
POST   /api/roles
DELETE /api/roles/{target_user_id}
POST   /api/objects
PATCH  /api/objects/{object_id}/status
POST   /api/objects/{object_id}/stages
PATCH  /api/objects/{object_id}/stages/{row_num}
DELETE /api/objects/{object_id}/stages/{row_num}
POST   /api/objects/{object_id}/assign
DELETE /api/objects/{object_id}/assign/{user_id}
PATCH  /api/tasks/{task_id}
PATCH  /api/tasks/{task_id}/complete
POST   /api/tools
PATCH  /api/tools/{serial}
POST   /api/critical-alerts
PATCH  /api/abwesenheit/{entry_id}/status
GET    /api/abwesenheit/all
POST   /api/chat/threads/close
POST   /api/chat/threads/reopen
```

This matches expectations: creating/editing objects and stages, managing role whitelist, approving/rejecting absence, force-completing tasks, closing chat threads — all owner actions.

## Worker-accessible routes with inline ownership checks (spot-checked, not owner-gated but correctly self-scoped)

- `GET /api/checkin` — non-owner callers are filtered to their own sessions only (`if role != 'owner': items = [i for i in items if i['user_id'] == user['id']]`). Comment in code references this as a 2026-07-15 fix for a prior GPS-leak bug — confirmed present in current code.
- `DELETE /api/chat/messages/{msg_id}` — non-owner can only delete their own messages (`if role != 'owner' and target['user_id'] != user['id']: raise 403`).
- `PATCH /api/tools/{serial}/checkout` — intentionally any authenticated worker can self-checkout a tool (writes `user['id']` as the new holder); this is correct by design, not a gap.
- `POST /api/critical-alerts/{alert_id}/ack` and `/resolve` — intentionally any authenticated user, since critical alerts are pushed *to* workers to act on; correct by design.

## Findings worth the owner's attention (not silently changed)

- **`POST /api/objects/{object_id}/tasks`** — any authenticated worker can create a task on *any* object, not just one they're assigned to. Not a data-exposure risk (tasks are visible to whoever can see the object regardless), but a product/workflow gap: a worker could add tasks to a site they have nothing to do with. Low severity, flagging rather than fixing — worth a product decision on whether task creation should be assignment-scoped.
- **Route inventory beyond the above was not exhaustively re-verified line-by-line in this recovery pass** (93 routes total; the ones above were spot-checked because they handle GPS, personal messages, or write access to shared resources — the highest-risk categories). Before relying on "everything else is fine," a follow-up pass should grep every route lacking `require_owner` and confirm each one's data-scoping logic matches its risk level, the way the three above were checked here. Tracked in [TODO.md](TODO.md).

## Planned/nonexistent roles

No `admin`, `manager`, `foreman`, `office`, `client`, `subcontractor` roles exist in code or data. If multi-tier permissions become necessary, that's new work, not a hidden existing feature.
