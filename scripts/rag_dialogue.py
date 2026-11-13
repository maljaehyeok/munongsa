"""Small, stateless conversation rules over the already verified RAG corpus."""
import json
import re
import rag_profile


def candidate_order(key, corpus, context, relevance=0):
    """Rank discovery only. Reuse approved comparison and date judgments."""
    import rag_search
    from datetime import datetime, timezone
    document=corpus['documents'][key]
    comparison=rag_profile.compare(document,context,rag_search.valid_url,AREAS)
    period=rag_search.recruitment_context(document,datetime.now(timezone.utc))
    mismatch=comparison['label']=='조건 불일치'
    elapsed=period['date_state']=='elapsed'
    timing={'within_recorded_dates':0,'deadline_day_time_unknown':0,'upcoming':1,'unknown':2,'elapsed':3}[period['date_state']]
    return (mismatch,elapsed,timing,-relevance,comparison['label']!='관련 가능성 있음',document['public']['title'])

PREFIX='[무농사 대화 참고]\n'
SEPARATOR='\n[질문]\n'
AREAS={'전주':('전주','전북'),'부안':('부안','전북'),'고창':('고창','전북'),
       '안산':('안산','경기'),'김제':('김제','전북'),'군산':('군산','전북'),'익산':('익산','전북'),'정읍':('정읍','전북'),'남원':('남원','전북'),'완주':('완주','전북'),'진안':('진안','전북'),'무주':('무주','전북'),'장수':('장수','전북'),'임실':('임실','전북'),'순창':('순창','전북'),
       '파주':('파주','경기'),'포항':('포항','경북'),'부산':('부산','부산'),
       '서울':('서울','서울'),'전북':('전북',None),'전남':('전남',None),
       '경북':('경북',None),'경남':('경남',None),'경기':('경기',None),
       '충남':('충남',None),'충북':('충북',None),'강원':('강원',None),'제주':('제주',None),
       '인천':('인천',None),'대전':('대전',None),'대구':('대구',None),'광주':('광주',None),'울산':('울산',None),'세종':('세종',None)}
ALIASES={'전북특별자치도':'전북','전라북도':'전북','전라남도':'전남','경상북도':'경북',
         '경상남도':'경남','경기도':'경기','충청남도':'충남','충청북도':'충북','강원특별자치도':'강원'}
CROPS=('마늘','고추','배추','딸기','토마토','상추','감자','벼','쌀','사과','포도','콩','오이','버섯')

def normalized(value):
    for old,new in ALIASES.items():value=value.replace(old,new)
    return value

def decode(value):
    context={};question=value
    if value.startswith(PREFIX):
        raw,question=value[len(PREFIX):].split(SEPARATOR,1)
        if len(raw)>1600:raise ValueError('context_too_long')
        context=json.loads(raw)
        if not isinstance(context,dict) or set(context)-({'region','crop','farm_registered','notice_ids','list_ids','list_versions','last_kind'}|rag_profile.KEYS):raise ValueError('context_fields')
        if 'region' in context and context['region'] not in AREAS:raise ValueError('context_region')
        if 'crop' in context and context['crop'] not in CROPS:raise ValueError('context_crop')
        if 'farm_registered' in context and context['farm_registered'] not in ('yes','no'):raise ValueError('context_registration')
        if not rag_profile.valid_context(context,AREAS):raise ValueError('context_values')
        ids=context.get('notice_ids',[])
        if not isinstance(ids,list) or len(ids)>3 or any(not isinstance(v,str) or not re.fullmatch('NOTICE-[A-Za-z0-9_-]{1,70}',v) for v in ids):raise ValueError('context_notices')
        listed=context.get('list_ids',[]);versions=context.get('list_versions',[])
        if not isinstance(listed,list) or len(listed)>3 or len(set(str(v) for v in listed))!=len(listed) or any(not isinstance(v,str) or not re.fullmatch('NOTICE-[A-Za-z0-9_-]{1,70}',v) for v in listed):raise ValueError('context_list')
        if not isinstance(versions,list) or len(versions)!=len(listed) or any(not isinstance(v,str) or not re.fullmatch('[a-f0-9]{64}',v) for v in versions):raise ValueError('context_versions')
        if context.get('last_kind','help') not in ('help','results','clarify','context'):raise ValueError('context_kind')
    if not isinstance(question,str) or not 1<=len(question.strip())<=1000:raise ValueError('question_length')
    return question.strip(),context

