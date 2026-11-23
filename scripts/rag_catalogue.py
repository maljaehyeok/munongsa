"""Public listing discovery only. Never inserts a record into approved RAG evidence."""
from datetime import datetime,timezone
import re,json,hashlib
import rag_search,rag_dialogue
import support_notice_review as review

HOSTS={'www.rda.go.kr','www.buan.go.kr','www.gochang.go.kr','www.jinan.go.kr','www.imsil.go.kr','www.sunchang.go.kr','www.jeonbuk.go.kr','www.bizinfo.go.kr','bizinfo.go.kr','www.mafra.go.kr','global.at.or.kr','agriacademy.jeonbuk.go.kr','www.gunsan.go.kr','www.jeonju.go.kr','www.koat.or.kr','www.gimje.go.kr','www.oads.or.kr'}
PAGE_PREFIX='[공식 공고 더 보기]\n'

def requested_count(question):
    match=re.search(r'(?<!\d)(\d{1,2})\s*(?:[~～〜\-–]\s*(\d{1,2}))?\s*개(?:\s*정도)?',question)
    return min(10,max(1,int(match[2] or match[1]))) if match else None

def scope_request(question):
    text=rag_dialogue.normalized(question)
    if not re.search(r'넓혀|확대|전체로|전국.*(?:사업|공고|찾|보여)',text):return None
    return '전국' if '전국' in text else rag_dialogue.area_in(text)

def scope_relevance(item,feed,now,scope):
    """Published locality is a discovery signal, never an eligibility condition."""
    if scope=='전국':return 0
    parts=rag_dialogue.normalized(scope).split()
    explicit_parent=parts[0] if len(parts)==2 else None
    if explicit_parent:scope=re.sub(r'[시군구]$','',parts[-1])
    hay=search_text(item,feed,now)
    places={a for a in rag_dialogue.AREAS if a in hay}
    if scope in places:return 2
    parent=rag_dialogue.AREAS.get(scope,(scope,None))[1] or explicit_parent
    if not parent and any(p==scope and a in places for a,(_,p) in rag_dialogue.AREAS.items()):return 2
    if parent and any(p==parent and a!=scope and a in places for a,(_,p) in rag_dialogue.AREAS.items()):return -1
    if parent in places:return 1
    # No known locality remains discoverable with its original unknown verdict.
    return -1 if places else 0

def archive_requested(question):
    return bool(re.search(r'지난\s*(?:사업|공고|지원)|과거|예전|종료된|마감된|기한\s*경과|기간\s*경과',question))

def page_request(question):
    if not question.startswith(PAGE_PREFIX):return None
    try:
        value=json.loads(question[len(PAGE_PREFIX):])
        if (not isinstance(value,dict) or set(value)!={'query','offset','fingerprint'}
            or not isinstance(value['query'],str) or not 1<=len(value['query'])<=300 or value['query'].startswith(PAGE_PREFIX)
            or type(value['offset']) is not int or not 3<=value['offset']<=1998 or value['offset']%3
            or not re.fullmatch('[a-f0-9]{64}',value['fingerprint'])):raise ValueError()
        return value
    except (ValueError,TypeError,KeyError):raise ValueError('invalid_catalogue_page')

def verified_conditions(item,feed,now):
    basis={k:item.get(k) for k in ('id','title','url','target','region','reference_application_dates','application_period','eligibility')}
    for key in ('verified_comparisons','verified_facts'):
        value=feed.get(key,{}).get(item['id'],{})
        try:
            conditions=value.get('conditions',[])
            if value.get('review_required') or value.get('basis')!=basis or value.get('complete') is not False or not datetime.fromisoformat(value['checked_at'])<=now<datetime.fromisoformat(value['expires_at']):continue
            if conditions and all(c.get('presence')=='specified' and c.get('status')=='verified' and c.get('evidence',{}).get('fact_confirmed') is True and c['evidence'].get('url')==item['url'] and c['evidence'].get('location') for c in conditions):return conditions
        except (KeyError,TypeError,ValueError):continue
    return []

def approved_conditions(item,feed,now):
    """Use both existing approval paths, never private extracted candidates."""
    import rag_profile
    direct=rag_profile.project_public(item,safe_url).get('eligibility',{}).get('conditions',[])
    result=[];seen=set()
    for c in direct+verified_conditions(item,feed,now):
        if (c.get('status')=='verified' and c.get('presence')=='specified'
                and c.get('evidence',{}).get('location') and safe_url(c.get('evidence',{}).get('url',''))
                and (c['evidence'].get('fact_confirmed') is True or c['evidence'].get('quote'))
                and c['condition_id'] not in seen):
            result.append(c);seen.add(c['condition_id'])
    return result


