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
    assert len(plan['records']) == 3, 'only the three reviewed notices are in scope'
    identities = set()
    for r in plan['records']:
        b = r['basis']
        assert b['id'] not in identities
        identities.add(b['id'])
        host = urlsplit(b['url']).hostname
        assert host in {'www.rda.go.kr', 'www.gochang.go.kr', 'global.at.or.kr'}
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
    if args.approve and output.exists():
        old = json.loads(output.read_text('utf-8'))
        if old.get('records'):
            p.error('existing approved details require a separate reviewed merge; refusing overwrite')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({'approved': args.approve, 'count': len(doc['records']), 'plan_sha256': digest}))


if __name__ == '__main__':
    main()
