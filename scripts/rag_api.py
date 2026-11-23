"""Loopback-only, local-evidence API. No keys, remote LLM, DB or result-file writes."""
import argparse
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import rag_answer
import rag_search

API_PATH = '/api/chat'
MAX_QUESTION = 3000  # Bounded list versions + profile; the user question stays <=1,000.
MAX_BODY = 8192
PIPELINE_TIMEOUT = 8
REQUEST_TIMEOUT = 15
EXPECTED_DOCUMENTS = 11


def load_api_corpus():
    # Explicit server selection; request parameters cannot change the corpus or mode.
    directory = os.environ.get('MUNONGSA_RAG_SYNC_DIR')
    if directory:
        import rag_sync
        return rag_sync.load(directory)
    return rag_search.load_corpus(expanded=True)


def corpus_ready(corpus):
    if corpus.get('sync_generation'):
        return corpus.get('sync_verified') is True
    return not corpus['excluded'] and len(corpus['documents']) == EXPECTED_DOCUMENTS


class VerificationError(Exception):
    pass


def validate_input(data):
    if not isinstance(data, dict) or set(data) != {'question'}:
        raise ValueError('invalid_input')
    question = data['question']
    if (not isinstance(question, str) or not 1 <= len(question.strip()) <= MAX_QUESTION
            or len(question) > MAX_QUESTION
            or any((ord(c) < 32 and c not in '\n\t\r') or 0xD800 <= ord(c) <= 0xDFFF for c in question)):
        raise ValueError('invalid_question')
    import rag_dialogue
    rag_dialogue.decode(question)
    return question.strip()


def failure(message):
    return {'mode': 'local', 'status': 'error', 'answer': message, 'programs': [], 'sources': []}


def checked_at(value):
    value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        raise VerificationError()
    return value.astimezone(rag_answer.KST).isoformat()


def public_source(value):
    if not rag_search.valid_url(value['url']):
        raise VerificationError()
    return {'url': value['url'], 'location': value['location'], 'checked_at': checked_at(value['checked_at'])}


def public_response(result):
    """Allowlist public fields; never serialize retrieval internals or raw exceptions."""
    if result.get('excluded') or result.get('status') == 'data_unavailable':
        raise VerificationError()
    if result.get('status') == 'not_found':
        return {'mode': 'local', 'status': 'no_evidence',
                'answer': '공개 승인된 공고의 저장 근거에서 질문에 답할 내용을 찾지 못했습니다. 사업명이나 질문을 바꿔 주세요.',
                'programs': [], 'sources': []}
    groups = result.get('businesses', [])
    if not groups or any(g.get('evidence_status') == 'data_unavailable' for g in groups):
        raise VerificationError()
    generation = result['answer_generation']
    if generation.get('llm_called') or not result.get('local_only'):
        raise VerificationError()
    programs = []
    for group in groups:
        if not rag_search.valid_url(group['official_source']):
            raise VerificationError()
        period = group['recruitment']
        dates = period['recorded_dates']
        programs.append({
            'id': group['notice_id'], 'name': group['business_name'],
            'source_url': group['official_source'], 'checked_at': checked_at(group['checked_at']),
            'required_conditions': [v for c in group['key_eligibility'] for v in c['approved_values']],
            'additional_checks': list(group['unconfirmed_conditions']['statements']) + list(group.get('conflicts', [])),
            'evidence_level': '승인된 요약 근거' if group.get('source_material_kind') == 'approved_summary' else '저장 원문 발췌',
            'evidence_note': ('원문 직접 인용이 아닌 기존 승인 요약입니다. 최신 원문 전체를 다시 검증한 답변이 아닙니다.'
                              if group.get('source_material_kind') == 'approved_summary' else
                              '저장된 원문에서 검토한 구간입니다. 최신 변경·전체 자격·실제 접수 여부는 별도 확인이 필요합니다.'),
            'application_period': {
                'start': {k: (dates.get('start') or {}).get(k) for k in ('date', 'time', 'timezone')},
                'end': {k: (dates.get('end') or {}).get(k) for k in ('date', 'time', 'timezone')},
                'description': period['date_message'], 'actual_reception_confirmed': False},
            'needs_verification': group['answer_policy'] != 'grounded_explanation_only'})
    response = {'mode': 'local', 'status': 'needs_verification' if any(p['needs_verification'] for p in programs) else 'answered',
                'answer': generation['local_answer'], 'programs': programs,
                'sources': [public_source(s) for s in generation['local_citations']]}
    # Defense against accidentally introducing local paths into a public text field.
    serialized = json.dumps(response, ensure_ascii=False)
    if re.search(r'(?i)(?:(?<![a-z])[a-z]:[\\/]|file://|(?:work|scripts|assets)[\\/])', serialized):
        raise VerificationError()
    return response