def search_text(item,feed,now):
    # Only current, version-bound typed conditions augment title relevance.
    labels={'farm_registration':'농업경영체 등록','crop':'작물 재배','residence':'거주지','business_location':'영농지 농지','applicant':'신청자'}
    values=[item['title'],item['institution']]
    # Approved locality text supports discovery only, never a location requirement.
    if item.get('publication') in ('approved','approved_reference') and item.get('verification_status')=='verified':
        for field in ('region','target','support'):
            value=item.get(field);evidence=item.get('evidence',{}).get(field,{})
            if isinstance(value,str) and len(value)<=1000 and evidence.get('url')==item['url'] and evidence.get('location'):values.append(value)
    observed=review.project(review.fact_project(item,feed.get('verified_facts',{}).get(item['id']),now),feed.get('notice_observations',{}).get(item['id']),now)
    # Office locality helps discovery, never supplies a residence/farm requirement.
    for field in ('target','support'):
        value=observed.get(field)
        if observed.get('verified_facts_at') and isinstance(value,str) and len(value)<=1000:values.append(value)
    office=observed.get('application_preparation',{}).get('office_note')
    if isinstance(office,str) and len(office)<=100:values.append(office)
    for condition in approved_conditions(item,feed,now):
        values.append(labels.get(condition.get('kind'),''))
        values.append(json.dumps(condition.get('value',{}),ensure_ascii=False))
    return rag_dialogue.normalized(' '.join(values))

def safe_url(value):
    from urllib.parse import urlsplit,parse_qs
    try:
        u=urlsplit(value)
        return u.scheme=='https' and u.hostname in HOSTS and not u.username and not u.password and u.port in (None,443) and not u.fragment and not any(re.search(r'key|token|auth|secret|password|session',k,re.I) for k in parse_qs(u.query))
    except (ValueError,TypeError):return False

def records(feed,now=None):
    from urllib.parse import urlsplit
    now=now or datetime.now(timezone.utc)
    if not isinstance(feed,dict) or feed.get('local_review_only') is True or feed.get('schema_version')!='munongsa-support-public-v1':return []
    values=feed.get('notices',[])
    if not isinstance(values,list) or len(values)>2000:return []
    ids=[v.get('id') for v in values if isinstance(v,dict)]
    if len(ids)!=len(values) or len(set(ids))!=len(ids):return []
    out=[]
    for value in values:
        try:
            if value.get('local_review_only') is True:continue
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

TOPICS=(('startup',r'창업|귀농|처음|초보|정착|농사.{0,6}시작',r'창업|귀농|정착|후계농','창업·영농 시작'),('facility',r'시설|하우스|온실|스마트팜|현대화',r'시설|하우스|온실|스마트팜|현대화','시설 설치·개선'),('machinery',r'농기계|트랙터|농업기계',r'농기계|트랙터|농업기계','농기계 구입'),('education',r'교육|배우|연수|공부',r'교육|연수|대학|교육생|학습|수강','농업 교육'),('fertilizer',r'비료|유기질|유기농업자재|토양',r'비료|유기질|유기농업자재|토양','비료·토양 관리'),('export',r'수출|해외판로',r'수출|해외판로','수출 지원'),('insurance',r'보험|재해',r'보험|재해','보험·재해'),('finance',r'융자|대출|금융|운영\s*자금|자금.{0,4}부족',r'융자|대출|금융|운영\s*자금','금융·운영 자금'))

def discovery_quality(question,title,hay,context=None,purpose=None):
    q=question.lower();title=title.lower();hay=hay.lower()
    terms=[re.sub(r'(?:으로|에서|관련|을|를|이|가|은|는)$','',t) for t in re.findall('[가-힣a-z0-9]+',q)]
    terms=[t for t in terms if len(t)>1 and t not in {'지원사업','지원','사업','공고','농사','농업','농업인','관련','어떤','있어','알려줘','보여줘','하려고','해요'}]
    hits=[t for t in terms if t in hay]
    purpose=hay if purpose is None else purpose.lower()
    wanted=[g for g in TOPICS if re.search(g[1],q)]
    installation=bool(re.search(r'설치|하우스|온실|현대화',q))
    thematic=[g for g in wanted if re.search(g[2],purpose) and (g[0]!='facility' or not installation or re.search(r'시설원예|시설현대화|시설지원|시설\s*지원|온실|하우스|스마트팜|시설.{0,8}(?:설치|신축|개보수|현대화)',purpose))]
    import rag_crops
    crop=rag_crops.find(question) or (context or {}).get('search_crop') or (context or {}).get('crop')
    broadened=not wanted and bool(crop) and (context or {}).get('planned') is True and bool(re.search(TOPICS[0][2],purpose))
    related=len(thematic)==len(wanted) if wanted else bool(crop in hay or broadened) if crop else bool(hits)
    reasons=[' · '.join(g[3] for g in thematic)+' 분야의 공개 정보 일치'] if thematic else ['영농 준비 관련 대안 · 작물 전용 사업 아님'] if broadened else ['공개 정보에 '+crop+' 명시'] if crop and crop in hay else ['검색어가 공개 정보에 포함'] if hits else []
    return {'score':sum(20 if t in title else 8 for t in hits)+sum(70 if re.search(g[2],title) else 35 for g in thematic),'matches':related,'reasons':reasons,'broadened':broadened}

