"""Private AWS collector; scheduled execution never grants publication approval."""
import argparse
import concurrent.futures
import copy
import json
import os
import sqlite3
import sys
import uuid
from contextlib import closing
from pathlib import Path

import support_monitor as monitor
import export_support_public as public
from support_runtime import ingestion, periods, boards

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config/collector_sources.json'


def paths(state, output, sandbox=False):
    state, output = Path(state).resolve(), Path(output).resolve()
    if state == output or state in output.parents or output in state.parents:
        raise ValueError('private and public directories must be separate')
    for path in (state, output):
        if path == ROOT or ROOT in path.parents:
            if not sandbox or ROOT / 'work' not in path.parents:
                raise ValueError('runtime files must be outside the checkout; sandbox uses work/ only')
    if sandbox and any(ROOT / 'work' not in p.parents for p in (state, output)):
        raise ValueError('sandbox paths must be under work/')
    return state, output


def sources(config=CONFIG):
    data = json.loads(Path(config).read_text('utf8'))
    result = data['sources']
    if data.get('schema_version') != 1 or len({s['source_id'] for s in result}) != len(result):
        raise ValueError('invalid registry')
    if len({s['kind'] for s in result}) != len(result):
        raise ValueError('duplicate source kind')
    for s in result:
        if not isinstance(s['enabled'], bool) or s['method'] not in ('html', 'rss', 'bizinfo_api'):
            raise ValueError('invalid source settings')
        monitor.canonical_url(s['board_url'], s.get('official_hosts', s.get('allowed_hosts', [])))
    return result


def prepare_state(state):
    marker = state / 'runtime.json'
    if marker.exists() and not (state / 'monitor.sqlite3').is_file():
        raise ValueError('initialized DB is missing; restore a checked backup instead of creating an empty DB')
    if (state / 'monitor.sqlite3').exists() and not marker.exists():
        raise ValueError('existing DB requires explicit migration review; trial DB import forbidden')
    state.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        state.chmod(0o700)
    if not marker.exists():
        ingestion.atomic(marker, {'schema_version': 1, 'trial_imported': False})


def entries(connection, registry):
    by_id = {s['source_id']: s for s in registry}
    result = []
    for row in connection.execute('SELECT * FROM discovered_notices'):
        if row['source_id'] not in by_id:
            continue
        h = json.loads(row['hints_json'])
        result.append({'id': row['notice_id'], 'kind': by_id[row['source_id']]['kind'],
            'metadata': {'original_id': row['original_id'], 'title': row['title'],
                         'original_url': row['original_url'], 'published_at': row['published_at']},
            'facts': h.get('objective_facts', {}), 'checked_at': h.get('daily_checked_at'),
            'recruitment': h.get('recruitment_assessment', {}), 'status': 'partial'})
    return result


def backup(connection, state, run_id):
    folder = state / 'backups'
    folder.mkdir(exist_ok=True)
    target = folder / (run_id + '.sqlite3')
    with closing(sqlite3.connect(target)) as dest:
        connection.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('backup integrity check failed')
    if os.name != 'nt':
        target.chmod(0o600)
    return target


def collect(registry, saved, now):
    groups = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(ingestion.collect_source, s, saved, now, not saved): s
                for s in registry if s['enabled'] and s['method'] == 'html'}
        for job in concurrent.futures.as_completed(jobs):
            s = jobs[job]
            try:
                groups.append(job.result())
            except Exception as error:
                groups.append({'kind': s['kind'], 'analyses': [], 'errors': [{'error': type(error).__name__}]})
    for s in registry:
        if not s['enabled']:
            groups.append({'kind': s['kind'], 'skipped': True, 'analyses': [], 'errors': []})
        elif s['method'] != 'html':
            groups.append(ingestion.central(s, s['kind']))
    return groups


def export_public(state, output, rights_file, now=None):
    # No rights manifest means fail closed, not permission inferred from a URL.
    if rights_file.resolve() == output.resolve() or output.resolve() in rights_file.resolve().parents:
        raise ValueError('rights manifest must remain private')
    if output.exists() and any(p.name != 'support-public.json' for p in output.iterdir()):
        raise ValueError('public mount must contain only the approved feed')
    if not rights_file.exists() and (output / 'support-public.json').exists():
        previous_data = json.loads((output / 'support-public.json').read_text('utf8'))
        if previous_data.get('notices'):
            raise ValueError('rights manifest missing; preserve last public feed and require operator review')
    rights = json.loads(rights_file.read_text('utf-8-sig')) if rights_file.exists() else {}
    if not isinstance(rights, dict):
        raise ValueError('invalid publication rights manifest')
    with closing(monitor.connect(state, readonly=True)) as ro:
        ro.execute('BEGIN')
        data, stats = public.export(ro, rights, now)
    output.mkdir(parents=True, exist_ok=True)
    previous = output / 'support-public.json'
    if previous.exists():
        ingestion.atomic(state / 'backups' / ('public-' + uuid.uuid4().hex + '.json'), json.loads(previous.read_text('utf8')))
    ingestion.atomic(previous, data, mode=0o644)
    if os.name != 'nt':
        output.chmod(0o755)
        (output / 'support-public.json').chmod(0o644)
    return stats


