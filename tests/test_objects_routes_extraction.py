"""Regression coverage for the objects router extraction."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402


OBJECT_ROUTE_KEYS = {
    ('GET', '/api/objects'),
    ('POST', '/api/objects'),
    ('GET', '/api/my-assignments'),
    ('GET', '/api/assignment-candidates'),
    ('GET', '/api/objects/{object_id}/history'),
    ('POST', '/api/objects/{object_id}/assign'),
    ('DELETE', '/api/objects/{object_id}/assign/{user_id}'),
    ('PATCH', '/api/objects/{object_id}/assignments/{assignment_id}'),
    ('DELETE', '/api/objects/{object_id}/assignments/{assignment_id}'),
    ('POST', '/api/objects/{object_id}/assign/{user_id}/respond'),
    ('POST', '/api/objects/{object_id}/assignments/batch'),
    ('GET', '/api/objects/{object_id}/description'),
    ('PATCH', '/api/objects/{object_id}/description'),
    ('GET', '/api/objects/{object_id}/info-items'),
    ('POST', '/api/objects/{object_id}/info-items'),
    ('DELETE', '/api/objects/{object_id}/info-items/{item_id}'),
    ('PATCH', '/api/objects/{object_id}/status'),
}


def _route_rows():
    for route in backend.app.routes:
        for method in sorted(getattr(route, 'methods', []) or []):
            if method in {'GET', 'POST', 'PATCH', 'DELETE'}:
                yield method, getattr(route, 'path', ''), route


def test_objects_domain_routes_are_flat_and_owned_by_routes_module():
    rows = list(_route_rows())
    keys = [(method, path) for method, path, _ in rows]

    assert not [route for route in backend.app.routes if not hasattr(route, 'path')]
    for key in OBJECT_ROUTE_KEYS:
        assert keys.count(key) == 1, key
        route = next(route for method, path, route in rows if (method, path) == key)
        assert route.endpoint.__module__.endswith('routes.objects')


def test_objects_router_has_no_main_import():
    src = Path(backend.BACKEND_DIR, 'routes', 'objects.py').read_text()
    assert 'import main' not in src
    assert 'from main import' not in src


def test_main_reexports_legacy_object_handlers_from_router():
    assert backend.list_objects.__module__.endswith('routes.objects')
    assert backend.assign_user.__module__.endswith('routes.objects')
    assert backend.create_object_endpoint.__module__.endswith('routes.objects')
