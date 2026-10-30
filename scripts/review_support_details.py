"""Field-level review artifact. No SQLite, collection, SSH or public-feed writes.

Preview is localhost-only. Approve only after the user accepts the exact plan hash.
The normal collector never writes this independent, Git-versioned asset.
"""
import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

FIELDS = {'summary', 'funding', 'conditions', 'method', 'office', 'documents_required',
          'documents_conditional', 'documents_bonus', 'contact', 'warnings', 'unconfirmed'}
ROOT = Path(__file__).resolve().parents[1]


def validate(plan):
    assert plan['schema'] == 'munongsa-support-details-plan-v1'
    assert 1 <= len(plan['records']) <= 11, 'review only an explicit bounded batch'
    identities = set()
    for r in plan['records']:
        b = r['basis']
        assert b['id'] not in identities
        identities.add(b['id'])
        host = urlsplit(b['url']).hostname
        assert host in {'www.rda.go.kr', 'www.gochang.go.kr', 'global.at.or.kr',
                        'www.buan.go.kr', 'www.jeonbuk.go.kr', 'www.jeonju.go.kr', 'www.oads.or.kr'}
        assert r['rights']['facts_only'] is True and r['rights']['policy_url']
        assert r['fields'] and set(r['fields']) <= FIELDS
        for f in r['fields'].values():
            value, e = f['value'], f['evidence']
            assert (isinstance(value, str) and value.strip()) or (
                isinstance(value, list) and value and all(isinstance(v, str) and v.strip() for v in value))
            assert urlsplit(e['url']).scheme == 'https' and urlsplit(e['url']).hostname == host
            assert e['location'].strip() and datetime.fromisoformat(e['checked_at']).tzinfo
    return plan


def build(plan, reviewer, reference, approved=False):
    validate(plan)
    records = copy.deepcopy(plan['records'])
    stamp = datetime.now(timezone.utc).isoformat()
    for r in records:
        r['approval'] = {'state': 'approved' if approved else 'preview', 'reviewer': reviewer,
                         'reference': reference, 'checked_at': stamp}
    return {'schema': 'munongsa-support-details-v1', 'preview': not approved, 'records': records}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--approve', action='store_true')
    p.add_argument('--reviewer')
    p.add_argument('--approval-reference')
    p.add_argument('--approved-plan-sha256')
    p.add_argument('--preserve-sha256', help='Exact existing approved asset hash, required to append')
    args = p.parse_args()
    raw = args.plan.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    output = args.output.resolve()
    if args.approve:
        if not (args.reviewer and args.approval_reference and args.approved_plan_sha256 == digest):
            p.error('explicit reviewer, approval reference and exact approved plan hash required')
        if output != ROOT / 'assets/support-details.json':
            p.error('approval output must be the dedicated explanatory asset')
    elif not output.is_relative_to(ROOT / 'work'):
        p.error('preview output must remain in private work/')
    doc = build(json.loads(raw), args.reviewer or 'local-preview', args.approval_reference or digest, args.approve)
    asset = ROOT / 'assets/support-details.json'
    old_raw = asset.read_bytes()
    old = json.loads(old_raw)
    old_records = old.get('records', [])
    if old.get('preview') is not False or any(r.get('approval', {}).get('state') != 'approved' for r in old_records):
        p.error('existing asset must contain approved records only')
    if {r['basis']['id'] for r in old_records} & {r['basis']['id'] for r in doc['records']}:
        p.error('append only: existing reviewed notices cannot be replaced')
    if args.approve and old_records and args.preserve_sha256 != hashlib.sha256(old_raw).hexdigest():
        p.error('exact preservation hash of existing approved descriptions required')
    doc['records'] = old_records + doc['records']
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({'approved': args.approve, 'count': len(doc['records']), 'plan_sha256': digest}))


if __name__ == '__main__':
    main()
