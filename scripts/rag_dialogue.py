"""Small, stateless conversation rules over the already verified RAG corpus."""
import json
import re
import rag_profile

PREFIX='[무농사 대화 참고]\n'
SEPARATOR='\n[질문]\n'
AREAS={'전주':('전주','전북'),'부안':('부안','전북'),'고창':('고창','전북'),
       '파주':('파주','경기'),'포항':('포항','경북'),'부산':('부산','부산'),
       '서울':('서울','서울'),'전북':('전북',None),'전남':('전남',None),
       '경북':('경북',None),'경남':('경남',None),'경기':('경기',None),
       '충남':('충남',None),'충북':('충북',None),'강원':('강원',None),'제주':('제주',None)}
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
        if len(raw)>900:raise ValueError('context_too_long')
        context=json.loads(raw)
        if not isinstance(context,dict) or set(context)-({'region','crop','farm_registered','notice_ids'}|rag_profile.KEYS):raise ValueError('context_fields')
        if 'region' in context and context['region'] not in AREAS:raise ValueError('context_region')
        if 'crop' in context and context['crop'] not in CROPS:raise ValueError('context_crop')
        if 'farm_registered' in context and context['farm_registered'] not in ('yes','no'):raise ValueError('context_registration')
        if not rag_profile.valid_context(context,AREAS):raise ValueError('context_values')
        ids=context.get('notice_ids',[])
        if not isinstance(ids,list) or len(ids)>3 or any(not isinstance(v,str) or not re.fullmatch('NOTICE-[A-Za-z0-9_-]{1,70}',v) for v in ids):raise ValueError('context_notices')
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
    return 0

def corpus_text(document):
    item=document['public'];record=document['record']
    fields=record.get('fields',{})
    return ' '.join(str(v) for v in (item.get('title',''),item.get('target',''),
        item.get('support',''),fields.get('conditions',{}).get('value','')))

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
    residence=bool(explicit_area and re.search(r'(살아|살고|살아요|살아[요.]?$|거주|주소)',question))
    registration=None
    if '경영체' in question:
        if re.search(r'(없|미등록|등록(?:이|을|은)?\s*안|등록하지\s*않)',question):registration='no'
        elif re.search(r'(등록(?:되어|했|돼|이야)|있어)',question):registration='yes'
    crop_statement=bool(explicit_crop and re.search(r'(재배(?:해|하고|중|할|예정)|키워|농사(?:를)?\s*짓)',question))
    if residence:context['region']=explicit_area
    if explicit_crop:context['crop']=explicit_crop
    if registration:context['farm_registered']=registration
    asks=bool(re.search(r'(공고|지원|사업|조건|자격|서류|알려|찾|가능|신청|방법|얼마|계산)',question))
    if (residence or crop_statement or registration) and not asks:
        facts=[]
        if residence:facts.append(explicit_area+'에 거주하시는군요.')
        if crop_statement:facts.append(explicit_crop+' 재배 상황을 참고할게요.')
        if registration:facts.append('농업경영체 '+('미등록' if registration=='no' else '등록')+'으로 알려주신 내용을 참고할게요.')
        return response(' '.join(facts)+'\n\n어떤 지원사업이 궁금하세요? 청년농업인 지원이나 재배 작물처럼 관심 분야를 알려주세요. 거주지와 실제 농지 소재지, 신청 자격은 별도로 확인해야 해요.',context,'context',suggestions=('청년농업인 지원사업','마늘 재배 지원'))
    # Identify explicit businesses before interpreting a contextual follow-up.
    aliases=corpus.get('aliases',{})
    named={k for k,names in aliases.items() if any(len(n)>=2 and n in question for n in names)
           and k in docs and (any(v in question for v in (docs[k]['public']['title'],'R&D','이차보전','비가림','면세유','재해보험','K-Fresh'))
           or (not re.search('청년|귀농',question) and any(v in question for v in ('신청','자격','조건','서류','계산','면적','한도','이자'))))}
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
        generic=bool(area or topic or re.search(r'(지원사업|지원\s*사업|공고|받을\s*수\s*있는\s*지원)',question))
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
            ranked=[v for v in ranked if v[0]>=2]
            if AREAS[area][1] and any(v[0]==3 for v in ranked):ranked=[v for v in ranked if v[0]==3]
        keys=[k for _,k in sorted(ranked,key=lambda v:(-v[0],docs[v[1]]['public']['title']))]
        if not keys:
            label=' · '.join(v for v in (area,crop,'청년농업인' if re.search('청년|후계농',question) else None) if v) or '말씀하신 조건'
            context['notice_ids']=[]
            return response(label+' 관련 공고를 현재 승인된 공개 자료에서 찾지 못했어요. 전국의 모든 공고가 없다는 뜻은 아니에요.\n\n전북 또는 전국으로 검색 범위를 넓히거나, 지역·작물 조건을 하나씩 바꿔볼까요?',context,'catalogue',status='no_evidence',suggestions=('전북 지원사업','전국 지원사업'))
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


def respond(encoded,corpus,grounded):
    question,context=decode(encoded)
    facts,error=rag_profile.extract(question,AREAS,CROPS,normalized)
    if error:return response(error,context,'clarify',status='needs_verification')
    context={**context,**facts}
    encoded=PREFIX+json.dumps(context,ensure_ascii=False)+SEPARATOR+question
    personal=any(k in context for k in ('age','applicant','group_size','farm_registered','farming_years','planned','facility_sqm','cultivating','farm_region'))
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
    if out['kind'] in ('greeting','thanks','help'):return out
    wants=bool(facts or re.search('추천|맞는|받을|신청.*가능|지원사업|공고',question))
    if personal and wants and not (followup and context.get('notice_ids')) and out['kind']!='answer':
        area=context.get('farm_region') or context.get('region');crop=context.get('crop');ranked=[]
        for key,document in corpus['documents'].items():
            score=region_matches(area,document['public'],document) if area else 0
            topic=(crop and crop in corpus_text(document)) or ('청년' in question and '청년' in corpus_text(document))
            if score>=2 or topic:ranked.append((score,key))
        if not ranked:
            context['notice_ids']=[]
            return response('알려주신 상황을 현재 대화에서 참고할게요. 현재 승인된 공개 공고 범위에서 관련 사업을 찾지 못했어요. 전체 지원사업이 없다는 뜻은 아닙니다.\n\n영농지역 또는 관심 작물을 한 가지 알려주시거나 사업명을 지정해 주세요. 나이와 영농 예정 여부만으로 신청 자격을 확정하지 않아요.',context,'catalogue',status='no_evidence',suggestions=('전북 지원사업','전국 지원사업'))
        ranked.sort(key=lambda v:(-v[0],v[1]));programs=[];sources=[]
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