def grounded_response(question, corpus, notice=None):
    retrieved = rag_search.search(question, corpus, notice=notice, limit=3)
    result = rag_answer.generate(retrieved, local_only=True, manifest={}, environ={})
    directory = os.environ.get('MUNONGSA_RAG_SYNC_DIR')
    if directory:
        import rag_sync
        current = rag_sync.load(directory)
        for business in result.get('businesses', []):
            key = business['notice_key']
            if key not in current['documents'] or key not in corpus['documents']:
                raise VerificationError()
            before, after = corpus['documents'][key], current['documents'][key]
            if (rag_search.record_sha(before['record']) != rag_search.record_sha(after['record'])
                    or rag_sync.material(before['public']) != rag_sync.material(after['public'])):
                raise VerificationError()
    return public_response(result)


def local_pipeline(question):
    # No server session or DB writes. Every factual response uses the existing
    # approval/hash loader, including contextual follow-ups and discovery lists.
    corpus = load_api_corpus()
    if not corpus_ready(corpus):
        raise VerificationError()
    import rag_dialogue,rag_nlu
    original,context=rag_dialogue.decode(question)
    import rag_catalogue,rag_crops
    scoped=rag_dialogue.scope_response(question)
    if scoped:
        scoped['understanding']='rules'
        return scoped
    if context.get('casual_topic')=='scope':
        context.pop('casual_topic',None)
        question=rag_dialogue.PREFIX+json.dumps(context,ensure_ascii=False)+rag_dialogue.SEPARATOR+original
    import rag_turn
    turn=rag_turn.resolve(original,context,corpus)
    if turn:
        turn.setdefault('understanding','rules')
        return catalogue_response(turn,corpus) if turn.get('programs') else rag_dialogue.remember(turn,corpus)
    count=rag_catalogue.requested_count(original)
    count_only=bool(count and re.fullmatch(r'(?:그럼\s*|그러면\s*)?\d{1,2}\s*(?:[~～〜\-–]\s*\d{1,2})?\s*개(?:로|\s*정도)?\s*(?:추천|보여|알려|찾아|보고)[가-힣\s.!?]*',original))
    more=bool(re.fullmatch(r'(?:조금\s*)?더\s*(?:보여|알려|찾아)[가-힣\s.!?]*',original))
    if (count_only or more) and context.get('search_query'):
        if more and not context.get('search_offset'):
            return rag_dialogue.response('같은 검색에서 추가로 안내할 관련 공고가 없어요. 검색 지역이나 지원 목적을 바꿀 수 있으며 실제 영농 조건은 유지합니다.',context,'clarify',status='no_evidence')
        query=context['search_query']
        if count_only:
            query=re.sub(r'\d{1,2}\s*(?:[~～〜\-–]\s*\d{1,2})?\s*개(?:로|\s*정도)?','',query).strip()+f' {count}개 추천해 줘'
            if len(query)>300:return rag_dialogue.response('검색 목적을 짧게 알려주시면 요청한 개수로 다시 찾을게요.',context,'clarify')
        kept={k:v for k,v in context.items() if k not in ('notice_ids','list_ids','list_versions','last_kind','search_offset','search_fingerprint')}
        request=rag_catalogue.PAGE_PREFIX+json.dumps({'query':query,'offset':context['search_offset'],'fingerprint':context['search_fingerprint']},ensure_ascii=False) if more else query
        return catalogue_response(rag_catalogue.respond(rag_dialogue.PREFIX+json.dumps(kept,ensure_ascii=False)+rag_dialogue.SEPARATOR+request,corpus),corpus)
    import rag_crops
    if rag_crops.technology(original):
        result=rag_dialogue.service_response(question,corpus)
        if result:result['understanding']='rules';return result
    search_scope=rag_catalogue.scope_request(original)
    if search_scope:
        # Search expansion is routing metadata, not a new residence/farm fact.
        new_purpose=rag_catalogue.requested_count(original) or any(re.search(group[1],original) for group in rag_catalogue.TOPICS) or rag_crops.find(original)
        query=original if new_purpose else context.get('search_query','지원사업 알려줘')
        query=rag_dialogue.normalized(query)
        for area in sorted(rag_dialogue.AREAS,key=len,reverse=True):query=query.replace(area,'')
        query=query.replace('전국','').strip() or '지원사업 알려줘'
        kept={k:v for k,v in context.items() if k not in ('notice_ids','list_ids','list_versions','last_kind','conversation_topic','casual_topic')}
        kept.update(search_scope=search_scope,search_query=query)
        encoded=rag_dialogue.PREFIX+json.dumps(kept,ensure_ascii=False)+rag_dialogue.SEPARATOR+query
        return catalogue_response(rag_catalogue.respond(encoded,corpus),corpus)
    # A new definition question or a follow-up to ordinary conversation must
    # not inherit an old crop/list as the subject. One existing NLU call only.
    explanation=bool(re.search(r'뭐야|무엇(?:이야|인가|인지)|무슨\s*(?:뜻|말)|뜻(?:이|은)|설명|풀어\s*(?:줘|줄)',original))
    knowledge_request=rag_nlu.concept_request(original,context)
    if knowledge_request:
        referential=bool(context.get('conversation_topic')) and bool(re.search(r'그게|그건|그거|그걸|그것|왜|다시|쉽게|풀어|예를|예시|무슨\s*(?:뜻|말)',original)) and not re.search(r'농업|농사|재배|작물|스마트팜|윤작|연작|경영체|독립경영|청년후계농|보조금|융자',original)
        # Resolve the subject, not the answer. No second call or factual history.
        interpreted_question=context['conversation_topic']+'에 대해, 후속 질문: '+original if referential else original
        understood=rag_nlu.interpret(interpreted_question,context)
        reply=rag_nlu.safe_conversation_reply(understood or {},original)
        clean={k:v for k,v in context.items() if k not in ('casual_topic','conversation_topic')}
        live_ids={d['public']['id'] for d in corpus['documents'].values()}|{n['id'] for n in rag_catalogue.records(corpus.get('guidance_feed',{}))}
        if 'notice_ids' in clean:
            clean['notice_ids']=[i for i in clean['notice_ids'] if i in live_ids]
            if not clean['notice_ids']:clean.pop('notice_ids')
        topic=context['conversation_topic'] if referential else (understood or {}).get('topic') or (original if rag_nlu.valid_topic(original) else '')
        if topic and rag_nlu.valid_topic(topic):clean['conversation_topic']=topic
        fallback='현재 AI 설명의 호출 한도에 도달했어요. 지원사업 검색·확인된 자격 비교·신청 준비와 금융·재배기술 자료 찾기는 계속 이용할 수 있어요.' if rag_nlu.failure_reason()=='budget_limit' else '지금은 AI 설명을 확인하지 못했어요. 질문은 유지되며, 지원사업 검색이나 금융·재배기술 자료 찾기는 계속 이용할 수 있어요.'
        out=rag_dialogue.response(reply or fallback,clean,'context',status='answered' if reply else 'needs_verification')
        out['understanding']='gpt' if reply else 'rules'
        return rag_dialogue.remember(out,corpus)
    # An explicit service switch takes precedence over a vague "then" follow-up.
    if re.search(r'대출|융자|정책자금|금융|자금\s*부족|자금이\s*부족|시설\s*(?:설치\s*)?자금',original) and not re.search(r'지원사업|보조금',original):
        clean={k:v for k,v in context.items() if k not in ('conversation_topic','casual_topic')}
        guidance=rag_dialogue.service_response(rag_dialogue.PREFIX+json.dumps(clean,ensure_ascii=False)+rag_dialogue.SEPARATOR+original,corpus)
        if guidance:
            guidance['understanding']='rules'
            return rag_dialogue.remember(guidance,corpus)
    if original.startswith(rag_catalogue.PAGE_PREFIX) or re.fullmatch(r'(?:전체|모든)\s*(?:공식|공개)?\s*(?:공고|지원사업)',original.strip()) or rag_catalogue.archive_requested(original) or re.search(r'신청기간.{0,8}남|기간.{0,5}남은|마감.{0,5}남은',original):
        listing=rag_catalogue.respond(question,corpus)
        return catalogue_response(listing,corpus) if listing else rag_dialogue.response('공개 목록이 변경됐어요. 같은 질문으로 다시 검색해 주세요.',context,'clarify',status='needs_verification')
    def followup_evidence(query,key):
        out=grounded_response(query,corpus,key)
        decorate_cards(out,corpus)
        return out
    if not rag_catalogue.named_records(original,corpus.get('guidance_feed',{})):
        public_followup=rag_catalogue.continuation(question,corpus,followup_evidence)
        if public_followup:return catalogue_response(public_followup,corpus)
    listing=rag_catalogue.respond(question,corpus,explicit=True)
    if listing:return catalogue_response(listing,corpus)
    # A named public business must not be replaced by a generic profile/crop search.
    named=rag_catalogue.named_response(question,corpus)
    if named:return catalogue_response(named,corpus)
    if '경영체' in original and re.search(r'미등록|등록.{0,5}안\s*했',original) and re.search(r'지원받|지원\s*받|가능',original) and not rag_catalogue.named_records(original,corpus.get('guidance_feed',{})):
        facts,error=rag_dialogue.rag_profile.extract(original,rag_dialogue.AREAS,rag_dialogue.CROPS,rag_dialogue.normalized)
        if not error:
            encoded=rag_dialogue.PREFIX+json.dumps({**context,**facts},ensure_ascii=False)+rag_dialogue.SEPARATOR+'선택한 조건으로 지원사업을 찾아주세요.'
            listing=rag_catalogue.respond(encoded,corpus)
            if listing:return catalogue_response(listing,corpus)
    # Exact official names are routed locally; do not send listing titles to NLU.
    compact=lambda value:re.sub(r'[^0-9a-z가-힣]','',rag_dialogue.normalized(value).lower())
    exact=[(key,d) for key,d in corpus['documents'].items() if len(compact(d['public']['title']))>=6 and compact(d['public']['title']) in compact(original)]
    if len(exact)==1:
        key,document=exact[0]
        response=grounded_response(original,corpus,key)
        if not response['programs']:
            # A name lookup can succeed even when no reviewed passage answers it.
            # Return only current public metadata, never invent a detailed answer.
            listing=rag_catalogue.respond(question,corpus,explicit=True,include_approved=True)
            if listing:return catalogue_response(listing,corpus)
        response.update(kind='answer',conversation={**context,'notice_ids':[document['public']['id']]},suggestions=[],understanding='rules')
        decorate_cards(response,corpus)
        return rag_dialogue.remember(response,corpus)
    guidance=rag_dialogue.service_response(question,corpus) or rag_dialogue.continuation(question,corpus,lambda query,notice:grounded_response(query,corpus,notice))
    # Topic discovery is independent of eligibility. Reuse only the validated
    # profile parser; never infer residence from a notice or spend a model call.
    discovery_intent=bool(re.search(r'지원|사업|시설|하우스|농기계|창업|귀농|교육|비료|보험|시작하려|재배하려|영농\s*준비|농사\s*준비',original)) and not re.search(r'신청 가능|자격|서류|방법|마감|그\s*사업|대출|금융|융자',original)
    if discovery_intent and not rag_dialogue.rag_profile.hypothetical(original) and (not guidance or guidance.get('kind')=='help'):
        facts,error=rag_dialogue.rag_profile.extract(original,rag_dialogue.AREAS,rag_dialogue.CROPS,rag_dialogue.normalized)
        if not error:
            discovery_context={k:v for k,v in context.items() if k not in ('notice_ids','list_ids','list_versions','last_kind','search_query')}
            area=rag_dialogue.area_in(original)
            if area:discovery_context['search_scope']=area
            encoded=rag_dialogue.PREFIX+json.dumps({**discovery_context,**facts},ensure_ascii=False)+rag_dialogue.SEPARATOR+original
            listing=rag_catalogue.respond(encoded,corpus)
            if listing:return catalogue_response(listing,corpus)
            if re.search(r'재배하려|농기계|하우스|시설|교육|수출',original):
                return rag_dialogue.response('현재 공개 정보에서 말씀하신 목적과 직접 관련된 공고를 찾지 못했어요. 작물만으로 창업 지원을 원한다고 판단하지 않습니다. 시설 설치·교육·신규 영농 준비 중 어떤 도움을 찾는지 알려주시면 입력한 조건을 유지해 다시 탐색할게요. 신청 자격이 없다는 뜻은 아닙니다.',{**context,**facts},'clarify',status='no_evidence')
    if guidance and not guidance['programs']:
        listing=rag_catalogue.respond(question,corpus,fallback=guidance)
        if listing and guidance.get('kind') in ('catalogue','clarify'):return catalogue_response(listing,corpus)
        guidance['understanding']='rules'
        return rag_dialogue.remember(guidance,corpus)
    # Explicit condition selection already carries the same validated profile.
    # Do not spend a model call reinterpreting this fixed UI action.
    understood=None if guidance or original=='선택한 조건으로 지원사업을 찾아주세요.' else rag_nlu.interpret(original,context)
    used_gpt=understood is not None
    if understood and understood.get('intent')=='other':
        return rag_dialogue.response('어떤 영농 상황이나 사업을 확인하려는지 조금 더 알려주세요. 기존 입력 조건은 유지합니다.',context,'clarify',status='needs_verification')
    if understood and rag_nlu.safe_conversation_reply(understood,original):
        clean={k:v for k,v in context.items() if k not in ('notice_ids','list_ids','list_versions','casual_topic','conversation_topic')}
        topic=understood.get('topic','')
        if topic and rag_nlu.valid_topic(topic):clean['conversation_topic']=topic
        out=rag_dialogue.response(understood['reply'],clean,'context')
        out['understanding']='gpt'
        return rag_dialogue.remember(out,corpus)
    if understood and understood['intent'] in ('knowledge','other') and not understood['facts'] and not re.search(r'지원|사업|공고|신청|자격|금액|대출|금융|서류|마감',original):
        clean={k:v for k,v in context.items() if k not in ('notice_ids','list_ids','list_versions','casual_topic','conversation_topic')}
        return rag_dialogue.remember(rag_dialogue.response('어떤 내용을 알고 싶으세요? 이전 검색 조건은 유지하되, 새 질문에 맞춰 이야기할게요. 확인되지 않은 제도나 신청 정보는 추측하지 않습니다.',clean,'context',status='needs_verification'),corpus)
    if understood is None and not guidance and not re.search(r'지원|사업|공고|신청|자격|등록|서류|마감|시설|교육|농기계|비료|보험|금융|대출|융자|자금|그럼|아까|그\s*사업',original):
        facts,error=rag_dialogue.rag_profile.extract(original,rag_dialogue.AREAS,rag_dialogue.CROPS,rag_dialogue.normalized)
        if not facts and not error:
            clean=dict(context)
            return rag_dialogue.remember(rag_dialogue.response('새 질문의 뜻을 충분히 파악하지 못했어요. 어떤 이야기를 하고 싶은지 조금 더 알려주세요. 이전 작물 조건만으로 지원사업을 대신 추천하지 않을게요.',clean,'context',status='needs_verification'),corpus)
    if understood is None and rag_dialogue.rag_profile.hypothetical(original):
        understood={'intent':'discover','facts':{},'hypothetical':True,'reference_previous':bool(context.get('notice_ids')),'uncertain':[]}
    # Conservative follow-up routing still works when GPT is unavailable.
    if understood is None and context.get('notice_ids') and re.search(r'그\s*사업|아까|그럼',original):
        intent='deadline' if re.search(r'언제까지|마감|언제.*신청',original) else 'eligibility'
        understood={'intent':intent,'facts':{},'hypothetical':bool(re.search(r'등록\s*(?:하면|한다면|할\s*경우)',original)),'reference_previous':True,'uncertain':[]}
    routed,actual,evaluation=rag_nlu.route(question,understood) if understood else (question,None,None)
    guidance=guidance or ((rag_dialogue.service_response(routed,corpus,understood['intent']) or rag_dialogue.continuation(routed,corpus,lambda query,notice:grounded_response(query,corpus,notice),understood['intent'])) if understood else None)
    if guidance:
        response=guidance
    elif (understood and understood['intent']=='independent_management') or re.search(r'부모.*돕.*독립경영',original):
        response=rag_dialogue.response('부모님 농사를 돕는다는 사실만으로 독립경영 인정 여부를 확정할 수 없습니다. 사업마다 공식 정의·인정 서류·기준일이 다를 수 있어요. 확인하려는 지원사업명과 본인 농업경영체 등록 여부를 알려주세요.',actual or context,'clarify',status='needs_verification')
    else:
        response = rag_dialogue.respond(routed, corpus,
            lambda query, notice: grounded_response(query, corpus, notice))
    listing=rag_catalogue.respond(routed,corpus,fallback=response)
    if listing and (response.get('kind') in ('catalogue','recommendation','clarify') or context.get('notice_ids')):
        if understood and understood['hypothetical'] and actual is not None:
            for p in listing['programs']:p['comparison']['hypothetical']=True
            listing['conversation']={**actual,'notice_ids':listing['conversation'].get('notice_ids',[]),'list_ids':[],'list_versions':[],'last_kind':'results'}
            listing['answer']='가정한 조건으로 탐색했습니다. 실제 입력 상태와 전체 신청 자격은 변경하거나 확정하지 않았습니다.\n\n'+listing['answer']
        return catalogue_response(listing,corpus)
    decorate_cards(response,corpus)
    discovery=not context.get('notice_ids') and bool(re.search(r'찾아|지원사업.*(?:알려|있)|관련.*사업',original))
    if (response.get('kind') in ('catalogue','recommendation') or discovery) and not rag_catalogue.archive_requested(original):
        current_programs=[p for p in response['programs'] if p.get('card',{}).get('period_state')!='elapsed']
        if len(current_programs)!=len(response['programs']):
            if not current_programs:
                listing=rag_catalogue.respond(routed,corpus)
                if listing:return catalogue_response(listing,corpus)
                response=rag_dialogue.response('현재 공개 자료에서 기간이 지나지 않은 관련 공고를 찾지 못했어요. 기간 미확인은 마감으로 처리하지 않습니다. 지난 공고도 보려면 “지난 공고”와 지역·사업명을 함께 알려주세요.',{**response.get('conversation',context),'notice_ids':[],'list_ids':[],'list_versions':[]},'catalogue',status='no_evidence')
            else:
                response['programs']=current_programs
                urls={p['source_url'] for p in current_programs};response['sources']=[s for s in response.get('sources',[]) if s['url'] in urls]
                response['answer']='기간이 지난 공고를 제외하고 현재 확인할 공고를 안내합니다. 날짜 기준 상태와 실제 접수·전체 신청 자격은 별개입니다.'
                response['conversation']={**response.get('conversation',context),'notice_ids':[p['id'] for p in current_programs],'list_ids':[],'list_versions':[]}
                response['followup_questions']=list(dict.fromkeys(q for p in current_programs for q in p['card'].get('questions',[])))[:2]
    if understood and understood['hypothetical'] and actual is not None:
        notice_ids=response.get('conversation',{}).get('notice_ids',context.get('notice_ids',[]))
        response['conversation']={**actual,'notice_ids':notice_ids}
        note='가정한 조건으로 비교했습니다. 실제 입력 상태는 변경하지 않았으며 전체 신청 자격을 확정하지 않습니다.'
        for program in response['programs']:
            program['comparison']['checks'].insert(0,note)
            program['comparison']['hypothetical']=True
        response['answer']=note+'\n\n'+response['answer']
    response['understanding']='gpt' if used_gpt else 'rules'
    if used_gpt:response['answer']=response['answer'].replace('외부 AI에 자료를 보내지 않고 저장된 검증 근거를 정리했습니다.','질문 이해에는 GPT를, 지원사업 안내에는 저장된 공식 근거를 사용했습니다.')
    directory = os.environ.get('MUNONGSA_RAG_SYNC_DIR')
    if directory and response['programs']:
        import rag_sync
        current = rag_sync.load(directory)
        before = {d['public']['id']: d for d in corpus['documents'].values()}
        after = {d['public']['id']: d for d in current['documents'].values()}
        for program in response['programs']:
            identity = program['id']
            if (identity not in after or identity not in before
                    or rag_search.record_sha(before[identity]['record']) != rag_search.record_sha(after[identity]['record'])
                    or rag_sync.material(before[identity]['public']) != rag_sync.material(after[identity]['public'])):
                raise VerificationError()
    return rag_dialogue.remember(response,corpus)


