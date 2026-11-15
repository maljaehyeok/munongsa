"""Public listing discovery only. Never inserts a record into approved RAG evidence."""
from datetime import datetime,timezone
import re
import rag_search,rag_dialogue
import support_notice_review as review

HOSTS={'www.rda.go.kr','www.buan.go.kr','www.gochang.go.kr','www.jinan.go.kr','www.imsil.go.kr','www.sunchang.go.kr','www.jeonbuk.go.kr','www.bizinfo.go.kr','bizinfo.go.kr','www.mafra.go.kr','global.at.or.kr','agriacademy.jeonbuk.go.kr','www.gunsan.go.kr','www.jeonju.go.kr','www.koat.or.kr','www.gimje.go.kr','www.oads.or.kr'}

def safe_url(value):
    from urllib.parse import urlsplit,parse_qs
    try:
        u=urlsplit(value)
        return u.scheme=='https' and u.hostname in HOSTS and not u.username and not u.password and u.port in (None,443) and not u.fragment and not any(re.search(r'key|token|auth|secret|password|session',k,re.I) for k in parse_qs(u.query))
    except (ValueError,TypeError):return False

def records(feed,now=None):
    from urllib.parse import urlsplit
    now=now or datetime.now(timezone.utc)
    if not isinstance(feed,dict) or feed.get('schema_version')!='munongsa-support-public-v1':return []
    values=feed.get('notices',[])
    if not isinstance(values,list) or len(values)>2000:return []
    ids=[v.get('id') for v in values if isinstance(v,dict)]
    if len(ids)!=len(values) or len(set(ids))!=len(ids):return []
    out=[]
    for value in values:
        try:
            if not re.fullmatch(r'NOTICE-[A-Za-z0-9_-]{1,70}',value['id']):continue
            if not safe_url(value['url']):continue
            if value.get('rights',{}).get('public_display')!='allowed' or value.get('freshness')!='current':continue
            publication=value.get('publication')
            if publication=='official_guidance':
                if value.get('verification_status')!='basics_only' or value.get('recommendation_eligible') is not False:continue
                if datetime.fromisoformat(value['guidance_expires_at'])<=now:continue
            elif publication not in ('approved','approved_reference') or value.get('verification_status')!='verified':continue
            if not all(isinstance(value.get(k),str) and 0<len(value[k])<=500 and not re.search(r'[<>\x00-\x1f]',value[k]) for k in ('title','institution')):continue
            checked=datetime.fromisoformat(value['last_checked_at'])
            if checked.tzinfo is None:continue
            out.append(value)
        except (KeyError,ValueError,TypeError):continue
    return out

def matches(question,feed,context=None,now=None):
    context=context or {};text=rag_dialogue.normalized(question)
    compact=re.sub(r'[^0-9a-z가-힣]','',text.lower())
    area=rag_dialogue.area_in(text) or context.get('farm_region') or context.get('region')
    crop=next((v for v in rag_dialogue.CROPS if v in text),None) or context.get('crop')
    generic={'지원사업','지원','공고','사업','안내','신청','모집','농업','농업인','관련','알려줘','확인','조건','자격','해주세요','현재','전체','공개','있나요','있는','에서','찾아줘'}
    terms=[v for v in re.findall(r'[가-힣A-Za-z0-9]+',text) if len(v)>=2 and v not in generic and v not in rag_dialogue.AREAS and not v.endswith(('에서','관련'))]
    ranked=[]
    for raw in records(feed,now):
        title=rag_dialogue.normalized(raw['title']);hay=title+' '+raw['institution'];nt=re.sub(r'[^0-9a-z가-힣]','',title.lower())
        exact=len(nt)>=6 and nt in compact
        if not exact:
            # A title/location word is relevance only, never a residence or farm requirement.
            if area and area not in hay and not ('전국' in text and '전국' in hay):continue
            if crop and crop not in hay:continue
            topical=[t for t in terms if t not in ('지원사업을','지원사업이','사업명으로','알려주세요')]
            if topical and not any(t in hay for t in topical):continue
            if not (area or crop or topical or re.search(r'전체|공개|지원사업|공고',text)):continue
        ranked.append((100 if exact else sum(v in hay for v in terms)+bool(area and area in hay),raw))
    return [r for _,r in sorted(ranked,key=lambda pair:(-pair[0],pair[1]['title']))]

