"""Explicit, read-only review DB -> allowlisted public JSON. Never approves records.

Default output is private. Promotion to a served path requires a separate operator
decision. Rights manifest is per notice, not an inferred source-wide license.
"""
import argparse
import json
import re
from contextlib import closing
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import support_monitor as monitor
import support_eligibility as eligibility
from support_source_registry import url as public_url

SCHEMA_VERSION = 'munongsa-support-public-v1'
CONTACT = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}(?!\d)|[A-Za-z]:[\\/]')


def checked_url(value):
    public_url(value)
    return value


def public_text(value):
    if not isinstance(value, str) or CONTACT.search(value):
        raise ValueError('unsafe public text; manual redaction required')
    return value


def proof(value):
    return {'url': checked_url(value['url']), 'location': public_text(value.get('location', ''))}


def rights_for(manifest, identity, now):
    value = manifest.get(identity, {})
    if value.get('public_display') != 'allowed':
        return None
    checked = date.fromisoformat(value['checked_at'])
    if checked > now.astimezone(timezone(timedelta(hours=9))).date():
        return None
    return {'public_display': 'allowed', 'evidence_url': checked_url(value['evidence_url']),
            'checked_at': checked.isoformat()}


def period_status(record, now):
    # A passed deadline alone is not proof that extension/reannouncement is absent.
    if not record['application_period_verified']:
        return 'unknown'
    start, end = monitor.checked_period(record['verified_application_period'])
    if now > end:
        return 'closed_verified' if record['application_status'] == 'closed' else 'period_elapsed'
    if now < start:
        return 'upcoming_verified' if record['application_status'] == 'upcoming' else 'unknown'
    return 'open_verified' if record['application_status'] == 'open' else 'unknown'


def reference_dates(grant, record):
    """Human-confirmed date facts only; never substitutes for a verified time window."""
    if (grant.get('notice_content_hash') != record['content_hash']
            or grant.get('reference_dates_verified') is not True):
        return {}
    raw = grant.get('reference_dates', {})
    result = {}
    for key in ('start', 'end'):
        if key not in raw:
            continue
        part = raw[key]
        value = part['date']
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('invalid reference date')
        evidence = proof(part['evidence'])
        if not evidence['location'].strip():
            raise ValueError('reference date needs a checked evidence location')
        result[key] = {'date': value, 'evidence': evidence}
        if part.get('time') not in (None, 'unknown'):
            if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?', part['time']) or part.get('timezone') != 'Asia/Seoul':
                raise ValueError('invalid reference time')
            result[key].update(time=part['time'], timezone='Asia/Seoul')
    if result.get('start') and result.get('end') and result['start']['date'] > result['end']['date']:
        raise ValueError('invalid reference date range')
    return result