def catalogue_response(response,corpus):
    """Recheck the served public listing before returning metadata or partial facts."""
    for key in ('conversation_topic','casual_topic'):response.setdefault('conversation',{}).pop(key,None)
    if os.environ.get('MUNONGSA_RAG_SYNC_DIR'):
        import rag_sync,rag_catalogue
        current=rag_sync.load(os.environ['MUNONGSA_RAG_SYNC_DIR'])
        old=corpus.get('guidance_feed',{});new=current.get('guidance_feed',{})
        before={n['id']:n for n in rag_catalogue.records(old)};after={n['id']:n for n in rag_catalogue.records(new)}
        for p in response['programs']:
            identity=p['id']
            if identity not in before or before[identity]!=after.get(identity):raise VerificationError()
            for key in ('notice_observations','verified_facts','verified_comparisons'):
                if old.get(key,{}).get(identity)!=new.get(key,{}).get(identity):raise VerificationError()
    return response


def decorate_cards(response,corpus):
    """Public, hash-verified facts only. Never parse new eligibility rules here."""
    if not response['programs']:return
    import rag_profile,rag_dialogue,support_notice_review,support_recommendation_readiness as readiness
    by_id={d['public']['id']:d for d in corpus['documents'].values()}
    context=response.get('conversation',{})
    def clean(value):
        if not isinstance(value,str) or not value.strip() or value in ('unknown','unconfirmed'):return '확인 필요'
        if re.search(r'(?i)(?:[a-z]:[\\/]|file://|(?:work|scripts|assets)[\\/])',value):raise VerificationError()
        return value.strip()[:1600]
    def field(document,name):
        row=document['record']['fields'].get(name,{})
        evidence=row.get('evidence',{})
        if not (rag_search.valid_url(evidence.get('url','')) and evidence.get('location') and evidence.get('checked_at')):return []
        raw=row.get('value',[]);raw=raw if isinstance(raw,list) else [raw]
        return list(dict.fromkeys(clean(v) for v in raw if isinstance(v,str) and v.strip()))[:12]
    for program in response['programs']:
        document=by_id[program['id']];public=document['public']
        live=None
        comparison=program.get('comparison') or rag_profile.compare(document,context,rag_search.valid_url,rag_dialogue.AREAS)
        if corpus.get('guidance_feed'):
            import rag_catalogue
            live=next((n for n in rag_catalogue.records(corpus['guidance_feed']) if n['id']==program['id']),None)
            partial=rag_catalogue.comparison(live,corpus['guidance_feed'],context,datetime.now(rag_answer.KST)) if live else None
            if partial:
                comparison={**comparison,'label':'조건 불일치' if '조건 불일치' in (comparison['label'],partial['label']) else '관련 가능성 있음' if '관련 가능성 있음' in (comparison['label'],partial['label']) else '추가 확인 필요',
                            'region_state':partial.get('region_state',comparison.get('region_state','check')),
                            'structured_state':partial.get('structured_state',comparison.get('structured_state','check')),
                            'verified_condition_count':max(partial.get('verified_condition_count',0),comparison.get('verified_condition_count',0)),
                            'reasons':list(dict.fromkeys(comparison.get('reasons',[])+partial['reasons']))[:3],
                            'checks':list(dict.fromkeys(partial['checks']+comparison.get('checks',[])))[:4],
                            'questions':list(dict.fromkeys(partial['questions']+comparison.get('questions',[])))[:2]}
        program['comparison']=comparison
        observed=public
        period=rag_search.recruitment_context(document,datetime.now(rag_answer.KST))
        if corpus.get('guidance_feed') and live:
            import support_notice_review
            observed=support_notice_review.project(support_notice_review.fact_project(live,corpus['guidance_feed'].get('verified_facts',{}).get(program['id']),datetime.now(rag_answer.KST)),corpus['guidance_feed'].get('notice_observations',{}).get(program['id']),datetime.now(rag_answer.KST))
            if observed.get('official_observation_at') or observed.get('verified_period_at'):
                dates=observed.get('reference_application_dates',{})
                state=support_notice_review.notice_state(observed,datetime.now(rag_answer.KST))
                period={**period,'date_state':{'window':'within_recorded_dates','upcoming':'upcoming','elapsed':'elapsed'}.get(state,'unknown')}
                program['application_period']={**program['application_period'],'start':dates.get('start',{}),'end':dates.get('end',{}),'description':'공식 본문에서 확인한 기재 신청기간 · 실제 접수·전체 자격은 별도 확인','actual_reception_confirmed':False}
                preparation=observed.get('application_preparation',{})
                program['application_entry_url']=preparation.get('entry_url')
                program['application_entry_kind']=preparation.get('entry_kind')
        closing=support_notice_review.closure_label(observed if live else public)
        if closing:period={**period,'date_state':'elapsed'}
        if period['date_state']=='elapsed':
            program['application_period']['description']=(closing or '기재 신청기간 경과')+' · 과거 금액·조건은 현재 신청에 적용할 수 없습니다. 연장·재공고는 별도 확인하세요.'
        audience=bool(context.get('planned') and any('수출' in v for v in field(document,'conditions')))
        comparison=readiness.apply(comparison,national=observed.get('geographic_scope')=='nationwide_verified' and bool(observed.get('verified_facts_at')),
                                  complete=public.get('eligibility_complete') is True,audience_check=audience)
        program['comparison']=comparison;verdict=comparison['decision']
        group='elapsed' if period['date_state']=='elapsed' else 'mismatch' if verdict['excluded'] else 'related' if verdict['category']=='A' else 'check'
        program['card']={'group':group,'label':verdict['label'],
            'period_state':period['date_state'],'lifecycle_label':closing,'institution':clean(public.get('institution')),
            'facts':{'region':clean(public.get('region')),'target':clean(public.get('target')),'support':clean(public.get('support')),
                     'funding':field(document,'funding'),'method':field(document,'method'),
                     'documents':field(document,'documents_required')},
            'questions':comparison['questions'][:2]}
        if live and observed.get('official_observation_at'):
            program['card']['lifecycle_label']=support_notice_review.closure_label(observed)
            preparation=observed.get('application_preparation',{})
            if preparation.get('method'):program['card']['facts']['method']=[preparation['method']]
            if preparation.get('documents_note'):program['card']['facts']['documents']=[preparation['documents_note']]
            program['card']['reception_state']=observed.get('actual_reception_state','unconfirmed')
    if response.get('kind')=='recommendation':
        response['programs']=[p for p in response['programs'] if not p['comparison']['decision']['excluded']]
    response['programs'].sort(key=lambda p:(p['comparison']['decision']['tier'],p['comparison']['decision']['audience_check'],p['card']['period_state']=='elapsed',
        {'within_recorded_dates':0,'deadline_day_time_unknown':0,'upcoming':1,'unknown':2,'elapsed':3}[p['card']['period_state']]))
    if response.get('kind')=='recommendation' or response.get('answer','').startswith('조건 비교'):
        qualified=any(p['comparison']['decision']['region_state']=='match' for p in response['programs'])
        intro='공식 지역 조건과 확인된 자격조건을 비교했습니다. 전체 신청 자격은 미확정입니다.' if qualified else '지역·주요 조건이 확인된 추천 공고가 부족합니다. 아래는 추가 확인이 필요한 참고 공고입니다.'
        response['answer']=intro+'\n\n'+'\n\n'.join(p['name']+' — '+p['card']['label']+'\n'+('비교 이유: '+' / '.join(p['comparison']['reasons'])+'\n' if p['comparison']['reasons'] else '')+'확인할 조건: '+' / '.join(p['comparison']['checks']) for p in response['programs'])
        kept={p['source_url'] for p in response['programs']};response['sources']=[s for s in response.get('sources',[]) if s['url'] in kept]
        response.setdefault('conversation',{})['notice_ids']=[p['id'] for p in response['programs']]
        response['conversation'].update(list_ids=[],list_versions=[])
    response['followup_questions']=list(dict.fromkeys(q for p in response['programs'] for q in p['card']['questions']))[:2]


