"""Disabled Bizinfo ingestion plus an explicitly invoked, non-persisting probe.

Contract: https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoApi
Scheduled ingestion stays disabled. Explicit manual collection supplies a single-
request transport after confirmation and backup. The probe never writes a DB.
"""
import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import support_monitor as monitor


ENDPOINT = 'https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do'
KEY_ENV = 'BIZINFO_API_KEY'
PARAMETERS = {'dataType', 'searchCnt', 'searchLclasId', 'hashtags', 'pageUnit', 'pageIndex'}


class BizinfoError(monitor.MonitorError):
    def __init__(self, code, stage=None):
        allowed = {'missing_key; configure BIZINFO_API_KEY in server environment',
                   'live_transport_disabled; mock transport only in this stage',
                   'invalid_endpoint', 'invalid_parameters', 'unsafe_or_unbounded_request',
                   'authentication_failed', 'rate_limited', 'http_error', 'schema_error',
                   'empty_response', 'response_too_large', 'api_response_error', 'unsafe_xml',
                   'too_many_items', 'conflicting_identifiers', 'missing_or_invalid_id',
                   'missing_required_field', 'unsafe_notice_url', 'transport_error'}
        code = code if code in allowed else 'adapter_error'
        self.code = code
        self.stage = stage if stage in {'json_root', 'json_envelope', 'json_items', 'item_type',
                                       'item_field_type', 'invalid_json', 'invalid_encoding',
                                       'invalid_xml', 'xml_envelope'} else None
        # Never interpolate exceptions, response bodies, key values or request URLs.
        super().__init__('bizinfo: ' + code)


def read_key(environ=None):
    env = os.environ if environ is None else environ
    value = env.get(KEY_ENV, '').strip()
    if not value:
        raise BizinfoError('missing_key; configure BIZINFO_API_KEY in server environment')
    return value


def check_configuration(source, environ=None):
    read_key(environ)
    return {'source_id': source['source_id'], 'key_configured': True,
            'enabled': bool(source['enabled']), 'live_transport': 'disabled',
            'official_call_quota': 'unknown'}


def prepare_request(source, environ=None):
    key = read_key(environ)
    if source.get('discovery_url') != ENDPOINT:
        raise BizinfoError('invalid_endpoint')
    params = dict(source.get('parameters', {}))
    if set(params) - PARAMETERS or params.get('dataType') not in {'json', 'rss'}:
        raise BizinfoError('invalid_parameters')
    # These are local pilot bounds, not an assertion about the provider's quota.
    for field in ('searchCnt', 'pageUnit', 'pageIndex'):
        value = str(params.get(field, ''))
        if not value.isdigit() or int(value) < 1 or int(value) > (1000 if field == 'pageIndex' else 50):
            raise BizinfoError('unsafe_or_unbounded_request')
    params['crtfcKey'] = key
    return urllib.request.Request(ENDPOINT + '?' + urllib.parse.urlencode(params),
                                  headers={'User-Agent': monitor.USER_AGENT, 'Accept': 'application/json, application/rss+xml'})


def reject_status(status):
    if status in (401, 403):
        raise BizinfoError('authentication_failed')
    if status == 429:
        raise BizinfoError('rate_limited')
    if status != 200:
        raise BizinfoError('http_error')


def alias(item, *names):
    values = [item[n] for n in names if item.get(n) not in (None, '')]
    if any(not isinstance(v, str) for v in values):
        raise BizinfoError('schema_error', 'item_field_type')
    return values[0] if values else ''


