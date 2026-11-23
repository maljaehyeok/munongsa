"""Bounded turn resolution. Search preferences never become eligibility facts."""
import re,json,hashlib
import rag_dialogue as d,rag_catalogue as cat,rag_crops as crops,rag_profile

KEYS={'search_crop','search_mode','empty_search','service','tech_crop','tech_topic','tech_resource'}
def valid(c):
 return (all(k not in c or c[k] in crops.CROPS for k in ('search_crop','tech_crop'))
         and ('search_mode' not in c or c['search_mode'] in ('focused','regional','profile'))
         and ('empty_search' not in c or isinstance(c['empty_search'],str) and re.fullmatch('[a-f0-9]{64}',c['empty_search']) is not None)
         and ('service' not in c or c['service'] in ('support','finance','cultivation'))
         and ('tech_topic' not in c or type(c['tech_topic']) is int and 0<=c['tech_topic']<6)
         and ('tech_resource' not in c or c['tech_resource'] in ('general','pesticide')))

def clear_list(c):
 for k in ('notice_ids','list_ids','list_versions','last_kind','search_offset','search_fingerprint','conversation_topic','casual_topic'):c.pop(k,None)

def selection_request(text):
 return bool(re.search(r'(?:선택|입력|설정|저장)(?:한|된)?\s*(?:영농\s*)?조건',text) and re.search(r'검색|찾|탐색|지원\s*사업',text))