def response(answer,context,kind='context',status='answered',programs=None,sources=None,suggestions=()):
    return {'mode':'local','status':status,'answer':answer,'programs':programs or [],'sources':sources or [],
            'kind':kind,'conversation':context,'suggestions':list(suggestions)[:3]}

def area_in(question):
    text=normalized(question)
    found=[(m.start(),area) for area in AREAS for m in re.finditer(re.escape(area),text)]
    return max(found)[1] if found else None

def region_matches(area,item,document=None):
    """Discovery relevance only; residence is never a complete eligibility check."""
    region=normalized(str(item.get('region','')))
    if region in ('','unknown') and document:
        region=normalized(str(document['record'].get('fields',{}).get('conditions',{}).get('value','')))
    city,province=AREAS[area]
    if any(v in region for v in ('국가 지원사업','전국','지역 제한 없음','지역제한 없음')):return 1
    if city in region:return 3
    if province and province in region:
        other_cities=[name for name,(c,p) in AREAS.items() if p==province and name!=area]
        if not any(c in region for c in other_cities):return 2
    if not province and any(p==city and name in region for name,(c,p) in AREAS.items()):return 2
    if not region.strip() or region=='unknown' or re.search(r'미확인|확인 필요|확인되지|접수 공고',region):return 1
    return 0

def corpus_text(document):
    item=document['public'];record=document['record']
    fields=record.get('fields',{})
    return ' '.join(str(v) for v in (item.get('title',''),item.get('target',''),
        item.get('support',''),fields.get('conditions',{}).get('value','')))


