"""MAFRA 13-notice pilot: private HTML evidence, never attachments or publication."""
import json
import re
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import support_monitor as monitor


PILOT_IDS = frozenset('582042 579285 579452 579438 579406 579387 579380 579314 579312 579290 579218 579161 579134'.split())
SCHEMA = """
CREATE TABLE IF NOT EXISTS body_fetches (
 fetch_id INTEGER PRIMARY KEY, notice_id TEXT NOT NULL REFERENCES discovered_notices(notice_id),
 original_url TEXT NOT NULL, collected_at TEXT NOT NULL, status TEXT NOT NULL,
 change_type TEXT, http_status INTEGER, response_hash TEXT, raw_html BLOB, error TEXT
);
CREATE TABLE IF NOT EXISTS body_versions (
 body_version_id INTEGER PRIMARY KEY, notice_id TEXT NOT NULL REFERENCES discovered_notices(notice_id),
 fetch_id INTEGER NOT NULL REFERENCES body_fetches(fetch_id), content_hash TEXT NOT NULL,
 collected_at TEXT NOT NULL, page_title TEXT NOT NULL, body_text TEXT NOT NULL,
 attachments_json TEXT NOT NULL, extracted_json TEXT NOT NULL, rights_hint TEXT NOT NULL
);
"""


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        if self.tag in {'script', 'style', 'noscript'} or 'hidden' in self.attrs or self.attrs.get('aria-hidden') == 'true' or re.search(r'display\s*:\s*none', self.attrs.get('style', ''), re.I):
            return ''
        content = ''.join(c.text() if isinstance(c, Node) else c for c in self.children)
        if self.tag in {'p', 'div', 'li', 'tr', 'br', 'h1', 'h2', 'h3'}:
            content = '\n' + content + '\n'
        elif self.tag in {'td', 'th'}:
            content += ' | '
        return content

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_page(raw, url, source):
    if len(raw) > monitor.MAX_BYTES:
        raise monitor.MonitorError('본문 응답 크기 제한 초과')
    parser = PageParser()
    parser.feed(raw.decode('utf-8-sig'))
    nodes = list(parser.root.walk())
    bodies = [n for n in nodes if 'view_contents' in n.attrs.get('class', '').split()]
    if len(bodies) != 1:
        raise monitor.MonitorError('공식 본문 영역을 식별하지 못함')
    lines = [' '.join(line.split()) for line in bodies[0].text().splitlines() if line.strip()]
    tops = [n for n in nodes if 'view_top' in n.attrs.get('class', '').split()]
    titles = [monitor.plain(n.text()) for top in tops for n in top.walk() if n.tag == 'dt']
    if len(titles) != 1 or not titles[0]:
        raise monitor.MonitorError('공고 제목 영역을 식별하지 못함')
    attachments = []
    for n in nodes:
        href = n.attrs.get('href', '')
        if n.tag != 'a' or not re.fullmatch(r'/bbs/home/791/\d+/download\.do', urllib.parse.urlsplit(href).path):
            continue
        try:
            link = monitor.canonical_url(urllib.parse.urljoin(url, href), source['allowed_hosts'])
        except (ValueError, monitor.MonitorError):
            continue
        name = monitor.plain(n.text())
        match = re.search(r'^(.+?\.(?:hwpx?|pdf|xlsx?|docx?|zip|png|jpe?g))(?:\s|$)', name, re.I)
        if not match:
            continue
        item = {'filename': match[1], 'url': link, 'content_analyzed': False}
        if item not in attachments:
            attachments.append(item)
    rights = [n.attrs.get('src', '') for n in nodes if n.tag == 'img' and 'img_opentype' in n.attrs.get('src', '')]
    return {'page_title': titles[0], 'body_text': '\n'.join(lines), 'attachments': attachments,
            'rights_hint': rights[0] if len(rights) == 1 else 'unknown'}


LABELS = {
    'program_name': ('사업명',), 'region': ('대상 지역', '사업 지역', '지원 지역'),
    'target': ('지원 대상', '신청 대상', '신청 자격', '신청대상 및 자격'),
    'support': ('지원 내용',), 'amount': ('지원 금액', '지원 한도'),
    'application_method': ('신청 방법', '접수 방법'),
    'application_period': ('신청 기간', '접수 기간', '모집 기간'),
}