def finish_search(out,c):
 state=out['conversation']
 if out.get('programs'):
  state.pop('empty_search',None);return out
 if out.get('status')!='no_evidence':return out
 signature=hashlib.sha256(json.dumps({k:v for k,v in c.items() if k in rag_profile.KEYS|{'region','crop','farm_registered','search_scope','search_crop','search_query','search_mode'}},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 scope=c.get('search_scope')
 alternatives=([scope+' 지역 지원사업 찾아줘'] if scope and scope!='전국' and c.get('search_mode')!='regional' else ['작물 제한 없이 지원사업 찾아줘'] if c.get('search_mode')!='regional' else [])
 if scope!='전국':alternatives.append('그럼 전국은?')
 alternatives+=['농업 교육 지원사업 찾아줘','영농 시작 지원사업 찾아줘','농업금융 알려줘']
 out['suggestions']=alternatives[:3]
 if c.get('empty_search')==signature:
  out['answer']='같은 탐색 조건에서 새로 안내할 관련 공고가 없어요. 아래의 다른 탐색 조건이나 지원 분야를 선택해 검색을 바꿔보세요. 실제 영농 조건은 바꾸지 않으며 신청 자격을 완화하지 않습니다.'
 state['empty_search']=signature
 return out

def resolve(q,context,corpus):
 c=dict(context);text=d.normalized(q).strip();compact=re.sub(r'[\s?？!.,]','',text)
 if text.startswith(cat.PAGE_PREFIX) or re.fullmatch(r'(?:전체|모든|공개|지난)\s*(?:지원사업|공고)',text):return None
 if re.search(r'(?:첫|두|세|[1-3])\s*(?:번째|번)|그\s*사업|그\s*중',text):return None
 # Business references and specific official facts retain the existing evidence path.
 if cat.named_records(text,corpus.get('guidance_feed',{})):return None
 import rag_nlu
 if rag_nlu.concept_request(text,c):return None
 if re.search(r'아니.*(?:그게|내\s*말)|그게\s*아니',text):
  return d.response('어느 부분을 바꿀까요? 검색 지역·관심 작물·찾는 지원 분야 중 하나만 알려주세요. 실제 입력 조건은 그대로 유지했어요.',c,'clarify')
 crop=crops.find(text);area=d.area_in(text);selection=selection_request(text)
 short_area=bool(area and re.fullmatch(r'(?:그럼|그러면|아니)?\s*'+re.escape(area)+r'(?:\s*지역)?\s*(?:은|는|으로|로)?(?:요)?\s*[?？.!]*',text))
 short_national=bool(re.fullmatch(r'(?:그럼\s*)?전국(?:은|으로|도)?[?？.!\s]*',text))
 return_support=bool(re.search(r'(?:아까|다시|말고|돌아).*(?:지원사업|보조금)|(?:지원사업|보조금).*(?:돌아|복귀)|아까.*사업.*(?:돌아|복귀)',text))
 support=bool(re.search(r'지원\s*사업|보조금|관련\s*공고',text)) or return_support
 plan=bool(crop and re.search(r'지으려|재배.*(?:싶|준비|계획|예정|하려)|농사.*(?:준비|생각|시작|싶)|키우.*(?:싶|계획)',text)) and not rag_profile.hypothetical(text)
 crop_change=bool(crop and re.search(r'바꿔|변경|그런데|그럼|은[?？]?$|는[?？]?$',text))
 technology=crops.technology(text) or bool(re.search(r'재배법|재배\s*기술|농약\s*정보',text))
 tech_follow=c.get('service')=='cultivation' and (crop_change or bool(re.search(r'병해충|농약|비료|관수|수확|저장',text))) and not support
 if (technology or tech_follow) and not support:
  selected=crop or c.get('tech_crop') or c.get('search_crop') or c.get('crop')
  topic=crops.topic(text) if technology or re.search(r'병해충|농약|비료|관수|수확|저장',text) else c.get('tech_topic',0)
  c.update(service='cultivation',tech_topic=topic)
  resource='pesticide' if '농약' in text else c.get('tech_resource','general') if crop_change and not technology else 'general'
  c['tech_resource']=resource
  mentioned,_=rag_profile.extract(text,d.AREAS,d.CROPS,d.normalized)
  if mentioned.get('planned') is True and not rag_profile.hypothetical(text):c['planned']=True
  if selected:c['tech_crop']=selected
  return {**d.response('선택한 작물·주제의 공식 자료를 안내해요. 자료 탐색은 실제 재배 사실이나 개인별 농약 처방을 뜻하지 않습니다.',c,'cultivation'),'cultivation':{'crop':selected,'topic':topic,'resource':'pesticide' if resource=='pesticide' else None}}
 if c.get('service')=='finance' and re.search(r'그(?:건|게|거).*무슨\s*뜻|다시\s*설명',text):
  c['conversation_topic']='농업금융 용어'
  return d.response('어떤 금융 용어가 궁금하세요? 융자·금리·거치·상환 중 하나를 알려주시면 쉽게 설명할게요. 이전 지원사업을 대신 설명하지 않겠습니다.',c,'clarify')
 finance=bool(re.search(r'금융|융자|대출|시설\s*자금|운영\s*자금|자금.*부족',text)) and not support
 if finance or c.get('service')=='finance' and re.search(r'빌리|이자|상환',text) and not support:
  c.update(service='finance');c.pop('conversation_topic',None);c.pop('casual_topic',None)
  return d.response('기존 영농 조건으로 농업금융을 비교해 볼게요. 제도를 고른 뒤 공식 금리와 가정 대출금액으로 예상 이자를 확인할 수 있어요. 대출 승인·확정 금리·실제 상환액은 별도 확인이 필요합니다.',c,'context')
 more=bool(re.fullmatch(r'(?:좀\s*)?(?:더\s*(?:찾아|보여|알려)(?:줘|주세요)?|다른\s*(?:것|거|사업)?(?:도)?\s*(?:있어|있나|보여줘))[?？.!\s]*',text))
 if more and c.get('search_query'):
  if not c.get('search_offset'):return finish_search(d.response('같은 검색에서 추가로 확인할 관련 공고가 없어요. 아래에서 바꿀 탐색 조건을 선택해 주세요. 실제 영농 조건과 신청 자격은 그대로 유지합니다.',c,'clarify',status='no_evidence'),c)
  page=cat.PAGE_PREFIX+json.dumps({'query':c['search_query'],'offset':c['search_offset'],'fingerprint':c['search_fingerprint']})
  return cat.respond(d.PREFIX+json.dumps(c,ensure_ascii=False)+d.SEPARATOR+page,corpus)
 if not (support or short_area or short_national or plan or selection or crop_change and c.get('service')=='support'):return None
 # Hypothetical eligibility is evaluated by the established engine, not saved here.
 if rag_profile.hypothetical(text) or re.search(r'신청\s*(?:가능|자격)|필수|서류|마감',text) and not re.search(r'찾아|관련',text):return None
 facts,error=rag_profile.extract(text,d.AREAS,d.CROPS,d.normalized)
 if error:return d.response(error,c,'clarify')
 if not rag_profile.hypothetical(text):
  for k,v in facts.items():
   if k=='region' or k not in ('crop','farm_region','cultivating') and k in rag_profile.KEYS:c[k]=v
   elif k in ('crop','farm_region','cultivating') and facts.get('cultivating') is True:c[k]=v
 topics=[g for g in cat.TOPICS if re.search(g[1],text) and not re.search('(?:'+g[1]+r')\s*(?:말고|아닌|제외)',text)]
 general=bool(support and not crop and not topics and not plan and (area and not short_area and not re.search(r'넓혀|확대|전체로|같은\s*조건|그\s*조건',text) or re.search(r'작물\s*(?:제한\s*)?없이|작물\s*무관|작물\s*제한\s*(?:해제|풀)',text)))
 previous=c.get('search_query','')
 if general or selection:
  for k in ('search_crop','search_query'):c.pop(k,None)
  previous=''
  c['search_mode']='profile' if selection else 'regional'
 if crop:
  c['search_crop']=crop;c['search_mode']='focused'
 if plan:c['planned']=True
 if area:c['search_scope']=area
 if short_national or '전국' in text:c['search_scope']='전국'
 if 'search_scope' not in c and c.get('farm_region'):c['search_scope']=c['farm_region']
 if selection:
  c.pop('search_scope',None)
  if c.get('crop'):c['search_crop']=c['crop']
  if c.get('farm_region') or c.get('region'):c['search_scope']=c.get('farm_region') or c['region']
  if not any(c.get(k) for k in ('crop','farm_region','region')):
   clear_list(c);c.pop('empty_search',None);c['service']='support'
   return d.response('선택된 지역·작물이 없어요. 앞선 상담의 검색 조건을 실제 영농 조건으로 대신 사용하지 않았습니다. 내 조건을 입력하거나 원하는 지역·지원 분야로 탐색해 주세요.',c,'clarify',suggestions=('전국 지원사업 찾아줘','농업 교육 지원사업 찾아줘','영농 시작 지원사업 찾아줘'))
 # Rebuild only known search slots; never carry an obsolete crop/area in free text.
 wanted=[g[3] for g in topics]
 if plan and not wanted:wanted=[cat.TOPICS[0][3]]
 if not wanted:wanted=[g[3] for g in cat.TOPICS if re.search(g[1],previous) and not re.search('(?:'+g[1]+r')\s*(?:말고|아닌|제외)',text)]
 selected=c.get('search_crop') or (c.get('crop') if c.get('search_mode')!='regional' else None)
 query=' '.join(filter(None,[c.get('search_scope'),selected,' '.join(wanted),'지원사업 알려줘']))
 if '보조금' in text:query+=' 보조금'
 count=cat.requested_count(text) or cat.requested_count(previous)
 if count:query+=f' {count}개'
 clear_list(c);c['service']='support';c['search_query']=query[:180]
 out=cat.respond(d.PREFIX+json.dumps(c,ensure_ascii=False)+d.SEPARATOR+c['search_query'],corpus)
 if out:
  out['answer']='탐색 조건: '+' · '.join(filter(None,[c.get('search_scope'),selected,'작물 제한 없음' if c.get('search_mode')=='regional' else '', ' '.join(wanted)]))+'. 실제 영농 조건과 신청 자격은 별도로 비교합니다.\n\n'+out['answer']
  return finish_search(out,c)
 return finish_search({**d.response('현재 공개된 정보에서 '+(' · '.join(filter(None,[c.get('search_scope'),selected])) or '요청한 조건')+'와 직접 관련된 공고를 확인하지 못했어요. 다른 지역·작물 전용 사업을 대신 추천하지 않았습니다. 아래 선택지로 탐색 조건을 바꿀 수 있어요.',c,'catalogue',status='no_evidence'),'catalogue_total':0,'catalogue_requested':count,'catalogue_next':None,'catalogue_start':0,'catalogue_available':0,'catalogue_scope':'current','catalogue_search_scope':c.get('search_scope')},c)
