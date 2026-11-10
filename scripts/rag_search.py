"""Offline evidence retrieval for three reviewed notices. No network or LLM.

Only explicitly selected source ranges linked to pinned approved explanations are
indexed. Only the CLI's latest execution result is written, under private work/.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DETAILS = Path('assets/support-details.json')
SNAPSHOT = Path('work/support-p0-2/public.json')
SOURCE_DIR = Path('work/support-p0-2')
LATEST_RESULT = ROOT / 'work/rag-search/latest-result.json'

# Each range uses 1-based extracted-text lines, NOT PDF pages. Changing a pinned
# version requires a new review of both the approval and the selected passages.
SPECS = {
    'buan': {
        'id': 'NOTICE-0e7513c42a20a18de5949c24',
        'record_sha': '82b48eb5ef903223cc3c12f35be51ee8acdefc3288fa58271479f05dd74d7bbd',
        'original': '371110.hwpx',
        'original_sha': 'a15cb57cce2d10c32f644b157c5ce504e195665374802975a6310ba43e48aa82',
        'text': '371110-attachment.txt',
        'text_sha': '6e570954f77cfd008af9b9b80243215da7270e01025f932e8e9db16023fe7b4b',
        'passages': [
            ('conditions', 102, 102), ('conditions', 103, 103),
            ('funding', 55, 56), ('method', 106, 106),
            ('documents_required', 120, 125),
            ('documents_conditional', 126, 127),
            ('documents_conditional', 130, 137),
            ('documents_conditional', 139, 147),
            ('warnings', 104, 104),
        ],
    },
    'gochang': {
        'id': 'NOTICE-3239df22b6d0dd3ed8cc7557',
        'record_sha': 'ab151ec334737ccb6cdc48deac6fc9898ec8f2c50c68f8a080453b0aa3f57f71',
        'original': '836510.hwpx',
        'original_sha': 'd7d1190ddae14c04bdde7da8937079b4b60eb2b96b8a8e3687697e96703d6af4',
        'text': '836510-attachment.txt',
        'text_sha': 'c8287b4ea1574437e942355504ff6831ae225d1861f7d38543171da4192a9fbe',
        'passages': [
            ('conditions', 38, 38), ('conditions', 56, 56),
            ('method', 40, 40), ('documents_required', 42, 43),
            ('warnings', 23, 23), ('funding', 26, 26),
        ],
    },
    'paju': {
        'id': 'NOTICE-2ad9a2d4eca77d3de20ec09e',
        'record_sha': '5e4689bf4e659202c05e4afe5d891f29297f48cf78ba8b82848794fd08f44e99',
        'original': 'NOTICE-2ad9a2d4eca77d3de20ec09e.html',
        'original_sha': '03316d5eef45ba4ca536f6893e7415adc303e7993308c83400867f2bac589573',
        'text': 'NOTICE-2ad9a2d4eca77d3de20ec09e.txt',
        'text_sha': 'f9ce8a40af9e2ae999945975ed27a73f2fbfc18d52030eaa8ad1fe3a8fd400c2',
        'passages': [
            ('conditions', 499, 500), ('conditions', 504, 504),
            ('conditions', 507, 507),
            ('documents_conditional', 501, 501), ('funding', 502, 502),
            ('documents_required', 508, 508, '▪ 제출서류 : 사업신청서, 사업계획서, 농업경영체 등록확인서, 견적서 및 설계도'),
            ('method', 510, 511),
            ('warnings', 513, 517),
        ],
    },
}

# Reviewed public explanations: summary versions, never represented as original documents.
EXPANDED_SPECS = {'at_safety': {'id': 'NOTICE-e99ca7409dc98cd24fa4e992',
               'record_sha': '8c62fdf81ce19d352cf0a7d90ddbc53d092da0421dcf717f031101408d839b52',
               'original_sha': '8c62fdf81ce19d352cf0a7d90ddbc53d092da0421dcf717f031101408d839b52',
               'summary_only': True},
 'garlic': {'id': 'NOTICE-2593a32e903d2f3e3ac46fea',
            'record_sha': 'd22560f3c053c42dcec0ecc38edc89c2ce7051e5a21b144002b24961a8cd02f5',
            'original_sha': 'd22560f3c053c42dcec0ecc38edc89c2ce7051e5a21b144002b24961a8cd02f5',
            'summary_only': True},
 'pohang': {'id': 'NOTICE-3c1fa3ff958b07b3b63d44c4',
            'record_sha': '07dcd5ffd5342720db17aa0eb324625174bfa0033f66aad651a6be614697933f',
            'original_sha': '07dcd5ffd5342720db17aa0eb324625174bfa0033f66aad651a6be614697933f',
            'summary_only': True},
 'import_safety': {'id': 'NOTICE-4753ef5fedcfd8ce196e53ce',
                   'record_sha': '7066f1447814e477919bb6540155b384b86aec788fa50e212b8cc24692f63363',
                   'original_sha': '7066f1447814e477919bb6540155b384b86aec788fa50e212b8cc24692f63363',
                   'summary_only': True},
 'vietnam_dc': {'id': 'NOTICE-5db02076c5e5481f3b1a50af',
                'record_sha': '3ee9fd8712dcad662917aa5d3a0776deb1a1fc29f458db2cdbc1bef58c9605d8',
                'original_sha': '3ee9fd8712dcad662917aa5d3a0776deb1a1fc29f458db2cdbc1bef58c9605d8',
                'summary_only': True},
 'japan': {'id': 'NOTICE-6256203b1389e81e3666cda8',
           'record_sha': '87d1d295fb0696b1756bd4e0090adac68c6c2c537d9449c70aa933d465538f33',
           'original_sha': '87d1d295fb0696b1756bd4e0090adac68c6c2c537d9449c70aa933d465538f33',
           'summary_only': True},
 'jeonju_fuel': {'id': 'NOTICE-ad792916c9574b1c4b48e414',
                 'record_sha': '0370cd59386044eac0f8789a6720ec33b7c96632fae6f6d3bf9eb312da3c8458',
                 'original_sha': '0370cd59386044eac0f8789a6720ec33b7c96632fae6f6d3bf9eb312da3c8458',
                 'summary_only': True},
 'kfresh': {'id': 'NOTICE-c0a58a0bf6c10446688ce877',
            'record_sha': '71c21293c0aca657bb5d8ca71886f758ecec54fd280aefb34dbcfc0dbc2fddfd',
            'original_sha': '71c21293c0aca657bb5d8ca71886f758ecec54fd280aefb34dbcfc0dbc2fddfd',
            'summary_only': True}}
CURRENT_SNAPSHOT = Path("work/rag-search/current-public-snapshot.json")

EXTRA_ALIASES = {
    'at_safety': ('aT 안전성', 'at 안전성', '수출 안전성'),
    'garlic': ('마늘', '재해보험'), 'pohang': ('포항', '농지 임대료'),
    'import_safety': ('국내반입', '국내 반입', '해외농업'),
    'vietnam_dc': ('베트남', '물류센터', 'dc'),
    'japan': ('대일', '일본', '사전등록'), 'jeonju_fuel': ('전주', '면세유'),
    'kfresh': ('k-fresh', 'kfresh', '글로벌성장패키지'),
}
FOLLOW_UP = {
    'buan': ['신청 단체의 유형·인원과 대표자의 주소 기준일 충족 여부를 알려주세요.'],
    'gochang': ['귀농 창업·주택구입 대출 실행 및 이자 납부 여부를 알려주세요.'],
    'paju': ['농지 소재지, 고추 재배 여부와 설치하려는 시설면적을 알려주세요.'],
    'garlic': ['마늘 농지 소재지와 농업경영체 등록 여부를 알려주세요.'],
    'pohang': ['거주지, 농업경영체 등록과 농지은행 임대차 계약 여부를 알려주세요. 연령 기준은 담당기관 확인이 필요합니다.'],
    'import_safety': ['신청 기업의 해외농업 사업계획 신고 여부와 직접 생산·반입 품목을 알려주세요.'],
    'at_safety': ['신청 기업의 수출 품목·실적과 검사 종류를 알려주세요.'],
    'vietnam_dc': ['수출 품목과 베트남 물류센터 이용 계획을 알려주세요.'],
    'japan': ['수출 품목·실적과 생산시설의 위생관리 요건 해당 여부를 알려주세요.'],
    'jeonju_fuel': ['주소지, 농업경영체 등록과 면세유 구입카드 발급 여부를 알려주세요.'],
    'kfresh': ['수출 품목·실적과 통합조직 회원가입 여부를 알려주세요.'],
}


def summary_chunks(key, spec, record, item):
    """Only pinned, already approved factual summaries; never invent raw quotes."""
    chunks = []
    for field in LABELS:
        reviewed = record['fields'].get(field)
        if not reviewed:
            continue
        evidence = reviewed['evidence']
        if (not valid_url(evidence['url']) or not evidence.get('location')
                or datetime.fromisoformat(evidence['checked_at']).tzinfo is None):
            raise ValueError('승인 요약의 공식 출처·확인일이 부족합니다.')
        value = reviewed['value']
        if not isinstance(value, (str, list)) or isinstance(value, list) and not all(isinstance(v, str) for v in value):
            raise ValueError('승인 요약의 내용 형식이 올바르지 않습니다.')
        summary = value if isinstance(value, str) else ' / '.join(value)
        if not summary.strip():
            raise ValueError('승인 요약의 내용이 비어 있습니다.')
        unknown = list(record['fields'].get('unconfirmed', {}).get('value', []))
        unknown.append('저장된 승인 요약 근거이며 원문 직접 인용이 아닙니다. 원문·첨부 전체 및 최신 변경 여부를 이번에 재확인하지 않았습니다.')
        chunks.append({
            'chunk_id': key + '-' + field, 'notice_key': key, 'notice_id': spec['id'],
            'business_name': item['title'], 'field': field, 'topic': LABELS[field],
            'evidence_sentence': '', 'approved_summary': summary,
            'source_material_kind': 'approved_summary',
            'official_source': record['fields']['conditions']['evidence']['url'],
            'approval_evidence_source': evidence['url'], 'notice_source': item['url'],
            'evidence_location': evidence['location'],
            'local_excerpt_location': str(DETAILS) + '#' + spec['id'] + '/fields/' + field,
            'document_version': 'sha256:' + spec['record_sha'],
            'document_version_kind': 'approved_summary_record_not_original_file',
            'text_version': None, 'approval_version': 'sha256:' + spec['record_sha'],
            'checked_at': evidence['checked_at'], 'approval_reference': record['approval']['reference'],
            'unconfirmed': unknown, 'local_only': True,
        })
    if not chunks or not any(c['field'] == 'conditions' for c in chunks):
        raise ValueError('승인된 자격조건 근거가 없어 제외했습니다.')
    return chunks

LABELS = {
    'summary': '지원 내용',
    'conditions': '신청 자격·조건', 'funding': '지원 금액·비율',
    'method': '신청 방법·접수처', 'documents_required': '필수 제출서류',
    'documents_conditional': '해당자 제출서류', 'warnings': '제외·중복지원·주의사항',
}
TOPICS = {
    'summary': ('지원내용', '지원 내용', '어떤 지원', '무슨 사업'),
    'conditions': ('자격', '대상', '개인', '혼자', '인원', '대표', '연령', '나이', '주소', '거주', '면적', '시설', '등록', '교육'),
    'funding': ('지원금', '금액', '비율', '자부담', '한도', '얼마', '몇퍼센트'),
    'method': ('신청방법', '신청 방법', '접수', '어디', '방문'),
    'documents_required': ('서류', '준비물', '증빙'),
    'documents_conditional': ('서류', '교육', '이수증', '법인', '품목모임체'),
    'warnings': ('제외', '중복', '체납', '부정수급', '포기', '제한'),
}
ALIASES = {'buan': ('부안',), 'gochang': ('고창', '이차보전'), 'paju': ('파주', '고추비가림', '고추 비가림')}
STOP = {'신청', '지원', '사업', '공고', '가능', '가능한가요', '가능해요', '필요', '필요한',
        '알려줘', '알려주세요', '궁금해요', '무엇인가요', '어떻게', '해주세요', '무농사'}
NOTICE = '저장된 검증 문서의 근거 검색입니다. 현재 접수 가능 여부나 전체 신청 자격을 판정하지 않습니다.'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def record_sha(record):
    return sha(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def basis(item):
    """Same binding as assets/support-details.js; do not mix revisions."""
    def date(part):
        return {'date': part['date'], 'time': part.get('time'), 'timezone': part.get('timezone')} if part and part.get('date') else None
    facts = item.get('reference_application_dates', {})
    eligibility = item.get('eligibility') or {}
    return {**{k: item.get(k) for k in ('id', 'url', 'title', 'target', 'region')},
            'dates': {k: date(facts.get(k)) for k in ('start', 'end')},
            'period': item.get('application_period') or {},
            'eligibility': {'conditions': [{k: c.get(k) for k in ('condition_id', 'kind', 'presence', 'status', 'value')}
                                           for c in eligibility.get('conditions', [])], 'logic': eligibility.get('logic')}}


def valid_url(url):
    u = urlsplit(url)
    return u.scheme == 'https' and u.hostname in {'www.buan.go.kr', 'www.gochang.go.kr', 'www.rda.go.kr', 'www.jeonbuk.go.kr', 'www.oads.or.kr', 'global.at.or.kr', 'www.jeonju.go.kr'} and not u.username and not u.password and not u.port


def load_corpus(root=ROOT, snapshot=SNAPSHOT, *, expanded=False):
    """Read only. Missing/changed/unapproved documents fail closed individually."""
    specs = {**SPECS, **EXPANDED_SPECS} if expanded else SPECS
    if expanded and snapshot == SNAPSHOT:
        snapshot = CURRENT_SNAPSHOT
    details = read_json(root / DETAILS)
    public = read_json(root / snapshot)
    if details.get('schema') != 'munongsa-support-details-v1' or details.get('preview') is not False:
        raise ValueError('승인된 설명 자료 형식이 아니어서 검색을 중단했습니다.')
    if public.get('schema_version') != 'munongsa-support-public-v1':
        raise ValueError('공개 승인 스냅샷 형식이 올바르지 않습니다.')
    chunks, excluded, documents = [], [], {}
    for key, spec in specs.items():
        try:
            records = [r for r in details['records'] if r.get('basis', {}).get('id') == spec['id']]
            notices = [n for n in public['notices'] if n.get('id') == spec['id']]
            if len(records) != 1 or len(notices) != 1:
                raise ValueError('승인 자료가 없거나 같은 ID가 중복됐습니다.')
            record, item = records[0], notices[0]
            approval = record.get('approval', {})
            if (approval.get('state') != 'approved' or not all(approval.get(k) for k in ('reviewer', 'reference', 'checked_at'))
                    or record.get('rights', {}).get('facts_only') is not True):
                raise ValueError('설명 정보의 공개 승인이 확인되지 않습니다.')
            if (item.get('publication') not in ('approved', 'approved_reference')
                    or item.get('verification_status') != 'verified' or item.get('freshness') != 'current'
                    or item.get('rights', {}).get('public_display') != 'allowed'):
                raise ValueError('공고의 공개·검증 상태가 확인되지 않습니다.')
            if record['basis'] != basis(item) or record_sha(record) != spec['record_sha']:
                raise ValueError('승인 버전이 바뀌었습니다. 근거 구간을 재검토해야 합니다.')
            if spec.get('summary_only'):
                local_chunks = summary_chunks(key, spec, record, item)
                chunks.extend(local_chunks)
                documents[key] = {'record': record, 'public': item}
                continue
            original, text_path = root / SOURCE_DIR / spec['original'], root / SOURCE_DIR / spec['text']
            raw, extracted = original.read_bytes(), text_path.read_bytes()
            if sha(raw) != spec['original_sha'] or sha(extracted) != spec['text_sha']:
                raise ValueError('원문 또는 추출 텍스트 버전이 바뀌어 제외했습니다.')
            lines = extracted.decode('utf-8').splitlines()
            local_chunks = []
            for number, passage in enumerate(spec['passages'], 1):
                field, first, last = passage[:3]
                reviewed = record['fields'][field]
                e = reviewed['evidence']
                if not valid_url(e['url']) or not e.get('location') or datetime.fromisoformat(e['checked_at']).tzinfo is None:
                    raise ValueError('필드별 공식 근거·확인일이 부족합니다.')
                excerpt = '\n'.join(lines[first - 1:last]).strip()
                if not excerpt or last > len(lines):
                    raise ValueError('검토한 원문 구간을 찾지 못했습니다.')
                if len(passage) == 4:
                    if passage[3] not in excerpt:
                        raise ValueError('검토한 부분 발췌를 찾지 못했습니다.')
                    excerpt = passage[3]
                value = reviewed['value']
                summary = value if isinstance(value, str) else ' / '.join(value)
                local_chunks.append({
                    'chunk_id': f'{key}-{number}', 'notice_key': key, 'notice_id': spec['id'],
                    'business_name': item['title'], 'field': field, 'topic': LABELS[field],
                    'evidence_sentence': excerpt, 'approved_summary': summary,
                    'official_source': record['fields']['conditions']['evidence']['url'],
                    'approval_evidence_source': e['url'], 'notice_source': item['url'],
                    'evidence_location': e['location'],
                    'local_excerpt_location': f'{SOURCE_DIR / spec["text"]}:{first}-{last} (추출 텍스트 행; 원문 쪽수 아님)',
                    'document_version': 'sha256:' + spec['original_sha'],
                    'text_version': 'sha256:' + spec['text_sha'],
                    'approval_version': 'sha256:' + spec['record_sha'],
                    'checked_at': e['checked_at'], 'approval_reference': approval['reference'],
                    'unconfirmed': record['fields'].get('unconfirmed', {}).get('value', []),
                    'local_only': True,
                })
            chunks.extend(local_chunks)
            documents[key] = {'record': record, 'public': item}
        except (KeyError, TypeError, ValueError, OSError) as error:
            # No partial document is retained after any validation failure.
            excluded.append({'notice_key': key, 'notice_id': spec['id'], 'reason': str(error)})
    return {'chunks': chunks, 'excluded': excluded, 'documents': documents,
            'snapshot_as_of': public.get('generated_at'), 'specs': specs,
            'aliases': {**ALIASES, **EXTRA_ALIASES} if expanded else ALIASES, 'expanded': expanded}


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).casefold()).strip()


def query_terms(query, aliases=None):
    q = normalize(query)
    tokens = set(re.findall(r'[가-힣a-z0-9]+', q))
    for token in list(tokens):
        for ending in ('인가요', '할까요', '있나요', '에서', '으로', '에게', '은', '는', '이', '가', '을', '를', '도'):
            if token.endswith(ending) and len(token) - len(ending) >= 2:
                tokens.add(token[:-len(ending)])
                break
    tokens.update(normalize(word) for words in TOPICS.values() for word in words if normalize(word) in q)
    if '혼자' in q:
        tokens.add('개인')
    if '몇 명' in q or '몇명' in q:
        tokens.add('인원')
    if '어디' in q:
        tokens.add('접수')
    if '얼마' in q:
        tokens.add('금액')
    business_words = {normalize(v) for names in (ALIASES if aliases is None else aliases).values() for v in names}
    return {t for t in tokens if len(t) >= 2 and t not in STOP and t not in business_words}


def recruitment_context(document, as_of):
    """Date metadata is independent of eligibility and actual reception status."""
    dates = document['record']['basis']['dates']
    start, end = dates.get('start'), dates.get('end')
    kst = as_of.astimezone(timezone(timedelta(hours=9)))
    state, conflicts = 'unknown', []
    try:
        first = datetime.strptime(start['date'], '%Y-%m-%d').date() if start else None
        last = datetime.strptime(end['date'], '%Y-%m-%d').date() if end else None
        if first and last and first > last:
            conflicts.append('기재 신청 시작일이 마감일보다 늦습니다.')
        elif last and kst.date() > last:
            state = 'elapsed'
        elif first and kst.date() < first:
            state = 'upcoming'
        elif first and last:
            state = 'deadline_day_time_unknown' if kst.date() == last else 'within_recorded_dates'
            if end.get('time') and end.get('timezone') == 'Asia/Seoul':
                closing = datetime.fromisoformat(end['date'] + 'T' + end['time'] + '+09:00')
                state = 'elapsed' if kst >= closing else 'within_recorded_dates'
    except (TypeError, ValueError, KeyError):
        conflicts.append('기재 신청기간을 정확하게 해석할 수 없습니다.')
    labels = {'unknown': '신청기간 확인 필요', 'elapsed': '기재 모집기간 경과 · 연장 여부 별도 확인',
              'upcoming': '기재 모집 시작일 전', 'within_recorded_dates': '기재 모집기간 내 · 실제 접수 여부 미확인',
              'deadline_day_time_unknown': '기재 마감일 당일 · 마감 시각 미확인'}
    return {'recorded_dates': dates, 'date_state': state, 'date_message': labels[state],
            'as_of_kst': kst.isoformat(), 'actual_reception': 'unverified',
            'basis': '해시로 고정된 승인 공고 기준정보의 날짜이며 최신 접수 상태는 조회하지 않았습니다.',
            'official_source': document['record']['basis']['url'],
            'evidence_location': '승인 공고 기준정보의 신청기간', 'conflicts': conflicts}


def group_evidence(query, corpus, results, scope, unresolved, as_of):
    """Add bounded, reviewed context without changing keyword hits or judgments."""
    specs = corpus.get('specs', SPECS)
    keys = scope or {r['notice_key'] for r in results}
    groups = []
    for key in sorted(keys):
        related = [r for r in results if r['notice_key'] == key]
        document = corpus.get('documents', {}).get(key)
        if document is None:
            groups.append({'notice_id': specs[key]['id'], 'notice_key': key,
                           'business_name': key,
                           'question_evidence': [], 'key_eligibility': [],
                           'evidence_status': 'data_unavailable', 'application_eligibility': 'not_determined',
                           'answer_policy': 'abstain',
                           'issues': ['승인·문서 검사를 통과한 자료가 없어 자격조건을 제공하지 않습니다.']})
            continue
        record, spec = document['record'], specs[key]
        fields = record['fields']
        core = []
        for field in ('conditions', 'warnings', 'documents_conditional'):
            if field not in fields:
                continue
            f = fields[field]
            core.append({'topic': LABELS[field],
                         'approved_values': f['value'] if isinstance(f['value'], list) else [f['value']],
                         'official_source': f['evidence']['url'],
                         'evidence_location': f['evidence']['location'],
                         'checked_at': f['evidence']['checked_at'],
                         'document_version': 'sha256:' + spec['original_sha'],
                         'evidence_passages': [c for c in corpus['chunks']
                                               if c['notice_key'] == key and c['field'] == field]})
        unknown = fields.get('unconfirmed', {})
        unknown_values = unknown.get('value', [])
        if isinstance(unknown_values, str):
            unknown_values = [unknown_values]
        period = recruitment_context(document, as_of)
        conflicts = list(period['conflicts'])
        if key == 'pohang':
            conflicts.append('포항 연령 기준 충돌: 만 나이와 출생연도 범위의 적용 기준 확인 전 연령 적합 여부를 판단하지 않습니다.')
        conflicts.extend(v for v in unknown_values if any(w in v for w in ('기준 충돌', '근거 충돌', '상충')))
        versions = {(c['document_version'], c['approval_version']) for c in corpus['chunks'] if c['notice_key'] == key}
        if len(versions) != 1 or versions != {('sha256:' + spec['original_sha'], 'sha256:' + spec['record_sha'])}:
            conflicts.append('같은 사업의 근거 문서 또는 승인 버전이 서로 다릅니다.')
        calc_unverified = key == 'gochang' and (unresolved or any(w in normalize(query) for w in ('계산', '예상액', '예상 지원액')))
        status = ('conflicting_evidence' if conflicts else 'verification_required' if calc_unverified
                  else 'keyword_evidence_found' if related else 'no_question_evidence')
        issues = ['확인된 일부 조건 목록이며 전체 자격조건을 빠짐없이 확보했다는 뜻이 아닙니다.']
        if not related:
            issues.append('질문에 직접 관련된 검색 근거가 없습니다. 공통 자격조건만으로 질문에 답하면 안 됩니다.')
        if calc_unverified:
            issues.append('고창 1% 계산 기준 미확인: 관련 일반 근거가 있어도 예상 지원액 계산에 사용할 수 없습니다.')
        if conflicts:
            issues.append('근거가 충돌하여 답변을 보류해야 합니다. 한쪽 근거를 임의로 선택하면 안 됩니다.')
        groups.append({'notice_key': key, 'notice_id': spec['id'], 'business_name': record['basis']['title'],
                       'official_source': record['basis']['url'],
                       'document_version': 'sha256:' + spec['original_sha'],
                       'approval_version': 'sha256:' + spec['record_sha'],
                       'checked_at': fields['conditions']['evidence']['checked_at'],
                       'question_evidence': related, 'key_eligibility': core,
                       'unconfirmed_conditions': {'statements': unknown_values, 'evidence': unknown.get('evidence', {})},
                       'recruitment': period, 'evidence_status': status, 'conflicts': conflicts, 'issues': issues,
                       'answer_policy': 'grounded_explanation_only' if status == 'keyword_evidence_found' else 'abstain',
                       'eligibility_evidence_complete': False, 'application_eligibility': 'not_determined',
                       'must_review_together': True,
                       'source_material_kind': 'approved_summary' if spec.get('summary_only') else 'original_excerpt',
                       'document_version_kind': 'approved_summary_record_not_original_file' if spec.get('summary_only') else 'original_file',
                       'follow_up_questions': FOLLOW_UP.get(key, []) if any(w in normalize(query) for w in ('신청', '자격', '가능', '대상')) else []})
    return groups


def search(query, corpus, notice=None, limit=3, as_of=None):
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise ValueError('질문은 1~1,000자로 입력해 주세요.')
    specs = corpus.get('specs', SPECS)
    if notice is not None and notice not in specs:
        raise ValueError('검색 가능한 사업은 buan, gochang, paju입니다.')
    if not 1 <= limit <= 10:
        raise ValueError('결과 수는 1~10개로 지정해 주세요.')
    as_of = as_of or datetime.now(timezone(timedelta(hours=9)))
    if as_of.tzinfo is None:
        raise ValueError('기간 비교 시각에는 시간대가 필요합니다.')
    q = normalize(query)
    scope = {notice} if notice else {k for k, names in corpus.get('aliases', ALIASES).items() if any(normalize(n) in q for n in names)}
    terms = query_terms(query, corpus.get('aliases', ALIASES))
    results = []
    excluded = [r for r in corpus['excluded'] if not scope or r['notice_key'] in scope]
    # The unresolved 1% rule is not a calculable entitlement. Do not retrieve its
    # ambiguous raw sentence as a verified rule just because it contains keywords.
    unresolved = ('gochang' in scope and any(w in q for w in ('1%', '1퍼센트')))
    for chunk in corpus['chunks']:
        if scope and chunk['notice_key'] not in scope or unresolved:
            continue
        text = normalize(chunk['evidence_sentence'] + ' ' + chunk['approved_summary'] + ' ' + chunk['topic'])
        matches = sorted(t for t in terms if t in text)
        topic_hit = sum(normalize(w) in q for w in TOPICS[chunk['field']])
        if not matches:
            continue
        quote = normalize(chunk['evidence_sentence'])
        score = sum(min(len(t), 6) * (3 if t in quote else 1) for t in matches) + 8 * bool(topic_hit)
        results.append({**chunk, 'matched_keywords': matches, 'score': score})
    results.sort(key=lambda r: (-r['score'], r['notice_id'], r['chunk_id']))
    results = results[:limit]
    status = 'found' if results else 'verification_required' if unresolved else 'data_unavailable' if excluded else 'not_found'
    messages = {'found': '질문과 관련된 검토 근거를 찾았습니다. 근거 문장과 미확인 항목을 함께 확인하세요.',
                'not_found': '검색 실패: 승인·검증된 범위에서 질문과 관련된 근거를 찾지 못했습니다.',
                'data_unavailable': '검색 실패: 해당 자료가 없거나 승인·문서 버전 검사를 통과하지 못했습니다.',
                'verification_required': '검색 실패: 고창 원문의 1% 계산 기준은 미확인입니다. 지원액 계산 근거로 사용할 수 없습니다.'}
    businesses = group_evidence(query, corpus, results, scope, unresolved, as_of)
    safety = ('conflicting_evidence' if any(g['evidence_status'] == 'conflicting_evidence' for g in businesses)
              else 'verification_required' if any(g['evidence_status'] == 'verification_required' for g in businesses)
              else 'limited_evidence' if results else 'no_question_evidence')
    return {'result_schema': 'munongsa-local-evidence-v2', 'evidence_safety': safety,
            'status': status, 'message': messages[status], 'query': query,
            'snapshot_as_of': corpus['snapshot_as_of'], 'notice': NOTICE,
            'local_only': True, 'results': results, 'businesses': businesses, 'excluded': excluded,
            'expanded_local_only': corpus.get('expanded', False),
            'usage_limits': ['results는 기존 키워드 검색 결과이며 안전한 활용에는 businesses의 필수 확인 맥락을 함께 사용해야 합니다.',
                             '검색 성공·날짜상 기간 내·조건 일부 일치를 신청 가능 확정으로 해석하지 마세요.',
                             '상충 또는 미확인 상태는 답변 보류·추가 확인 대상으로 유지하세요.'],
            'conflict_detection_scope': '기록된 충돌 문구·문서/승인 버전·날짜 역전만 검사합니다. 일반 문장 간 의미 충돌을 자동 판별하지 않습니다.'}


def save_latest(result):
    """Atomic replacement: never leave a half-written latest result."""
    destination = LATEST_RESULT
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.' + result['execution']['run_id'] + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='무농사 승인 근거 로컬 검색 — 외부 전송·생성형 답변 없음')
    parser.add_argument('question', nargs='?', help='생략하면 터미널에서 한 번 입력')
    parser.add_argument('--notice', choices=tuple({**SPECS, **EXPANDED_SPECS}))
    parser.add_argument('--all-public', action='store_true', help='로컬에서 승인된 공개 11건의 요약 근거까지 검색')
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--json', action='store_true', help='기계 판독용 결과')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    execution = {'run_id': uuid.uuid4().hex,
                 'started_at_kst': datetime.now(timezone(timedelta(hours=9))).isoformat()}
    question, exit_code, json_output = None, 0, False
    try:
        args = parser.parse_args(argv)
        json_output = args.json
        question = args.question if args.question is not None else input('질문: ')
        result = search(question, load_corpus(expanded=args.all_public), args.notice, args.limit)
    except SystemExit as error:
        if error.code == 0:
            return 0  # --help is not a search execution.
        exit_code = 2
        result = {'status': 'error', 'message': '검색 중단: 실행 인수가 올바르지 않습니다.',
                  'query': question, 'results': [], 'local_only': True}
    except (ValueError, OSError, KeyError, TypeError, EOFError, KeyboardInterrupt) as error:
        exit_code = 2
        result = {'status': 'error', 'message': '검색 중단: ' + (str(error) or '입력이 취소됐습니다.'),
                  'query': question, 'results': [], 'local_only': True}
    execution['completed_at_kst'] = datetime.now(timezone(timedelta(hours=9))).isoformat()
    result.update(execution=execution, exit_code=exit_code, result_file=str(LATEST_RESULT))
    try:
        save_latest(result)
    except OSError as error:
        # Old files must not be mistaken for this run after a write failure.
        print('결과 파일 저장 실패: 이번 실행은 파일로 확인할 수 없습니다. ' + str(error), file=sys.stderr)
        result['result_file_saved'] = False
        result['exit_code'] = exit_code = 3
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result['status'] == 'error':
            print(result['message'], file=sys.stderr)
        else:
            print(result['message'] + '\n' + NOTICE)
            print('승인 스냅샷 기준: ' + str(result['snapshot_as_of']))
            for r in result['results']:
                print(f'\n[{r["business_name"]}] {r["topic"]}\n공고 ID: {r["notice_id"]}')
                print('원문 발췌: ' + r['evidence_sentence'] if r['evidence_sentence'] else '원문 발췌 없음: 버전이 고정된 승인 요약입니다.')
                print('승인 요약(직접 인용 아님): ' + r['approved_summary'])
                print('공식 출처: ' + r['official_source'])
                print('기존 검증 위치: ' + r['evidence_location'])
                print('발췌 위치: ' + r['local_excerpt_location'])
                print('확인일: ' + datetime.fromisoformat(r['checked_at']).astimezone(timezone(timedelta(hours=9))).isoformat())
                print('문서 버전: ' + r['document_version'])
                if r['unconfirmed']:
                    print('미확인: ' + ' / '.join(r['unconfirmed']))
            for e in result['excluded']:
                print('자료 제외: ' + e['notice_key'] + ' — ' + e['reason'])
            for group in result['businesses']:
                print('\n함께 확인: ' + group.get('business_name', group['notice_id']))
                for core in group['key_eligibility']:
                    print(core['topic'] + ': ' + ' / '.join(core['approved_values']))
                if group.get('recruitment'):
                    print('모집기간: ' + group['recruitment']['date_message'])
                for issue in group['issues']:
                    print('주의: ' + issue)
                for conflict in group.get('conflicts', []):
                    print('충돌: ' + conflict)
        if exit_code != 3:
            print('실행 결과 저장: ' + str(LATEST_RESULT))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