def run_pipeline(question, timeout=PIPELINE_TIMEOUT):
    # No inherited API keys. A child process can be killed when the deadline expires.
    env = {k: v for k, v in os.environ.items() if k.upper() in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')}
    env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    if os.environ.get('MUNONGSA_RAG_SYNC_DIR'):
        env['MUNONGSA_RAG_SYNC_DIR'] = os.environ['MUNONGSA_RAG_SYNC_DIR']
    completed = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--worker'],
                               input=json.dumps({'question': question}, ensure_ascii=False),
                               encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=timeout, env=env, check=False)
    if completed.returncode != 0 or len(completed.stdout) > 262144:
        raise VerificationError()
    return json.loads(completed.stdout)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8
    allow_reuse_address = True

    def __init__(self, port, origins, rate_limit=10, pipeline=run_pipeline):
        self.origins, self.rate_limit, self.pipeline = set(origins), rate_limit, pipeline
        self.recent, self.rate_lock, self.slots = deque(), threading.Lock(), threading.BoundedSemaphore(4)
        super().__init__(('127.0.0.1', port), Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                body = json.dumps(failure('처리 중인 질문이 많습니다. 잠시 후 다시 시도해 주세요.'), ensure_ascii=False).encode('utf-8')
                headers = ('HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json; charset=utf-8\r\n'
                           f'Content-Length: {len(body)}\r\nCache-Control: no-store\r\nRetry-After: 5\r\nConnection: close\r\n\r\n')
                request.sendall(headers.encode('ascii') + body)
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # No request bodies, headers, paths or tracebacks in server logs.

    def take_request(self):
        now = time.monotonic()
        with self.rate_lock:
            while self.recent and now - self.recent[0] >= 60:
                self.recent.popleft()
            if len(self.recent) >= self.rate_limit:
                return False
            self.recent.append(now)
            return True


class Handler(BaseHTTPRequestHandler):
    server_version = 'MunongsaLocal'
    sys_version = ''

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.reply(code, failure('요청을 처리할 수 없습니다. 입력과 주소를 확인해 주세요.'))

    def handle(self):
        self.connection.settimeout(5)
        def expire():
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        deadline = threading.Timer(REQUEST_TIMEOUT, expire)
        deadline.daemon = True
        deadline.start()
        try:
            super().handle()
        finally:
            deadline.cancel()

    def reply(self, code, data=None):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else b''
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Connection', 'close')
            origin = self.headers.get('Origin') if hasattr(self, 'headers') else None
            if origin in self.server.origins:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
                self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            if code in (429, 503):
                self.send_header('Retry-After', '60' if code == 429 else '5')
            self.end_headers()
            if body:
                self.wfile.write(body)
        except OSError:
            pass
        self.close_connection = True

    def allowed(self):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host_headers = self.headers.get_all('Host', [])
        origins = self.headers.get_all('Origin', [])
        if (len(host_headers) != 1 or host_headers[0] not in hosts
                or len(origins) > 1 or (origins and origins[0] not in self.server.origins)):
            self.reply(403, failure('허용된 로컬 화면에서만 사용할 수 있습니다.'))
            return False
        if self.path != API_PATH:
            self.reply(404, failure('요청한 API 경로를 찾지 못했습니다.'))
            return False
        return True

    def do_OPTIONS(self):
        if self.allowed():
            self.reply(204)

    def do_GET(self):
        if self.allowed():
            self.reply(405, failure('질문은 POST 방식으로 보내 주세요.'))

    def do_POST(self):
        if not self.allowed():
            return
        if not self.server.take_request():
            self.reply(429, failure('질문 요청이 많습니다. 잠시 후 다시 시도해 주세요.'))
            return
        if self.headers.get_content_type() != 'application/json':
            self.reply(415, failure('JSON 형식으로 질문을 보내 주세요.'))
            return
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,8}', lengths[0]):
            self.reply(400, failure('요청 크기 정보를 확인할 수 없습니다.'))
            return
        length = int(lengths[0])
        if not 1 <= length <= MAX_BODY:
            self.reply(413, failure('요청이 너무 큽니다. 질문을 1,000자 이내로 줄여 주세요.'))
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError()
            question = validate_input(json.loads(raw.decode('utf-8')))
        except (ValueError, UnicodeError, RecursionError):
            self.reply(400, failure('질문만 포함한 JSON을 보내 주세요. 질문은 공백을 제외해 1~1,000자여야 합니다.'))
            return
        except OSError:
            self.reply(408, failure('질문 수신 시간이 초과됐습니다. 다시 시도해 주세요.'))
            return
        try:
            self.reply(200, self.server.pipeline(question))
        except subprocess.TimeoutExpired:
            self.reply(504, failure('답변 처리 시간이 초과됐습니다. 질문을 짧게 바꿔 주세요.'))
        except Exception:
            self.reply(503, failure('근거 자료 검증 또는 처리에 실패해 답변을 보류합니다. 자료를 확인해 주세요.'))


