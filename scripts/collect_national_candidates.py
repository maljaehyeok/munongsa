"""Local, private review export using existing collectors. Never publishes."""
import argparse
import copy
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import support_monitor as monitor
from support_runtime import conditions, ingestion

ROOT = Path(__file__).resolve().parents[1]


def identity(url):
    p = urlsplit(url)
    pairs = dict(parse_qsl(p.query))
    for key in ('sId', 'pblancId', 'dataSid', 'dataUid', 'postUid', 'nttId'):
        if key in pairs:
            return (p.hostname, p.path, key, pairs[key])
    return ingestion.identity(url)


def prepare(groups, baseline):
    """All geographic discovery hints remain non-decisive. Approval is separate."""
    existing = {identity(n['url']) for n in baseline['notices']}
    titles = {re.sub(r'\s+', '', n['title']) for n in baseline['notices']}
    seen = set()
    result = []
    duplicate = failed = 0
    for group in groups:
        registry = json.loads((ROOT / 'config/collector_sources.json').read_text('utf8'))['sources']
        source = next(s for s in registry if s['kind'] == group['kind'])
        for entry in group.get('analyses', []):
            row = entry['metadata']
            monitor.canonical_url(row['original_url'], source.get('official_hosts', source.get('allowed_hosts', [])))
            key = identity(row['original_url'])
            if key in existing or key in seen:
                duplicate += 1
                continue
            seen.add(key)
            if entry.get('status') == 'failed':
                failed += 1
                continue
            facts = {k: copy.deepcopy(f) for k, f in entry.get('facts', {}).items()
                     if isinstance(f, dict) and conditions.clean_proof(f)
                     and identity(f['evidence']['url']) == key}
            # Reuse existing predicate builder; candidates cannot grant eligibility.
            payload = conditions.payload_for(facts, {})
            same_title = re.sub(r'\s+', '', row['title']) in titles
            missing = [k for k in ('target_description', 'application_method') if k not in facts]
            if not entry.get('recruitment', {}).get('period'):
                missing.append('application_period')
            if not facts:
                missing.append('official_detail_facts')
            if same_title:
                missing.append('possible_duplicate_requires_review')
            if len(row['title']) > 150:
                missing.append('independent_official_title_required')
            if re.search(r'정정|연장|취소|재공고', row['title']):
                missing.append('amended_notice_requires_version_review')
            missing.extend(['publication_rights', 'private_operating_db_duplicate_check',
                            'complete_eligibility', 'current_application_acceptance'])
            result.append({
                'source_kind': group['kind'], 'original_id': row['original_id'],
                'institution': source['institution'],
                'title': row['title'], 'official_url': row['original_url'],
                'checked_at': entry.get('checked_at'),
                'discovery_region': row.get('list_region', 'unknown'),
                'region_basis': 'discovery_only_not_residence_or_farm_eligibility',
                'facts': facts, 'eligibility_candidate': payload,
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
        'new_against_public_baseline': len(result), 'duplicates_excluded': duplicate,
        'detail_failures': failed,
        'discovery_regions_not_eligibility': dict(Counter(r['discovery_region'] for r in result)),
        'facts_ready_for_review': sum(r['review_priority'] == 'facts_ready' for r in result),
        'title_repair_required': sum('independent_official_title_required' in r['unknown_fields'] for r in result),
        'needs_information': sum(r['review_priority'] != 'facts_ready' for r in result),
        'fact_coverage': dict(Counter(k for r in result for k in r['facts'])),
        'condition_candidates': dict(Counter(c['kind'] for r in result
            for c in r['eligibility_candidate']['conditions'] if c['presence'] == 'specified')),
        'period_status_not_actual_acceptance': dict(Counter(
            r['recruitment'].get('status', 'unknown') for r in result)),
        'source_results': [{k: g.get(k) for k in (
            'kind', 'list_count', 'candidate_count', 'requests', 'errors', 'state')} for g in groups],
        'approved': 0, 'published': 0, 'operating_private_db_compared': False,
    }
    return {'schema_version': 1, 'summary': summary, 'candidates': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--result', type=Path, action='append', required=True,
                        help='Private result JSON from an existing collector; no network re-run')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT / 'work' not in output.parents:
        parser.error('output must be private work/; public assets and operational files forbidden')
    baseline = json.loads(args.baseline.read_text('utf-8-sig'))
    groups = [json.loads(p.read_text('utf-8-sig')) for p in args.result]
    result = prepare(groups, baseline)
    ingestion.atomic(output, result)
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