def notice_version(document):
    import hashlib
    # Covers both evidence and approved public conditions/dates, never feed time.
    return hashlib.sha256(json.dumps({'public':document['public'],'record':document['record']},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def remember(out,corpus):
    """Only bounded routing metadata in browser memory; no answer/history text."""
    context=out.setdefault('conversation',{});programs=out.get('programs',[])
    by_id={d['public']['id']:d for d in corpus['documents'].values()}
    ids=context.get('list_ids',[]);versions=context.get('list_versions',[])
    intact=bool(ids) and len(ids)==len(versions) and all(i in by_id and notice_version(by_id[i])==v for i,v in zip(ids,versions))
    if programs and (out.get('kind') in ('catalogue','recommendation') or not intact):
        ids=[p['id'] for p in programs]
        context.update(list_ids=ids,list_versions=[notice_version(by_id[i]) for i in ids])
    context['last_kind']='results' if programs else 'help' if out.get('kind') in ('help','greeting','thanks','condition_edit') else 'clarify' if out.get('kind')=='clarify' else 'context'
    return out


def continuation(encoded,corpus,grounded,intent=None):
    """Resolve follow-ups against an intact displayed list, then reuse evidence."""
    question,context=decode(encoded);context=dict(context)
    facts,error=rag_profile.extract(question,AREAS,CROPS,normalized)
    if facts or error or rag_profile.hypothetical(question):return None
    compact=re.sub(r'[\s?!.,~，。]','',question)
    correction=compact in ('아니','아니내말은그게아니라','내말은그게아니야') or intent=='correction'
    repeat=compact in ('응','네','무슨뜻이야','무슨말이야','다시설명해줘','다시설명해','아까말한거다시알려줘','아까알려준거다시알려줘') or intent=='rephrase'
    next_step=compact in ('그럼어떻게해야해','어떻게하면돼','다음엔뭘해야해') or intent=='next_step'
    ordinal=[]
    for m in re.finditer(r'(첫|두|세|[1-3])\s*(?:번째|번)(?:째)?',question):
        i={'첫':0,'두':1,'세':2,'1':0,'2':1,'3':2}[m[1]]
        if i not in ordinal:ordinal.append(i)
    group=bool(re.search(r'그\s*중|그중|아까.*(?:사업|공고).*중',question))
    if not (correction or repeat or next_step or ordinal or group or intent in ('compare','open_notices')):return None
    if correction:
        return response('제가 어떤 부분을 다르게 이해했나요? 바꾸려는 지역·등록 여부나 궁금한 사업을 짧게 알려주세요. 말씀하시기 전까지 기존 조건은 바꾸지 않을게요.',context,'clarify')
    by_id={d['public']['id']:k for k,d in corpus['documents'].items()}
    ids=context.get('list_ids',[]);versions=context.get('list_versions',[])
    intact=bool(ids) and len(ids)==len(versions) and all(i in by_id and notice_version(corpus['documents'][by_id[i]])==v for i,v in zip(ids,versions))
    if (repeat or next_step) and not ids:
        if context.get('last_kind')=='help':
            return service_response('어떤 도움을 줄 수 있어?',corpus) | {'conversation':context,'answer':'쉽게 말해, 농업 지원사업을 찾고 내 조건과 비교하는 서비스예요. 질문을 입력하거나 ‘내 조건 선택·수정’에서 시작하세요. 모르는 항목은 건너뛰어도 돼요.'}
        return response('앞서 어떤 내용을 다시 확인하고 싶으세요? 사업 이름이나 바꾸려는 조건 하나만 알려주세요. 기존 조건은 그대로 두었어요.',context,'clarify')
    def choose(message):
        suggestions=tuple(corpus['documents'][by_id[i]]['public']['title']+' 신청 조건' for i in ids if i in by_id)
        return response(message,context,'clarify',status='needs_verification',suggestions=suggestions or ('현재 공개 지원사업',))
    if not intact:return choose('앞서 본 목록이 변경됐거나 순서를 확인할 수 없어 임의로 사업을 고르지 않았어요. 사업명을 선택하거나 현재 공개 목록을 다시 확인해 주세요.')
    if any(i>=len(ids) for i in ordinal):return choose('말씀하신 순서에 해당하는 사업을 앞선 목록에서 확인할 수 없어요. 어떤 사업인지 선택해 주세요.')
    if not ordinal and not (repeat or next_step or group or intent=='open_notices'):
        return choose('어떤 사업들을 비교할까요? 앞서 안내한 사업의 순서나 이름을 알려주세요.')
    selected=[ids[i] for i in ordinal] if ordinal else list(ids)
    if next_step:
        return choose('신청 준비를 확인할 사업을 골라주세요. 그 사업의 공식 신청 방법·서류·접수처 중 저장된 근거가 있는 내용만 안내할게요. 전체 신청 자격이나 현재 접수 가능 여부는 별도 확인이 필요해요.')
    query='지원 금액 한도' if re.search('얼마|지원금|금액',question) or intent=='funding' else '신청 대상 조건과 모집기간 마감' if re.search('마감|언제|모집',question) or intent in ('deadline','open_notices') else '신청 대상 자격 조건 지원 내용' 
    if '서류' in question or intent=='documents':query='필수 제출서류 신청처'
    date_filter=bool(re.search(r'모집\s*중|신청\s*기간\s*내',question)) or intent=='open_notices'
    import rag_search
    from datetime import datetime,timezone
    if date_filter:
        selected=[i for i in selected if rag_search.recruitment_context(corpus['documents'][by_id[i]],datetime.now(timezone.utc))['date_state'] in ('within_recorded_dates','deadline_day_time_unknown')]
        if not selected:return response('앞서 안내한 목록에서 기재 날짜상 모집기간 내인 공고를 확인하지 못했어요. 실제 접수 상황·연장 여부는 공식 기관에 확인해야 해요.',context,'clarify',status='needs_verification')
    programs=[];sources=[];parts=[];missing=[]
    for i in selected:
        found=grounded(query,by_id[i]);parts.append(found['answer'])
        if not found['programs']:missing.append(corpus['documents'][by_id[i]]['public']['title'])
        for program in found['programs']:
            program['comparison']=rag_profile.compare(corpus['documents'][by_id[i]],context,rag_search.valid_url,AREAS)
            programs.append(program)
        sources.extend(found['sources'])
    if not programs:return choose('해당 사업의 저장된 근거에서 질문하신 정보를 확인하지 못했어요. 금액·조건·서류를 추측하지 않고 공식 원문 확인을 안내해요.')
    context['notice_ids']=[p['id'] for p in programs]
    prefix='앞서 안내한 목록의 사업을 같은 순서로 다시 확인했어요.' if repeat else '선택한 사업의 확인 가능한 근거를 비교했어요.'
    if group and not date_filter:prefix+=' 일부 조건이 맞아도 신청 가능으로 확정하지 않으며, 불일치·미확인을 함께 표시해요.'
    if date_filter:prefix+=' 기재 날짜 기준이며 실제 접수 가능 여부를 확인한 결과는 아니에요.'
    if missing:prefix+=' 다음 사업은 질문에 해당하는 저장 근거가 부족해 비교를 보류했어요: '+' / '.join(missing)
    return response(prefix+'\n\n'+'\n\n'.join(parts),context,'answer',status='needs_verification',programs=programs,sources=sources)

def service_response(encoded,corpus,intent=None):
    """Bounded service guidance, not generated grant facts. No model call needed."""
    question,context=decode(encoded);context=dict(context)
    live={d['public']['id'] for d in corpus['documents'].values()}
    context['notice_ids']=[v for v in context.get('notice_ids',[]) if v in live]
    facts,error=rag_profile.extract(question,AREAS,CROPS,normalized)
    if error:return None
    # Advice/help must not consume new facts or a factual business question.
    if facts:return None
    compact=re.sub(r'[\s!?.~,，。]','',question)
    rest=re.sub(r'^(?:안녕하세요|안녕하십니까|안녕|반가워요?|반갑습니다)[,，!\s]*','',question).strip()
    rest=re.sub(r'[\s!?.~,，。]','',rest)
    edit=bool(re.fullmatch(r'(?:내|제)?조건(?:을)?(?:바꾸고싶어|바꾸고싶어요|변경하고싶어|수정하고싶어|수정|변경|선택)(?:요)?',compact))
    guide=bool(re.search(r'너는누구|무농사(?:는|가)?(?:어떤|무슨)서비스|(?:너는)?(?:무슨|어떤)역할|어떤도움|무엇을할수|뭘할수|어떻게사용|사용방법|도움말|어떤기능|어떤정보(?:를)?알려|지원사업도찾아줄수',rest))
    starter=bool(re.fullmatch(r'(?:나는|제가)?농업(?:을)?처음시작하려고(?:하는데)?어떻게(?:해야해|하면돼)(?:요)?',compact))
    greet=bool(re.fullmatch(r'(안녕|안녕하세요|안녕하십니까|반가워|반가워요|반갑습니다)(무농사)?',compact))
    thanks=bool(re.fullmatch(r'(고마워|고마워요|감사합니다|감사해|감사해요|고맙습니다|감사)',compact))
    # Validated GPT intents help paraphrases without replacing factual questions.
    specific=bool(area_in(question) or any(c in question for c in CROPS) or re.search(r'자격|마감|서류|지원금|얼마|계산|이차보전|비가림|R&D',question))
    if specific:guide=False
    if intent in ('greeting','help','thanks') and not specific:
        greet=greet or intent=='greeting';guide=guide or intent=='help';thanks=thanks or intent=='thanks'
    if edit:
        return response('아래 ‘내 조건 선택·수정’에서 바꿀 항목만 고쳐주세요. 이미 알려주신 값은 채워 두고, 적용하면 같은 공식 근거로 다시 비교해요. 모르는 항목은 비워 두어도 됩니다.',context,'condition_edit')
    if thanks and not guide:
        return response('도움이 되셨다니 다행이에요. 궁금한 사업의 신청 조건이나 마감일을 이어서 물어보세요.',context,'thanks')
    if re.fullmatch(r'(?:오늘)?(?:날씨(?:는|어때|알려줘)?|점심(?:뭐먹지|추천해줘)|저녁메뉴추천|재밌는이야기해줘|농담해줘)',compact):
        return response('저는 농업 지원사업 탐색과 신청 준비를 돕는 상담이에요. 날씨·식사·일반 잡담은 안내 범위가 아니지만, 지역이나 관심 작물을 알려주시면 공개된 사업을 함께 찾아볼 수 있어요.',context,'help',suggestions=('내 조건에 맞는 지원사업을 찾고 싶어',))
    if not (guide or greet or starter):return None
    missing=[]
    if 'farm_region' not in context:missing.append('어느 시·군에서 농사짓고 있거나 시작할 예정인가요?')
    if 'farm_registered' not in context:missing.append('농업경영체 등록 여부를 알려주세요. 잘 모르시면 건너뛰어도 돼요.')
    answer=('안녕하세요! 무농사 AI 상담이에요. ' if greet else '')+'공식 농업 지원사업을 찾고, 알려주신 조건과 공고 요건을 비교하며 신청 방법·서류·마감일을 근거와 함께 확인해 드려요.'
    answer+='\n\n질문을 바로 입력하거나 아래에서 조건을 한 번에 선택해 주세요. 거주지와 영농지는 구분하며, 모르는 조건은 비워 두어도 검색할 수 있어요.'
    if missing:answer+='\n\n먼저 '+missing[0]
    answer+='\n\n일부 조건이 맞아도 신청 자격이나 현재 접수 가능 여부를 확정하지 않아요. 확인되지 않은 내용은 따로 안내해요.'
    out=response(answer,context,'help',suggestions=('내 조건에 맞는 지원사업을 찾고 싶어','청년농업인 지원사업'))
    out['followup_questions']=missing[:2]
    return out


def basic_response(encoded,corpus,grounded):
    question,context=decode(encoded);context=dict(context)
    compact=re.sub(r'[\s!?.~。]+','',question)
    docs=corpus['documents'];by_id={v['public']['id']:k for k,v in docs.items()}
    previous=list(context.get('notice_ids',[]))
    context['notice_ids']=[i for i in previous if i in by_id]
    if re.fullmatch(r'(안녕|안녕하세요|안녕하십니까|반가워|반가워요|반갑습니다)(무농사)?',compact):
        return response('안녕하세요! 무농사 상담이에요. 공식 농업 지원사업의 지역·신청 조건·필요 서류를 함께 살펴볼 수 있어요. 어떤 지원사업이 궁금하세요?',context,'greeting',suggestions=('전주 관련 공고','청년농업인 지원사업','마늘 재배 지원'))
    if re.fullmatch(r'(고마워|고마워요|감사합니다|감사해|감사해요|고맙습니다|감사)',compact):
        return response('도움이 되셨다니 다행이에요. 더 궁금한 신청 조건이나 서류가 있으면 이어서 물어보세요.',context,'thanks')
    if any(v in compact for v in ('무엇을할수','뭘할수','어떻게사용','사용방법','도움말','어떤기능')):
        return response('공개된 농업 지원사업을 지역·작물·사업명으로 찾고, 확인된 신청 조건과 서류를 안내해요.\n\n예: “전주 관련 공고”, “부안 사업의 신청 조건은?”, “마늘 재배 지원”\n\n이번 대화에서 알려주신 지역·작물은 다음 질문에 참고하고 새 대화를 시작하면 지워요. 간단한 규칙과 저장된 공식 근거로 안내하며, 모든 일상 대화를 이해하거나 신청 자격을 확정하지는 않아요.',context,'help')
    explicit_area=area_in(question)
    crops=[(question.rfind(v),v) for v in CROPS if v in question]
    explicit_crop=max(crops)[1] if crops else None
    mentioned,_=rag_profile.extract(question,AREAS,CROPS,normalized)
    residence='region' in mentioned
    registration=None
    if '경영체' in question:
        if re.search(r'(없|미등록|등록(?:이|을|은)?\s*안|등록하지\s*않)',question):registration='no'
        elif re.search(r'(등록(?:되어|했|돼|이야)|있어)',question):registration='yes'
    crop_statement=bool(explicit_crop and re.search(r'(재배(?:해|하고|중|할|예정)|키워|농사(?:를)?\s*짓)',question))
    if residence:context['region']=mentioned['region']
    if explicit_crop:context['crop']=explicit_crop
    if registration:context['farm_registered']=registration
    asks=bool(re.search(r'(공고|지원|사업|조건|자격|서류|알려|찾|가능|신청|방법|얼마|계산)',question))
    if (residence or crop_statement or registration) and not asks:
        facts=[]
        if residence:facts.append(context['region']+'에 거주하시는군요.')
        if crop_statement:facts.append(explicit_crop+' 재배 상황을 참고할게요.')
        if registration:facts.append('농업경영체 '+('미등록' if registration=='no' else '등록')+'으로 알려주신 내용을 참고할게요.')
        return response(' '.join(facts)+'\n\n어떤 지원사업이 궁금하세요? 청년농업인 지원이나 재배 작물처럼 관심 분야를 알려주세요. 거주지와 실제 농지 소재지, 신청 자격은 별도로 확인해야 해요.',context,'context',suggestions=('청년농업인 지원사업','마늘 재배 지원'))
    # Identify explicit businesses before interpreting a contextual follow-up.
    aliases=corpus.get('aliases',{})
    named={k for k,names in aliases.items() if any(len(n)>=2 and n in question for n in names)
           and k in docs and (any(v in question for v in (docs[k]['public']['title'],'R&D','이차보전','비가림','면세유','재해보험','K-Fresh'))
           or (not re.search('청년|귀농',question) and any(v in question for v in ('신청','자격','조건','서류','계산','면적','한도','이자'))))}
    generic={'농업기술센터','농업인','농업경영체','청년농업인','농산물','지원사업','신청','안내','공고','모집','사업','추가','알림','첨부파일','있음','신청자','대상자','교육생','참가업체','수시'}
    specific={k for k,d in docs.items() if any(len(word)>=3 and word not in generic and not re.search(r'\d',word) and word in question
        for word in re.findall(r'[가-힣]+',d['public']['title']))}
    if specific:
        if explicit_area:
            scoped={k for k in specific if region_matches(explicit_area,docs[k]['public'],docs[k])>=1 or docs[k]['public'].get('region') in (None,'','unknown')}
            if not scoped:return {**response('질문하신 사업과 '+explicit_area+' 지역 조건을 함께 확인할 수 있는 공개 공고를 찾지 못했어요. 다른 지역 공고를 해당 지역의 신청 대상이라고 안내하지 않아요. 지역이나 사업명을 다시 알려주세요.',context,'clarify',status='no_evidence'),'scope_not_found':True}
            specific=scoped
        named=specific
    followup=bool(re.search(r'(그럼|그\s*사업|이\s*사업|지원금|보조금|필요한\s*서류|신청\s*조건|신청\s*서류|신청\s*방법|지원\s*금액|마감일)',question))
    if named:
        keys=sorted(named)
    elif followup and previous:
        if not context['notice_ids']:return response('앞서 본 공고를 현재 승인된 공개 근거에서 확인할 수 없어요. 최신 공개 목록에서 다른 사업을 찾아볼까요?',context,'clarify',status='no_evidence')
        keys=[by_id[i] for i in context['notice_ids']]
        if len(keys)>1:return response('어느 사업의 조건이나 서류가 궁금하신가요? 앞서 안내한 사업명을 함께 적어주시면 그 사업의 근거만 확인할게요.',context,'clarify',suggestions=tuple(docs[k]['public']['title']+' 신청 조건' for k in keys))
    elif followup and not previous and not explicit_area:
        return response('어떤 사업의 신청 조건이나 서류가 궁금하신가요? 사업명을 알려주시거나 먼저 지역·작물로 공고를 찾아보세요.',context,'clarify',suggestions=('전주 관련 공고','청년농업인 지원사업'))
    else:keys=[]
    area=None if '전국' in question else explicit_area or context.get('region');crop=explicit_crop or context.get('crop')
    if keys:
        if len(keys)==1:
            out=grounded(question,keys[0]);out['kind']='answer';context['notice_ids']=[docs[keys[0]]['public']['id']]
            if not out['programs']:
                out['answer']='이 사업의 저장된 승인 근거에서 질문하신 내용을 확인하지 못했어요. 확인되지 않은 서류나 조건은 임의로 채우지 않아요. 공고 원문이나 담당 기관의 안내가 필요해요.'
            out['conversation']=context;out['suggestions']=[]
            if context.get('farm_registered')=='no':out['answer']+='\n\n농업경영체 미등록으로 알려주셨어요. 이 사업의 등록 요건은 별도 확인이 필요하며, 전체 자격 충족으로 판단하지 않아요.'
            return out
    else:
        topic=[]
        if re.search('청년|후계농',question):topic.append(('청년','후계농'))
        if '귀농' in question:topic.append(('귀농',))
        if crop:topic.append((crop,))
        generic=bool(area or topic or re.search(r'(지원사업|지원\s*사업|공고|지원\s*받|받을\s*수\s*있는\s*지원)',question))
        if not generic:return response('지원사업을 찾는 질문으로 조금 더 구체적으로 알려주세요. 지역, 재배 작물, 사업명 중 하나를 적으면 확인된 공식 근거를 찾을 수 있어요.',context,'clarify',status='no_evidence',suggestions=('전주 관련 공고','마늘 재배 지원'))
        ranked=[]
        for k,document in docs.items():
            score=region_matches(area,document['public'],document) if area else 1
            if not score:continue
            haystack=corpus_text(document)
            if any(not any(term in haystack for term in group) for group in topic):continue
            # Without another topic, prefer explicitly local notices over nationwide ones.
            ranked.append((score,k))
        if area and not topic:
            if AREAS[area][1] and any(v[0]==3 for v in ranked):ranked=[v for v in ranked if v[0]==3]
        keys=[k for score,k in sorted(ranked,key=lambda v:candidate_order(v[1],corpus,context,v[0]))]
        if not keys:
            label=' · '.join(v for v in (area,crop,'청년농업인' if re.search('청년|후계농',question) else None) if v) or '말씀하신 조건'
            context['notice_ids']=[]
            return response(label+' 관련 공고를 현재 승인된 공개 자료에서 찾지 못했어요. 전국의 모든 공고가 없다는 뜻은 아니에요.\n\n전북 또는 전국으로 검색 범위를 넓히거나, 지역·작물 조건을 하나씩 바꿔볼까요?',context,'catalogue',status='no_evidence',suggestions=('전북 지원사업','전국 지원사업'))
    if len(keys)>1:keys.sort(key=lambda k:candidate_order(k,corpus,context,region_matches(area,docs[k]['public'],docs[k]) if area else 0))
    total=len(keys);keys=keys[:3];programs=[];sources=[]
    for key in keys:
        item=grounded('신청 대상 조건 지원 내용',key)
        programs.extend(item['programs']);sources.extend(item['sources'])
    if not programs:return response('관련된 공고는 있으나 현재 답변에 필요한 근거를 충분히 확인하지 못했어요. 사업명을 지정해 다시 질문하거나 공식 원문을 확인해 주세요.',context,'clarify',status='no_evidence')
    context['notice_ids']=[p['id'] for p in programs]
    parts=[(area+' 관련 ' if area else '')+'공개 공고 '+str(total)+'건을 찾았어요.'+(' 먼저 '+str(len(programs))+'건을 안내해요.' if total>len(programs) else '')]
    for i,p in enumerate(programs,1):
        document=docs[by_id[p['id']]]['public']
        region=document.get('region','확인 필요');target=document.get('target','확인 필요')
        if region in ('','unknown'):region='기본 지역 정보 미확인 · 공식 근거의 주소 요건 확인 필요'
        if target in ('','unknown'):target='확인 필요'
        parts.append(str(i)+'. '+p['name']+'\n지원 지역: '+region+'\n신청 대상: '+target+'\n'+p['application_period']['description'])
    parts.append('지역 관련 자료를 찾은 결과이며 신청 자격 충족이나 실제 접수 가능 여부를 뜻하지 않아요. 궁금한 사업의 이름과 함께 조건·서류를 질문해 주세요.')
    if context.get('farm_registered')=='no':parts.append('농업경영체 미등록으로 알려주신 상황을 참고했어요. 등록 요건을 충족했다고 판단하지 않으며 각 공고에서 확인해야 해요.')
    unique={(s['url'],s['location'],s['checked_at']):s for s in sources}
    return response('\n\n'.join(parts),context,'catalogue',programs=programs,sources=list(unique.values()),suggestions=('그럼 신청 조건은?','필요한 서류는?'))


def _respond(encoded,corpus,grounded):
    guidance=service_response(encoded,corpus)
    if guidance:return guidance
    question,context=decode(encoded)
    facts,error=rag_profile.extract(question,AREAS,CROPS,normalized)
    if error:return response(error,context,'clarify',status='needs_verification')
    context={**context,**facts}
    encoded=PREFIX+json.dumps(context,ensure_ascii=False)+SEPARATOR+question
    personal=any(k in context for k in ('region','age','applicant','group_size','farm_registered','farming_years','planned','facility_sqm','cultivating','farm_region'))
    followup=bool(re.search(r'그\s*사업|그럼|신청\s*(?:서류|조건)|필요한\s*서류|지원금|보조금',question))
    # Reuse the existing scoped evidence retriever for named notices and follow-ups.
    compact=re.sub(r'[\s?？.!]','',question)
    canonical=None
    if re.fullmatch(r'그사업(?:은|는|이뭐야|알려줘)?',compact):canonical='신청 대상 자격 조건 지원 내용'
    elif re.fullmatch(r'(?:그럼)?(?:신청조건|신청자격)(?:은|는)?',compact):canonical='신청 대상 자격 조건'
    elif re.fullmatch(r'(?:그럼)?(?:신청서류|필요한서류|제출서류)(?:은|는)?',compact):canonical='필수 제출서류 신청서'
    elif re.fullmatch(r'(?:그럼)?(?:지원금|보조금)(?:은|는|얼마야)?',compact):canonical='지원 금액 비율'
    live_by_id={d['public']['id']:k for k,d in corpus['documents'].items()}
    ids=context.get('notice_ids',[])
    if canonical and len(ids)==1 and ids[0] in live_by_id:
        # Map a short follow-up to existing search terms only after resolving one
        # current verified notice. Never drop a calculation amount or a 1% caveat.
        out=grounded(canonical,live_by_id[ids[0]])
        out.update(kind='answer',conversation=context,suggestions=[])
    else:out=basic_response(encoded,corpus,grounded)
    if out['kind'] in ('greeting','thanks','help','condition_edit') or out.get('scope_not_found'):return out
    wants=bool(facts or re.search('추천|맞는|받을|신청.*가능|지원사업|공고',question))
    explicit_explore=bool(area_in(question) and re.search(r'공고|사업|지원|신청',question) and area_in(question) not in (context.get('region'),context.get('farm_region')))
    if personal and wants and not explicit_explore and not (followup and context.get('notice_ids')) and out['kind']!='answer':
        area=context.get('farm_region') or context.get('region');crop=context.get('crop');ranked=[]
        for key,document in corpus['documents'].items():
            score=region_matches(area,document['public'],document) if area else 0
            topic=(crop and crop in corpus_text(document)) or ('청년' in question and '청년' in corpus_text(document))
            import rag_search
            comparison=rag_profile.compare(document,context,rag_search.valid_url,AREAS)
            # Proven ineligibility is not a recommendation. Explicit named
            # exploration above remains available with its mismatch explanation.
            if comparison['label']=='조건 불일치':continue
            if score>=1 or topic or not area:ranked.append((score,key))
        if not ranked and not area and not crop and out.get('programs'):
            # Age/applicant alone must not prevent an incomplete-profile search.
            # Reuse the existing general discovery list and compare it below.
            ranked=[(0,live_by_id[p['id']]) for p in out['programs']]
        if not ranked:
            context['notice_ids']=[]
            return response('알려주신 상황을 현재 대화에서 참고할게요. 현재 승인된 공개 공고 범위에서 관련 사업을 찾지 못했어요. 전체 지원사업이 없다는 뜻은 아닙니다.\n\n영농지역 또는 관심 작물을 한 가지 알려주시거나 사업명을 지정해 주세요. 나이와 영농 예정 여부만으로 신청 자격을 확정하지 않아요.',context,'catalogue',status='no_evidence',suggestions=('전북 지원사업','전국 지원사업'))
        ranked.sort(key=lambda v:candidate_order(v[1],corpus,context,v[0]));programs=[];sources=[]
        for _,key in ranked[:3]:
            found=grounded('신청 대상 조건 지원 내용',key);programs.extend(found['programs']);sources.extend(found['sources'])
        if not programs:return response('관련 공고는 있지만 검증된 근거가 부족해 비교를 보류합니다.',context,'clarify',status='no_evidence')
        out=response('알려주신 상황과 현재 승인된 공고의 확인 가능한 조건을 비교했어요. 전체 신청 자격이나 현재 접수 가능 여부를 확정하는 결과는 아닙니다.',context,'recommendation',status='needs_verification',programs=programs,sources=sources)
    # Even a generic named-notice question gets a comparison only when the user
    # supplied a profile. No fabricated age, residence, registration or farming facts.
    if personal and out['programs']:
        by_id={d['public']['id']:d for d in corpus['documents'].values()};questions=[];parts=[]
        import rag_search
        for program in out['programs']:
            comparison=rag_profile.compare(by_id[program['id']],context,rag_search.valid_url,AREAS)
            program['comparison']=comparison
            parts.append(program['name']+' — '+comparison['label']+'\n'+program['application_period']['description'])
            if comparison['reasons']:parts.append('비교 이유: '+' / '.join(comparison['reasons']))
            if comparison['checks']:parts.append('확인할 조건: '+' / '.join(comparison['checks']))
            questions.extend(comparison['questions'])
        summary=['조건 비교']+parts
        if questions:summary.append('더 정확히 비교하려면:\n'+'\n'.join(list(dict.fromkeys(questions))[:2]))
        summary.append('일치하는 일부 조건이 있어도 신청 자격 충족·지원금 지급을 의미하지 않습니다. 모집기간 경과와 자격 비교는 별개입니다.')
        comparison_text='\n\n'.join(summary)
        if re.search('서류|지원금|보조금|계산|얼마',question):out['answer']+='\n\n'+comparison_text
        else:out['answer']=comparison_text+'\n\n'+out['answer']
        out['status']='needs_verification'
        context['notice_ids']=[p['id'] for p in out['programs']]
    # Preserve facts extracted from separate residence/farming clauses. Do not let
    # a business name overwrite the user's actual residence.
    out['conversation']={**out.get('conversation',context),**facts}
    if out['programs']:out['conversation']['notice_ids']=[p['id'] for p in out['programs']]
    return out

def respond(encoded,corpus,grounded):
    question,actual=decode(encoded)
    out=_respond(encoded,corpus,grounded)
    if rag_profile.hypothetical(question):
        out['conversation']={**actual,'notice_ids':out.get('conversation',{}).get('notice_ids',actual.get('notice_ids',[]))}
    return out