def main():
    parser = argparse.ArgumentParser(description='무농사 로컬 전용 질문 API · 외부 AI 호출 없음')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--ui-origin', action='append', help='허용할 로컬 UI 주소. 예: http://127.0.0.1:8000')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        # This process cannot open sockets, even if a later pipeline edit tries to.
        def no_network(*args, **kwargs):
            raise RuntimeError('network_disabled')
        socket.socket = no_network
        try:
            data = json.loads(sys.stdin.buffer.read(MAX_BODY + 1))
            result = local_pipeline(validate_input(data))
            sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            return 0
        except Exception:
            return 2
    origins = args.ui_origin or ['http://127.0.0.1:8000', 'http://localhost:8000']
    for origin in origins:
        try:
            url = urlsplit(origin)
            valid = (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost')
                     and url.port and not url.username and not url.password and not url.path and not url.query and not url.fragment)
        except ValueError:
            valid = False
        if not valid:
            parser.error('UI 주소는 포트를 포함한 로컬 HTTP 주소여야 합니다.')
    if not 1 <= args.port <= 65535:
        parser.error('포트 범위를 확인해 주세요.')
    try:
        server = LocalServer(args.port, origins)
    except OSError:
        print('로컬 서버를 시작하지 못했습니다. 사용 중인 포트인지 확인해 주세요.', file=sys.stderr)
        return 1
    print(f'Local-only API: http://127.0.0.1:{args.port}{API_PATH}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
