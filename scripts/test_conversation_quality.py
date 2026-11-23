"""Multiturn acceptance over an approved operating feed snapshot, no live model calls."""
import sys,json,unittest,os
from pathlib import Path
from unittest.mock import patch
import rag_api as api,rag_dialogue as d,rag_nlu as nlu,rag_crops as crops,rag_catalogue as cat

# These quoted utterances were supplied as text, not recovered from screenshots.
SCENARIOS=[
 ('provided_text',['안녕 익산 지역의 지원사업 있나?','충남?','충남 지역의 지원사업은?','익산에서 딸기농사를 지으려고 해요.','익산','익산 지역의 지원사업 있냐고','내가 익산에 사는데 익산에서 딸기를 재배하고 싶다고','선택한 조건으로 지원사업을 찾아주세요.']),
 ('scope',['익산 딸기 지원사업 알려줘','충남은?','그럼 전국은?','경기는?','경북은?','전주 지원사업 알려줘']),
 ('crop',['김제 마늘 지원사업 찾아줘','딸기로 바꿔줘.','토마토로 바꿔줘','벼로 바꿔줘','사과로 바꿔줘','참다래로 바꿔줘']),
 ('counts',['전국 귀농 지원사업 찾아줘','10개 보여줘.','더 찾아줘.','다른 것도 있어?','첫 번째 사업은?','그 사업 신청 자격은?']),
 ('repair',['익산 딸기 지원사업 찾아줘','아니 그게 아니라.','군산','시설 설치 지원사업 찾아줘','아까 지원사업으로 돌아가자.','충남?']),
 ('finance',['익산 마늘 지원사업 찾아줘','농업금융 알려줘.','융자 말고 보조금은?','귀농해서 시설자금이 필요해.','그럼 5천만 원 빌리면?','아까 지원사업으로 돌아가자.']),
 ('technology',['딸기 재배방법 알려줘.','병해충은?','농약 정보도 찾아줘.','그런데 토마토는?','다시 딸기 지원사업 알려줘.','그럼 전국은?']),
 ('kiwi',['키위 재배법 알려줘','병해충은?','농약 정보도 찾아줘','그런데 사과는?','참다래 지원사업 알려줘','전국은?']),
 ('facts',['마늘 재배 방법 알려줘.','마늘 농사를 시작할 생각이야.','마늘 농사를 이미 짓고 있어.','만약 경영체 등록을 하면 달라져?','농업경영체 등록이 뭐야?','충남 지원사업 찾아줘']),
 ('residence',['저는 전주에 살고 있어요','익산 딸기 지원사업 찾아줘','경기는?','김제 마늘 지원사업 찾아줘','충남은?','전국은?']),
 ('facilities',['토마토 시설하우스 설치 지원사업 찾아줘','전국은?','충남?','딸기로 바꿔줘','시설 설치 지원사업 찾아줘','다른 것도 있어?']),
 ('education',['전북 농업 교육 지원사업 찾아줘','충남은?','경북은?','그럼 전국은?','10개 보여줘','더 찾아줘']),
 ('insurance',['전북 마늘 보험 지원사업 찾아줘','딸기로 바꿔줘','경기는?','전국은?','농업금융 알려줘','아까 지원사업으로 돌아가자']),
 ('export',['수출 지원사업 찾아줘','전국은?','개인 농업인이야','익산 딸기농사를 준비 중이야','선택한 조건으로 지원사업을 찾아주세요.','더 찾아줘']),
 ('polite',['익산에서딸기농사를지으려고해요','지원 사업 찾아주세요','충남은요?','충남지역지원사업좀알려줘','그럼 농업금융도 알려줘','마늘 병해충 정보도 알려줘']),
 ('repeat',['익산 지역 지원사업 알려줘','익산 지역 지원사업 알려줘','익산?','아니 그게 아니라','딸기로 바꿔줘','전국은?']),
 ('scope_pause',['군산 지원사업 찾아줘','오늘 저녁 메뉴 추천해줘','군산은?','농업금융 알려줘','다시 지원사업으로 돌아가자','전주?']),
 ('no_data',['참다래 시설 설치 지원사업 찾아줘','익산?','군산?','경북?','전국은?','다른 것도 있어?']),
 ('concept_failure',['윤작이 뭐야?','그게 왜 필요한데?','쉽게 예를 들어 설명해 줘.','농업경영체 등록이 뭐야?','ㄱㄴㄷ???','김제 지원사업 찾아줘']),
 ('cross_service',['경기 사과 지원사업 알려줘','그럼 융자는?','그건 무슨 뜻이야?','딸기 재배기술 찾아줘','농약 정보도 찾아줘','다시 경기 사과 지원사업 알려줘'])]