def discovery_score(question,title,hay):
    r=discovery_quality(question,title,hay)
    return r['score'],r['matches']

def matches(question,feed,context=None,now=None):
    context=context or {};now=now or datetime.now(timezone.utc);text=rag_dialogue.normalized(question)
    personal=question=='선택한 조건으로 지원사업을 찾아주세요.'
    archive=archive_requested(text)
    text=re.sub(r'지난|과거|예전|종료된|마감된|기한\s*경과|기간\s*경과|보여줘|포함','',text)
    compact=re.sub(r'[^0-9a-z가-힣]','',text.lower())
    area=rag_dialogue.area_in(text) or context.get('farm_region') or context.get('region')
    import rag_crops
    crop=rag_crops.find(text) or context.get('search_crop') or context.get('crop')
    generic={'지원사업','지원','공고','사업','안내','신청','모집','농업','농업인','관련','알려줘','확인','조건','자격','해주세요','현재','전체','공개','있나요','있는','에서','찾아줘'}
    terms=[re.sub(r'(?:으로|에서|관련|을|를|이|가|은|는)$','',v) for v in re.findall(r'[가-힣A-Za-z0-9]+',text)]
    terms=[v for v in terms if len(v)>=2 and v not in generic and v not in rag_dialogue.AREAS and v not in {'농사짓는데','농사짓고','찾고','싶어요','받을','있을까요','알고','싶어','해주세요','시작하려는데','재배해요','키워요','있어요','알려주세요','등록했어요','등록해야','어떤','해당하는','가능한'}]
    terms=[v for v in terms if v not in ('공식','모든')]
    ranked=[]
    for raw in records(feed,now):
        title=rag_dialogue.normalized(raw['title']);hay=search_text(raw,feed,now);nt=re.sub(r'[^0-9a-z가-힣]','',title.lower())
        exact=len(nt)>=6 and nt in compact
        title_crop=rag_crops.find(title)
        full_catalogue=bool(re.fullmatch(r'(?:전체|모든|공개)\s*(?:지원사업|공고)',text))
        if not exact and not full_catalogue:
            if '보조금' in text and not re.search(r'융자|대출|금융',text) and re.search(r'융자|대출|신용보증|이차보전',title):continue
            if crop and title_crop and title_crop!=crop:continue
            farm_intent=bool(crop or context.get('planned') or context.get('applicant')=='individual_farmer')
            if farm_intent and re.search(r'수출|가공식품|기업|업체|기관\s*모집',title) and not re.search(r'수출|가공|기업|업체|기관',text):continue
        shown=review.project(review.fact_project(raw,feed.get('verified_facts',{}).get(raw['id']),now),feed.get('notice_observations',{}).get(raw['id']),now)
        past=review.notice_state(shown,now)=='elapsed'
        if not exact and past!=archive:continue
        if re.search(r'신청기간.{0,8}남|기간.{0,5}남은|마감.{0,5}남은',text) and review.notice_state(shown,now) not in ('window','upcoming'):continue
        quality=discovery_quality(text,title,hay.replace(raw['institution'],''),context,title+' '+str(shown.get('support','')));relevance,related=quality['score'],quality['matches']
        constrained=bool(crop or any(re.search(g[1],text) for g in TOPICS))
        if not exact and constrained and not full_catalogue and not related:continue
        if (context.get('planned') is True or context.get('applicant')=='individual_farmer') and re.search(r'기업|수출업체|기관 모집',title) and not re.search(r'기업|수출',text):relevance-=45
        period_only=bool(re.search(r'신청기간.{0,8}남|기간.{0,5}남은|마감.{0,5}남은',text)) and not any(re.search(g[1],text) for g in TOPICS)
        broad=bool(re.fullmatch(r'(?:전체|공개|지난)?\s*(?:지원사업|공고)',text)) or bool(re.fullmatch(r'.{0,10}(?:지원사업|공고)\s*(?:알려줘|찾아줘|보여줘)[.!?]*',text))
        if not exact and not personal and not related and not broad and not period_only:continue
        scope=context.get('search_scope')
        locality=scope_relevance(raw,feed,now,scope) if scope else 0
        if not exact and scope and locality<0:continue
        # Definite ineligibility cannot be repaired by relevance or wider search.
        if not full_catalogue and (comparison(raw,feed,context,now) or {}).get('decision',{}).get('excluded'):continue
        ranked.append((1000 if exact else relevance+locality*30,raw))
    def order(pair):
        score,item=pair
        shown=review.project(review.fact_project(item,feed.get('verified_facts',{}).get(item['id']),now),feed.get('notice_observations',{}).get(item['id']),now)
        period=review.notice_state(shown,now)
        compared=comparison(item,feed,context,now)
        mismatch=bool(compared and compared.get('decision',{}).get('excluded'))
        tier=compared['decision']['tier'] if compared and compared.get('decision') else 3
        announced=shown.get('actual_reception_state')=='operator_notice'
        try:checked=-datetime.fromisoformat(item['last_checked_at']).timestamp()
        except (ValueError,KeyError,TypeError):checked=0
        return (score!=1000,mismatch,0 if personal else -score,tier,{'window':0 if announced else 1,'upcoming':2,'standing':3,'unknown':4,'elapsed':5}[period],-score,checked,item['title'])
    found=[];seen=set()
    for _,r in sorted(ranked,key=order):
        key=(r['url'],re.sub(r'[^0-9a-z가-힣]','',r['title'].lower()))
        if key not in seen:found.append(r);seen.add(key)
    return [r for r in found if not (comparison(r,feed,context,now) or {}).get('decision',{}).get('excluded')] if personal else found