def parse_response(raw, source):
    if not raw or not raw.strip():
        raise BizinfoError('empty_response')
    if len(raw) > monitor.MAX_BYTES:
        raise BizinfoError('response_too_large')
    try:
        text = raw.decode('utf-8-sig')
        if text.lstrip().startswith(('{', '[')):
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise BizinfoError('schema_error', 'json_root')
            if 'error' in payload or 'errors' in payload:
                raise BizinfoError('api_response_error')
            channel = payload.get('jsonArray')
            if isinstance(channel, list):
                # Confirmed by the user's live, redacted structure diagnostic.
                items = channel
            elif isinstance(channel, dict) and 'item' in channel:
                items = channel['item']
                if isinstance(items, dict):
                    items = [items]
            else:
                raise BizinfoError('schema_error', 'json_envelope')
        else:
            probe = raw.replace(b'\0', b'').upper()
            if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
                raise BizinfoError('unsafe_xml')
            root = ET.fromstring(text)
            if root.tag != 'rss' or root.find('channel') is None:
                raise BizinfoError('schema_error', 'xml_envelope')
            items = [{node.tag: ''.join(node.itertext()).strip() for node in element}
                     for element in root.findall('./channel/item')]
        if not isinstance(items, list):
            raise BizinfoError('schema_error', 'json_items')
        if not items:
            raise BizinfoError('empty_response')
        if len(items) > source.get('max_items', 50):
            raise BizinfoError('too_many_items')
        result = []
        for item in items:
            if not isinstance(item, dict):
                raise BizinfoError('schema_error', 'item_type')
            identity = alias(item, 'seq', 'pblancId')
            if item.get('seq') and item.get('pblancId') and item['seq'] != item['pblancId']:
                raise BizinfoError('conflicting_identifiers')
            if not re.fullmatch(r'PBLN_[A-Za-z0-9_]+', identity):
                raise BizinfoError('missing_or_invalid_id')
            title = monitor.plain(alias(item, 'title', 'pblancNm'))
            url = alias(item, 'link', 'pblancUrl')
            if not title or not url:
                raise BizinfoError('missing_required_field')
            url = monitor.canonical_url(url, source['allowed_hosts'])
            parsed_url = urllib.parse.urlsplit(url)
            # An API request/credential-bearing URL is never accepted as a notice URL.
            query = urllib.parse.parse_qs(parsed_url.query)
            if parsed_url.path == urllib.parse.urlsplit(ENDPOINT).path or any(k.lower() in {'crtfckey','servicekey','api_key','token'} for k in query):
                raise BizinfoError('unsafe_notice_url')
            url_id = query.get('pblancId', [])
            if url_id and url_id != [identity]:
                raise BizinfoError('conflicting_identifiers')
            posted = alias(item, 'pubDate', 'creatPnttm')
            record = {'original_id': identity, 'title': title, 'original_url': url,
                      'published_at_raw': posted, 'published_at': monitor.published_iso(posted),
                      'description': monitor.plain(alias(item, 'description', 'bsnsSumryCn')),
                      'category_as_recorded': alias(item, 'lcategory', 'pldirSportRealmLclasCodeNm'),
                      'api_fields': {'target': alias(item, 'trgetNm'),
                                     'application_period': alias(item, 'reqstDt', 'reqstBeginEndDe'),
                                     'agency': alias(item, 'author', 'jrsdInsttNm'),
                                     'implementing_agency': alias(item, 'excInsttNm'),
                                     'application_method': alias(item, 'reqstMthPapersCn')}}
            # inqireCo, channel clocks, credentials, contact fields and unknown fields
            # are excluded. View-count changes must not trigger a review reset.
            result.append(record)
        return result
    except BizinfoError:
        raise
    except json.JSONDecodeError:
        raise BizinfoError('schema_error', 'invalid_json') from None
    except UnicodeDecodeError:
        raise BizinfoError('schema_error', 'invalid_encoding') from None
    except ET.ParseError:
        raise BizinfoError('schema_error', 'invalid_xml') from None
    except Exception:
        raise BizinfoError('schema_error') from None


def redact(value, secret):
    if isinstance(value, dict):
        return {k: redact(v, secret) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secret) for v in value]
    if isinstance(value, str):
        for variant in sorted({secret, urllib.parse.quote(secret, safe=''), urllib.parse.quote_plus(secret)}, key=len, reverse=True):
            if variant:
                value = value.replace(variant, '[REDACTED]')
        return re.sub(r'(?i)((?:crtfcKey|serviceKey|api_key|token)\s*[=:]\s*)[^&\s<>"\']+', r'\1[REDACTED]', value)
    return value


