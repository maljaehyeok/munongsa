"""Multi-turn purpose/state checks against an explicitly supplied public feed.

Offline replay only: no collection, approvals, external model or database writes.
Assertions inspect effective slots, public IDs, reference integrity and next steps.
"""
import argparse,json,os
from pathlib import Path
from unittest.mock import patch
import rag_api,rag_dialogue as d,rag_nlu,rag_turn as t,rag_catalogue as cat

def step(q,**expect):return {'q':q,'expect':expect}
def form(**values):return {'form':values,'q':'선택한 검색 조건으로 찾아줘','expect':{**values}}
def scenario(name,steps,profile=None):return {'name':name,'steps':steps,'profile':profile or {}}

SCENARIOS=[
 scenario('익산 딸기 초보',[step('익산 딸기 지원사업 있나요?',search_scope='익산',search_crop='딸기'),step('익산에 딸기 지원해 주는 거 있냐?',search_crop='딸기'),step('딸기 농사 시작할 건데 뭐 받을 수 있어?'),step('왜 이거 추천한 거야?'),step('지원받으려면 뭐부터 해야 해?')]),
 scenario('전주 거주 김제 예정',[step('전주에 살고 김제에서 토마토 농사를 시작할 예정이야.'),step('선택한 조건으로 검색',search_scope='김제',search_crop='토마토'),step('전북 전체로 넓혀줘',search_scope='전북'),step('그건 내가 신청할 수 있어?'),step('신청 서류 알려줘')],{'region':'전주','farm_region':'김제','crop':'토마토','planned':True}),
 scenario('군산 기존 벼농사',[step('군산 벼 지원사업 찾아줘',search_crop='벼'),step('관련 사업 7개로 보여줘',search_limit=7),step('그중 두 번째 사업은?'),step('그 사업 문의처는?'),step('농업금융도 알려줘',service='finance')],{'farm_region':'군산','crop':'벼','cultivating':True,'planned':False}),
 scenario('충남 사과 광역 변경',[step('충남 사과 지원사업 찾아줘',search_scope='충남'),step('전북은?',search_scope='전북',search_crop='사과'),step('전국으로 찾아줘.',search_scope='전국'),step('아니 익산 말고 전국.',search_scope='전국'),step('사과 말고 마늘로 바꿔줘',search_crop='마늘')]),
 scenario('경북 마늘',[step('경북 마늘 사업 찾아줘',search_scope='경북',search_crop='마늘'),step('경북 지역 지원사업!',search_scope='경북',search_crop=None),step('시설 지원사업은?',search_purpose='facility'),step('전국으로 찾아줘'),step('그거 말고 다른 거.')]),
 scenario('전북에서 전국 마늘',[step('전북 딸기 시설 지원사업 찾아줘'),step('익산뿐 아니라 전국의 마늘 지원사업 찾아줘.',search_scope='전국',search_crop='마늘'),step('지역 제한 없이 농업 교육 지원사업.',search_scope=None,search_crop=None,search_purpose='education'),step('10개 추천해줘',search_limit=10),step('아까 두 번째 사업.')]),
 scenario('딸기에서 미나리',[step('익산 딸기 지원사업 찾아줘'),step('미나리로 바꿔줘',search_crop='미나리'),step('마늘로 바꿔줘',search_crop='마늘'),step('전북 지역 지원사업',search_crop=None,search_scope='전북'),step('현재 검색 조건으로 다시 검색',search_scope='전북',search_crop=None)]),
 scenario('폼 지역만 선택',[form(search_scope='전북',search_crop='미나리'),form(search_scope='전북'),step('현재 검색 조건으로 다시 검색',search_crop=None),step('교육 지원사업 찾아줘',search_purpose='education'),step('그건 내가 신청할 수 있어?')],{'crop':'벼','farm_region':'군산'}),
 scenario('폼 작물만 선택',[form(search_scope='충남',search_crop='딸기'),form(search_crop='마늘'),step('현재 검색 조건으로 다시 검색',search_scope=None,search_crop='마늘'),form(search_crop='미나리'),step('전국으로 찾아줘',search_scope='전국',search_crop='미나리')]),
 scenario('전체 초기화와 새 대화',[step('익산 딸기 지원사업 찾아줘'),step('조건 다 지워줘.'),step('영농 조건과 상담 모두 초기화',empty_profile=True),step('새 대화',empty_profile=True),step('현재 검색 조건으로 다시 검색',search_scope=None,search_crop=None)],{'farm_region':'익산','crop':'딸기','cultivating':True}),
 scenario('검색만 초기화',[step('충남 미나리 지원사업 찾아줘'),step('검색 조건 초기화',search_scope=None,search_crop=None),step('현재 검색 조건으로 다시 검색',search_scope=None,search_crop=None),step('선택한 조건으로 검색',search_scope='김제',search_crop='마늘'),step('농업금융 알려줘',service='finance')],{'farm_region':'김제','crop':'마늘','farm_registered':'yes','cultivating':True}),
 scenario('미등록과 가정',[step('익산 마늘 지원사업 찾아줘'),step('아직 농업경영체 등록 안 했어',farm_registered='no'),step('만약 경영체 등록을 하면 달라져?',farm_registered='no'),step('내가 신청할 수 있어?'),step('마늘 재배 방법 알려줘',service='cultivation')],{'farm_region':'익산','planned':True,'farm_registered':'no'}),
 scenario('제도 개념과 자격',[step('농업경영체 등록이 뭐야?',no_cards=True),step('그럼 청년후계농 선정이랑 다른 거야?',no_cards=True),step('그게 무슨 뜻이야?',no_cards=True),step('전국 청년 농업 지원사업 찾아줘'),step('나는 올해 선정될 수 있어?')]),
 scenario('시설과 금융',[step('토마토 시설하우스 설치 지원사업 찾아줘',search_purpose='facility'),step('그럼 농업금융도 알려줘',service='finance'),step('대출은 꼭 갚아야 해?'),step('아까 지원사업으로 돌아가자'),step('전북 시설 지원사업 찾아줘',search_scope='전북')]),
 scenario('보조금과 융자 정정',[step('전국 융자 지원사업 찾아줘'),step('융자 말고 보조금은?',search_purpose='grant'),step('현재 검색 조건으로 다시 검색',search_purpose='grant'),step('아니 보조금 말고 대출.',service='finance'),step('보조금과 융자의 차이는?',no_cards=True)]),
 scenario('정책자금 금액',[step('정책자금 5천만 원 대출 알아보고 싶어',service='finance'),step('이자가 얼마나 나와?'),step('그럼 승인받을 수 있어?'),step('공식 신청 방법 알려줘'),step('다시 지원사업 찾아줘')],{'farm_region':'김제','crop':'마늘'}),
 scenario('농기계 목적',[step('농기계 구입 지원사업 찾아줘',search_purpose='machinery'),step('전북으로 넓혀줘'),step('10개 추천해 줘',search_limit=10),step('그거 말고 다른 거.'),step('교육 지원사업 찾아줘',search_purpose='education')]),
 scenario('교육 목적 해제',[step('익산 딸기 지원사업 찾아줘'),step('지역 제한 없이 농업 교육 지원사업.',search_crop=None,search_scope=None,search_purpose='education'),step('농업 연수도 있어?'),step('다른 관련 사업 보여줘'),step('신청하려면 뭐부터 해야 해?')]),
 scenario('토마토 병해충',[step('토마토 병해충 정보 알려줘',service='cultivation',tech_crop='토마토'),step('그럼 농약은?',tech_resource='pesticide'),step('오이로 바꿔줘',tech_crop='오이'),step('비료 정보도 알려줘'),step('전북 오이 지원사업 찾아줘',search_crop='오이',service='support')]),
 scenario('배추 농약',[step('배추 농약 정보를 찾고 싶어',service='cultivation',tech_crop='배추',tech_resource='pesticide'),step('그럼 병해충은?'),step('배추 재배 방법 알려줘',tech_crop='배추'),step('배추 비료 정보 알려줘'),step('배추 지원사업 찾아줘',search_crop='배추')]),
 scenario('참다래와 별칭',[step('참다래 재배 방법 알려줘',tech_crop='참다래'),step('참다래 병해충 정보 알려줘',tech_crop='참다래'),step('키위 농약 정보 알려줘',tech_crop='참다래'),step('참다래 지원사업 찾아줘',search_crop='참다래'),step('전국으로 찾아줘',search_scope='전국')]),
 scenario('반복과 정정',[step('익산 딸기 지원사업 있어?'),step('익산 지역 지원사업!',search_crop=None),step('익산 지역 지원사업!'),step('아니 내 말은 그게 아니라'),step('전국 농업 교육 지원사업 찾아줘',search_purpose='education')]),
 scenario('0건과 범위 확대',[step('제주 미나리 지원사업 찾아줘'),step('제주 미나리 지원사업 있나요?'),step('그거 말고 다른 거.'),step('전국으로 찾아줘',search_scope='전국'),step('지역 제한 없이 농업 교육 지원사업.',search_crop=None,search_purpose='education')]),
 scenario('메뉴 장거리와 초기화',[step('익산 마늘 지원사업 찾아줘'),step('농업금융 알려줘',service='finance'),step('마늘 재배기술 알려줘',service='cultivation'),step('아까 지원사업으로 돌아가자',service='support'),step('다시 처음부터')],{'region':'전주','farm_region':'익산','crop':'마늘','planned':True})
]