def extract_body(page, url):
    result = {k: 'unknown' for k in LABELS}
    result.update(application_start='unknown', application_end='unknown', classification='unknown',
                  application_status='unknown', verification_status='unverified', publication='review',
                  evidence={}, attachment_review_required=bool(page['attachments']), warnings=[])
    for field, labels in LABELS.items():
        matches = []
        for line in page['body_text'].splitlines():
            for label in labels:
                pattern = r'^\s*[□○◦ㅇ*·\-\d.)\s]*' + r'\s*'.join(map(re.escape, label.split())) + r'\s*[:：|]\s*(.+?)\s*(?:\|\s*)?$'
                found = re.match(pattern, line)
                if found:
                    value = found[1].strip()
                    if value not in {'unknown', '미정', '미확인'} and not re.search(r'붙임|첨부|별첨|별도|참조|참고|추후', value) and not re.search(r'[:：|]', value):
                        matches.append((value, line))
        values = {v for v, _ in matches}
        if len(values) == 1:
            value, quote = matches[0]
            result[field] = value
            result['evidence'][field] = {'url': url, 'location': 'div.view_contents', 'quote': quote}
        elif len(values) > 1:
            result['warnings'].append(field + ': conflicting or separate labelled values; review required')
    period = result['application_period']
    if period != 'unknown':
        dates = re.fullmatch(r'(\d{4}[-.]\s*\d{1,2}[-.]\s*\d{1,2})\s*[~～]\s*(\d{4}[-.]\s*\d{1,2}[-.]\s*\d{1,2})\.?', period)
        if dates:
            try:
                start, end = [datetime.strptime(re.sub(r'\s', '', d).replace('.', '-'), '%Y-%m-%d').date().isoformat() for d in dates.groups()]
                if start <= end:
                    result.update(application_start=start, application_end=end)
            except ValueError:
                pass
        # Date-only hints never invent cutoff times/timezone and never imply 'open'.
    target = result['target']
    if target != 'unknown' and not re.search(r'제외|불가|아닌|하지\s*않|할\s*수\s*없', target):
        groups = {
            'direct_farmer_support': bool(re.search(r'개인\s*농업인|청년\s*농업인|귀농인|일반\s*농업인', target)),
            'business_support': bool(re.search(r'농업\s*법인|농식품\s*기업|중소기업|도축장.*영업자|집유장.*영업자', target)),
            'institution_call': bool(re.search(r'지방자치단체|지자체|지방정부|공공기관|수행기관', target)),
        }
        found = [k for k, yes in groups.items() if yes]
        if len(found) == 1:
            result['classification'] = found[0]
            result['evidence']['classification'] = dict(result['evidence']['target'])
    if result['classification'] == 'unknown' and target == 'unknown':
        general = next((line for line in page['body_text'].splitlines() if re.search(r'후보자.*공개\s*검증|개정.*의견\s*수렴', line)), None)
        if general:
            result['classification'] = 'policy_reference'
            result['evidence']['classification'] = {'url': url, 'location': 'div.view_contents', 'quote': general}
    result['extraction_status'] = 'partial_hints' if result['evidence'] else 'no_information'
    return result


class OfficialBodyFetcher:
    def __init__(self, source):
        self.source, self.policy, self.policy_error = source, None, None
        self.last_request = None
        self.delay = 2.0

    def request(self, url):
        if self.last_request is not None:
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        try:
            return monitor.request_bytes(url, self.source)
        finally:
            self.last_request = time.monotonic()

    def __call__(self, url):
        if self.policy_error:
            raise monitor.MonitorError(self.policy_error)
        if self.policy is None:
            try:
                body, _, kind = self.request('https://www.mafra.go.kr/robots.txt')
                if 'html' in kind.lower():
                    raise monitor.MonitorError('robots 정책 응답 확인 필요')
                self.policy = urllib.robotparser.RobotFileParser()
                self.policy.parse(body.decode('utf-8-sig').splitlines())
                self.delay = max(2, self.policy.crawl_delay(monitor.USER_AGENT) or 0)
            except Exception as error:
                self.policy_error = monitor.safe_error(error)
                raise
        if not self.policy.can_fetch(monitor.USER_AGENT, url):
            raise monitor.MonitorError('robots 정책에서 본문 접근을 허용하지 않음')
        return self.request(url)