def extract_hints(item):
    hints = monitor.extract_hints(item)
    fields = item['api_fields']
    for field in ('target', 'application_method'):
        if fields[field]:
            hints[field] = fields[field]
            hints['evidence'][field] = {'url': item['original_url'], 'location': 'API item.' + field, 'quote': fields[field], 'verification_status': 'unverified'}
    if item['description']:
        hints['support'] = item['description']
        hints['evidence']['support'] = {'url': item['original_url'], 'location': 'API item.description/bsnsSumryCn', 'verification_status': 'unverified'}
    value = fields['application_period']
    hints['application_period_as_recorded'] = value or 'unknown'
    match = re.fullmatch(r'(\d{8}|\d{4}-\d{2}-\d{2})\s*~\s*(\d{8}|\d{4}-\d{2}-\d{2})', value)
    if match:
        try:
            start, end = [datetime.strptime(v, '%Y-%m-%d' if '-' in v else '%Y%m%d').date().isoformat() for v in match.groups()]
            if start <= end:
                hints['application_period'] = {'start': start, 'end': end, 'timezone': 'Asia/Seoul', 'end_time': 'unknown'}
                hints['evidence']['application_period'] = {'url': item['original_url'], 'location': 'API item.reqstDt/reqstBeginEndDe', 'quote': value, 'verification_status': 'unverified'}
        except ValueError:
            pass
    # API dates/keywords do not establish current availability or eligibility.
    hints['application_status'] = 'unknown'
    evidence_text = ' '.join((item['title'], item['description'], fields['target']))
    hints['agriculture_relation'] = 'keyword_related' if re.search(r'농업|농식품|농촌|농가|청년농|귀농|스마트팜|축산|원예|농산물', evidence_text) else 'unknown'
    hints['agriculture_relation_status'] = 'unverified'
    # A relation to agriculture is separate from who may actually apply.
    target = fields['target'] or (hints['target'] if hints['target'] != 'unknown' else '')
    groups = {
        'direct_farmer_support': bool(re.search(r'개인\s*농업인|청년\s*농업인|귀농인', target)),
        'business_support': bool(re.search(r'농업\s*법인|농업회사법인|영농조합법인|기업|사업자', target)),
        'institution_call': bool(re.search(r'지방자치단체|지자체|기관|단체|대학', target)),
    }
    matches = [name for name, yes in groups.items() if yes]
    hints['classification'] = matches[0] if len(matches) == 1 and not re.search(r'제외|불가|아닌|할\s*수\s*없', target) else 'unknown'
    if not target and re.search(r'지정\s*결과|선정\s*결과|공개\s*검증|보도자료', evidence_text):
        hints['classification'] = 'policy_reference'
    hints['classification_status'] = 'unverified'
    hints['individual_farmer_eligibility'] = 'unknown'
    return hints


def collect_bizinfo(connection, source, *, transport=None, environ=None, force=False):
    if not source['enabled']:
        return monitor.collect_source(connection, source, force=force)
    secret = read_key(environ)
    if transport is None:
        raise BizinfoError('live_transport_disabled; mock transport only in this stage')
    def fetch(_):
        try:
            request = prepare_request(source, environ)
            raw, status, kind = transport(request, timeout=15)
            reject_status(status)
            normalized = redact(parse_response(raw, source), secret)
            # Never persist raw API/error responses: they can echo a key or URL.
            sanitized = monitor.packed({'items': normalized}).encode('utf-8')
            return sanitized, 200, 'application/json; profile=private-normalized'
        except urllib.error.HTTPError as error:
            reject_status(error.code)
            raise BizinfoError('http_error') from None
        except BizinfoError:
            raise
        except Exception:
            raise BizinfoError('transport_error') from None
    return monitor.collect_source(connection, source, fetcher=fetch, extractor=extract_hints,
                                  parser=lambda raw, _: json.loads(raw)['items'], force=force)


class NoProbeRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        # Refuse even same-host redirects: never forward a credential to a new URL.
        return None


def response_structure(raw, secret=''):
    """Bounded shape only. Unknown field names/messages/values never leave memory."""
    allowed = set(('jsonArray item items rss channel data result results response header body '
                   'error errors code resultCode errorCode status statusCode success message resultMsg '
                   'totalCount totCnt title link seq pblancId pblancNm pblancUrl author excInsttNm '
                   'description lcategory pubDate reqstDt trgetNm inqireCo flpthNm fileNm '
                   'printFlpthNm printFileNm hashTags jrsdInsttNm bsnsSumryCn reqstMthPapersCn '
                   'refrncNm rceptEngnHmpgUrl pldirSportRealmLclasCodeNm creatPnttm reqstBeginEndDe').split())
    codes = {'401','403','429','200','00','OK','SUCCESS','UNAUTHORIZED','FORBIDDEN',
             'INVALID_KEY','INVALID_SERVICE_KEY','AUTHENTICATION_FAILED','RATE_LIMITED','TOO_MANY_REQUESTS'}
    error_fields = {'code','resultCode','errorCode','statusCode'}
    def shape(value, depth=0, field=None):
        if isinstance(value, dict):
            keys = sorted(k for k in value if k in allowed and (not secret or secret not in k))
            return {'type':'object', 'fields': {k:shape(value[k],depth+1,k) for k in keys[:45]} if depth<4 else {},
                    'hidden_field_count':len(value)-len(keys[:45]) if depth<4 else len(value)}
        if isinstance(value, list):
            return {'type':'array','length':len(value), 'sample_structure':shape(value[0],depth+1) if value and depth<4 else None}
        result = {'type':'null' if value is None else 'boolean' if isinstance(value,bool) else
                  'number' if isinstance(value,(int,float)) else 'string'}
        if field in error_fields and isinstance(value,(str,int)) and not isinstance(value,bool):
            code = str(value)
            result['safe_code'] = code if code in codes and (not secret or secret not in code) else 'withheld'
        return result
    if len(raw)>monitor.MAX_BYTES:
        return {'inspection':'size_limit'}
    try:
        text=raw.decode('utf-8-sig')
        if text.lstrip().startswith(('{','[')):
            return {'inspection':'json_shape', 'structure':shape(json.loads(text))}
        return {'inspection':'non_json; no body disclosed'}
    except Exception:
        return {'inspection':'unparseable; no body disclosed'}


