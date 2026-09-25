"""Stages and roadmap HTTP routes.

This module deliberately does not import backend.main. main.py owns the shared
runtime state/loaders and wires them through StagesRouteDeps, then re-exports
the handlers for legacy direct-call tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


class NewStageBody(BaseModel):
    name: str
    description: str = ''


class StageDescriptionBody(BaseModel):
    description: str


class StageStatusBody(BaseModel):
    status: str


class StageSwapBody(BaseModel):
    row_num_b: int


class StageBlockerBody(BaseModel):
    quick_reason: str = ''
    comment: str = ''
    photo_url: str = ''
    who_decides: str = ''
    expected_date: str = ''


class RoadmapCategoryBody(BaseModel):
    title: str


class RoadmapItemCreateBody(BaseModel):
    title: str
    category_id: str | None = None
    description: str = ''
    required: bool = True
    safety_critical: bool = False
    weight: int = 1


class RoadmapItemEditBody(BaseModel):
    title: str | None = None
    description: str | None = None
    required: bool | None = None
    safety_critical: bool | None = None
    weight: int | None = None
    category_id: str | None = None


class RoadmapItemStatusBody(BaseModel):
    status: str


class RoadmapNoteBody(BaseModel):
    text: str
    item_id: str | None = None


class StageRequestBody(BaseModel):
    kind: str
    new_status: str = ''


class StageRequestDecisionBody(BaseModel):
    approve: bool


@dataclass(frozen=True)
class StagesRouteDeps:
    get_current_user: Callable
    get_role: Callable
    require_owner: Callable
    require_object_access: Callable
    cached_get_used_range: Callable
    load_repo_objekte_lib: Callable
    roadmap_lib: Callable
    safe_load_json: Callable
    update_json_transaction: Callable
    business_today_str: Callable
    append_object_history_best_effort: Callable
    get_worker_profile: Callable
    sanitize_display_name: Callable
    load_roles: Callable
    create_critical_alert: Callable
    send_telegram_message: Callable


def create_stages_router(deps: StagesRouteDeps):
    router = APIRouter()

    def _cached_all_stages(object_id: str) -> list:
        o = deps.load_repo_objekte_lib()
        values = deps.cached_get_used_range('Этапы')
        if not values:
            return []
        headers = values[0]
        rows = []
        for i, r in enumerate(values[1:], start=2):
            if r and r[0].strip().upper() == object_id.strip().upper():
                d = o._row_to_dict(headers, r)
                d['_row'] = i
                rows.append(d)
        rows.sort(key=lambda d: int(d.get('№ этапа') or 0))
        return rows

    def _load_roadmap_store() -> dict:
        rl = deps.roadmap_lib()
        return deps.safe_load_json(rl.ROADMAP_FILE, rl._default_store())

    def _load_stage_requests() -> list:
        rl = deps.roadmap_lib()
        return deps.safe_load_json(rl.STAGE_REQUESTS_FILE, rl._default_requests())

    def _find_stage_by_row(object_id: str, row_num: int) -> dict:
        o = deps.load_repo_objekte_lib()
        stages = o.all_stages(object_id)
        stage = next((s for s in stages if s['_row'] == row_num), None)
        if not stage:
            raise HTTPException(404, "Этап не найден")
        return stage

    @router.get("/api/objects/{object_id}/stages")
    def get_stages(object_id: str, user: dict = Depends(deps.get_current_user)):
        # 28.07: owner request -- любой воркер может просматривать этапы любого объекта.
        return {"stages": _cached_all_stages(object_id)}

    @router.post("/api/objects/{object_id}/stages")
    def create_stage(object_id: str, body: NewStageBody, user: dict = Depends(deps.get_current_user),
                     _: None = Depends(deps.require_object_access)):
        o = deps.load_repo_objekte_lib()
        if not body.name.strip():
            raise HTTPException(400, "Name erforderlich")
        num = o.add_stage(object_id, body.name.strip(), body.description.strip()[:2000])
        o.sync_current_stage(object_id)
        return {"stage_num": num}

    @router.patch("/api/objects/{object_id}/stages/{row_num}/description")
    def update_stage_description_endpoint(object_id: str, row_num: int, body: StageDescriptionBody,
                                          user: dict = Depends(deps.get_current_user),
                                          _: None = Depends(deps.require_object_access)):
        o = deps.load_repo_objekte_lib()
        try:
            o.update_stage_description(row_num, body.description.strip()[:2000])
        except ValueError as e:
            raise HTTPException(404, str(e))
        return {"status": "ok"}

    @router.patch("/api/objects/{object_id}/stages/{row_num}")
    def update_stage(object_id: str, row_num: int, body: StageStatusBody,
                     user: dict = Depends(deps.get_current_user), _: None = Depends(deps.require_owner)):
        o = deps.load_repo_objekte_lib()
        try:
            stage_before = _find_stage_by_row(object_id, row_num)
        except Exception:
            stage_before = {}
        try:
            o.update_stage_status(row_num, body.status, deps.business_today_str())
        except ValueError as e:
            raise HTTPException(400, str(e))
        o.sync_current_stage(object_id)
        stage_name = stage_before.get('Название этапа') or f'#{row_num}'
        old_status = stage_before.get('Статус', '')
        subtitle = f'{stage_name} · {old_status} -> {body.status}' if old_status else f'{stage_name} · {body.status}'
        deps.append_object_history_best_effort(
            object_id, 'stage_status_changed', 'Статус этапа изменён',
            user=user, subtitle=subtitle,
            meta={
                "row_num": row_num,
                "stage_name": stage_name,
                "old_status": old_status,
                "new_status": body.status,
            },
        )
        return {"status": "ok"}

    @router.delete("/api/objects/{object_id}/stages/{row_num}")
    def remove_stage(object_id: str, row_num: int, user: dict = Depends(deps.get_current_user),
                     _: None = Depends(deps.require_owner)):
        o = deps.load_repo_objekte_lib()
        try:
            o.delete_stage(object_id, row_num)
        except ValueError as e:
            raise HTTPException(404, str(e))
        o.sync_current_stage(object_id)
        return {"status": "ok"}

    @router.patch("/api/objects/{object_id}/stages/{row_num}/swap")
    def swap_stage(object_id: str, row_num: int, body: StageSwapBody,
                   user: dict = Depends(deps.get_current_user), _: None = Depends(deps.require_owner)):
        o = deps.load_repo_objekte_lib()
        try:
            o.swap_stage_order(object_id, row_num, body.row_num_b)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"status": "ok"}

    @router.post("/api/objects/{object_id}/stages/{row_num}/complete")
    def worker_complete_stage(object_id: str, row_num: int, user: dict = Depends(deps.get_current_user),
                              _: None = Depends(deps.require_object_access)):
        o = deps.load_repo_objekte_lib()
        try:
            stage_before = _find_stage_by_row(object_id, row_num)
        except Exception:
            stage_before = {}
        try:
            o.worker_complete_stage(object_id, row_num, str(user['id']), deps.business_today_str())
        except ValueError as e:
            raise HTTPException(400, str(e))
        stage_name = stage_before.get('Название этапа') or f'#{row_num}'
        deps.append_object_history_best_effort(
            object_id, 'stage_completed', 'Этап завершён',
            user=user, subtitle=stage_name,
            meta={"row_num": row_num, "stage_name": stage_name},
        )
        return {"status": "ok"}

    @router.post("/api/objects/{object_id}/stages/{row_num}/blocker")
    def set_stage_blocker(object_id: str, row_num: int, body: StageBlockerBody,
                          user: dict = Depends(deps.get_current_user),
                          _: None = Depends(deps.require_object_access)):
        if not (body.quick_reason.strip() or body.comment.strip()):
            raise HTTPException(400, "Укажите причину")
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        stage_key = stage['ID строки этапа']

        def _mutate(store):
            return rl.set_stage_block_meta(
                store, stage_key, None, str(user['id']),
                quick_reason=body.quick_reason, comment=body.comment, photo_url=body.photo_url,
                who_decides=body.who_decides, expected_date=body.expected_date,
            )
        meta = deps.update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)
        return {"status": "ok", "meta": meta}

    @router.delete("/api/objects/{object_id}/stages/{row_num}/blocker")
    def clear_stage_blocker(object_id: str, row_num: int, user: dict = Depends(deps.get_current_user),
                            _: None = Depends(deps.require_object_access)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        stage_key = stage['ID строки этапа']

        def _mutate(store):
            rl.clear_stage_block_meta(store, stage_key)
            return {"status": "ok"}
        return deps.update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)

    @router.get("/api/objects/{object_id}/stages/{row_num}/roadmap")
    def get_stage_roadmap(object_id: str, row_num: int, user: dict = Depends(deps.get_current_user)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        store = _load_roadmap_store()
        snapshot = rl.stage_snapshot(store, stage['ID строки этапа'])
        snapshot['stage'] = stage
        return snapshot

    @router.post("/api/objects/{object_id}/stages/{row_num}/roadmap/categories")
    def create_roadmap_category(object_id: str, row_num: int, body: RoadmapCategoryBody,
                                user: dict = Depends(deps.get_current_user),
                                _: None = Depends(deps.require_owner)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        if not body.title.strip():
            raise HTTPException(400, "Название категории обязательно")
        return deps.update_json_transaction(
            rl.ROADMAP_FILE, rl._default_store,
            lambda store: rl.new_category(store, stage['ID строки этапа'], body.title.strip()[:100]),
        )

    @router.delete("/api/objects/{object_id}/stages/{row_num}/roadmap/categories/{category_id}")
    def delete_roadmap_category(object_id: str, row_num: int, category_id: str,
                                user: dict = Depends(deps.get_current_user),
                                _: None = Depends(deps.require_owner)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        stage_key = stage['ID строки этапа']

        def _mutate(store):
            has_items = any(i.get('category_id') == category_id for i in store['items'].get(stage_key, []))
            if has_items:
                raise HTTPException(400, "Нельзя удалить категорию с пунктами -- сначала перенесите или удалите их")
            if not rl.delete_category(store, stage_key, category_id):
                raise HTTPException(404, "Категория не найдена")
            return {"status": "ok"}

        return deps.update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)

    @router.post("/api/objects/{object_id}/stages/{row_num}/roadmap/items")
    def create_roadmap_item(object_id: str, row_num: int, body: RoadmapItemCreateBody,
                            user: dict = Depends(deps.get_current_user),
                            _: None = Depends(deps.require_owner)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        if not body.title.strip():
            raise HTTPException(400, "Название пункта обязательно")
        stage_key = stage['ID строки этапа']
        return deps.update_json_transaction(
            rl.ROADMAP_FILE, rl._default_store,
            lambda store: rl.new_item(
                store, stage_key, body.title.strip()[:200], category_id=body.category_id,
                description=body.description.strip()[:1000], required=body.required,
                safety_critical=body.safety_critical, weight=body.weight,
            ),
        )

    @router.patch("/api/objects/{object_id}/stages/{row_num}/roadmap/items/{item_id}")
    def edit_roadmap_item(object_id: str, row_num: int, item_id: str, body: RoadmapItemEditBody,
                          user: dict = Depends(deps.get_current_user),
                          _: None = Depends(deps.require_owner)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        stage_key = stage['ID строки этапа']

        def _mutate(store):
            item = rl.edit_item(store, stage_key, item_id, **fields)
            if not item:
                raise HTTPException(404, "Пункт не найден")
            return item

        return deps.update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)

    @router.delete("/api/objects/{object_id}/stages/{row_num}/roadmap/items/{item_id}")
    def delete_roadmap_item(object_id: str, row_num: int, item_id: str,
                            user: dict = Depends(deps.get_current_user),
                            _: None = Depends(deps.require_owner)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        stage_key = stage['ID строки этапа']

        def _mutate(store):
            if not rl.delete_item(store, stage_key, item_id):
                raise HTTPException(404, "Пункт не найден")
            return {"status": "ok"}

        return deps.update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)

    @router.post("/api/objects/{object_id}/stages/{row_num}/roadmap/items/{item_id}/status")
    def update_roadmap_item_status(object_id: str, row_num: int, item_id: str, body: RoadmapItemStatusBody,
                                   user: dict = Depends(deps.get_current_user),
                                   _: None = Depends(deps.require_object_access)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        stage_key = stage['ID строки этапа']

        def _mutate(store):
            try:
                item = rl.update_item_status(store, stage_key, item_id, body.status, str(user['id']))
            except ValueError as e:
                raise HTTPException(400, str(e))
            if not item:
                raise HTTPException(404, "Пункт не найден")
            return item

        return deps.update_json_transaction(rl.ROADMAP_FILE, rl._default_store, _mutate)

    @router.post("/api/objects/{object_id}/stages/{row_num}/roadmap/notes")
    def create_roadmap_note(object_id: str, row_num: int, body: RoadmapNoteBody,
                            user: dict = Depends(deps.get_current_user),
                            _: None = Depends(deps.require_object_access)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        if not body.text.strip():
            raise HTTPException(400, "Текст заметки обязателен")
        profile = deps.get_worker_profile(user['id'])
        author_name = deps.sanitize_display_name(profile.get('name'), str(user['id']))
        stage_key = stage['ID строки этапа']
        return deps.update_json_transaction(
            rl.ROADMAP_FILE, rl._default_store,
            lambda store: rl.new_note(store, stage_key, str(user['id']), author_name, body.text, item_id=body.item_id),
        )

    @router.get("/api/objects/{object_id}/stages/{row_num}/roadmap/notes")
    def list_roadmap_notes(object_id: str, row_num: int, item_id: str = '',
                           user: dict = Depends(deps.get_current_user)):
        rl = deps.roadmap_lib()
        stage = _find_stage_by_row(object_id, row_num)
        store = _load_roadmap_store()
        notes = rl.stage_notes(store, stage['ID строки этапа'], item_id=item_id or None)
        return {"notes": sorted(notes, key=lambda n: n['created_at'])}

    @router.post("/api/objects/{object_id}/stages/{row_num}/request")
    def create_stage_request(object_id: str, row_num: int, body: StageRequestBody,
                             user: dict = Depends(deps.get_current_user), role: str = Depends(deps.get_role),
                             _: None = Depends(deps.require_object_access)):
        rl = deps.roadmap_lib()
        o = deps.load_repo_objekte_lib()
        if role == 'owner':
            raise HTTPException(400, "Owner меняет этапы напрямую, без запроса")
        stage = _find_stage_by_row(object_id, row_num)
        if body.kind not in rl.REQUEST_KINDS:
            raise HTTPException(400, "Недопустимый тип запроса")
        payload = {}
        if body.kind == 'change_status':
            if body.new_status not in o.VALID_STAGE_STATUS:
                raise HTTPException(400, "Недопустимый статус")
            payload['new_status'] = body.new_status

        profile = deps.get_worker_profile(user['id'])
        requester_name = deps.sanitize_display_name(profile.get('name'), str(user['id']))
        stage_key = stage['ID строки этапа']
        req = deps.update_json_transaction(
            rl.STAGE_REQUESTS_FILE, rl._default_requests,
            lambda requests: rl.new_stage_request(
                requests, object_id, stage_key, row_num, body.kind,
                str(user['id']), requester_name, payload=payload,
            ),
        )

        roles = deps.load_roles()
        owner_id = next((uid for uid, r in roles.items() if r == 'owner'), None)
        if owner_id:
            kind_label = 'удаление этапа' if body.kind == 'delete_stage' else f"смену статуса на «{payload.get('new_status', '')}»"
            alert = deps.create_critical_alert(
                target_user_id=owner_id, kind='stage_request',
                title=f"{requester_name} просит {kind_label}",
                subtitle=stage.get('Название этапа', ''), ref_id=req['id'],
            )
            req['critical_alert_id'] = alert['id']

            def _attach_alert(requests):
                r = rl.find_stage_request(requests, req['id'])
                if r:
                    r['critical_alert_id'] = alert['id']
                return r
            deps.update_json_transaction(rl.STAGE_REQUESTS_FILE, rl._default_requests, _attach_alert)
        return req

    @router.get("/api/objects/{object_id}/stages/requests")
    def list_stage_requests(object_id: str, user: dict = Depends(deps.get_current_user),
                            _: None = Depends(deps.require_owner)):
        rl = deps.roadmap_lib()
        requests = _load_stage_requests()
        return {"requests": rl.pending_requests_for_object(requests, object_id)}

    @router.post("/api/objects/{object_id}/stages/requests/{request_id}/decide")
    def decide_stage_request_endpoint(object_id: str, request_id: str, body: StageRequestDecisionBody,
                                      user: dict = Depends(deps.get_current_user),
                                      _: None = Depends(deps.require_owner)):
        rl = deps.roadmap_lib()
        o = deps.load_repo_objekte_lib()
        existing = _load_stage_requests()
        pre_check = rl.find_stage_request(existing, request_id)
        if not pre_check or pre_check['object_id'] != object_id:
            raise HTTPException(404, "Запрос не найден")

        def _mutate(requests):
            decided = rl.decide_stage_request(requests, request_id, body.approve, str(user['id']))
            if not decided:
                raise HTTPException(400, "Запрос уже обработан")
            return decided

        decided = deps.update_json_transaction(rl.STAGE_REQUESTS_FILE, rl._default_requests, _mutate)

        if body.approve:
            try:
                if decided['kind'] == 'delete_stage':
                    o.delete_stage(decided['object_id'], decided['stage_row'])
                    o.sync_current_stage(decided['object_id'])
                elif decided['kind'] == 'change_status':
                    o.update_stage_status(decided['stage_row'], decided['payload']['new_status'], deps.business_today_str())
                    o.sync_current_stage(decided['object_id'])
            except ValueError as e:
                raise HTTPException(400, str(e))

        try:
            deps.send_telegram_message(
                int(decided['requested_by']),
                f"{'Одобрено' if body.approve else 'Отклонено'}: ваш запрос по этапу «{decided.get('stage_row')}»",
            )
        except Exception:
            pass
        return decided

    return router, SimpleNamespace(
        get_stages=get_stages,
        create_stage=create_stage,
        update_stage_description_endpoint=update_stage_description_endpoint,
        update_stage=update_stage,
        remove_stage=remove_stage,
        swap_stage=swap_stage,
        worker_complete_stage=worker_complete_stage,
        set_stage_blocker=set_stage_blocker,
        clear_stage_blocker=clear_stage_blocker,
        get_stage_roadmap=get_stage_roadmap,
        create_roadmap_category=create_roadmap_category,
        delete_roadmap_category=delete_roadmap_category,
        create_roadmap_item=create_roadmap_item,
        edit_roadmap_item=edit_roadmap_item,
        delete_roadmap_item=delete_roadmap_item,
        update_roadmap_item_status=update_roadmap_item_status,
        create_roadmap_note=create_roadmap_note,
        list_roadmap_notes=list_roadmap_notes,
        create_stage_request=create_stage_request,
        list_stage_requests=list_stage_requests,
        decide_stage_request_endpoint=decide_stage_request_endpoint,
    )
