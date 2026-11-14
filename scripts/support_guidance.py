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


def select(rows, portal, link_check, now=None):
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
                reason = 'source_reuse_policy_unconfirmed'
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


def refresh(db, state, *, now=None, portal=None, link_check=None):
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
    result = select(records(db), portal, link_check, now)
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
            key = canonical(item['url']); safe_title(item['title']); safe_title(item['institution'])
            if key in seen or item['id'] in ids or item['policy_id'] != POLICY['id']:
                continue
            feed['notices'].append({'id': item['id'], 'title': item['title'], 'institution': item['institution'],
                'url': item['url'], 'source_id': item['source_id'], 'publication': 'official_guidance',
                'guidance_expires_at': manifest['expires_at'],
                'verification_status': 'basics_only', 'freshness': 'current', 'last_checked_at': item['checked_at'],
                'recommendation_eligible': False, 'eligibility_complete': False, 'guidance_level': 'official_notice',
                'application_status': 'unknown', 'application_period': {}, 'reference_application_dates': {},
                'region': 'unknown', 'target': 'unknown', 'support': 'unknown',
                'eligibility': {'conditions': [], 'logic': {'op': 'UNKNOWN', 'children': []}},
                'evidence': {'notice': {'url': item['url'], 'location': '공식 API 제목·원문 링크 확인'}},
                'rights': {'public_display': 'allowed', 'evidence_url': POLICY['url'], 'checked_at': POLICY['checked_at']},
                'attribution': '출처: 중소벤처기업부·기업마당 / 공공데이터포털', 'license': POLICY['license']})
            ids.add(item['id']); seen.add(key); total += 1
        except (ValueError, TypeError, KeyError, monitor.MonitorError):
            continue
    return total
