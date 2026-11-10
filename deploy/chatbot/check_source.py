"""Focused offline source/release checks. No network, service control or result writes."""
import argparse
import copy
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import socket
import ssl
import sys
from unittest.mock import patch

import render_units
import stage_host_release

ROOT = Path(__file__).resolve().parents[2]
CASES = [
    ('buan', '부안 개인 신청이 가능한가요?', '5인 이상'),
    ('gochang', '고창 1% 이차보전 지원액 계산', '계산'),
    ('paju', '파주 고추비가림 시설의 최소 면적은?', '330㎡'),
    ('garlic', '전북 마늘 재해보험 지원 대상은?', '전북 마늘'),
    ('pohang', '포항 농지 임대료 연령 자격은?', '연령 기준 충돌'),
    ('import_safety', '국내반입 안전성 검사 지원 대상은?', '일반 개인농 대상 사업 아님'),
    ('at_safety', 'aT 안전성 검사비 지원금 한도는?', '8천만원'),
    ('vietnam_dc', '베트남 물류센터 지원 대상은?', '수출'),
    ('japan', '일본 사전등록 지원 대상은?', 'HACCP'),
    ('jeonju_fuel', '전주 면세유 신청 대상은?', '전주시 주소'),
    ('kfresh', 'K-Fresh 통합조직 신청 대상은?', '1만 달러'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', type=Path, required=True)
    args = parser.parse_args()
    app = args.release.resolve() / 'app'
    manifest = json.loads((ROOT/'deploy/chatbot/source-manifest.json').read_text(encoding='utf-8'))
    checks = []

    def check(name, test):
        test()
        checks.append(name)

    def require(value):
        if not value:
            raise AssertionError('focused verification failed')

    def reject(fn):
        try:
            fn()
        except (ValueError, FileNotFoundError):
            return
        raise AssertionError('unsafe candidate accepted')

    def hashes():
        for name, expected in (manifest['runtime'] | manifest['private_corpus']).items():
            require(stage_host_release.digest(app/name) == expected)
        for name, expected in manifest['web'].items():
            require(stage_host_release.digest(ROOT/name) == expected)
        for name, expected in manifest['runtime'].items():
            source = ROOT/name if Path(name).name.startswith('rag_') else ROOT/'deploy/chatbot'/Path(name).name
            require(stage_host_release.digest(source) == expected)
    check('reviewed_source_and_private_release_hashes', hashes)
    values = dict(RELEASE_DIR='/opt/example-release', VENV_DIR='/opt/example-venv',
                  SERVICE_USER='example_chat', BRIDGE_GATEWAY='172.20.0.1',
                  NGINX_PEER='172.20.0.2', BRIDGE_INTERFACE='example0')
    units = render_units.render(values)
    check('unit_hardening', lambda: require(all(x in units['munongsa-chat-api.service'] for x in
          ('PrivateNetwork=yes', 'SystemCallFilter=~connect', 'MemoryMax=128M',
           'MemorySwapMax=0', 'NoNewPrivileges=yes', '/usr/bin/env -i'))))
    for key, value in [('SERVICE_USER','root'), ('BRIDGE_GATEWAY','0.0.0.0'), ('VENV_DIR','/a\nExecStart=/bin/false')]:
        check('reject_settings_'+key, lambda key=key,value=value: reject(lambda: render_units.render(values|{key:value})))
    check('docker_chat_and_seo_inputs', lambda: require(all((ROOT/n).is_file() and '!'+n in (ROOT/'.dockerignore').read_text()
          for n in ('robots.txt','sitemap.xml','google47097a3f576b2117.html','naver27efe6015ca42de5395a94c7796d92da.html'))
          and 'COPY assets/' in (ROOT/'Dockerfile').read_text()
          and '/assets/chat-ui.js' in (ROOT/'Dockerfile').read_text()))

    sys.path.insert(0, str(app/'scripts'))
    import rag_api
    import chat_wsgi
    from host_proxy_entry import PeerOnly
    search, answer = rag_api.rag_search, rag_api.rag_answer
    as_of = datetime.fromisoformat('2026-11-10T21:00:00+09:00')

    def forbidden(*a, **k):
        raise AssertionError('network forbidden')

    def pipeline(question, corpus):
        with patch.object(socket,'socket',side_effect=forbidden):
            return answer.generate(search.search(question,corpus,as_of=as_of),
                                   local_only=True,manifest={},environ={})

    corpus = rag_api.load_api_corpus()
    old = search.load_corpus()
    check('11_approved_70_passages_original_3_23_preserved', lambda: require(
        len(corpus['documents'])==11 and len(corpus['chunks'])==70 and not corpus['excluded']
        and len(old['documents'])==3 and len(old['chunks'])==23
        and [c for c in corpus['chunks'] if c['notice_key'] in search.SPECS]==old['chunks']))
    for key, question, expected in CASES:
        def representative(key=key,question=question,expected=expected):
            result = pipeline(question,corpus)
            require({b['notice_key'] for b in result['businesses']}=={key})
            require(expected in result['answer_generation']['local_answer'])
            require(not result['answer_generation']['llm_called'])
            response = rag_api.public_response(result)
            require(response['mode']=='local' and response['programs'])
            require(all(p['source_url'] and p['checked_at'] and p['evidence_level'] for p in response['programs']))
            require(all(b['application_eligibility']=='not_determined' and
                        b['recruitment']['actual_reception']=='unverified' for b in result['businesses']))
        check('representative_'+key,representative)
    check('summary_never_presented_as_raw_quote', lambda: require(all(
        not c['evidence_sentence'] and c['document_version_kind']=='approved_summary_record_not_original_file'
        for c in corpus['chunks'] if c['notice_key'] in search.EXPANDED_SPECS)))
    check('no_evidence',lambda: require(pipeline('양자컴퓨터 초전도 큐비트',corpus)['status']=='not_found'))
    check('unverified_calculation_abstains',lambda: require(pipeline(CASES[1][1],corpus)['businesses'][0]['answer_policy']=='abstain'))
    check('elapsed_not_currently_receiving',lambda: require(pipeline(CASES[2][1],corpus)['businesses'][0]['recruitment']['date_state']=='elapsed'))
    for change in ('approval','summary','publication','deleted','duplicate'):
        def tamper(change=change):
            details = copy.deepcopy(search.read_json(app/search.DETAILS))
            public = copy.deepcopy(search.read_json(app/search.CURRENT_SNAPSHOT))
            identity = search.EXPANDED_SPECS['garlic']['id']
            record = next(r for r in details['records'] if r['basis']['id']==identity)
            notice = next(n for n in public['notices'] if n['id']==identity)
            if change=='approval': record['approval']['state']='review'
            if change=='summary': record['fields']['conditions']['value']=['unverified replacement']
            if change=='publication': notice['publication']='review'
            if change=='deleted': public['notices'].remove(notice)
            if change=='duplicate': public['notices'].append(notice)
            with patch.object(search,'read_json',side_effect=[details,public]):
                broken=search.load_corpus(expanded=True)
            require('garlic' not in broken['documents'])
            require(pipeline('마늘 신청 자격',broken)['status']=='data_unavailable')
        check('fail_closed_'+change,tamper)
    def forced_local():
        with patch.object(answer,'transmission_allowed',side_effect=forbidden):
            result=answer.generate(search.search('마늘 지원 대상',corpus,as_of=as_of),
                                   local_only=False,manifest={},environ={},transport=forbidden)
        require(not result['answer_generation']['llm_called'])
    check('expanded_forces_local_only',forced_local)
    def wsgi():
        def request(origin='https://munongsa.duckdns.org',peer='172.20.0.2'):
            data=json.dumps({'question':CASES[0][1]}).encode()
            env=dict(PATH_INFO='/api/chat',REQUEST_METHOD='POST',HTTP_HOST='munongsa.duckdns.org',
                     HTTP_ORIGIN=origin,REMOTE_ADDR=peer,CONTENT_TYPE='application/json',CONTENT_LENGTH=str(len(data)))
            env['wsgi.input']=io.BytesIO(data)
            statuses=[]
            wrapped=PeerOnly(chat_wsgi.Application(pipeline=lambda q:rag_api.public_response(pipeline(q,corpus)),ready=True),'172.20.0.2')
            body=b''.join(wrapped(env,lambda status,headers:statuses.append(status)))
            return statuses[0],json.loads(body)
        status,result=request()
        require(status.startswith('200') and result['mode']=='local')
        require(request(origin='https://untrusted.invalid')[0].startswith('403'))
        require(request(peer='172.20.0.3')[0].startswith('403'))
    check('wsgi_request_and_origin_real_peer_access',wsgi)
    print(json.dumps({'passed':len(checks),'checks':checks,'external_llm_calls':0,'aws_changes':False}))


if __name__=='__main__':
    main()
