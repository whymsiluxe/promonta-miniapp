"""Regression coverage for the DailyPlan router extraction."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402
from conftest import iter_app_routes  # noqa: E402


DAILY_PLAN_ROUTE_KEYS = {
    ('GET', '/api/daily-plan/today'),
    ('POST', '/api/daily-plan/{plan_id}/accept'),
    ('POST', '/api/daily-plan/{plan_id}/amendments/{amendment_id}/accept'),
    ('POST', '/api/daily-plan/{plan_id}/blocker'),
    ('GET', '/api/daily-plan/owner/today'),
    ('GET', '/api/daily-plan/object/{object_id}'),
    ('POST', '/api/daily-plan'),
    ('GET', '/api/daily-plan/{plan_id}'),
    ('GET', '/api/productivity/workers/{target_user_id}'),
    ('POST', '/api/productivity/workers/{target_user_id}/baseline'),
    ('GET', '/api/daily-plan/owner/matrix'),
    ('POST', '/api/daily-plan/replan/{object_id}'),
}


def _route_rows():
    for route in iter_app_routes(backend.app):
        for method in sorted(getattr(route, 'methods', []) or []):
            if method in {'GET', 'POST', 'PATCH', 'DELETE'}:
                yield method, getattr(route, 'path', ''), route


def test_daily_plan_domain_routes_are_registered_once_and_owned_by_routes_module():
    rows = list(_route_rows())
    keys = [(method, path) for method, path, _ in rows]

    for key in DAILY_PLAN_ROUTE_KEYS:
        assert keys.count(key) == 1, key
        route = next(route for method, path, route in rows if (method, path) == key)
        assert route.endpoint.__module__.endswith('routes.daily_plan')


def test_no_duplicate_routes_anywhere_in_the_app():
    rows = list(_route_rows())
    keys = [(method, path) for method, path, _ in rows]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    assert duplicates == []


def test_daily_plan_router_has_no_main_import():
    src = Path(backend.BACKEND_DIR, 'routes', 'daily_plan.py').read_text()
    assert 'import main' not in src
    assert 'from main import' not in src


def test_main_reexports_legacy_daily_plan_handlers_from_router():
    assert backend.daily_plan_today.__module__.endswith('routes.daily_plan')
    assert backend.daily_plan_report_blocker.__module__.endswith('routes.daily_plan')
    assert backend.daily_plan_owner_matrix.__module__.endswith('routes.daily_plan')
    assert backend.get_worker_productivity_api.__module__.endswith('routes.daily_plan')
    assert backend.set_worker_baseline.__module__.endswith('routes.daily_plan')


def test_auth_and_objects_and_stages_routes_are_untouched():
    rows = list(_route_rows())
    by_key = {(m, p): r for m, p, r in rows}
    assert by_key[('GET', '/api/roles')].endpoint.__module__.endswith('routes.auth')
    assert by_key[('GET', '/api/objects')].endpoint.__module__.endswith('routes.objects')
