"""Minimal official metadata browsing, independent of recommendation approval.

Only the licensed data.go.kr response is eligible. Full text, attachments,
unreviewed eligibility and amounts are never published by this module.
"""
import concurrent.futures
import hashlib
import json
import re
import urllib.robotparser
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

import export_support_public as public
import support_monitor as monitor
from support_review_queue import report, identity

POLICY = {
    'id': 'data-go-kr-15157820-metadata-v1',
    'url': 'https://www.data.go.kr/data/15157820/openapi.do',
    'license': '공공누리 제3유형 · 출처표시·변경금지',
    'checked_at': '2026-11-14',
    'fields': ['title', 'institution', 'url'],
    'scope': '공식 API의 공고 제목·출처·공식 링크만 원형대로 안내; 본문·첨부·요약·자격 판정 제외',
}
SCHEMA = 'munongsa-official-guidance-v1'
TTL = timedelta(days=3)


def instant(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('timezone required')
    return result


def canonical(value):
    public.checked_url(value)
    u = urlsplit(value)
    if u.hostname not in ('www.bizinfo.go.kr', 'bizinfo.go.kr') or u.path not in ('/web/lay1/bbs/S1T122C128/AS/74/view.do', '/sii/siia/selectSIIA200Detail.do'):
        raise ValueError('official detail required')
    from urllib.parse import parse_qs
    q = parse_qs(u.query)
    if not re.fullmatch(r'PBLN_[0-9]+', q.get('pblancId', [''])[0]):
        raise ValueError('official identity required')
    return identity(value)


def safe_title(value):
    public.public_text(value)
    if not value.strip() or len(value) > 500 or re.search(r'[<>\x00-\x1f]|https?://|AKIA[0-9A-Z]{16}|\d{6}[- ]?[1-4]\d{6}|[가-힣]+(?:로|길)\s*\d+(?:-\d+)?', value):
        raise ValueError('unsafe metadata')
    return value


def records(db):
    return [dict(r) for r in db.execute('SELECT n.*,s.institution FROM discovered_notices n JOIN monitor_sources s ON s.source_id=n.source_id ORDER BY n.first_collected_at,n.notice_id')]


def select(rows, portal, link_check, now=None, source_checks=None):
    """All pending rows are classified; only matching licensed metadata can pass."""
    now = now or datetime.now(timezone.utc)
    import support_official_apis as api
    pending = [r for r in rows if r['publication'] == 'review']
    published = [r for r in rows if r['publication'] in ('approved', 'approved_reference')]
    triage = report(pending, now, published)
    classified = {r['notice_id']: r for r in triage['candidates']}
    by_url = {}
    conflicts = set()
    for row in portal:
        try:
            key = canonical(row['original_url'])
            if key in by_url and by_url[key] != row:
                conflicts.add(key)
            by_url[key] = row
        except (ValueError, monitor.MonitorError):
            continue
    seen = {identity(r['original_url']) for r in published}
    items, decisions = [], []
    for row in pending:
        reason = None
        category = classified[row['notice_id']]['category']
        try:
            key = identity(row['original_url'])
            if category == 'unrelated':
                reason = 'agricultural_relevance_insufficient'
            elif key in seen or category == 'duplicate':
                reason = 'duplicate'
            elif row['source_id'] != 'bizinfo-support-api':
                import support_guidance_sources as sources
                checked = (source_checks or {}).get(row['notice_id'], {})
                policy = sources.validate_item(row, checked)
                if checked.get('duplicate_of'):
                    reason='duplicate';policy=None
                elif checked.get('decision_changed'):
                    reason='official_version_recheck_required';policy=None
                if re.search(r'종자대\s*지원대상[이가]?\s*아님',checked.get('article','')):
                    reason='agricultural_relevance_insufficient';policy=None
                if policy and category != 'reference':
                    safe_title(row['title']);safe_title(row['institution'])
                    public.checked_url(row['original_url'])
                    items.append({'id':row['notice_id'],'content_hash':row['content_hash'],'title':row['title'],
                                  'institution':row['institution'],'url':row['original_url'],'source_id':row['source_id'],
                                  'checked_at':now.isoformat(),'policy_id':sources.POLICY_ID,'source_policy':policy,
                                  'archive':category=='elapsed'})
                    seen.add(key)
                else:
                    reason = reason or ('reference_document' if policy and category=='reference' else 'official_link_unconfirmed' if checked and checked.get('status')!='checked' else 'source_reuse_policy_unconfirmed')
            else:
                canonical(row['original_url'])
                origin = by_url.get(key)
                if key in conflicts:
                    reason = 'conflicting_official_metadata'
                elif not origin or origin['title'] != row['title']:
                    reason = 'licensed_metadata_version_unconfirmed'
                elif not api.agricultural(origin):
                    reason = 'agricultural_relevance_insufficient'
                else:
                    safe_title(row['title']); safe_title(row['institution'])
                    if not link_check(row['original_url']):
                        reason = 'official_link_unconfirmed'
                    else:
                        checked = now.isoformat()
                        items.append({'id': row['notice_id'], 'content_hash': row['content_hash'],
                                      'title': row['title'], 'institution': row['institution'],
                                      'url': row['original_url'], 'source_id': row['source_id'],
                                      'checked_at': checked, 'policy_id': POLICY['id']})
                        seen.add(key)
        except (ValueError, TypeError, KeyError, monitor.MonitorError):
            reason = 'unsafe_or_invalid_metadata'
        decisions.append({'id': row['notice_id'], 'category': category,
                          'basic_guidance': reason is None, 'hold_reason': reason})
    from collections import Counter
    return {'schema': SCHEMA, 'generated_at': now.isoformat(), 'expires_at': (now+TTL).isoformat(),
            'policy': dict(POLICY), 'items': items, 'decisions': decisions,
            'summary': {'pending_examined': len(pending), 'new_guidance': len(items),
                        'held': dict(Counter(d['hold_reason'] for d in decisions if d['hold_reason'])),
                        'triage': triage['counts'],
                        'elapsed_pending': sum(d['category'] == 'elapsed' for d in decisions)}}


def refresh(db, state, *, now=None, portal=None, link_check=None, source_checks=None):
    """Explicit bounded public network checks. DB remains read-only."""
    import support_official_apis as api
    from support_runtime import ingestion
    if portal is None:
        portal = []
        for page in (1, 2):
            batch, _ = api.fetch('data_go_kr_bizinfo', 50, page)
            portal.extend(batch)
            if len(batch) < 50:
                break
    if link_check is None:
        import support_bizinfo as biz
        import urllib.request
        robots_raw, status, _ = biz.probe_transport(urllib.request.Request('https://www.bizinfo.go.kr/robots.txt', headers={'User-Agent': monitor.USER_AGENT}), timeout=10)
        if status != 200:
            raise ValueError('robots_unconfirmed')
        robot = urllib.robotparser.RobotFileParser()
        robot.parse(robots_raw.decode('utf-8-sig').splitlines())
        titles = {r['original_url']: r['title'] for r in records(db)}
        def check(url):
            try:
                if not robot.can_fetch(monitor.USER_AGENT, url):
                    return False
                raw, code, _ = biz.probe_transport(urllib.request.Request(url, headers={'User-Agent': monitor.USER_AGENT}), timeout=8)
                # Reject login/error/challenge pages returned with 200 as well.
                text = raw.decode('utf-8', errors='replace')
                from bs4 import BeautifulSoup
                normalized = lambda s: re.sub(r'\s+', '', s)
                return (code == 200 and normalized(titles[url]) in normalized(BeautifulSoup(text, 'html.parser').get_text(' ', strip=True))
                        and not re.search(r'<title>[^<]*(?:오류|접근제한|로그인)', text))
            except Exception:
                return False
        candidates = {r['original_url'] for r in records(db) if r['publication'] == 'review' and r['source_id'] == 'bizinfo-support-api'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = dict(zip(sorted(candidates), pool.map(check, sorted(candidates))))
        link_check = lambda url: outcomes.get(url, False)
    import support_guidance_sources as sources
    now=now or datetime.now(timezone.utc)
    plans_path=state/'comparison-plans.json'
    plans=json.loads(plans_path.read_text('utf-8')) if plans_path.exists() else []
    facts_path=state/'verified-fact-plans.json'
    fact_plans=json.loads(facts_path.read_text('utf-8')) if facts_path.exists() else []
    decisions_path=state/'guidance-source-decisions.json'
    decisions=json.loads(decisions_path.read_text('utf-8')) if decisions_path.exists() else {}
    all_rows=records(db)
    if source_checks is None:
        planned={p['id'] for p in plans+fact_plans}|{d['primary'] for d in decisions.values()}|{r['notice_id'] for r in all_rows if r['publication'] in ('approved','approved_reference')}
        candidates=[r for r in all_rows if (r['source_id']!='bizinfo-support-api' and r['publication']=='review') or r['notice_id'] in planned]
        preferred={'jeonbuk-jeonju-official','jeonbuk-gunsan-official','jeonbuk-sunchang-official'}
        candidates.sort(key=lambda r:(r['notice_id'] not in planned,r['source_id'] not in preferred))
        source_checks=sources.inspect(candidates)
    sources.apply_decisions(source_checks,decisions)
    result = select(all_rows, portal, link_check, now, source_checks)
    rights=json.loads((state/'publication-rights.json').read_text('utf-8')) if (state/'publication-rights.json').exists() else {}
    strict,_=public.export(db,rights,now)
    result['verified_comparisons']=sources.verified_comparisons(strict,plans,source_checks,now)
    result['source_review']={n['id']:{'title_needs_review':True,'checked_at':now.isoformat()} for n in strict['notices']
                              if n['id'] in source_checks and source_checks[n['id']].get('status')=='checked' and not source_checks[n['id']].get('title_match')}
    from collections import Counter
    result['summary']['by_source']={source:dict(Counter(d['hold_reason'] or 'basic_guidance' for d in result['decisions'] if next(r for r in all_rows if r['notice_id']==d['id'])['source_id']==source)) for source in sorted({r['source_id'] for r in all_rows if r['publication']=='review'})}
    result['summary']['comparison_ready']=len(result['verified_comparisons'])
    append(db,strict,result,now)
    result['verified_facts']=sources.reviewed_facts(strict,fact_plans,source_checks,now)
    ingestion.atomic(state/'official-guidance.json', result)
    ingestion.atomic(state/'logs'/('guidance-'+hashlib.sha256(result['generated_at'].encode()).hexdigest()[:16]+'.json'), result)
    return result


def append(db, feed, manifest, now=None):
    """Hash/state/expiry rechecked on every export; revoked records cannot inherit."""
    now = now or datetime.now(timezone.utc)
    if (manifest.get('schema') != SCHEMA or manifest.get('policy') != POLICY
            or not instant(manifest['generated_at']) <= now < instant(manifest['expires_at'])
            or instant(manifest['expires_at'])-instant(manifest['generated_at']) > TTL):
        return 0
    seen = {identity(n['url']) for n in feed['notices']}
    ids = {n['id'] for n in feed['notices']}
    total = 0
    for item in manifest['items']:
        try:
            row = db.execute('SELECT * FROM discovered_notices WHERE notice_id=?', (item['id'],)).fetchone()
            if not row or row['publication'] != 'review' or row['content_hash'] != item['content_hash']:
                continue
            if any(row[k] != item[v] for k,v in [('title','title'),('original_url','url'),('source_id','source_id')]):
                continue
            policy=item.get('source_policy')
            if policy:
                import support_guidance_sources as sources
                if (item['policy_id']!=sources.POLICY_ID or policy['id']!=sources.POLICY_ID or policy['scope']!='unchanged_metadata_only'
                        or policy['type'] not in ('1','2','3','4') or urlsplit(item['url']).hostname!=sources.source_hosts().get(item['source_id'])
                        or policy['type'] in ('2','4') and not sources.NONCOMMERCIAL_METADATA_ONLY):continue
                public.checked_url(item['url']);key=identity(item['url'])
                evidence_url=policy['evidence_url'];checked_day=item['checked_at'][:10]
                license_name='공공누리 제'+policy['type']+'유형 · 출처표시'+('·비상업적 이용' if policy['type'] in ('2','4') else '')+('·변경금지' if policy['type'] in ('3','4') else '')
                attribution='출처: '+item['institution']+' · 공식 공고 원문'
            else:
                key=canonical(item['url']);evidence_url=POLICY['url'];checked_day=POLICY['checked_at'];license_name=POLICY['license'];attribution='출처: 중소벤처기업부·기업마당 / 공공데이터포털'
                if item['policy_id']!=POLICY['id']:continue
            safe_title(item['title']); safe_title(item['institution'])
            if key in seen or item['id'] in ids:
                continue
            feed['notices'].append({'id': item['id'], 'title': item['title'], 'institution': item['institution'],
                'url': item['url'], 'source_id': item['source_id'], 'publication': 'official_guidance',
                'guidance_expires_at': manifest['expires_at'],
                'verification_status': 'basics_only', 'freshness': 'current', 'last_checked_at': item['checked_at'],
                'recommendation_eligible': False, 'eligibility_complete': False, 'guidance_level': 'official_notice',
                'application_status': 'unknown', 'application_period': {}, 'reference_application_dates': {},
                **({'recorded_period_elapsed':True} if item.get('archive') is True else {}),
                'region': 'unknown', 'target': 'unknown', 'support': 'unknown',
                'eligibility': {'conditions': [], 'logic': {'op': 'UNKNOWN', 'children': []}},
                'evidence': {'notice': {'url': item['url'], 'location': '공식 API 제목·원문 링크 확인'}},
                'rights': {'public_display': 'allowed', 'evidence_url': evidence_url, 'checked_at': checked_day},
                'attribution': attribution, 'license': license_name})
            ids.add(item['id']); seen.add(key); total += 1
        except (ValueError, TypeError, KeyError, monitor.MonitorError):
            continue
    by_id={n['id']:n for n in feed['notices']}
    import support_guidance_sources as sources
    feed['verified_comparisons']={k:v for k,v in manifest.get('verified_comparisons',{}).items() if k in by_id and sources.comparison_basis(by_id[k])==v['basis'] and v.get('complete') is False and instant(v['expires_at'])>now}
    feed['source_review']={k:v for k,v in manifest.get('source_review',{}).items() if k in by_id}
    feed['verified_facts']={k:v for k,v in manifest.get('verified_facts',{}).items() if k in by_id
                            and sources.comparison_basis(by_id[k])==v.get('basis') and v.get('complete') is False
                            and instant(v['expires_at'])>now}
    return total