def comparison(item,feed,context,now):
    import rag_profile
    basis={k:item.get(k) for k in ('id','title','url','target','region','reference_application_dates','application_period','eligibility')}
    candidates=[feed.get('verified_comparisons',{}).get(item['id']),feed.get('verified_facts',{}).get(item['id'])]
    for annotation in candidates:
        try:
            if not annotation or annotation.get('complete') is not False or annotation.get('basis')!=basis or datetime.fromisoformat(annotation['expires_at'])<=now:continue
            values=annotation.get('conditions',[])
            if not values or not all(c.get('status')=='verified' and c.get('presence')=='specified' and c.get('evidence',{}).get('fact_confirmed') is True and c['evidence'].get('url')==item['url'] and c['evidence'].get('location') for c in values):continue
            payload=item.get('eligibility',{});conditions=list(payload.get('conditions',[]))+values
            if len({c['condition_id'] for c in conditions})!=len(conditions):continue
            projected={**item,'eligibility':{'conditions':conditions,'logic':{'op':'AND','children':[payload.get('logic',{'op':'UNKNOWN','children':[]})]+[{'condition_id':c['condition_id']} for c in values]}}}
            result=rag_profile.compare({'public':projected,'record':{'fields':{}}},context,safe_url,rag_dialogue.AREAS)
            result['checks'].insert(0,'확인된 필수조건 일부만 비교했습니다. 전체 신청 자격과 실제 접수 가능 여부는 미확정입니다.')
            return result
        except (KeyError,ValueError,TypeError):continue
    return None

def program(item,feed,now,context=None):
    shown=review.project(item,feed.get('notice_observations',{}).get(item['id']),now)
    dates=shown.get('reference_application_dates',{})
    state=review.state(dates,now)
    conditions=[]
    compared=comparison(item,feed,context or {},now)
    result_comparison=compared or {'label':'추가 확인 필요','reasons':[], 'checks':['제목·기관·공식 링크 중심의 기본 안내입니다. 지역·작물 관련성은 신청 자격 충족을 뜻하지 않습니다.'], 'questions':[]}
    return {'id':item['id'],'name':item['title'],'source_url':item['url'],'checked_at':shown.get('official_observation_at',item['last_checked_at']),
            'required_conditions':conditions,'additional_checks':['전체 신청 자격·지원금·서류는 검증된 상세 근거가 없으면 공식 원문과 담당 기관에서 확인해 주세요.'],
            'evidence_level':'공식 공고 기본 안내','evidence_note':'공식 제목·기관·링크 안내이며, 승인된 상세 근거나 최신 원문 전체 자격 검증이 아닙니다.',
            'application_period':{'start':dates.get('start',{}),'end':dates.get('end',{}),'description':'기재 신청기간 경과 · 연장·재공고 별도 확인' if state=='elapsed' else '기재 신청기간과 실제 접수 가능 여부는 별개입니다.','actual_reception_confirmed':False},
            'needs_verification':True,'comparison':result_comparison,'guidance_only':not bool(compared),'partial_comparison':bool(compared),
            'card':{'group':'elapsed' if state=='elapsed' else 'check','label':'공식 공고 기본 안내','period_state':{'window':'within_recorded_dates','upcoming':'upcoming','elapsed':'elapsed'}.get(state,'unknown'),
                    'institution':item['institution'],'reception_state':shown.get('actual_reception_state','unconfirmed'),'facts':{'region':'확인 필요','target':'확인 필요','support':'공식 원문에서 확인','funding':[],'method':[shown['application_method']] if shown.get('application_method') else [],'documents':[]},'questions':[]}}

def respond(encoded,corpus,*,explicit=False,fallback=None):
    feed=corpus.get('guidance_feed')
    if not feed:return None
    question,context=rag_dialogue.decode(encoded);now=datetime.now(timezone.utc)
    strict={d['public']['id'] for d in corpus['documents'].values()}
    found=matches(question,feed,context,now)
    exact=[n for n in found if re.sub(r'[^0-9a-z가-힣]','',rag_dialogue.normalized(n['title']).lower()) in re.sub(r'[^0-9a-z가-힣]','',rag_dialogue.normalized(question).lower())]
    if explicit:
        found=[n for n in exact if n['id'] not in strict]
        if not found:return None
    elif fallback and fallback.get('programs'):return None
    # Follow-up to a metadata-only listing: do not redirect it to another approved business.
    previous=context.get('notice_ids',[])
    if not explicit and previous and any(i not in strict for i in previous) and re.search(r'그\s*사업|서류|지원금|자격|조건|마감|첫\s*번째|두\s*번째',question):
        by_id={n['id']:n for n in records(feed,now)}
        found=[by_id[i] for i in previous if i in by_id]
        if not found:return rag_dialogue.response('앞서 본 공고를 최신 공개 목록에서 확인할 수 없어 안내를 보류했어요. 사업명으로 다시 찾아주세요.',{},'clarify',status='needs_verification')
    if not found:return None
    chosen=found[:3];programs=[program(n,feed,now,context) for n in chosen]
    conversation={**context,'notice_ids':[n['id'] for n in chosen],'list_ids':[],'list_versions':[],'last_kind':'results'}
    return {**rag_dialogue.response(f'공식 공고 {len(found)}건을 찾았어요. '+('먼저 3건을 안내합니다. ' if len(found)>3 else '')+'기본 안내의 지역·키워드 관련성은 신청 가능 판정이 아닙니다. 상세 자격과 실제 접수는 공식 원문에서 확인해 주세요.',conversation,'catalogue',status='needs_verification',programs=programs),
            'sources':[{'url':p['source_url'],'location':'공식 제목·기관·원문 링크 확인','checked_at':p['checked_at']} for p in programs],
            'catalogue_total':len(found),'understanding':'rules'}