def latest_body(connection, notice_id):
    if not monitor.has_table(connection, 'body_versions'):
        return None
    row = connection.execute('SELECT * FROM body_versions WHERE notice_id=? ORDER BY body_version_id DESC LIMIT 1', (notice_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result['attachments'] = json.loads(result.pop('attachments_json'))
    result['extracted'] = json.loads(result.pop('extracted_json'))
    return result


def collect_bodies(connection, source, notice_id=None, fetcher=None):
    # Exact pilot allowlist; no arbitrary URL, board or source can be requested.
    rows = [dict(r) for r in connection.execute('SELECT * FROM discovered_notices WHERE source_id=? ORDER BY original_id', ('mafra-notices-rss',))
            if r['original_id'] in {'791:' + n for n in PILOT_IDS}]
    if notice_id:
        rows = [r for r in rows if r['notice_id'] == notice_id]
    if not rows or len(rows) > 13 or source['source_id'] != 'mafra-notices-rss' or not source['enabled']:
        raise monitor.MonitorError('지정된 농식품부 시범 공고 13건만 수집할 수 있습니다.')
    connection.executescript(SCHEMA)
    fetcher = fetcher or OfficialBodyFetcher(source)
    results = []
    for row in rows:
        result = {'notice_id': row['notice_id'], 'status': 'access_failed', 'change_type': None,
                  'classification': 'unknown', 'extraction_status': 'not_attempted'}
        # Lock makes the daily guard and write atomic, including competing CLI runs.
        with connection:
            connection.execute('BEGIN IMMEDIATE')
            last = connection.execute('SELECT collected_at FROM body_fetches WHERE notice_id=? ORDER BY fetch_id DESC LIMIT 1', (row['notice_id'],)).fetchone()
            if last and datetime.now(timezone.utc) - datetime.fromisoformat(last['collected_at']) < timedelta(hours=24):
                result['status'] = 'skipped_interval'
                results.append(result)
                continue
            collected_at = monitor.utc_now()
            raw, http_status, response_hash, error = None, None, None, None
            try:
                url = monitor.canonical_url(row['original_url'], source['allowed_hosts'])
                if not re.fullmatch(r'/bbs/home/791/(?:' + '|'.join(sorted(PILOT_IDS)) + r')/artclView\.do', urllib.parse.urlsplit(url).path):
                    raise monitor.MonitorError('시범 원문 URL 범위 밖의 요청 거부')
                raw, http_status, kind = fetcher(url)
                response_hash = monitor.digest(raw)
                result['status'] = 'extraction_failed'
                if http_status != 200 or 'html' not in kind.lower():
                    raise monitor.MonitorError('정상 HTML 본문 응답이 아님')
                page = parse_page(raw, url, source)
                hints = extract_body(page, url)
                fingerprint = monitor.digest(monitor.packed(page))
                old = latest_body(connection, row['notice_id'])
                change = 'new' if old is None else 'unchanged' if old['content_hash'] == fingerprint else 'modified'
                if not page['body_text'] and old is not None:
                    change = None
                result.update(status='success' if page['body_text'] else 'no_information', change_type=change,
                              classification=hints['classification'], extraction_status=hints['extraction_status'])
            except Exception as exception:
                error = monitor.safe_error(exception)
            cursor = connection.execute('''INSERT INTO body_fetches
              (notice_id,original_url,collected_at,status,change_type,http_status,response_hash,raw_html,error)
              VALUES (?,?,?,?,?,?,?,?,?)''', (row['notice_id'], row['original_url'], collected_at, result['status'],
                                            result['change_type'], http_status, response_hash, raw, error))
            if error is None:
                before = monitor.notice_record(connection, row['notice_id'])
                # An empty body is not proof that previously reviewed content changed.
                if change != 'unchanged' and (page['body_text'] or old is None):
                    connection.execute('''INSERT INTO body_versions
                      (notice_id,fetch_id,content_hash,collected_at,page_title,body_text,attachments_json,extracted_json,rights_hint)
                      VALUES (?,?,?,?,?,?,?,?,?)''', (row['notice_id'], cursor.lastrowid, fingerprint, collected_at,
                      page['page_title'], page['body_text'], monitor.packed(page['attachments']), monitor.packed(hints), page['rights_hint']))
                    if page['body_text'] and (change == 'modified' or before['publication'] in {'approved', 'approved_reference'}):
                        after = dict(before)
                        after.update(verification_status='unverified', freshness='unknown', publication='review',
                                     application_status='unknown', review_status='pending', target='unknown', region='unknown',
                                     support='unknown', verified_application_period={}, conditions_verified=False,
                                     application_period_verified=False, field_evidence={}, reviewer=None, reviewed_at=None,
                                     approved_by=None, approved_at=None)
                        monitor.save_review(connection, before, after, 'body_changed', 'body-collector',
                                            '본문/첨부 메타데이터 변경 또는 최초 본문 기준선: 재검토 필요')
                result['attachment_count'] = len(page['attachments'])
            else:
                result['error'] = error
        results.append(result)
    return results