def probe_transport(request, *, timeout):
    """One GET attempt, no retry/redirect, no response or exception logging."""
    opener = urllib.request.build_opener(NoProbeRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(monitor.MAX_BYTES + 1)
            return raw, response.status, response.headers.get('Content-Type', '')
    except urllib.error.HTTPError as error:
        # Discard error body/URL (either could echo the key).
        status = error.code
        error.close()
        return b'', status, ''


def backup_database(source_path, target_path):
    """Consistent SQLite backup (including WAL); never overwrites an earlier backup."""
    target_path = Path(target_path)
    descriptor = os.open(str(target_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    original = snapshot = None
    try:
        original = sqlite3.connect(Path(source_path).resolve().as_uri() + '?mode=ro', uri=True)
        snapshot = sqlite3.connect(target_path)
        original.backup(snapshot)
        if snapshot.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise BizinfoError('adapter_error')
    finally:
        if snapshot is not None:
            snapshot.close()
        if original is not None:
            original.close()


def manual_collect(source, *, state_dir=monitor.DEFAULT_STATE, confirm_live=False,
                   confirm_db_write=False, limit=10, environ=None, transport=None):
    """One explicit bounded request: trial clone by default, review DB only with opt-in."""
    if not confirm_live:
        raise monitor.MonitorError('수동 수집은 --confirm-live 확인이 필요합니다.')
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise monitor.MonitorError('수동 수집 limit은 1~20건이어야 합니다.')
    read_key(environ)  # before folders, DB, backup or network
    if source['source_id'] != 'bizinfo-support-api' or source['enabled']:
        raise monitor.MonitorError('기업마당 운영 정보원은 비활성 상태여야 합니다.')
    params = {**source.get('parameters', {}), 'dataType': 'json', 'searchCnt': str(limit),
              'pageUnit': str(limit), 'pageIndex': '1'}
    active = {**source, 'enabled': True, 'parameters': params, 'max_items': limit}
    prepare_request(active, environ)  # validate before any side effects; never print it
    folder = Path(state_dir).resolve()
    for public in (monitor.ROOT / 'data', monitor.ROOT / 'assets'):
        if folder == public or public in folder.parents:
            raise monitor.MonitorError('공개 경로에 검토 DB를 저장할 수 없습니다.')
    original = folder / 'monitor.sqlite3'
    if not original.is_file():
        raise monitor.MonitorError('기존 검토 DB가 없습니다. 자동 생성하지 않습니다.')
    backups = folder / 'backups'
    backups.mkdir(exist_ok=True, mode=0o700)
    identifier = uuid4().hex
    backup = backups / ('before-bizinfo-' + identifier + '.sqlite3')
    backup_database(original, backup)  # must succeed before opening a writable DB/request
    target = folder
    if not confirm_db_write:
        target = folder / 'trials' / ('bizinfo-' + identifier)
        target.mkdir(parents=True, mode=0o700)
        backup_database(backup, target / 'monitor.sqlite3')
    connection = monitor.connect(target, require_existing=True)
    count = 0
    try:
        # Persist only the original disabled registration, not the in-memory request switch.
        monitor.register_sources(connection, [source])
        def one_request(request, **kwargs):
            nonlocal count
            if count:
                raise BizinfoError('transport_error')
            count += 1
            return (transport or probe_transport)(request, **kwargs)
        result = collect_bizinfo(connection, active, transport=one_request, environ=environ)
        categories = {}
        agriculture = 0
        if result.get('run_id'):
            for row in connection.execute('SELECT hints_json FROM notice_versions WHERE run_id=?', (result['run_id'],)):
                hints = json.loads(row[0])
                category = hints.get('classification', 'unknown')
                categories[category] = categories.get(category, 0) + 1
                agriculture += hints.get('agriculture_relation') == 'keyword_related'
        return {**result, 'request_count': count,
                'storage_mode': 'review_db' if confirm_db_write else 'trial_clone',
                'state_dir': str(target), 'backup_file': str(backup),
                'classification_counts_new_or_modified': categories,
                'agriculture_related_new_or_modified': agriculture,
                'operational_source_enabled': False}
    finally:
        connection.close()



def jeonbuk_trial(source, *, state_dir=monitor.DEFAULT_STATE, confirm_live=False,
                  limit=20, environ=None, transport=None, output_root=None):
    """One Jeonbuk request, isolated snapshot and offline replay; no source activation."""
    if not confirm_live:
        raise monitor.MonitorError('전북 시험 수집에는 --confirm-live가 필요합니다.')
    read_key(environ)  # fail before creating files or opening DBs
    if source['source_id'] != 'bizinfo-support-api' or source['enabled']:
        raise monitor.MonitorError('기존 기업마당 정보원은 비활성 상태여야 합니다.')
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise monitor.MonitorError('조회 건수는 1~20건이어야 합니다.')
    active = {**source, 'enabled': True, 'max_items': limit, 'parameters': {
        'dataType': 'json', 'searchCnt': str(limit), 'pageUnit': str(limit),
        'pageIndex': '1', 'hashtags': '전북'}}
    prepare_request(active, environ)  # validate without emitting credential URL
    original = Path(state_dir).resolve() / 'monitor.sqlite3'
    if not original.is_file():
        raise monitor.MonitorError('복사할 기존 검토 DB가 없습니다.')
    # All new files are private and separate from the original state directory.
    root = Path(output_root or monitor.ROOT / 'work/bizinfo-jeonbuk-trials').resolve()
    private = (monitor.ROOT / 'work').resolve()
    if root != private and private not in root.parents:
        raise monitor.MonitorError('시험 결과는 비공개 work 경로에만 저장할 수 있습니다.')
    folder = root / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    backup_database(original, folder / 'monitor.sqlite3')
    connection = monitor.connect(folder, require_existing=True)
    count = 0
    http_status = None
    def one_request(request, **kwargs):
        nonlocal count, http_status
        if count:
            raise BizinfoError('transport_error')
        count += 1
        raw, http_status, kind = (transport or probe_transport)(request, **kwargs)
        return raw, http_status, kind
    report = {'status': 'failed', 'request_count': 0, 'http_status': None,
              'region_filter': '전북', 'region_eligibility': 'unknown',
              'storage_mode': 'trial_clone', 'state_dir': str(folder),
              'operational_source_enabled': False, 'public_files_written': False,
              'reuse_permission': 'unknown; no publication or recommendation',
              'agriculture_related': 0, 'notices': []}
    try:
        monitor.register_sources(connection, [source])
        first = collect_bizinfo(connection, active, transport=one_request,
                                environ=environ, force=True)
        report.update(first=first, request_count=count, http_status=http_status)
        if first['status'] != 'success':
            report['error'] = first.get('error', 'extraction_failed')
            return report
        run = connection.execute('SELECT raw_response,content_type FROM crawl_runs WHERE run_id=?',
                                 (first['run_id'],)).fetchone()
        # This DB response was already parsed and redacted by collect_bizinfo.
        cached = bytes(run['raw_response'])
        items = json.loads(cached)['items']
        before = [tuple(row) for row in connection.execute(
            'SELECT notice_id,content_hash,publication,verification_status,application_status FROM discovered_notices ORDER BY notice_id')]
        versions = connection.execute('SELECT count(*) FROM notice_versions').fetchone()[0]
        replay = monitor.collect_source(connection, active,
            fetcher=lambda _: (cached, 200, run['content_type']), extractor=extract_hints,
            parser=lambda raw, _: json.loads(raw)['items'], force=True)
        after = [tuple(row) for row in connection.execute(
            'SELECT notice_id,content_hash,publication,verification_status,application_status FROM discovered_notices ORDER BY notice_id')]
        passed = (replay['status'] == 'success' and replay['new'] == replay['modified'] == 0
                  and replay['unchanged'] == len(items) and before == after
                  and connection.execute('SELECT count(*) FROM notice_versions').fetchone()[0] == versions)
        report.update(replay=replay, duplicate_check='passed' if passed else 'failed',
                      status='success' if passed else 'failed')
        for item in items:
            hints = extract_hints(item)
            notice_id = 'NOTICE-' + monitor.digest(source['source_id'] + '\n' + item['original_id'])[:24]
            row = connection.execute('SELECT publication,verification_status,application_status FROM discovered_notices WHERE notice_id=?',
                                     (notice_id,)).fetchone()
            report['notices'].append({
                'notice_id': notice_id, 'original_id': item['original_id'], 'title': item['title'],
                'official_url': item['original_url'], 'published_at': item['published_at'],
                'application_period_as_recorded': hints['application_period_as_recorded'],
                'application_period': hints['application_period'],
                'classification': hints['classification'],
                'agriculture_relation': hints['agriculture_relation'],
                'region_mention': monitor.review_region_hint(item),
                'individual_farmer_eligibility': 'unknown', **dict(row)})
            report['agriculture_related'] += hints['agriculture_relation'] == 'keyword_related'
        return report
    finally:
        connection.close()
        # Persist only a sanitized summary, never the original API response/request URL.
        (folder / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def probe_connection(source, *, confirm=False, environ=None, transport=None, diagnose=False):
    """Return only safe aggregate diagnostics; never calls collect/connect/save."""
    summary = {'status': 'not_started', 'request_count': 0, 'http_status': None,
               'authentication': 'not_checked', 'response_format': 'not_received',
               'records': 0, 'field_counts': {}, 'agriculture_title_matches': 0,
               'error': None, 'operational_source_enabled': bool(source['enabled'])}
    if not confirm:
        summary['error'] = 'confirmation_required; use --confirm-live'
        return summary
    try:
        # Small sample, no pagination or search broadening. Keep the actual source disabled.
        params = {**source.get('parameters', {}), 'dataType': 'json',
                  'searchCnt': '3', 'pageUnit': '3', 'pageIndex': '1'}
        probe_source = {**source, 'parameters': params}
        request = prepare_request(probe_source, environ)
    except BizinfoError as error:
        summary['error'] = error.code
        return summary
    except Exception:
        summary['error'] = 'invalid_configuration'
        return summary
    summary['request_count'] = 1
    try:
        raw, status, kind = (transport or probe_transport)(request, timeout=15)
        summary['http_status'] = status
        if status == 401:
            summary.update(status='failed', authentication='rejected', error='authentication_failed')
            return summary
        if status == 403:
            summary.update(status='failed', error='access_denied')
            return summary
        if status == 429:
            summary.update(status='failed', error='rate_limited')
            return summary
        if 300 <= status < 400:
            summary.update(status='failed', error='redirect_refused')
            return summary
        if status != 200:
            summary.update(status='failed', error='http_error')
            return summary
        probe = raw.lstrip().lower()
        fmt = ('json' if probe.startswith((b'{', b'[')) else
               'html' if probe.startswith((b'<!doctype html', b'<html')) or 'text/html' in kind.lower() else
               'xml' if probe.startswith(b'<') else 'unknown')
        summary['response_format'] = fmt
        if diagnose:
            summary['response_structure'] = response_structure(raw, read_key(environ))
        records = parse_response(raw, probe_source)
        summary.update(status='success', authentication='accepted_with_data', records=len(records))
        # Only aggregate presence counts; no title, URL, raw field or key is returned.
        summary['field_counts'] = {label: sum(bool(row.get(field)) for row in records)
                                   for label, field in [('id', 'original_id'), ('title', 'title'),
                                                        ('published_at', 'published_at'), ('original_url', 'original_url')]}
        summary['agriculture_title_matches'] = sum(bool(re.search(r'농업|농식품|농촌|농가|청년농|귀농|스마트팜|축산|원예', row['title']))
                                                   for row in records)
        return summary
    except BizinfoError as error:
        summary.update(status='failed', error=error.code)
        if diagnose and error.stage:
            summary['parse_stage'] = error.stage
    except Exception:
        # Never stringify a network exception, request, response, or API key.
        summary.update(status='failed', error='transport_or_response_error')
    return summary