def execute(state, output, rights_file, registry, groups=None, live=False, export_only=False, force=False, now=None):
    now = periods.as_of(now)
    prepare_state(state)
    ingestion.SOURCES.clear()
    ingestion.SOURCES.update({s['kind']: s for s in registry})
    run_id = now.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    with ingestion.lock(state / 'run.lock'):
        with closing(monitor.connect(state)) as db:
            monitor.register_sources(db, registry)
            previous = state / 'last-live.json'
            if live and not force and previous.exists() and periods.as_of(json.loads(previous.read_text('utf8'))['at']).date() == now.date():
                return {'status': 'skipped_interval', 'exit_code': 0}
            backup(db, state, run_id)
            saved = entries(db, registry)
            if not export_only and groups is None:
                if not live:
                    raise ValueError('explicit --live required')
                groups = collect(registry, saved, now)
            counts = {k: 0 for k in ('new', 'same', 'changed', 'enriched', 'metadata_conflict')}
            reports = []
            by_url = {ingestion.identity(e['metadata']['original_url']): e for e in saved}
            for group in groups or []:
                source = ingestion.SOURCES[group['kind']]
                if not source['enabled']:
                    reports.append({'source_id': source['source_id'], 'status': 'disabled', 'counts': {}})
                    continue
                errors = [e.get('error', 'source_failed') for e in group.get('errors', [])]
                local_counts = dict.fromkeys(counts, 0)
                old_success = db.execute('SELECT last_success_at FROM monitor_sources WHERE source_id=?', (source['source_id'],)).fetchone()[0]
                for item in group.get('analyses', []):
                    item = copy.deepcopy(item)
                    old = by_url.get(ingestion.identity(item['metadata']['original_url']))
                    if old:
                        item['id'] = old['id']
                        item['metadata']['original_id'] = old['metadata']['original_id']
                        if item.get('status') == 'failed' or not item.get('detail_fetched'):
                            retained = copy.deepcopy(old)
                            retained['metadata'].update(item['metadata'])
                            if item.get('status') == 'failed':
                                errors.append('detail_failed')
                            item = retained
                        else:
                            item['facts'] = {**old.get('facts', {}), **item.get('facts', {})}
                    elif item.get('status') == 'failed':
                        errors.append('detail_failed')
                    item['recruitment'] = periods.assess(item.get('facts', {}), item.get('period_parse'), now, item.get('checked_at'))
                    try:
                        result = ingestion.save(db, item)
                        counts[result['action']] += 1
                        local_counts[result['action']] += 1
                        if result.get('condition_error'):
                            errors.append(result['condition_error'])
                        by_url[ingestion.identity(item['metadata']['original_url'])] = item
                    except Exception as error:
                        errors.append(type(error).__name__)
                stamp = old_success if errors else now.isoformat()
                with db:
                    db.execute('UPDATE monitor_sources SET last_attempt_at=?,last_success_at=?,last_error=? WHERE source_id=?',
                               (now.isoformat(), stamp, 'source_failed' if errors else None, source['source_id']))
                # Never log exception bodies, authenticated URLs, raw HTML or credentials.
                reports.append({'source_id': source['source_id'], 'status': 'failed' if errors else 'completed',
                    'list_count': group.get('list_count', 0), 'candidate_count': group.get('candidate_count', 0),
                    'counts': local_counts, 'errors': [str(e).split(':')[0][:70] for e in errors], 'last_success_at': stamp})
            stats = export_public(state, output, rights_file, now)
            failed = any(r['status'] == 'failed' for r in reports)
            result = {'status': 'partial_failure' if failed else 'completed', 'exit_code': 1 if failed else 0,
                'run_id': run_id, 'counts': counts, 'sources': reports, 'publication': stats,
                'automatic_approval': False, 'schedule_enabled': False, 'live': live}
            ingestion.atomic(state / 'logs' / (run_id + '.json'), result)
            ingestion.atomic(state / 'latest-run.json', result)
            if live:
                ingestion.atomic(previous, {'at': now.isoformat()})
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path(os.environ.get('MUNONGSA_STATE_DIR', '/var/lib/munongsa')))
    parser.add_argument('--public-dir', type=Path, default=Path(os.environ.get('MUNONGSA_PUBLIC_DIR', '/var/lib/munongsa-public')))
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--rights-file', type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--export-only', action='store_true')
    parser.add_argument('--sandbox', action='store_true')
    parser.add_argument('--replay-capture', type=Path)
    args = parser.parse_args()
    try:
        state, output = paths(args.state_dir, args.public_dir, args.sandbox)
        if args.replay_capture and (not args.sandbox or args.live or args.export_only):
            raise ValueError('recorded responses are allowed only in isolated offline tests')
        groups = json.loads(args.replay_capture.read_text('utf8'))['groups'] if args.replay_capture else None
        if not (args.live or args.export_only or args.replay_capture):
            raise ValueError('choose --live or --export-only')
        if os.name != 'nt':
            os.umask(0o077)
        result = execute(state, output, args.rights_file or state / 'publication-rights.json',
                         sources(args.config), groups, args.live, args.export_only, args.force)
    except Exception as error:
        result = {'status': 'already_running' if str(error) == 'already_running' else 'failed',
                  'exit_code': 3 if str(error) == 'already_running' else 2, 'error': type(error).__name__}
    print(json.dumps(result, ensure_ascii=False))
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
