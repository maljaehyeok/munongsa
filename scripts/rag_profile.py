"""Bounded self-reported context and conservative approved-condition comparison.

Mirrors support-public.js AND/OR/NOT semantics. Unsupported predicates stay unknown.
No model, network, persistence, invented thresholds or eligibility certification.
"""
import re
import math

NUMBERS={'age':(0,120),'group_size':(1,100000),'farming_years':(0,100),'facility_sqm':(0,100000000)}
ENUMS={'age_basis':('international','unspecified'),'applicant':('individual_farmer','group','agricultural_corporation','business')}
BOOLEANS=('planned','cultivating','group_min')
KEYS=set(NUMBERS)|set(ENUMS)|set(BOOLEANS)|{'farm_region'}

def valid_context(c,areas):
    for key,(low,high) in NUMBERS.items():
        if key in c and (type(c[key]) not in (int,float) or not math.isfinite(c[key]) or not low<=c[key]<=high):return False
    if any(k in c and type(c[k]) is not bool for k in BOOLEANS):return False
    if any(k in c and c[k] not in values for k,values in ENUMS.items()):return False
    if 'farm_region' in c and c['farm_region'] not in areas:return False
    return all(k not in c or type(c[k]) is int for k in ('age','group_size'))

def extract(q,areas,crops,normalize):
    q=normalize(q);out={}
    for area in sorted(areas,key=len,reverse=True):
        for m in re.finditer(re.escape(area)+r'(?:시|군|도)?(?:에|에서|의)?\s*([^,，.\n]{0,18})',q):
            tail=m.group(1)
            if re.search(r'거주|살아|살고|사는|주소',tail):out['region']=area
            if re.search(r'농지|영농지역|재배지역|농사|재배',tail):out['farm_region']=area
    matches=list(re.finditer(r'(?<![\d-])(만\s*)?(\d{1,3})\s*(?:세|살)(?!\s*(?:이상|이하|미만|부터|까지|기준|조건))',q));m=matches[-1] if matches else None
    if m and not re.search(r'나이\s*기준|연령\s*기준',q):out.update(age=int(m[2]),age_basis='international' if m[1] else 'unspecified')
    if re.search(r'개인(?:\s*(?:농업인|농민|신청))?|혼자\s*(?:농사|신청)|단독\s*신청',q):out['applicant']='individual_farmer'
    if re.search(r'단체|모임체|모임|조합',q):out['applicant']='group'
    if re.search(r'농업법인|영농법인',q):out['applicant']='agricultural_corporation'
    matches=list(re.finditer(r'(\d{1,5})\s*(?:인|명)\s*(이상)?',q));m=matches[-1] if matches else None
    if m and ('applicant' in out and out['applicant']!='individual_farmer' or re.search('단체|구성원|회원|저희|우리',q)):
        out.update(group_size=int(m[1]),group_min=bool(m[2]))
    if '경영체' in q:
        if re.search(r'미등록|없[어음습]|등록(?:을|이|은)?\s*(?:안|못)|등록하지\s*않',q):out['farm_registered']='no'
        elif re.search(r'등록(?:했|하였|되어|됐|한|함)|등록.*있',q):out['farm_registered']='yes'
    if re.search(r'(?:영농|농사|농업|재배)\s*(?:경력)?\s*(\d+(?:\.\d+)?)\s*년',q):
        out['farming_years']=float(re.search(r'(?:영농|농사|농업|재배)\s*(?:경력)?\s*(\d+(?:\.\d+)?)\s*년',q)[1])
    if re.search(r'(?:영농|농사|농업|재배|시작).*?(?:시작\s*)?예정|시작하려|시작할\s*(?:계획|생각)',q):out['planned']=True
    if re.search(r'(?:영농|농사).*이미|시작했|농사짓고|재배하고',q):out['planned']=False
    selected=[(q.rfind(c),c) for c in crops if c in q]
    if selected:
        out['crop']=max(selected)[1]
        if re.search(re.escape(out['crop'])+r'.{0,12}(?:재배|농사|키우)',q):out['cultivating']=not out.get('planned',False)
    m=re.search(r'(?:시설\s*면적|비가림(?:하우스)?|하우스)\s*(?:은|는|이|가|:)?\s*(\d[\d,]*(?:\.\d+)?)\s*(㎡|제곱미터|m2|평)',q,re.I)
    if m:
        value=float(m[1].replace(',',''));out['facility_sqm']=round(value*(400/121 if m[2]=='평' else 1),4)
    elif re.search(r'시설\s*면적\s*(?:은|는|이|가|:)?\s*\d',q):
        return {},'시설면적은 숫자와 단위를 함께 알려주세요. 예: 시설면적 400㎡ 또는 하우스 150평. 이전 면적을 새 값으로 변경하지 않았어요.'
    # Bounds reject implausible extraction instead of silently retaining stale values.
    if not valid_context(out,areas):return {},'숫자의 범위를 확인해 주세요. 나이는 0~120세, 인원은 1명 이상으로 알려주세요.'
    return out,None