def export(connection, rights, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('timezone-aware export time required')
    result = {'schema_version': SCHEMA_VERSION, 'generated_at': now.isoformat(),
              'notices': [], 'policy': 'approved reference is never a recommendation'}
    stats = {'examined': 0, 'exported': 0, 'omitted': 0, 'recommendations': 0, 'references': 0}
    # Caller opens mode=ro; no migrations, registrations or approval writes here.
    for row in connection.execute('SELECT notice_id FROM discovered_notices ORDER BY notice_id'):
        stats['examined'] += 1
        try:
            r = monitor.notice_record(connection, row['notice_id'])
            license_record = rights_for(rights, r['notice_id'], now)
            if (r['publication'] not in ('approved', 'approved_reference')
                    or r['verification_status'] != 'verified' or r['freshness'] != 'current'
                    or not r['approved_by'] or not r['approved_at'] or not r['reviewer']
                    or not r['reviewed_at'] or not r['field_evidence'] or not license_record):
                raise ValueError('not eligible for public export')
            evidence = {k: proof(v) for k, v in r['field_evidence'].items()
                        if k in ('notice', 'target', 'region', 'support', 'application_period')}
            if not evidence:
                raise ValueError('no public evidence')
            revision = eligibility.show(connection, r['notice_id'])
            structured = {'conditions': [], 'logic': {'op': 'UNKNOWN', 'children': []}}
            all_verified = False
            # Legacy notice approvals are not bound to an eligibility revision.
            # Explicit export review binds the condition version in the rights
            # manifest; a new condition revision cannot inherit that permission.
            grant = rights[r['notice_id']]
            source_checked = r['reviewed_at']
            if grant.get('notice_content_hash') == r['content_hash'] and grant.get('source_checked_at'):
                parsed_checked = datetime.fromisoformat(grant['source_checked_at'])
                if parsed_checked.tzinfo is None or parsed_checked > now:
                    raise ValueError('invalid source check timestamp')
                source_checked = parsed_checked.isoformat()
            condition_release = (grant.get('eligibility_revision_id') == revision.get('revision_id')
                                 and grant.get('notice_content_hash') == r['content_hash'])
            if 'payload' in revision and not revision['needs_review'] and condition_release:
                original = revision['payload']
                # Revalidate even if DB has been edited outside the CLI.
                candidate = {'logic': original['logic'], 'conditions': [
                    {k: c[k] for k in ('condition_id', 'kind', 'presence', 'value', 'evidence')}
                    for c in original['conditions']]}
                eligibility.check_payload(candidate, r)
                conditions = []
                for c in original['conditions']:
                    verified = (c.get('effective_status') == 'verified'
                                and c.get('reviewer') and c.get('reviewed_at'))
                    if verified:
                        eligibility.check_condition(c, r, verified=True)
                        value = json.loads(json.dumps(c['value'], ensure_ascii=False))
                        public_text(json.dumps(value, ensure_ascii=False))
                        condition_proof = proof(c['evidence'])
                        if grant.get('facts_only') is True:
                            if c['kind'] not in ('applicant', 'residence', 'farm_registration'):
                                raise ValueError('condition outside reviewed facts-only scope')
                            condition_proof['fact_confirmed'] = True
                        else:
                            condition_proof['quote'] = public_text(c['evidence']['quote'])
                        conditions.append({'condition_id': c['condition_id'], 'kind': c['kind'],
                            'presence': c['presence'], 'value': value, 'status': 'verified',
                            'evidence': condition_proof})
                    else:
                        # Keep the logical position, never expose candidate assertions as facts.
                        conditions.append({'condition_id': c['condition_id'], 'kind': c['kind'],
                            'presence': 'unknown', 'value': None, 'status': 'unverified', 'evidence': {}})
                structured = {'conditions': conditions, 'logic': original['logic']}
                all_verified = bool(conditions) and all(c['status'] == 'verified' for c in conditions)
            allowed = monitor.recommendation_allowed(r, now) and all_verified
            source = connection.execute('SELECT institution FROM monitor_sources WHERE source_id=?',
                                        (r['source_id'],)).fetchone()
            item = {'id': r['notice_id'], 'program_id': r['program_id'], 'round_id': r['round_id'],
                    'title': public_text(r['title']), 'source_id': r['source_id'],
                    'institution': public_text(source['institution']), 'url': checked_url(r['original_url']),
                    'published_at': r['published_at'], 'last_checked_at': source_checked,
                    'publication': r['publication'], 'verification_status': r['verification_status'],
                    'freshness': r['freshness'], 'application_status': period_status(r, now),
                    'application_period': r['verified_application_period'] if r['application_period_verified'] else {},
                    'reference_application_dates': reference_dates(grant, r),
                    'recommendation_eligible': bool(allowed), 'rights': license_record,
                    'guidance_level': 'personalized_candidate' if allowed else 'official_notice',
                    'eligibility_complete': bool(all_verified),
                    'target': public_text(r['target']) if 'target' in evidence else 'unknown',
                    'region': public_text(r['region']) if 'region' in evidence else 'unknown',
                    'support': public_text(r['support']) if 'support' in evidence else 'unknown',
                    'evidence': evidence, 'eligibility': structured}
            result['notices'].append(item)
            stats['recommendations' if allowed else 'references'] += 1
        except (ValueError, TypeError, KeyError, monitor.MonitorError):
            # No record text, URLs, reviewers or exception messages in the summary.
            stats['omitted'] += 1
    stats['exported'] = len(result['notices'])
    return result, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=monitor.DEFAULT_STATE)
    parser.add_argument('--rights-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=monitor.ROOT / 'work/support-monitor/export/support-public.json')
    args = parser.parse_args()
    # Public promotion is deliberately outside this private generation command.
    output = args.output.resolve()
    private_root = (monitor.ROOT / 'work').resolve()
    if private_root not in output.parents or output.exists() or output.suffix != '.json':
        parser.error('use a new .json path under work/; public promotion requires separate approval')
    try:
        rights = json.loads(args.rights_file.read_text(encoding='utf-8-sig'))
        if not isinstance(rights, dict):
            raise ValueError()
        with closing(monitor.connect(args.state_dir, readonly=True)) as db:
            db.execute('BEGIN')
            data, stats = export(db, rights)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        print(json.dumps(stats))
        return 0
    except (ValueError, OSError, monitor.MonitorError):
        print('Export failed safely; check DB, rights manifest and output path. No DB writes.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
