"""Local, private review export using existing collectors. Never publishes."""
import argparse
import copy
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import support_monitor as monitor
import support_eligibility as eligibility
from support_runtime import conditions, ingestion

ROOT = Path(__file__).resolve().parents[1]


def basic_release_review(result, checks):
    """Draft only. No DB write, approval event, publication or eligibility grant."""
    ready=0
    for item in result['candidates']:
        check=checks.get(item['original_id'],{})
        policy=check.get('minimal_display_policy') or {}
        allowed=(result['summary']['operating_private_db_compared']
            and 'possible_duplicate_requires_review' not in item['unknown_fields']
            and not item.get('related_versions')
            and check.get('status')=='checked' and check.get('url')==item['official_url']
            and check.get('title_match') is True and check.get('metadata_title_confirmed') is True
            and check.get('metadata_link_restricted') is False
            and policy.get('id')=='official-notice-name-link-v1'
            and policy.get('scope')=='title_institution_link_only'
            and policy.get('body_redistribution') is False
            and policy.get('eligibility_approval') is False)
        item['basic_release_review']={'status':'candidate' if allowed else 'hold',
            'approved':False,'requires_operator_approval':True,
            'allowed_fields':['title','institution','official_url'] if allowed else [],
            'source_policy':policy if allowed else None,
            'reason':'minimal_name_link_policy_only' if allowed else 'official_title_link_policy_or_db_check_needed'}
        ready+=bool(allowed)
    result['summary']['basic_approval_candidates']=ready
    result['summary']['release_held']=len(result['candidates'])-ready
    return result


def identity(url):
    p = urlsplit(url)
    pairs = dict(parse_qsl(p.query))
    from support_runtime.source_quality import notice_key
    biz_key=notice_key(url)
    if isinstance(biz_key,tuple):return biz_key
    if 'proj_id' in pairs and 'proj_detail_id' in pairs:
        return (p.hostname, p.path, 'project', pairs['proj_id'], pairs['proj_detail_id'])
    if 'nttNo' in pairs:
        return (p.hostname,p.path,pairs.get('bbsNo'),'nttNo',pairs['nttNo'])
    for key in ('sId', 'pblancId', 'dataSid', 'dataUid', 'postUid', 'nttId'):
        if key in pairs:
            return (p.hostname, p.path, key, pairs[key])
    return ingestion.identity(url)