def comparison(item,feed,context,now):
    import rag_profile
    basis={k:item.get(k) for k in ('id','title','url','target','region','reference_application_dates','application_period','eligibility')}
    candidates=[feed.get('verified_comparisons',{}).get(item['id']),feed.get('verified_facts',{}).get(item['id'])]
    for annotation in candidates:
        try:
            if not annotation or annotation.get('review_required') or annotation.get('complete') is not False or annotation.get('basis')!=basis or datetime.fromisoformat(annotation['expires_at'])<=now:continue
            values=annotation.get('conditions',[])
            if not values or not all(c.get('status')=='verified' and c.get('presence')=='specified' and c.get('evidence',{}).get('fact_confirmed') is True and c['evidence'].get('url')==item['url'] and c['evidence'].get('location') for c in values):continue
            payload=item.get('eligibility',{});conditions=list(payload.get('conditions',[]))+values
            if len({c['condition_id'] for c in conditions})!=len(conditions):continue
            projected={**item,'eligibility':{'conditions':conditions,'logic':{'op':'AND','children':[payload.get('logic',{'op':'UNKNOWN','children':[]})]+[{'condition_id':c['condition_id']} for c in values]}}}
            result=rag_profile.compare({'public':projected,'record':{'fields':{}}},context,safe_url,rag_dialogue.AREAS)
            result['checks'].insert(0,'확인된 필수조건 일부만 비교했습니다. 전체 신청 자격과 실제 접수 가능 여부는 미확정입니다.')
            from support_recommendation_readiness import apply
            shown=review.fact_project(item,feed.get('verified_facts',{}).get(item['id']),now)
            audience=bool(context.get('planned') and (shown.get('verified_facts_at') and '수출' in shown.get('target','') or any(c.get('kind')=='export_activity' and c.get('value',{}).get('required') is True for c in rag_profile.project_public(item,safe_url).get('eligibility',{}).get('conditions',[]))))
            return apply(result,national=shown.get('geographic_scope')=='nationwide_verified' and bool(shown.get('verified_facts_at')),audience_check=audience)
        except (KeyError,ValueError,TypeError):continue
    shown=review.fact_project(item,feed.get('verified_facts',{}).get(item['id']),now)
    payload=item.get('eligibility',{})
    result=rag_profile.compare({'public':item,'record':{'fields':{}}},context,safe_url,rag_dialogue.AREAS)
    from support_recommendation_readiness import apply
    audience=bool(context.get('planned') and (shown.get('verified_facts_at') and '수출' in shown.get('target','') or any(c.get('kind')=='export_activity' and c.get('value',{}).get('required') is True for c in rag_profile.project_public(item,safe_url).get('eligibility',{}).get('conditions',[]))))
    return apply(result,national=shown.get('geographic_scope')=='nationwide_verified' and bool(shown.get('verified_facts_at')),audience_check=audience)

