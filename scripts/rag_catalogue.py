"""Public listing discovery only. Never inserts a record into approved RAG evidence."""
from datetime import datetime,timezone
import re,json,hashlib
import rag_search,rag_dialogue
import support_notice_review as review

HOSTS={'www.rda.go.kr','www.buan.go.kr','www.gochang.go.kr','www.jinan.go.kr','www.imsil.go.kr','www.sunchang.go.kr','www.jeonbuk.go.kr','www.bizinfo.go.kr','bizinfo.go.kr','www.mafra.go.kr','global.at.or.kr','agriacademy.jeonbuk.go.kr','www.gunsan.go.kr','www.jeonju.go.kr','www.koat.or.kr','www.gimje.go.kr','www.oads.or.kr'}
PAGE_PREFIX='[공식 공고 더 보기]\n'

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
    crop=next((c for c in ('토마토','딸기','감귤','마늘','벼','사과','포도','상추','고추','배추','콩','오이') if c in q),None)
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
    crop=next((v for v in rag_dialogue.CROPS if v in text),None) or context.get('crop')
    generic={'지원사업','지원','공고','사업','안내','신청','모집','농업','농업인','관련','알려줘','확인','조건','자격','해주세요','현재','전체','공개','있나요','있는','에서','찾아줘'}
    terms=[re.sub(r'(?:으로|에서|관련|을|를|이|가|은|는)$','',v) for v in re.findall(r'[가-힣A-Za-z0-9]+',text)]
    terms=[v for v in terms if len(v)>=2 and v not in generic and v not in rag_dialogue.AREAS and v not in {'농사짓는데','농사짓고','찾고','싶어요','받을','있을까요','알고','싶어','해주세요','시작하려는데','재배해요','키워요','있어요','알려주세요','등록했어요','등록해야','어떤','해당하는','가능한'}]
    terms=[v for v in terms if v not in ('공식','모든')]
    ranked=[]
    for raw in records(feed,now):
        title=rag_dialogue.normalized(raw['title']);hay=search_text(raw,feed,now);nt=re.sub(r'[^0-9a-z가-힣]','',title.lower())
        exact=len(nt)>=6 and nt in compact
        shown=review.project(review.fact_project(raw,feed.get('verified_facts',{}).get(raw['id']),now),feed.get('notice_observations',{}).get(raw['id']),now)
        past=review.notice_state(shown,now)=='elapsed'
        if not exact and past!=archive:continue
        if re.search(r'신청기간.{0,8}남|기간.{0,5}남은|마감.{0,5}남은',text) and review.notice_state(shown,now) not in ('window','upcoming'):continue
        quality=discovery_quality(text,title,hay.replace(raw['institution'],''),context,title+' '+str(shown.get('support','')));relevance,related=quality['score'],quality['matches']
        if (context.get('planned') is True or context.get('applicant')=='individual_farmer') and re.search(r'기업|수출업체|기관 모집',title) and not re.search(r'기업|수출',text):relevance-=45
        period_only=bool(re.search(r'신청기간.{0,8}남|기간.{0,5}남은|마감.{0,5}남은',text)) and not any(re.search(g[1],text) for g in TOPICS)
        if not exact and not personal and not related and not re.fullmatch(r'(?:전체|공개|지난)?\s*(?:지원사업|공고)',text) and not period_only:continue
        ranked.append((1000 if exact else relevance,raw))
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
    strict={d['public']['id'] for d in corpus['documents'].values()}
    found=records(feed,now) if named else matches(question,feed,context,now)
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
        if not explicit and not page and question=='선택한 조건으로 지원사업을 찾아주세요.':
            kept={k:v for k,v in context.items() if k not in ('notice_ids','list_ids','list_versions','last_kind')}
            return rag_dialogue.response('입력한 조건으로 안내할 수 있는 현재 공개 공고를 찾지 못했어요. 공고나 확인된 조건 정보가 부족할 수 있으며, 신청 자격이 없다는 뜻은 아닙니다. 조건을 수정하거나 전체 지원사업을 살펴보세요. 지난 공고는 현재 신청 정보와 구분하여 볼 수 있어요.',kept,'clarify',status='no_evidence',suggestions=('전체 지원사업','지난 공고'))
        return None
    fingerprint=hashlib.sha256(json.dumps([{'id':n['id'],'title':n['title'],'url':n['url'],'conditions':[{k:c.get(k) for k in ('condition_id','kind','value')} for c in verified_conditions(n,feed,now)]} for n in found],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    offset=page['offset'] if page else 0
    if page and (page['fingerprint']!=fingerprint or offset>=len(found)):
        return rag_dialogue.response('공고 목록이나 확인된 조건이 변경됐어요. 같은 질문으로 다시 검색해 주세요.',context,'clarify',status='needs_verification')
    chosen=found[offset:offset+3];programs=[program(n,feed,now,context) for n in chosen]
    for n,p in zip(chosen,programs):
        shown=review.fact_project(n,feed.get('verified_facts',{}).get(n['id']),now)
        quality=discovery_quality(question,n['title'],search_text(n,feed,now).replace(n['institution'],''),context,n['title']+' '+str(shown.get('support','')))
        p['card']['discovery_reason']='사업명 일치' if n in exact else ' / '.join(quality['reasons'])[:160]
    conversation={**context,'notice_ids':[n['id'] for n in chosen],'list_ids':[],'list_versions':[],'last_kind':'results'}
    summary='\n\n'.join(p['name']+' — '+p['card']['label']+'\n확인할 조건: '+' / '.join(p['comparison']['checks']) for p in programs)
    intro='질문과 공개 정보의 관련성을 기준으로 탐색한 결과입니다. 관련성이 신청 자격 충족을 뜻하지 않습니다. 공식 조건 비교와 추가 확인 사항을 따로 확인하세요.' if question!='선택한 조건으로 지원사업을 찾아주세요.' else '공식 조건 비교와 참고 공고를 구분해 안내합니다. 전체 신청 자격과 실제 접수는 별도 확인이 필요합니다.'
    return {**rag_dialogue.response(f'공식 공고 {len(found)}건 중 {offset+1}~{offset+len(chosen)}번째를 안내합니다. '+intro+'\n\n'+summary,conversation,'catalogue',status='needs_verification',programs=programs),
            'sources':[{'url':p['source_url'],'location':'공식 제목·기관·원문 링크 확인','checked_at':p['checked_at']} for p in programs],
            'catalogue_total':len(found),'catalogue_start':offset+1,'catalogue_scope':'past' if all(p['card']['period_state']=='elapsed' for p in programs) else 'current',
            'catalogue_next':{'query':question,'offset':offset+len(chosen),'fingerprint':fingerprint} if offset+len(chosen)<len(found) and len(question)<=300 else None,'understanding':'rules'}