SCENARIOS.append(('fresh_provided',list(SCENARIOS[0][1])))

def run_scenarios(feed):
 corpus={'documents':{},'guidance_feed':feed,'sync_generation':'isolated-operating-snapshot','sync_verified':True};rows=[];failures=[]
 for name,questions in SCENARIOS:
  fresh=name=='fresh_provided'
  c={} if fresh else {'region':'전주','farm_region':'김제','crop':'마늘','farm_registered':'no','planned':False}
  for index,q in enumerate(questions):
   before=dict(c)
   try:
    with patch.object(api,'load_api_corpus',return_value=corpus),patch.object(nlu,'interpret',return_value=None),patch.dict(os.environ,{'MUNONGSA_RAG_SYNC_DIR':''}):out=api.local_pipeline(d.PREFIX+json.dumps(c,ensure_ascii=False)+d.SEPARATOR+q)
    c=out['conversation'];issues=[]
    if c.get('farm_registered')!= (None if fresh else 'no'):issues.append('registration changed')
    if c.get('farm_region')!= (None if fresh else '김제') and not ('이미 짓고' in q):issues.append('search changed actual farm')
    if c.get('crop')!= (None if fresh else '마늘') and not ('이미 짓고' in q):issues.append('interest changed actual crop')
    if c.get('cultivating') is True and name!='facts':issues.append('unstated production')
    if q in ('충남?','충남은?','충남은요?','경기는?','경북은?','전주?','군산?','익산?','익산','전국은?','그럼 전국은?'):
     wanted='전국' if '전국' in q else d.area_in(q)
     if c.get('search_scope')!=wanted:issues.append('scope unresolved')
    if name in ('technology','kiwi') and index<4:
     if out.get('kind')!='cultivation':issues.append('technology continuity')
     expected=['딸기','딸기','딸기','토마토'][index] if name=='technology' else ['참다래','참다래','참다래','사과'][index]
     if out.get('cultivation',{}).get('crop')!=expected:issues.append('technology wrong crop')
     if index==3 and out.get('cultivation',{}).get('resource')!='pesticide':issues.append('technology topic lost')
    if name=='polite' and index in (0,1,2,3) and c.get('search_crop')!='딸기':issues.append('whitespace crop unresolved')
    if name=='finance' and index==2 and any(w in p['name'] for p in out['programs'] for w in ('융자','대출','이차보전')):issues.append('negated loan intent')
    if ('금융 알려줘' in q or q=='그럼 융자는?' or '시설자금이 필요' in q or '빌리면' in q) and out.get('programs'):issues.append('finance hijacked by support')
    interest=c.get('search_crop') or c.get('crop')
    if out.get('kind')=='catalogue':
     for p in out['programs']:
      found=crops.find(p['name'])
      if interest and found and found!=interest:issues.append('wrong crop discovery')
      if (c.get('planned') or interest) and not any(w in c.get('search_query','') for w in ('수출','기업','가공')) and any(w in p['name'] for w in ('수출','가공식품','기업')):issues.append('wrong audience discovery')
    if len(json.dumps(c,ensure_ascii=False))>1600:issues.append('context oversized')
    row={'scenario':name,'turn':index+1,'question':q,'kind':out['kind'],'status':out['status'],'context':c,'titles':[p['name'] for p in out['programs']],'issues':issues}
    rows.append(row)
    if issues:failures.append(row)
   except Exception as error:
    row={'scenario':name,'turn':index+1,'question':q,'error':type(error).__name__+':'+str(error)};rows.append(row);failures.append(row);c=before
 return rows,failures

if __name__=='__main__':
 feed=json.loads(Path(sys.argv[1]).read_text('utf8'));rows,failures=run_scenarios(feed)
 Path(sys.argv[2]).write_text(json.dumps({'scenarios':len(SCENARIOS),'turns':len(rows),'passed':len(rows)-len(failures),'failed':len(failures),'mode':'isolated operating-feed integration, GPT disabled','failures':failures,'rows':rows},ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'scenarios':len(SCENARIOS),'turns':len(rows),'passed':len(rows)-len(failures),'failed':len(failures),'failures':[{'scenario':r['scenario'],'turn':r['turn'],'issues':r.get('issues',r.get('error'))} for r in failures]},ensure_ascii=False))
 raise SystemExit(bool(failures))