def values(field):
    value=field.get('value',[])
    return value if isinstance(value,list) else [str(value)]

def compare(document,context,valid_url,areas):
    item=document['public'];fields=document['record']['fields'];payload=item.get('eligibility') or {}
    rows=[];missing=[];by_id={};negative=set()
    def refs(node,invert=False,depth=0):
        if not isinstance(node,dict) or depth>12:return
        if node.get('condition_id'):
            if invert:negative.add(node['condition_id'])
        else:
            for child in node.get('children',[]):refs(child,invert ^ (node.get('op')=='NOT'),depth+1)
    refs(payload.get('logic'))
    def add(status,reason,question=None):
        rows.append({'status':status,'reason':reason})
        if question and question not in missing:missing.append(question)
    def in_range(n,v):
        if type(v.get('min_inclusive')) is not bool or type(v.get('max_inclusive')) is not bool:return False
        return (v.get('min') is None or (n>=v['min'] if v['min_inclusive'] else n>v['min'])) and (v.get('max') is None or (n<=v['max'] if v['max_inclusive'] else n<v['max']))
    for cond in payload.get('conditions',[]):
        identity=cond.get('condition_id');kind=cond.get('kind');v=cond.get('value') or {};e=cond.get('evidence') or {};state='check'
        reason='공고의 미확인 조건은 별도 확인 필요'
        trusted=cond.get('status')=='verified' and (e.get('quote') or e.get('fact_confirmed') is True) and e.get('location') and valid_url(e.get('url',''))
        if trusted and cond.get('presence')=='no_restriction':state='match';reason='공식 근거에 제한 없음이 명시됨'
        elif trusted and cond.get('presence')=='specified':
            actual=None;known=False;ok=False
            if kind=='applicant':
                actual=context.get('applicant');known=actual is not None and isinstance(v.get('one_of'),list);ok=actual in v.get('one_of',[])
                reason='알려주신 신청자 유형과 공고의 신청 주체 비교'
                if not known:missing.append('개인으로 신청하시나요, 단체·법인으로 신청하시나요?')
            elif kind=='farm_registration':
                known=context.get('farm_registered') in ('yes','no') and type(v.get('registered')) is bool;ok=(context.get('farm_registered')=='yes')==v.get('registered');reason='농업경영체 등록 요건 비교'
                if not known:missing.append('농업경영체가 등록되어 있나요?')
            elif kind=='residence':
                area=context.get('region');scopes=v.get('regions',[]);known=bool(area and scopes)
                # A province alone never establishes a specific municipal address.
                if area and area in ('전북','전남','경북','경남','경기','충북','충남','강원','제주') and any(len(s.split())>1 for s in scopes):known=False
                province=areas.get(area,(None,None))[1]
                ok=bool(area and any(area in s or s=='전국' or (province and province in s and len(s.split())==1) for s in scopes));reason='알려주신 거주지와 공고 주소 요건 비교'
                if not known:missing.append('현재 거주하는 시·군을 알려주세요.')
            elif kind=='group_size' and v.get('unit')=='persons' and 'group_size' in context:
                known=not context.get('group_min') or v.get('max') is None;ok=in_range(context['group_size'],v);reason='공동 신청 인원 비교'
            elif kind=='crop' and isinstance(v.get('any_of'),list):
                known=bool(context.get('cultivating') and context.get('crop'));ok=context.get('crop') in v['any_of'];reason='실제 재배 작물과 공고 작물 비교'
            elif kind in ('age','farming_experience','independent_management'):
                reason='연령·경력의 공고 기준일을 확인하기 전에는 충족 여부 판단 보류'
            if known:state='match' if ok else 'mismatch'
        if identity in by_id:state='check'
        by_id[identity]=state
        effective={'match':'mismatch','mismatch':'match','check':'check'}[state] if identity in negative else state
        if identity in negative:reason='개인 단독 신청 대상 아님' if effective=='mismatch' else '명시된 개인 단독 제외 조건과 신청 주체 비교'
        add(effective,reason)
    count=[0]
    def walk(node,depth=0):
        count[0]+=1
        if not isinstance(node,dict) or depth>12 or count[0]>200:return 'check'
        if node.get('condition_id'):return by_id.get(node['condition_id'],'check')
        children=node.get('children',[])
        if not isinstance(children,list) or not children:return 'check'
        states=[walk(n,depth+1) for n in children]
        if node.get('op')=='AND':return 'mismatch' if 'mismatch' in states else 'check' if 'check' in states else 'match'
        if node.get('op')=='OR':return 'match' if 'match' in states else 'check' if 'check' in states else 'mismatch'
        if node.get('op')=='NOT' and len(states)==1:return {'match':'mismatch','mismatch':'match','check':'check'}[states[0]]
        return 'check'
    structured=walk(payload.get('logic'))
    # Only explicit approved conditions are parsed; never infer rules from titles,
    # funding totals, age examples, documents or other notices.
    f=fields.get('conditions',{});e=f.get('evidence',{})
    approved=bool(valid_url(e.get('url','')) and e.get('location') and e.get('checked_at'))
    lines=values(f) if approved else []
    for line in lines:
        if '거주' in line and ('주소' in line or '기준' in line):
            add('check','현재 거주지만으로 과거 기준일의 주소 요건을 충족한다고 보지 않습니다 · '+line)
        m=re.search(r'(\d+)\s*인\s*이상',line)
        if m and ('단체' in line or '법인' in line):
            if context.get('applicant')=='individual_farmer':add('mismatch','개인 단독 신청 대상 아님 · '+line)
            elif 'group_size' in context:add('match' if context['group_size']>=int(m[1]) else 'check' if context.get('group_min') else 'mismatch','공동 신청 '+str(context['group_size'])+('명 이상' if context.get('group_min') else '명')+' · '+line)
            else:add('check','공동 신청 최소 인원 확인 필요 · '+line,'공동 신청 단체의 구성원은 몇 명인가요?')
        m=re.search(r'시설면적\s*(\d+(?:\.\d+)?)\s*㎡\s*이상',line)
        if m:
            if 'facility_sqm' in context:add('match' if context['facility_sqm']>=float(m[1]) else 'mismatch','시설면적 '+format(context['facility_sqm'],'g')+'㎡ · '+line)
            else:add('check',line,'비가림하우스 시설면적은 몇 ㎡인가요?')
        if '농업경영체' in line and '등록' in line:
            if 'farm_registered' in context:add('match' if context['farm_registered']=='yes' else 'mismatch','농업경영체 등록 조건 · '+line)
            else:add('check',line,'농업경영체가 등록되어 있나요?')
        if '재배' in line and context.get('cultivating') and context.get('crop') and any(c in line for c in ('마늘','고추')):
            add('check','알려주신 재배 작물 '+context['crop']+' · 대상 품목·향후 사용 목적·등록 작물·교육 예외는 별도 확인 · '+line)
    unknown=values(fields.get('unconfirmed',{}));text=' '.join(unknown)
    conflict=any(w in text for w in ('충돌','상충','출생연도 범위'))
    if context.get('age') is not None:add('check','알려주신 나이 '+str(context['age'])+'세는 참고 정보이며 공고의 연령 기준일·대표자 적용 여부를 확인해야 합니다.')
    if 'farming_years' in context or context.get('planned'):add('check','영농 경력·시작 예정 여부는 참고하며 공고의 경력 기준일·실제 영농 요건은 별도 확인합니다.')
    if conflict:add('check','연령 기준 충돌로 연령 적합 여부 판단 보류')
    mismatch=structured=='mismatch' or any(r['status']=='mismatch' for r in rows if not payload.get('conditions') or r['reason'].startswith(('개인 단독','공동 신청','시설면적','농업경영체 등록 조건','재배 작물')))
    state='조건 불일치' if mismatch else '추가 확인 필요' if conflict or not any(r['status']=='match' for r in rows) else '관련 가능성 있음'
    return {'label':state,'reasons':list(dict.fromkeys(r['reason'] for r in rows if r['status']!='check'))[:3],
            'checks':list(dict.fromkeys(unknown+[r['reason'] for r in rows if r['status']=='check']))[:4],
            'questions':list(dict.fromkeys(missing))[:2]}
