"""22.09 hotfix — tests for backend/cleanup_legacy_critical_alert_duplicates.py,
the one-off migration that resolves the 196 legacy duplicate `birthday`
critical-alert records found in production. Grouping key: kind +
target_user_id + ref_id -- the SAME key _create_critical_alert() already uses
for its own live dedup (see that function's docstring), not a title/date-text
heuristic (owner explicitly rejected that as fragile -- whitespace/emoji/
locale drift could silently break it).

Non-destructive: nothing is ever deleted. One canonical PENDING record is
kept per duplicate group (the most recent by created_at); every other
unacknowledged record in the group is marked acknowledged_at + superseded_by
in place, so it stops showing in the pending-alerts popup but its full
history (title, timestamps, id) survives untouched.
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


def test_keeps_the_most_recent_record_as_canonical_and_supersedes_the_rest():
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

    # Nothing removed -- all 3 ids still present.
    assert {a['id'] for a in migrated} == {'a1', 'a2', 'a3'}

    assert report['total_records'] == 3
    assert report['superseded'] == 2
    assert report['groups_affected'] == 1


def test_grouping_key_is_kind_target_user_id_ref_id_not_title():
    # This is the exact legacy shape: two DIFFERENT titles ("3 days before" /
    # "the day of") sharing the same ref_id=uid -- by design, per the owner's
    # explicit correction, these DO fall into one group under this key. The
    # migration doesn't try to reconstruct which was which; it just keeps one
    # canonical pending record.
    alerts = [
        _alert('a1', ref_id='555', title='Через 3 дня день рождения у Иван', created_at=100),
        _alert('a2', ref_id='555', title='Сегодня день рождения у Иван', created_at=200),
    ]
    migrated, report = cleanup.migrate(alerts)
    assert report['groups_affected'] == 1
    by_id = {a['id']: a for a in migrated}
    assert by_id['a2']['acknowledged_at'] is None  # most recent kept pending
    assert by_id['a1']['superseded_by'] == 'a2'


def test_title_or_subtitle_differences_do_not_create_separate_groups():
    # Explicitly the opposite of a title-heuristic grouping key.
    alerts = [
        _alert('a1', title='completely different text A', created_at=100),
        _alert('a2', title='completely different text B', created_at=200),
    ]
    migrated, report = cleanup.migrate(alerts)
    assert report['groups_affected'] == 1
    assert report['superseded'] == 1


def test_already_acknowledged_records_are_never_touched():
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
    # The lone unacked record has no unacked sibling -- not touched either.
    assert by_id['a3']['acknowledged_at'] is None
    assert report['superseded'] == 0


def test_singleton_unacknowledged_records_are_never_touched():
    alerts = [_alert('a1'), _alert('a2', ref_id='different')]
    migrated, report = cleanup.migrate(alerts)
    assert all(a['acknowledged_at'] is None for a in migrated)
    assert report['superseded'] == 0
    assert report['groups_affected'] == 0


def test_different_target_users_are_never_merged():
    alerts = [_alert('a1', uid='111'), _alert('a2', uid='222')]
    migrated, report = cleanup.migrate(alerts)
    assert all(a['acknowledged_at'] is None for a in migrated)
    assert report['superseded'] == 0


def test_no_record_is_ever_removed_from_the_list():
    alerts = [_alert('a1', created_at=100), _alert('a2', created_at=200), _alert('a3', ref_id='other')]
    migrated, report = cleanup.migrate(alerts)
    assert len(migrated) == len(alerts)
    assert report['total_records'] == 3


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