def prepare(groups, baseline, inventory=None):
    """All geographic discovery hints remain non-decisive. Approval is separate."""
    public_keys = {identity(n['url']) for n in baseline['notices']}
    existing = set(public_keys)
    if inventory is not None:
        existing.update(identity(n['original_url']) for n in inventory['notices'])
    titles = {re.sub(r'\s+', '', n['title']) for n in baseline['notices']}
    if inventory is not None:
        titles.update(re.sub(r'\s+', '', n.get('title','')) for n in inventory['notices'])
    seen = set()
    result = []
    duplicate = failed = repeated = raw_count = 0
    for group in groups:
        registry = json.loads((ROOT / 'config/collector_sources.json').read_text('utf8'))['sources']
        source = next(s for s in registry if s['kind'] == group['kind'])
        for entry in group.get('analyses', []):
            raw_count += 1
            row = entry['metadata']
            monitor.canonical_url(row['original_url'], source.get('official_hosts', source.get('allowed_hosts', [])))
            key = identity(row['original_url'])
            if key in seen:
                repeated += 1
                continue
            seen.add(key)
            if key in existing:
                duplicate += 1
                continue
            if entry.get('status') == 'failed':
                failed += 1
                continue
            facts = {k: copy.deepcopy(f) for k, f in entry.get('facts', {}).items()
                     if isinstance(f, dict) and conditions.clean_proof(f)
                     and identity(f['evidence']['url']) == key}
            # List-level periods may be useful, but cannot become detailed
            # eligibility evidence merely because the host is official.
            listing_facts = {k: copy.deepcopy(f) for k, f in entry.get('facts', {}).items()
                if isinstance(f, dict) and conditions.clean_proof(f)
                and f['evidence']['url'] in (source['board_url'], source.get('discovery_url'))
                and identity(f['evidence']['url']) != key}
            # Reuse existing predicate builder; candidates cannot grant eligibility.
            payload = conditions.payload_for(facts, {})
            for clause in payload['conditions']:clause.pop('status',None)
            schema_error=False
            try:eligibility.check_payload(payload,{'original_url':row['original_url']})
            except (ValueError,TypeError,KeyError,monitor.MonitorError):
                schema_error=True
                payload=conditions.payload_for({}, {})
                for clause in payload['conditions']:clause.pop('status',None)
            same_title = re.sub(r'\s+', '', row['title']) in titles
            missing = [k for k in ('target_description', 'application_method') if k not in facts]
            if schema_error:missing.append('condition_schema_review_required')
            if not entry.get('recruitment', {}).get('period'):
                missing.append('application_period')
            if not facts:
                missing.append('official_detail_facts')
            if same_title:
                missing.append('possible_duplicate_requires_review')
            if len(row['title']) > 150:
                missing.append('independent_official_title_required')
            if re.search(r'정정|연장|취소|재공고|변경', row['title']):
                missing.append('amended_notice_requires_version_review')
            missing.extend(['publication_rights',
                            'complete_eligibility', 'current_application_acceptance'])
            if inventory is None:missing.append('private_operating_db_duplicate_check')
            result.append({
                'source_kind': group['kind'], 'original_id': row['original_id'],
                'institution': source['institution'],
                'institution_role':'source_publisher',
                'implementing_institution':facts.get('implementing_institution'),
                'title': row['title'], 'official_url': row['original_url'],
                'checked_at': entry.get('checked_at'),
                'discovery_region': row.get('list_region', 'unknown'),
                'region_basis': 'discovery_only_not_residence_or_farm_eligibility',
                'facts': facts, 'listing_facts': listing_facts, 'eligibility_candidate': payload,
                'condition_schema_valid':not schema_error,
                'recruitment': entry.get('recruitment', {}),
                'review_status': 'pending', 'publication': 'private',
                'recommendation_eligible': False,
                'review_priority': 'facts_ready' if not any(k in missing for k in (
                    'target_description', 'application_method', 'application_period',
                    'official_detail_facts', 'possible_duplicate_requires_review',
                    'independent_official_title_required', 'amended_notice_requires_version_review')) else 'needs_information',
                'unknown_fields': sorted(set(entry.get('unknown_fields', []) + missing)),
            })
    versions = {}
    for item in result:
        # Only flag a relation; never merge notices, overwrite dates or choose
        # the newest version from title words alone.
        family = re.sub(r'\s+|연장|정정|변경', '', item['title'])
        versions.setdefault((item['source_kind'], family), []).append(item)
    for family in versions.values():
        if len(family) > 1:
            for item in family:
                item['related_versions'] = [r['original_id'] for r in family if r is not item]
                item['unknown_fields'].append('related_notice_versions_require_review')
                item['review_priority'] = 'needs_information'
    summary = {
        'baseline_public_count': len(baseline['notices']),
        'baseline_generated_at': baseline.get('generated_at'),
        'new_against_public_baseline': sum(k not in public_keys for k in seen),
        'new_candidate_count':len(result), 'duplicates_excluded': duplicate,
        'input_records_including_reused': raw_count, 'distinct_input_records': len(seen),
        'repeated_records_in_results': repeated,
        'new_after_operating_dedup': len(result) if inventory is not None else None,
        'detail_failures': failed,
        'discovery_regions_not_eligibility': dict(Counter(r['discovery_region'] for r in result)),
        'facts_ready_for_review': sum(r['review_priority'] == 'facts_ready' for r in result),
        'title_repair_required': sum('independent_official_title_required' in r['unknown_fields'] for r in result),
        'needs_information': sum(r['review_priority'] != 'facts_ready' for r in result),
        'fact_coverage': dict(Counter(k for r in result for k in r['facts'])),
        'condition_candidates': dict(Counter(c['kind'] for r in result
            for c in r['eligibility_candidate']['conditions'] if c['presence'] == 'specified')),
        'condition_schema_failures':sum(not r['condition_schema_valid'] for r in result),
        'period_status_not_actual_acceptance': dict(Counter(
            r['recruitment'].get('status', 'unknown') for r in result)),
        'source_results': [{k: g.get(k) for k in (
            'kind', 'list_count', 'candidate_count', 'requests', 'errors', 'state')} for g in groups],
        'approved': 0, 'published': 0, 'operating_private_db_compared': inventory is not None,
        'operating_db_count': len(inventory['notices']) if inventory is not None else None,
    }
    return {'schema_version': 1, 'summary': summary, 'candidates': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--result', type=Path, action='append', required=True,
                        help='Private result JSON from an existing collector; no network re-run')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, help='Read-only operating inventory; never opens the DB')
    parser.add_argument('--metadata-review', type=Path, help='Existing official title/link checks; produces draft candidates only')
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT / 'work' not in output.parents:
        parser.error('output must be private work/; public assets and operational files forbidden')
    baseline = json.loads(args.baseline.read_text('utf-8-sig'))
    groups = [json.loads(p.read_text('utf-8-sig')) for p in args.result]
    inventory = json.loads(args.inventory.read_text('utf-8-sig')) if args.inventory else None
    result = prepare(groups, baseline, inventory)
    if args.metadata_review:
        basic_release_review(result,json.loads(args.metadata_review.read_text('utf-8-sig')))
    ingestion.atomic(output, result)
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