def program(item,feed,now,context=None):
    shown=review.project(review.fact_project(item,feed.get('verified_facts',{}).get(item['id']),now),feed.get('notice_observations',{}).get(item['id']),now)
    dates=shown.get('reference_application_dates',{})
    state=review.notice_state(shown,now)
    preparation=shown.get('application_preparation',{})
    conditions=[]
    for c in approved_conditions(item,feed,now):
        value=c.get('value',{})
        if c.get('kind')=='farm_registration' and value.get('registered') is True:conditions.append('농업경영체 등록 필요 · 확인된 일부 필수조건')
        elif c.get('kind')=='crop' and isinstance(value.get('any_of'),list):conditions.append('실제 재배 작물: '+' · '.join(str(v) for v in value['any_of']))
        elif c.get('kind')=='business_location' and value.get('location_basis')=='farm_land':conditions.append('영농지 기준: '+' · '.join(str(v) for v in value.get('regions',[])))
    compared=comparison(item,feed,context or {},now)
    result_comparison=compared or {'label':'추가 확인 필요','reasons':[], 'checks':['제목·기관·공식 링크 중심의 기본 안내입니다. 지역·작물 관련성은 신청 자격 충족을 뜻하지 않습니다.'], 'questions':[]}
    verdict=result_comparison['decision']
    return {'id':item['id'],'name':item['title'],'source_url':item['url'],'checked_at':shown.get('official_observation_at',item['last_checked_at']),
            'application_entry_url':preparation.get('entry_url'),'application_entry_kind':preparation.get('entry_kind'),
            'required_conditions':conditions,'additional_checks':['전체 신청 자격·지원금·서류는 검증된 상세 근거가 없으면 공식 원문과 담당 기관에서 확인해 주세요.'],
            'evidence_level':'공식 공고 기본 안내','evidence_note':'공식 제목·기관·링크 안내이며, 승인된 상세 근거나 최신 원문 전체 자격 검증이 아닙니다.',
            'application_period':{'start':dates.get('start',{}),'end':dates.get('end',{}),'description':(review.closure_label(shown) or '기재 신청기간 경과')+' · 과거 공고의 금액·조건은 현재 신청에 적용할 수 없습니다. 연장·재공고는 별도 확인하세요.' if state=='elapsed' else '기재 신청기간과 실제 접수 가능 여부는 별개입니다.','actual_reception_confirmed':False},
            'needs_verification':True,'comparison':result_comparison,'guidance_only':not bool(result_comparison.get('verified_condition_count')),'partial_comparison':bool(result_comparison.get('verified_condition_count')),
            'card':{'group':'elapsed' if state=='elapsed' else 'mismatch' if verdict['excluded'] else 'related' if verdict['category']=='A' else 'check','label':verdict['label'],'lifecycle_label':review.closure_label(shown),'period_state':{'window':'within_recorded_dates','upcoming':'upcoming','elapsed':'elapsed'}.get(state,'unknown'),
                    'institution':item['institution'],'reception_state':shown.get('actual_reception_state','unconfirmed'),'facts':{'region':'전국 · 세부 자격 별도 확인' if shown.get('geographic_scope')=='nationwide_verified' and shown.get('verified_facts_at') else shown.get('region') if shown.get('region') not in (None,'','unknown') else '확인 필요','target':shown.get('target') if shown.get('target') not in (None,'','unknown') else preparation.get('target_note','확인 필요'),'support':shown.get('support') if shown.get('support') not in (None,'','unknown') else '공식 원문에서 확인','funding':[],'method':[preparation.get('method') or shown['application_method']] if preparation.get('method') or shown.get('application_method') else [],'documents':[preparation['documents_note']] if preparation.get('documents_note') else []},'questions':result_comparison['questions']}}

