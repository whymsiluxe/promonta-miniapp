"""22.09/23.09 hotfix — tests for backend/cleanup_legacy_critical_alert_duplicates.py,
the one-off migration that resolves the 196 legacy duplicate `birthday`
critical-alert records found in production.

23.09 (owner review, second pass): the script's grouping must be scoped
EXCLUSIVELY to the legacy bare-uid birthday shape --
kind == 'birthday' AND ref_id non-empty AND ref_id is the bare numeric worker
uid (matches backend/main.py's own _is_legacy_bare_uid_birthday_ref(), used
by the live ACK-time supersede logic). A blank ref_id, a non-birthday kind,
or a new idem-shaped birthday ref_id (birthday:<uid>:<year>:3days / :today)
must NEVER be grouped or touched, regardless of what key they might
otherwise appear to share. Only records that pass that filter are grouped by
kind + target_user_id + ref_id -- no title/subtitle/date heuristic.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import cleanup_legacy_critical_alert_duplicates as cleanup  # noqa: E402


def _alert(id_, kind='birthday', uid='1', ref_id='555', title='t', subtitle='',
           created_at=1000, acknowledged_at=None):
    return {
        'id': id_, 'kind': kind, 'target_user_id': uid, 'ref_id': ref_id,
        'title': title, 'subtitle': subtitle, 'created_at': created_at,
        'acknowledged_at': acknowledged_at, 'comment': None,
    }


def test_three_legacy_birthday_siblings_same_target_ref_leaves_one_pending():
    alerts = [
        _alert('a1', created_at=100),
        _alert('a2', created_at=300),
        _alert('a3', created_at=200),
    ]
    migrated, report = cleanup.migrate(alerts)

    by_id = {a['id']: a for a in migrated}
    assert by_id['a2']['acknowledged_at'] is None
    assert 'superseded_by' not in by_id['a2']
    assert by_id['a1']['acknowledged_at'] is not None
    assert by_id['a1']['superseded_by'] == 'a2'
    assert by_id['a3']['acknowledged_at'] is not None
    assert by_id['a3']['superseded_by'] == 'a2'

    assert report['total_records'] == 3
    assert report['superseded'] == 2
    assert report['groups_affected'] == 1


def test_different_worker_ref_id_stays_a_separate_group():
    alerts = [
        _alert('a1', uid='1', ref_id='555', created_at=100),
        _alert('a2', uid='1', ref_id='555', created_at=200),
        _alert('a3', uid='1', ref_id='666', created_at=150),
    ]
    migrated, report = cleanup.migrate(alerts)
    by_id = {a['id']: a for a in migrated}
    assert by_id['a3']['acknowledged_at'] is None
    assert 'superseded_by' not in by_id['a3']
    assert report['groups_affected'] == 1


def test_two_manual_non_birthday_alerts_same_target_blank_ref_id_are_both_untouched():
    alerts = [
        _alert('a1', kind='manual', ref_id='', created_at=100),
        _alert('a2', kind='manual', ref_id='', created_at=200),
    ]
    migrated, report = cleanup.migrate(alerts)
    assert all(a['acknowledged_at'] is None for a in migrated)
    assert all('superseded_by' not in a for a in migrated)
    assert report['superseded'] == 0
    assert report['groups_affected'] == 0


def test_two_birthday_alerts_with_blank_ref_id_are_both_untouched():
    # Not the legacy shape -- ref_id must be non-empty AND numeric.
    alerts = [
        _alert('a1', kind='birthday', ref_id='', created_at=100),
        _alert('a2', kind='birthday', ref_id='', created_at=200),
    ]
    migrated, report = cleanup.migrate(alerts)
    assert all(a['acknowledged_at'] is None for a in migrated)
    assert report['superseded'] == 0
    assert report['groups_affected'] == 0


def test_two_non_birthday_alerts_with_same_numeric_ref_id_are_both_untouched():
    # A numeric-looking ref_id on a non-birthday kind must never be treated
    # as the legacy shape -- kind == 'birthday' is a hard requirement.
    alerts = [
        _alert('a1', kind='plan_overdue', ref_id='555', created_at=100),
        _alert('a2', kind='plan_overdue', ref_id='555', created_at=200),
    ]
    migrated, report = cleanup.migrate(alerts)
    assert all(a['acknowledged_at'] is None for a in migrated)
    assert report['superseded'] == 0
    assert report['groups_affected'] == 0


def test_new_idem_shaped_birthday_ref_ids_are_untouched():
    idem_a = 'birthday:555:2027:3days'
    idem_b = 'birthday:555:2027:today'
    alerts = [
        _alert('a1', kind='birthday', ref_id=idem_a, created_at=100),
        _alert('a2', kind='birthday', ref_id=idem_b, created_at=200),
    ]
    migrated, report = cleanup.migrate(alerts)
    assert all(a['acknowledged_at'] is None for a in migrated)
    assert report['superseded'] == 0
    assert report['groups_affected'] == 0


def test_acknowledged_records_are_never_removed_even_if_duplicated():
    alerts = [
        _alert('a1', created_at=100, acknowledged_at=999),
        _alert('a2', created_at=200, acknowledged_at=999),
        _alert('a3', created_at=300),
    ]
    original_a1 = dict(alerts[0])
    original_a2 = dict(alerts[1])

    migrated, report = cleanup.migrate(alerts)

    by_id = {a['id']: a for a in migrated}
    assert by_id['a1'] == original_a1
    assert by_id['a2'] == original_a2
    assert 'superseded_by' not in by_id['a1']
    assert 'superseded_by' not in by_id['a2']
    assert by_id['a3']['acknowledged_at'] is None
    assert report['superseded'] == 0


def test_singleton_unacknowledged_legacy_records_are_never_touched():
    alerts = [_alert('a1'), _alert('a2', ref_id='different')]
    migrated, report = cleanup.migrate(alerts)
    assert all(a['acknowledged_at'] is None for a in migrated)
    assert report['superseded'] == 0
    assert report['groups_affected'] == 0


def test_no_record_is_ever_physically_removed_from_the_list():
    alerts = [
        _alert('a1', created_at=100), _alert('a2', created_at=200),
        _alert('a3', kind='manual', ref_id='', created_at=150),
        _alert('a4', kind='birthday', ref_id='birthday:9:2027:today', created_at=175),
    ]
    migrated, report = cleanup.migrate(alerts)
    assert len(migrated) == len(alerts)
    assert {a['id'] for a in migrated} == {'a1', 'a2', 'a3', 'a4'}
    assert report['total_records'] == 4


def test_dry_run_does_not_write_the_file(tmp_path, monkeypatch, capsys):
    alerts_file = tmp_path / 'critical_alerts.json'
    import json
    alerts = [_alert('a1', created_at=100), _alert('a2', created_at=200)]
    alerts_file.write_text(json.dumps(alerts), encoding='utf-8')
    monkeypatch.setattr(cleanup, 'CRITICAL_ALERTS_FILE', str(alerts_file))
    monkeypatch.setattr(sys, 'argv', ['cleanup_legacy_critical_alert_duplicates.py'])

    cleanup.main()

    out = capsys.readouterr().out
    assert 'Dry run' in out
    # File on disk must be byte-for-byte unchanged.
    assert json.loads(alerts_file.read_text(encoding='utf-8')) == alerts
    assert not list(tmp_path.glob('*.backup-*'))


def test_apply_writes_a_backup_and_the_migrated_file(tmp_path, monkeypatch, capsys):
    alerts_file = tmp_path / 'critical_alerts.json'
    import json
    alerts = [_alert('a1', created_at=100), _alert('a2', created_at=200), _alert('a3', ref_id='other')]
    alerts_file.write_text(json.dumps(alerts), encoding='utf-8')
    monkeypatch.setattr(cleanup, 'CRITICAL_ALERTS_FILE', str(alerts_file))
    monkeypatch.setattr(sys, 'argv', ['cleanup_legacy_critical_alert_duplicates.py', '--apply'])

    cleanup.main()

    backups = list(tmp_path.glob('*.backup-*'))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding='utf-8')) == alerts

    result = json.loads(alerts_file.read_text(encoding='utf-8'))
    assert {a['id'] for a in result} == {'a1', 'a2', 'a3'}
    by_id = {a['id']: a for a in result}
    assert by_id['a2']['acknowledged_at'] is None
    assert by_id['a1']['superseded_by'] == 'a2'
    assert by_id['a3']['acknowledged_at'] is None


def test_apply_with_nothing_to_migrate_does_not_write_a_backup(tmp_path, monkeypatch, capsys):
    alerts_file = tmp_path / 'critical_alerts.json'
    import json
    alerts = [_alert('a1'), _alert('a2', ref_id='other')]
    alerts_file.write_text(json.dumps(alerts), encoding='utf-8')
    monkeypatch.setattr(cleanup, 'CRITICAL_ALERTS_FILE', str(alerts_file))
    monkeypatch.setattr(sys, 'argv', ['cleanup_legacy_critical_alert_duplicates.py', '--apply'])

    cleanup.main()

    assert not list(tmp_path.glob('*.backup-*'))
    assert json.loads(alerts_file.read_text(encoding='utf-8')) == alerts


def test_is_legacy_bare_uid_birthday_ref_matches_main_pys_semantics():
    # Direct unit coverage of the predicate itself, mirroring
    # backend/main.py's _is_legacy_bare_uid_birthday_ref() test expectations.
    assert cleanup._is_legacy_bare_uid_birthday_ref(_alert('x', kind='birthday', ref_id='555')) is True
    assert cleanup._is_legacy_bare_uid_birthday_ref(_alert('x', kind='birthday', ref_id='')) is False
    assert cleanup._is_legacy_bare_uid_birthday_ref(_alert('x', kind='birthday', ref_id='birthday:5:2027:today')) is False
    assert cleanup._is_legacy_bare_uid_birthday_ref(_alert('x', kind='manual', ref_id='555')) is False
    assert cleanup._is_legacy_bare_uid_birthday_ref(_alert('x', kind='plan_overdue', ref_id='555')) is False