def run(feed):
 # Outcome checks cover the conversational failures discovered by reading replies,
 # not just successful HTTP/schema checks or a preferred answer sentence.
 outcomes={(0,3):{'kind':'context'},(2,2):{'kind':'clarify','no_cards':True},(3,3):{'kind':'catalogue'},(9,1):{'kind':'clarify'},(9,2):{'reset_scope':'all'},(16,3):{'kind':'clarify'},(17,2):{'kind':'catalogue','search_purpose':'education'},(22,2):{'kind':'clarify'},(23,4):{'reset_scope':'conversation'}}
 corpus={'documents':{},'guidance_feed':feed,'sync_generation':'isolated','sync_verified':True}
 public={n['id'] for n in feed['notices']};results=[]
 for case_index,case in enumerate(SCENARIOS):
  c=dict(case['profile']);rows=[];protected=dict(case['profile'])
  for step_index,s in enumerate(case['steps']):
   sent=dict(c)
   if 'form' in s:
    sent={k:v for k,v in sent.items() if k not in t.SEARCH_KEYS|t.REFERENCE_KEYS|{'service','tech_crop','tech_topic','tech_resource'}}
    sent.update(search_mode='custom',search_action='replace',**s['form'])
   q=s['q'];fail=[]
   try:
    with patch.object(rag_api,'load_api_corpus',return_value=corpus),patch.object(rag_nlu,'interpret',return_value=None),patch.dict(os.environ,{'MUNONGSA_RAG_SYNC_DIR':''}):out=rag_api.local_pipeline(d.PREFIX+json.dumps(sent,ensure_ascii=False)+d.SEPARATOR+q)
    c=out['conversation']
    for k,v in {**s['expect'],**outcomes.get((case_index,step_index),{})}.items():
     if k=='no_cards':actual=not out['programs']
     elif k=='kind':actual=out['kind']
     elif k=='reset_scope':actual=out.get('reset_scope')
     elif k=='empty_profile':actual=not bool(t.PROFILE_KEYS.intersection(c))
     else:actual=c.get(k)
     if actual!=v:fail.append(f'{k}: expected {v!r}, got {actual!r}')
    if not t.valid(c):fail.append('invalid returned state')
    ids=[p['id'] for p in out['programs']]
    if len(ids)!=len(set(ids)) or not set(ids)<=public:fail.append('duplicate or nonpublic card')
    if not out.get('answer'):fail.append('empty answer')
    if out.get('reset_scope') in ('profile','all'):protected={}
    else:
     for k,v in protected.items():
      if c.get(k)!=v:fail.append('actual profile changed: '+k)
    rows.append({'question':q,'form':s.get('form'),'sent':sent,'response':out,'failures':fail})
   except Exception as e:rows.append({'question':q,'failures':[type(e).__name__+': '+str(e)]})
  results.append({'name':case['name'],'turns':rows})
 return results

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--feed',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 results=run(json.loads(args.feed.read_text('utf8')));args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
 failures=[{'scenario':r['name'],'q':s['question'],'failures':s['failures']} for r in results for s in r['turns'] if s['failures']]
 print(json.dumps({'scenarios':len(results),'turns':sum(len(r['turns']) for r in results),'failed_turns':len(failures),'failures':failures},ensure_ascii=False))
 raise SystemExit(1 if failures else 0)
