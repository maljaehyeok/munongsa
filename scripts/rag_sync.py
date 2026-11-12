"""Private approval/export -> validated RAG generations. No DB writes or network.

The input DB, rights, details and served feed must be operator-controlled. Hashes
detect corruption; they do not authenticate files writable by an attacker.
"""
import argparse
from contextlib import contextmanager, closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time
import uuid

import export_support_public as public_export
import support_monitor as monitor
import rag_search as search

SCHEMA = 'munongsa-approved-rag-generation-v1'
MAX_LEASE = 300
MAX_FILE = 16 * 1024 * 1024
PUBLICATIONS = ('approved', 'approved_reference')
PUBLISH_GID = None


class SyncError(ValueError):
    pass


def stamp(value):
    return search.record_sha(value)


def now_utc():
    return datetime.now(timezone.utc)


def instant(value, now):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed > now:
        raise SyncError('invalid_check_time')
    return parsed


def read(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > MAX_FILE:
        raise SyncError('unsafe_or_oversized_private_input')
    return json.loads(path.read_text(encoding='utf-8'))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if PUBLISH_GID is not None:
        os.chown(path.parent, -1, PUBLISH_GID); path.parent.chmod(0o750)
    tmp = path.with_name('.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('xb') as stream:
            if PUBLISH_GID is not None:
                os.chown(tmp, -1, PUBLISH_GID)
            os.chmod(tmp, 0o640 if PUBLISH_GID is not None else 0o600)
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = directory / '.refresh.lock'
    stream = lock.open('a+b')
    acquired = False
    try:
        if not lock.stat().st_size:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise FileExistsError('refresh_already_running') from exc
        acquired = True
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()  # Kernel releases the lock on a crash too; keep the inode.


def block(directory):
    if Path(directory).resolve().is_relative_to(search.ROOT.resolve()):
        raise SyncError('private_output_must_be_outside_source_checkout')
    atomic(Path(directory)/'authority.json', {'schema': SCHEMA, 'state': 'blocked'})


def suspend(directory, notice_ids=None):
    """Before a mutation, fence only known affected IDs; None is a global fence.

    The returned ticket must be completed AFTER commit/public promotion. A timer
    cannot clear a pending ticket merely because it read an older DB snapshot.
    """
    with locked(Path(directory)):
        path = Path(directory)/'authority.json'
        gate = read(path) if path.exists() else {'schema':SCHEMA,'state':'blocked','allowed':{}}
        identities = None if notice_ids is None else sorted(set(notice_ids))
        if identities is not None and (not identities or not all(isinstance(i,str) and i for i in identities)):
            raise SyncError('affected_notice_ids_required')
        ticket = uuid.uuid4().hex
        gate.setdefault('fences', {})[ticket] = identities
        atomic(path, gate)
        return ticket


def configure_reader_group(directory, name):
    """Optional Linux-only publisher group; API gets read/execute, never write."""
    global PUBLISH_GID
    if os.name == 'nt' or not re.fullmatch('[a-z_][a-z0-9_-]{0,30}', name):
        raise SyncError('linux_reader_group_required')
    import grp
    PUBLISH_GID = grp.getgrnam(name).gr_gid
    directory = Path(directory).resolve()
    if directory.is_relative_to(search.ROOT.resolve()):
        raise SyncError('private_output_must_be_outside_source_checkout')
    for path in (directory, directory/'releases'):
        path.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chown(path, -1, PUBLISH_GID); path.chmod(0o750)


def readable_stage(stage):
    if PUBLISH_GID is None:
        return
    for path in [stage, *stage.rglob('*')]:
        if path.is_symlink():
            raise SyncError('symlink_in_generation')
        os.chown(path, -1, PUBLISH_GID)
        path.chmod(0o750 if path.is_dir() else 0o640)


@contextmanager
def change(config, notice_ids=None):
    """Caller owns the authorized mutation AND public promotion; never auto-approves.

    No RAG/DB lock is held while the caller runs. An exception leaves the scoped
    fence pending so an unrelated timer cannot mistake a rollback for completion.
    """
    if config.get('reader_group'):
        configure_reader_group(config['sync_dir'], config['reader_group'])
    ticket = suspend(config['sync_dir'], notice_ids)
    yield ticket
    refresh(*(config[k] for k in ('state_dir','rights_file','served_feed','details_file','sync_dir')),
            legacy_root=config.get('legacy_root'), complete_change=[ticket])


def material(item):
    # This field is derived from the clock at export; dates still remain pinned.
    return stamp({k: v for k, v in item.items() if k != 'application_status'})


def unique(items):
    """Reject every member of duplicate ID/official URL/program-round groups."""
    if not isinstance(items, list):
        raise SyncError('notice_list_required')
    counts, bad, valid = {}, set(), []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id']:
            continue
        if not isinstance(item.get('url'), str) or not item['url']:
            bad.add(item['id']); continue
        valid.append(item)
        keys = [('id', item['id']), ('url', item['url'])]
        if item.get('program_id') and item.get('round_id'):
            keys.append(('round', item['program_id'], item['round_id']))
        for key in keys:
            counts[key] = counts.get(key, 0) + 1
    return {i['id']: i for i in valid if i['id'] not in bad and counts[('id', i['id'])] == counts[('url', i['url'])] == 1
            and (not (i.get('program_id') and i.get('round_id'))
                 or counts[('round', i['program_id'], i['round_id'])] == 1)}


def approval_version(db, item):
    record = monitor.notice_record(db, item['id'])
    event = db.execute('SELECT * FROM review_events WHERE notice_id=? AND action=? ORDER BY event_id DESC LIMIT 1',
                       (item['id'], 'publication')).fetchone()
    if not event or not event['actor'] or not event['reason']:
        raise SyncError('approval_audit_missing')
    approved = json.loads(event['after_json'])
    keys = ('content_hash', 'publication', 'approved_at', 'approved_by', 'reviewer', 'reviewed_at',
            'target', 'region', 'support', 'field_evidence', 'verified_application_period',
            'conditions_verified', 'application_period_verified')
    if record['publication'] not in PUBLICATIONS or any(record.get(k) != approved.get(k) for k in keys):
        raise SyncError('approval_revision_mismatch')
    return {'approval_version': stamp({'event_id': event['event_id'],
            'after': approved, 'content_hash': record['content_hash']}),
            'content_hash': record['content_hash'], 'approved_at': record['approved_at']}


def minimal_summary(item, binding, now):
    """Exact reviewed export facts only. No new qualifications or numeric inference."""
    for name in ('target', 'region', 'support'):
        if item.get(name) in (None, '', 'unknown') or not item['evidence'].get(name):
            raise SyncError('basic_official_evidence_missing')
        if not search.valid_url(item['evidence'][name]['url']) or not item['evidence'][name].get('location'):
            raise SyncError('basic_official_evidence_missing')
    checked = item['last_checked_at']
    instant(checked, now)
    if any(c.get('status') == 'verified' for c in item.get('eligibility', {}).get('conditions', [])):
        # Do not drop a structured required/exclusion condition when making a short summary.
        raise SyncError('structured_conditions_need_reviewed_detailed_summary')
    def field(value, name):
        proof = item['evidence'][name]
        return {'value': value, 'evidence': {**proof, 'checked_at': checked}}
    return {'basis': search.basis(item), 'rights': {'facts_only': True},
            'approval': {'state': 'approved', 'reviewer': 'existing-publication-approval',
                         'reference': 'publication-version:' + binding['approval_version'], 'checked_at': checked},
            'authority_content_hash': binding['content_hash'],
            'fields': {'summary': field(item['support'], 'support'),
                       'conditions': field(['신청 대상: ' + item['target'], '지원 지역: ' + item['region']], 'target'),
                       'unconfirmed': {'value': ['공개 승인된 기본 정보만 안내합니다. 전체 세부 자격·제외 조건·필요 서류와 실제 접수 가능 여부는 별도 확인이 필요합니다.'],
                           'evidence': {'url': item['url'], 'location': '공개 승인 범위 점검 · 전체 세부 자격을 검증했다는 뜻이 아님', 'checked_at': checked}}}}


def validate_record(record, item, now):
    if record.get('basis') != search.basis(item):
        raise SyncError('detailed_basis_changed')
    approval = record.get('approval', {})
    if (approval.get('state') != 'approved' or not approval.get('reviewer') or not approval.get('reference')
            or record.get('rights', {}).get('facts_only') is not True):
        raise SyncError('detailed_review_required')
    instant(approval['checked_at'], now)
    if not {'conditions', 'unconfirmed'} <= record['fields'].keys():
        raise SyncError('conditions_and_unknown_scope_required')
    for key, value in record['fields'].items():
        if key == 'unconfirmed':
            if not isinstance(value['value'], list) or not all(isinstance(v, str) for v in value['value']):
                raise SyncError('invalid_unknown_conditions')
        if key not in search.LABELS and key != 'unconfirmed':
            continue
        evidence = value['evidence']
        if not search.valid_url(evidence['url']) or not evidence.get('location'):
            raise SyncError('official_evidence_missing')
        instant(evidence['checked_at'], now)
    search.summary_chunks('validation', {'id': item['id'], 'record_sha': stamp(record)}, record, item)


def collect(db, rights, served, details, now, previous=None, legacy=None):
    """Read a single DB snapshot; both DB export and currently served feed must agree."""
    exported, _ = public_export.export(db, rights, now)
    if served.get('schema_version') != public_export.SCHEMA_VERSION:
        raise SyncError('served_feed_schema')
    if details.get('schema') != 'munongsa-support-details-v1' or details.get('preview') is not False:
        raise SyncError('details_schema')
    live, allowed = unique(served['notices']), unique(exported['notices'])
    previous = previous or {}
    baseline = {v['id']: (k, v) for k, v in {**search.SPECS, **search.EXPANDED_SPECS}.items()}
    aliases = {**search.ALIASES, **search.EXTRA_ALIASES}
    result = {'items': [], 'records': [], 'specs': {}, 'aliases': {}, 'bindings': {}, 'raw': {}, 'omitted': []}
    legacy_docs = search.load_corpus(root=legacy, expanded=True) if legacy else None
    for identity, item in sorted(allowed.items()):
        try:
            if identity not in live or material(item) != material(live[identity]):
                raise SyncError('not_currently_public_or_feed_outdated')
            binding = {**approval_version(db, item), 'material_sha': material(item)}
            instant(binding['approved_at'], now)
            if not search.valid_url(item['url']):
                raise SyncError('official_host_requires_manual_review')
            public_export.checked_url(item['url'])
            matches = [r for r in details['records'] if isinstance(r,dict) and isinstance(r.get('basis'),dict) and r['basis'].get('id') == identity]
            if len(matches) > 1:
                raise SyncError('duplicate_detail_records')
            if matches:
                record = matches[0]
                prior = previous.get(identity)
                # Changed source content cannot inherit an old detailed explanation.
                pinned = identity in baseline and stamp(record) == baseline[identity][1]['record_sha']
                baseline_item = (legacy_docs or {}).get('documents', {}).get(baseline.get(identity, ('',))[0], {}).get('public')
                imported = pinned and baseline_item is not None and material(baseline_item) == material(item)
                reviewed_content = record.get('authority_content_hash') == binding['content_hash']
                unchanged_content = prior and prior['content_hash'] == binding['content_hash'] and prior['record_sha'] == stamp(record)
                if not (imported or reviewed_content or unchanged_content):
                    raise SyncError('detailed_content_binding_review_required')
            else:
                # Never silently replace a previously reviewed detailed record with fewer conditions.
                if identity in previous and previous[identity].get('detailed'):
                    raise SyncError('previous_detailed_evidence_missing')
                if identity in baseline:
                    raise SyncError('baseline_detailed_evidence_missing')
                record = minimal_summary(item, binding, now)
            validate_record(record, item, now)
            key = baseline[identity][0] if identity in baseline else 'notice_' + search.sha(identity.encode())[:16]
            spec = {'id': identity, 'record_sha': stamp(record), 'original_sha': stamp(record), 'summary_only': True}
            # Only already reviewed passage plans are reused. New raw excerpts need human review.
            if identity in baseline and 'passages' in baseline[identity][1] and stamp(record) == baseline[identity][1]['record_sha']:
                if not legacy_docs or key not in legacy_docs['documents']:
                    raise SyncError('reviewed_raw_files_required')
                spec = baseline[identity][1].copy()
                for name in (spec['original'], spec['text']):
                    result['raw'][(search.SOURCE_DIR/name).as_posix()] = legacy/search.SOURCE_DIR/name
            spec['title'] = item['title']
            binding.update(record_sha=stamp(record), detailed=bool(matches))
            result['items'].append(item); result['records'].append(record)
            result['specs'][key] = spec
            result['aliases'][key] = list(aliases.get(key, ())) + [item['title']]
            result['bindings'][identity] = binding
        except (KeyError, ValueError, TypeError, OSError, monitor.MonitorError) as exc:
            result['omitted'].append({'id': identity, 'reason': str(exc) if isinstance(exc, SyncError) else 'invalid_evidence'})
    return result


def safe_file(root, name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise SyncError('unsafe_generation_path')
    dest = root/path
    if not dest.resolve().is_relative_to(root.resolve()) or any(p.is_symlink() for p in [dest, *dest.parents] if p != root.parent):
        raise SyncError('unsafe_generation_path')
    return dest


def current_manifest(directory, pointer=None):
    pointer = read(directory/'current.json') if pointer is None else pointer
    identity = pointer['generation']
    if not re.fullmatch('[a-f0-9]{32}', identity):
        raise SyncError('invalid_generation_pointer')
    root = safe_file(directory, 'releases/' + identity)
    path = root/'manifest.json'
    if search.sha(path.read_bytes()) != pointer['manifest_sha']:
        raise SyncError('manifest_hash_mismatch')
    manifest = read(path)
    if manifest.get('schema') != SCHEMA:
        raise SyncError('generation_schema')
    return root, manifest


def refresh(state_dir, rights_file, served_feed, details_file, directory, *, legacy_root=None, now=None, complete_change=()):
    """Local explicit refresh. DB is opened readonly; public feed is never changed."""
    now = now or now_utc(); directory = Path(directory).resolve()
    legacy_root = Path(legacy_root).resolve() if legacy_root else None
    with locked(directory):
        if directory.is_relative_to(search.ROOT.resolve()):
            raise SyncError('private_output_must_be_outside_source_checkout')
        prior_gate = read(directory/'authority.json') if (directory/'authority.json').exists() else {}
        fences = dict(prior_gate.get('fences', {}))
        if prior_gate.get('state') == 'blocked' and not fences:
            raise SyncError('legacy_block_requires_operator_review')
        if any(ticket not in fences for ticket in complete_change):
            raise SyncError('unknown_change_ticket')
        previous = {}
        old = None
        if (directory/'current.json').exists():
            old_root, old = current_manifest(directory)
            previous = old['bindings']
        # Read inputs before opening the DB snapshot. No staging work holds a DB lock.
        rights, served, details = read(rights_file), read(served_feed), read(details_file)
        with closing(monitor.connect(state_dir, readonly=True)) as db:
            db.execute('PRAGMA busy_timeout=250')
            deadline = time.monotonic() + 2
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            db.execute('BEGIN')
            bundle = collect(db, rights, served, details, now,
                             previous=previous, legacy=legacy_root)
        # Authority is independent of evidence construction. On a later build failure,
        # unchanged old bindings remain freshly verified; changed/withdrawn ones cannot match.
        gate = {'schema':SCHEMA, 'state':'ready', 'created_at':now.isoformat(),
                'expires_at':(now+timedelta(seconds=MAX_LEASE)).isoformat(),
                'served_feed':str(Path(served_feed).resolve()), 'allowed':bundle['bindings'], 'fences':fences}
        atomic(directory/'authority.json', gate)
        generation = uuid.uuid4().hex
        stage = directory/'releases'/('.stage-' + generation)
        stage.mkdir(parents=True, mode=0o700)
        files = {search.DETAILS.as_posix(): {'schema': 'munongsa-support-details-v1', 'preview': False, 'records': bundle['records']},
                 search.CURRENT_SNAPSHOT.as_posix(): {'schema_version': public_export.SCHEMA_VERSION,
                    'generated_at': max((i['last_checked_at'] for i in bundle['items']), default='1970-01-01T00:00:00+00:00'), 'notices': bundle['items']}}
        for name, value in files.items():
            atomic(safe_file(stage, name), value)
        for name, source in bundle['raw'].items():
            dest = safe_file(stage, name); dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(source, dest); dest.chmod(0o600)
        corpus = search.load_corpus(root=stage, expanded=True, specs_override=bundle['specs'], aliases_override=bundle['aliases'])
        if corpus['excluded'] or len(corpus['documents']) != len(bundle['bindings']):
            raise SyncError('staged_corpus_verification_failed')
        manifest = {'schema': SCHEMA, 'generated_at': now.isoformat(), 'mode': 'local-only',
                    'specs': bundle['specs'], 'aliases': bundle['aliases'], 'bindings': bundle['bindings'],
                    'files': {p.relative_to(stage).as_posix(): search.sha(p.read_bytes()) for p in stage.rglob('*') if p.is_file()}}
        # Passage plans contain Python tuples; persisted JSON contains lists.
        # Compare the stored representation so unchanged raw evidence is reused.
        manifest = json.loads(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        gate['fences'] = {k:v for k,v in fences.items() if k not in complete_change}
        if old and all(old[k] == manifest[k] for k in ('specs','aliases','bindings','files')) and all(
                search.sha(safe_file(old_root,n).read_bytes()) == h for n,h in old['files'].items()):
            # Delete ONLY this newly-created staging directory, never prior releases/backups.
            if stage.is_symlink() or stage.resolve().parent != (directory/'releases').resolve() or not stage.name.startswith('.stage-'):
                raise SyncError('unsafe_temporary_cleanup')
            shutil.rmtree(stage)
            atomic(directory/'authority.json', gate)
            return {'documents':len(corpus['documents']), 'passages':len(corpus['chunks']),
                    'omitted':bundle['omitted'], 'generation':old_root.name, 'mode':'local-only', 'reused':True}
        atomic(stage/'manifest.json', manifest)
        readable_stage(stage)
        final = directory/'releases'/generation
        os.replace(stage, final)
        # Keep every previous immutable release; changing authority never restores withdrawn evidence.
        if (directory/'current.json').exists():
            atomic(directory/'history'/(generation + '.json'), read(directory/'current.json'))
        atomic(directory/'current.json', {'generation': generation, 'manifest_sha': search.sha((final/'manifest.json').read_bytes())})
        atomic(directory/'authority.json', gate)
        return {'documents': len(corpus['documents']), 'passages': len(corpus['chunks']),
                'omitted': bundle['omitted'], 'generation': generation, 'mode': 'local-only'}


def load(directory, *, now=None, pointer=None):
    """Every request rechecks gate, served feed, generation and every evidence hash."""
    directory = Path(directory).resolve(); now = now or now_utc()
    gate = read(directory/'authority.json')
    if gate.get('schema') != SCHEMA or gate.get('state') != 'ready':
        raise SyncError('refresh_blocked')
    if any(value is None for value in gate.get('fences', {}).values()):
        raise SyncError('change_in_progress')
    denied = {identity for ids in gate.get('fences', {}).values() for identity in ids}
    created, expiry = datetime.fromisoformat(gate['created_at']), datetime.fromisoformat(gate['expires_at'])
    if created.tzinfo is None or expiry.tzinfo is None or not created <= now < expiry or not 0 < (expiry-created).total_seconds() <= MAX_LEASE:
        raise SyncError('authority_lease_expired')
    root, manifest = current_manifest(directory, pointer)
    shared = {search.DETAILS.as_posix(), search.CURRENT_SNAPSHOT.as_posix()}
    damaged = set()
    for name, expected in manifest['files'].items():
        path = safe_file(root, name)
        if name in shared:
            read(path)  # Per-record pins below isolate a changed JSON record safely.
        elif not path.is_file() or path.stat().st_size > MAX_FILE or search.sha(path.read_bytes()) != expected:
            damaged.add(name)
    feed = read(gate['served_feed'])
    if feed.get('schema_version') != public_export.SCHEMA_VERSION:
        raise SyncError('served_feed_schema')
    live = unique(feed['notices'])
    stored = unique(read(root/search.CURRENT_SNAPSHOT)['notices'])
    eligible = {i for i, binding in manifest['bindings'].items() if gate['allowed'].get(i) == binding
                and i not in denied and i in live and i in stored
                and material(live[i]) == material(stored[i]) == binding['material_sha']}
    specs = {k: s for k, s in manifest['specs'].items() if s['id'] in eligible}
    specs = {k:s for k,s in specs.items() if not any((search.SOURCE_DIR/s[n]).as_posix() in damaged
             for n in ('original','text') if n in s)}
    corpus = search.load_corpus(root=root, expanded=True, specs_override=specs, aliases_override=manifest['aliases'])
    # Keep aliases/scopes of removed notices so their names cannot select another business.
    corpus['specs'] = manifest['specs']
    corpus['sync_generation'] = root.name
    corpus['sync_verified'] = True
    corpus['unavailable_ids'] = sorted(set(manifest['bindings']) - {d['public']['id'] for d in corpus['documents'].values()})
    return corpus


def rollback(directory, history_key, *, now=None):
    """Select a preserved generation only through CURRENT authority; never restore a gate."""
    directory = Path(directory).resolve()
    if not re.fullmatch('[a-f0-9]{32}', history_key):
        raise SyncError('invalid_history_key')
    with locked(directory):
        pointer = read(directory/'history'/(history_key+'.json'))
        corpus = load(directory, now=now, pointer=pointer)
        # Partial revocations remain excluded; a damaged eligible record is not a good backup.
        if corpus['excluded']:
            raise SyncError('rollback_evidence_invalid')
        atomic(directory/'current.json', pointer)
        return {'generation':pointer['generation'],'documents':len(corpus['documents']), 'mode':'local-only'}


def main():
    parser = argparse.ArgumentParser(description='Local private RAG refresh; no approval, publication or AWS changes')
    parser.add_argument('action', choices=('suspend', 'refresh', 'rollback'))
    parser.add_argument('--sync-dir', type=Path, required=True)
    for name in ('state-dir','rights-file','served-feed','details-file','legacy-root'):
        parser.add_argument('--'+name, type=Path)
    parser.add_argument('--notice-id', action='append', help='Affected ID for a scoped pre-change fence')
    parser.add_argument('--complete-change', action='append', default=[], help='Ticket after DB commit and public promotion')
    parser.add_argument('--reader-group', help='Existing Linux read-only data group; never a DB group')
    parser.add_argument('--history-key', help='Preserved local generation history key')
    args = parser.parse_args()
    try:
        if args.reader_group:
            configure_reader_group(args.sync_dir,args.reader_group)
        if args.action == 'suspend':
            ticket=suspend(args.sync_dir,args.notice_id)
            print(json.dumps({'state':'change_pending','ticket':ticket})); return 0
        if args.action == 'rollback':
            print(json.dumps(rollback(args.sync_dir,args.history_key or ''))); return 0
        if not all((args.state_dir,args.rights_file,args.served_feed,args.details_file)):
            parser.error('refresh requires state, rights, served feed and details inputs')
        result = refresh(args.state_dir,args.rights_file,args.served_feed,args.details_file,args.sync_dir,
                         legacy_root=args.legacy_root,complete_change=args.complete_change)
        print(json.dumps({k: result[k] for k in ('documents','passages','generation','mode')} | {'omitted':len(result['omitted'])}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, monitor.MonitorError):
        print('{"status":"refresh_failed","reason":"Current authority and evidence checks still apply; prior release preserved."}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