def listing_version(item,feed,now=None):
    """Bound the existing three-item reference to public facts, not collection times."""
    now=now or datetime.now(timezone.utc)
    observation=feed.get('notice_observations',{}).get(item['id'],{})
    material={k:item.get(k) for k in ('id','title','url','target','region','support','application_period','reference_application_dates','eligibility','publication','verification_status')}
    material['conditions']=approved_conditions(item,feed,now)
    material['observed']={k:observation.get(k) for k in ('article_sha','reference_application_dates','standing','review_required')}
    return hashlib.sha256(json.dumps(material,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def continuation(encoded,corpus,grounded=None):
    """Resolve public-list follow-ups with the same comparison function, no new facts."""
    question,actual=rag_dialogue.decode(encoded);feed=corpus.get('guidance_feed',{});now=datetime.now(timezone.utc)
    ids=actual.get('list_ids',[]);versions=actual.get('list_versions',[])
    strict={d['public']['id'] for d in corpus['documents'].values()}
    if not ids or all(i in strict for i in ids):return None
    ordinal=[]
    for m in re.finditer(r'(첫|두|세|[1-3])\s*(?:번째|번)(?:째)?',question):
        index={'첫':0,'두':1,'세':2,'1':0,'2':1,'3':2}[m[1]]
        if index not in ordinal:ordinal.append(index)
    if actual.get('conversation_topic') and not ordinal and not re.search(r'사업|공고|아까|앞서',question):return None
    follow=bool(ordinal or re.search(r'그\s*(?:중|사업|공고|거|건|게)|아까|앞서|다시\s*설명|등록\s*(?:하면|한다면)|그럼|신청\s*(?:조건|서류)|필요한\s*서류',question))
    if not follow:return None
    facts,error=rag_dialogue.rag_profile.extract(question,rag_dialogue.AREAS,rag_dialogue.CROPS,rag_dialogue.normalized)
    if error:return rag_dialogue.response(error,actual,'clarify',status='needs_verification')
    if facts and not re.search(r'[?？]|신청|가능|달라|비교|조건|다시',question):return None
    by_id={n['id']:n for n in records(feed,now)}
    intact=len(ids)==len(versions) and all(i in by_id and listing_version(by_id[i],feed,now)==v for i,v in zip(ids,versions))
    if not intact:return rag_dialogue.response('앞서 본 공고의 근거나 목록이 변경되어 순서를 그대로 사용할 수 없어요. 사업명으로 다시 확인해 주세요.',actual,'clarify',status='needs_verification')
    if re.search(r'그거\s*말고\s*다른|아까.*말고.*다른',question):
        return rag_dialogue.response('현재 입력 조건은 유지했어요. 다른 공고를 찾을 분야나 사업명을 알려주세요. 같은 공고를 새로운 결과처럼 다시 추천하지 않을게요.',actual,'clarify',suggestions=('선택한 조건으로 지원사업을 찾아주세요.',))
    if re.search(r'아니.*내\s*말|그게\s*아니',question):return rag_dialogue.response('어떤 사업이나 조건을 다르게 이해했는지 짧게 알려주세요. 말씀하시기 전에는 입력 조건을 바꾸지 않을게요.',actual,'clarify')
    if any(i>=len(ids) for i in ordinal):return rag_dialogue.response('앞선 목록에 해당 순서가 없어요. 사업명이나 표시된 순서를 알려주세요.',actual,'clarify')
    current=[i for i in actual.get('notice_ids',[]) if i in ids] or ids
    if not ordinal and len(current)>1 and not re.search(r'그\s*중|사업.*기억|공고.*기억|목록|모두|다시\s*설명',question):
        return rag_dialogue.response('어느 사업을 확인할까요? 앞선 목록의 순서나 사업명을 알려주세요.',actual,'clarify',suggestions=tuple(by_id[i]['title'] for i in ids))
    selected=[ids[i] for i in ordinal] if ordinal else current
    hypothetical=rag_dialogue.rag_profile.hypothetical(question)
    evaluation={**actual,**facts}
    if hypothetical and re.search(r'등록\s*(?:하면|한다면|할\s*경우)',question):evaluation['farm_registered']='yes'
    context={**actual,'notice_ids':selected} if hypothetical else {**evaluation,'notice_ids':selected}
    programs=[]
    by_key={doc['public']['id']:key for key,doc in corpus['documents'].items()}
    query='신청 방법 접수처 필수 제출서류' if re.search(r'서류|접수|어떻게|준비|방법',question) else '지원 금액 한도' if re.search(r'지원금|금액|얼마',question) else '신청 대상 자격 조건 지원 내용'
    for identity in selected:
        part=grounded(query,by_key[identity]) if grounded and identity in by_key else None
        detailed=next((p for p in (part or {}).get('programs',[]) if p['id']==identity),None)
        if detailed:
            detailed['comparison']=comparison(by_id[identity],feed,evaluation,now)
            detailed['card']['label']=detailed['comparison']['decision']['label']
            detailed['card']['group']='mismatch' if detailed['comparison']['decision']['excluded'] else detailed['card']['group']
            detailed['card']['questions']=detailed['comparison']['questions']
        programs.append(detailed or program(by_id[identity],feed,now,evaluation))
    for p in programs:p['comparison']['hypothetical']=hypothetical
    intro='가정한 조건으로 비교했으며 실제 영농 조건은 변경하지 않았어요.' if hypothetical else '앞서 선택한 공고를 현재 입력 조건으로 다시 비교했어요.'
    parts=[p['name']+' — '+p['comparison']['decision']['label']+'\n추가 확인: '+' / '.join(p['comparison']['checks']) for p in programs]
    return {**rag_dialogue.response(intro+' 전체 신청 자격과 실제 접수는 확정하지 않습니다. 카드의 ‘내 조건·신청 준비 보기’에서 방법·서류·공식 근거를 확인하세요.\n\n'+'\n\n'.join(parts),context,'answer',status='needs_verification',programs=programs),
            'sources':[{'url':p['source_url'],'location':'현재 공개 공고·승인된 일부 조건 비교','checked_at':p['checked_at']} for p in programs],'understanding':'rules'}


def named_records(question,feed,now=None):
    """Public title phrases identify the subject, never an eligibility condition."""
    compact=lambda s:re.sub(r'[^0-9a-z가-힣]','',rag_dialogue.normalized(s).lower())
    q=compact(question);ranked=[]
    generic={'지원','지원사업','사업','공고','신청','안내','모집','추가','변경','연장','농업인','농업경영체','농업경영정보','농업법인','농업용','농업','계획','시행계획','첨부파일','있음','신청서','등록'}
    for item in records(feed,now):
        words=[v for v in re.findall(r'[가-힣a-zA-Z]+',item['title']) if v not in generic and len(v)>=2]
        phrases=[v for v in words if len(v)>=6]
        # Do not join across generic words: only actual adjacent title words.
        tokens=re.findall(r'[가-힣a-zA-Z]+',item['title'])
        phrases += [a+b for a,b in zip(tokens,tokens[1:]) if a not in generic and b not in generic and len(a)>=2 and len(b)>=2 and len(a+b)>=6]
        score=max([len(compact(item['title'])) if compact(item['title']) in q else 0]+[len(v) for v in phrases if compact(v) in q])
        if score>=6:ranked.append((score,item))
    if not ranked:return []
    best=max(s for s,_ in ranked);found=[n for s,n in ranked if s==best]
    area=rag_dialogue.area_in(question)
    local=[n for n in found if area and area in n['title']+' '+n['institution']]
    return local or found


def named_response(encoded,corpus):
    question,context=rag_dialogue.decode(encoded)
    if page_request(question) or question=='선택한 조건으로 지원사업을 찾아주세요.':return None
    compact=lambda s:re.sub(r'[^0-9a-z가-힣]','',rag_dialogue.normalized(s).lower())
    # Keep the existing full-title route and its reviewed detailed evidence.
    if any(compact(d['public']['title']) in compact(question) for d in corpus['documents'].values()):return None
    feed=corpus.get('guidance_feed',{});now=datetime.now(timezone.utc)
    named=named_records(question,feed,now)
    if not named:return None
    # Reuse only explicit self-reported facts; hypothetical facts stay separate.
    if not rag_dialogue.rag_profile.hypothetical(question):
        facts,error=rag_dialogue.rag_profile.extract(question,rag_dialogue.AREAS,rag_dialogue.CROPS,rag_dialogue.normalized)
        if not error:context={**context,**facts}
    scoped={**corpus,'guidance_feed':{**feed,'notices':named}}
    return respond(rag_dialogue.PREFIX+json.dumps(context,ensure_ascii=False)+rag_dialogue.SEPARATOR+question,scoped,named=True)


def respond(encoded,corpus,*,explicit=False,fallback=None,include_approved=False,named=False):
    feed=corpus.get('guidance_feed')
    if not feed:return None
    question,context=rag_dialogue.decode(encoded);now=datetime.now(timezone.utc)
    page=page_request(question)
    if page:
        question=page['query']
        context={k:v for k,v in context.items() if k not in ('notice_ids','list_ids','list_versions','last_kind')}
        explicit=False
        subjects=named_records(question,feed,now)
        if subjects:
            feed={**feed,'notices':subjects};named=True
    limit=requested_count(question)
    # Count words are presentation instructions, not business relevance terms.
    search_question=re.sub(r'\d{1,2}\s*(?:[~～〜\-–]\s*\d{1,2})?\s*개(?:\s*정도)?','',question)
    strict={d['public']['id'] for d in corpus['documents'].values()}
    found=records(feed,now) if named else matches(search_question,feed,context,now)
    exact=[n for n in found if re.sub(r'[^0-9a-z가-힣]','',rag_dialogue.normalized(n['title']).lower()) in re.sub(r'[^0-9a-z가-힣]','',rag_dialogue.normalized(question).lower())]
    if explicit:
        found=[n for n in exact if include_approved or n['id'] not in strict]
        if not found:return None
    elif fallback and fallback.get('programs') and not page and len(found)<=3 and question!='선택한 조건으로 지원사업을 찾아주세요.':return None
    # Follow-up to a metadata-only listing: do not redirect it to another approved business.
    previous=[] if page else context.get('notice_ids',[])
    if question!='선택한 조건으로 지원사업을 찾아주세요.' and not explicit and not named and previous and any(i not in strict for i in previous) and re.search(r'그\s*사업|서류|지원금|자격|조건|마감|첫\s*번째|두\s*번째|^신청\s*가능',question):
        by_id={n['id']:n for n in records(feed,now)}
        found=[by_id[i] for i in previous if i in by_id]
        if not found:return rag_dialogue.response('앞서 본 공고를 최신 공개 목록에서 확인할 수 없어 안내를 보류했어요. 사업명으로 다시 찾아주세요.',{},'clarify',status='needs_verification')
    if not found:
        if context.get('search_scope') and not explicit:
            kept={k:v for k,v in context.items() if k not in ('notice_ids','list_ids','list_versions','last_kind')}
            return {**rag_dialogue.response('현재 '+context['search_scope']+' 탐색 범위에서 질문과 관련된 공개 공고를 찾지 못했어요. 신청 자격이 없다는 뜻은 아닙니다. 검색 지역을 넓히거나 찾는 지원 목적을 바꿀 수 있어요.',kept,'catalogue',status='no_evidence'), 'catalogue_total':0,'catalogue_start':0,'catalogue_next':None,'catalogue_search_scope':context['search_scope'],'catalogue_requested':limit,'catalogue_available':0,'understanding':'rules'}
        if not explicit and not page and question=='선택한 조건으로 지원사업을 찾아주세요.':
            kept={k:v for k,v in context.items() if k not in ('notice_ids','list_ids','list_versions','last_kind')}
            return rag_dialogue.response('입력한 조건으로 안내할 수 있는 현재 공개 공고를 찾지 못했어요. 공고나 확인된 조건 정보가 부족할 수 있으며, 신청 자격이 없다는 뜻은 아닙니다. 조건을 수정하거나 전체 지원사업을 살펴보세요. 지난 공고는 현재 신청 정보와 구분하여 볼 수 있어요.',kept,'clarify',status='no_evidence',suggestions=('전체 지원사업','지난 공고'))
        return None
    available=len(found)
    if limit:found=found[:limit]
    fingerprint=hashlib.sha256(json.dumps({'scope':context.get('search_scope'),'profile':{k:v for k,v in context.items() if k in rag_dialogue.rag_profile.KEYS or k in ('region','crop','farm_registered','search_crop')},'items':[{'id':n['id'],'version':listing_version(n,feed,now)} for n in found]},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    offset=page['offset'] if page else 0
    if page and (page['fingerprint']!=fingerprint or offset>=len(found)):
        return rag_dialogue.response('공고 목록이나 확인된 조건이 변경됐어요. 같은 질문으로 다시 검색해 주세요.',context,'clarify',status='needs_verification')
    chosen=found[offset:offset+3];programs=[program(n,feed,now,context) for n in chosen]
    for n,p in zip(chosen,programs):
        shown=review.fact_project(n,feed.get('verified_facts',{}).get(n['id']),now)
        quality=discovery_quality(question,n['title'],search_text(n,feed,now).replace(n['institution'],''),context,n['title']+' '+str(shown.get('support','')))
        p['card']['discovery_reason']='사업명 일치' if n in exact else ' / '.join(quality['reasons'])[:160]
    conversation={**context,'notice_ids':[n['id'] for n in chosen],'list_ids':[n['id'] for n in chosen],'list_versions':[listing_version(n,feed,now) for n in chosen],'last_kind':'results'}
    for key in ('search_offset','search_fingerprint'):conversation.pop(key,None)
    if offset+len(chosen)<len(found):conversation.update(search_offset=offset+len(chosen),search_fingerprint=fingerprint)
    if len(question)<=300 and not re.search(r'[\x00-\x1f<>]',question):conversation['search_query']=question
    summary='\n\n'.join(p['name']+' — '+p['card']['label']+'\n확인할 조건: '+' / '.join(p['comparison']['checks']) for p in programs)
    intro='질문과 공개 정보의 관련성을 기준으로 탐색한 결과입니다. 관련성이 신청 자격 충족을 뜻하지 않습니다. 공식 조건 비교와 추가 확인 사항을 따로 확인하세요.' if question!='선택한 조건으로 지원사업을 찾아주세요.' else '공식 조건 비교와 참고 공고를 구분해 안내합니다. 전체 신청 자격과 실제 접수는 별도 확인이 필요합니다.'
    if limit:intro=f'요청하신 최대 {limit}건 중 관련 공개 공고 {len(found)}건을 {min(3,len(found))}건씩 안내합니다. '+('관련 공고가 부족해 개수를 채우지 않았습니다. ' if available<limit else '')+intro
    if context.get('search_scope'):intro=context['search_scope']+' 범위의 관련 공고 탐색입니다. 실제 영농지역·거주지는 유지했으며, 검색 지역이 신청 가능 지역을 뜻하지 않습니다. '+intro
    return {**rag_dialogue.response(f'공식 공고 {len(found)}건 중 {offset+1}~{offset+len(chosen)}번째를 안내합니다. '+intro+'\n\n'+summary,conversation,'catalogue',status='needs_verification',programs=programs),
            'sources':[{'url':p['source_url'],'location':'공식 제목·기관·원문 링크 확인','checked_at':p['checked_at']} for p in programs],
            'catalogue_total':len(found),'catalogue_requested':limit,'catalogue_available':available,'catalogue_search_scope':context.get('search_scope'),'catalogue_start':offset+1,'catalogue_scope':'past' if all(p['card']['period_state']=='elapsed' for p in programs) else 'current',
            'catalogue_next':{'query':question,'offset':offset+len(chosen),'fingerprint':fingerprint} if offset+len(chosen)<len(found) and len(question)<=300 else None,'understanding':'rules'}
