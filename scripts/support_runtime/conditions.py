"""Promoted from the working local collector (2026-10-28).
Senior project row/link/date parsing reused with the operator's permission.
No trial data, automatic approval or publication side effects.
"""
import re,copy
from urllib.parse import urlsplit,parse_qsl,urlencode,urlunsplit
import support_monitor as monitor
import export_support_public as public
from .boards import CITIES

def make_payload(facts):
    conditions=[]
    if facts.get('legal_entity_required',{}).get('value') is True:
        conditions.append({'condition_id':'legal_entity','kind':'applicant','presence':'specified',
            'value':{'one_of':['agricultural_business']},'evidence':facts['legal_entity_required']['evidence']})
    threshold=facts.get('annual_handling_threshold',{})
    value=threshold.get('value',{})
    if isinstance(value,dict) and value.get('comparison') in ('이상','초과'):
        conditions.append({'condition_id':'annual_handling','kind':'scale','presence':'specified',
            'value':{'min':value['amount_krw'],'max':None,'min_inclusive':value['comparison']=='이상',
                     'max_inclusive':False,'unit':'KRW','metric':value['metric'],
                     'measurement_basis':'원문 자격 문구 전체 참조; 계약재배 등 취급액과 임의 매출액을 동일시하지 않음'},
            'evidence':threshold['evidence']})
    conditions.extend([
        {'condition_id':'business_location_unknown','kind':'business_location','presence':'unknown','value':None,'evidence':{}},
        {'condition_id':'remaining_unknown','kind':'other_required','presence':'unknown','value':None,'evidence':{}}
    ])
    return {'conditions':conditions,'logic':{'op':'AND','children':[{'condition_id':c['condition_id']} for c in conditions]}}


def identity_url(value):
    # Strip nonidentity search controls for the old strict proof validator only.
    # The source record and visible official link retain their exact original URL.
    p=urlsplit(value)
    q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k not in ('keyword','searchType','page','startPage','paging')]
    result=urlunsplit((p.scheme,p.netloc,p.path,urlencode(q),p.fragment))
    public.checked_url(result)
    return result


def clean_proof(fact):
    e=fact.get('evidence',{})
    if not all(isinstance(e.get(k),str) and e[k].strip() for k in ('url','quote','location')):return None
    try:link=identity_url(e['url'])
    except (ValueError,monitor.MonitorError):return None
    return {'url':link,'quote':e['quote'],'location':e['location']}


def payload_for(facts,base):
    """Add only narrow, evidenced clauses; preserve existing AND/OR/NOT graph."""
    base=copy.deepcopy(base)
    conditions=base.get('conditions',[])
    if not conditions:
        conditions=[{'condition_id':'remaining_unknown','kind':'other_required','presence':'unknown','value':None,'evidence':{},'status':'candidate'}]
        base={'conditions':conditions,'logic':{'condition_id':'remaining_unknown'}}
    added=[]
    def add(name,kind,value,fact):
        proof=clean_proof(fact)
        if not proof or any(c['kind']==kind and c['presence']=='specified' for c in conditions):return
        c={'condition_id':name,'kind':kind,'presence':'specified','value':value,'evidence':proof,'status':'candidate'}
        conditions.append(c);added.append({'condition_id':name})
    target=facts.get('target_description',{});text=target.get('value','')
    if isinstance(text,str):
        complex_clause=bool(re.search(r'또는|제외|다만|모임체|대표|미등록',text))
        personal=bool(re.search(r'농업인|농가',text)) and not re.search(r'법인|기업|농협|조합|기관|단체',text)
        if personal and not complex_clause:add('text_applicant','applicant',{'one_of':['individual_farmer']},target)
        if personal and not complex_clause:
            for city in CITIES:
                if re.search(re.escape(city)+r'에\s*(?:주소(?:지)?를?\s*둔|주소를\s*두고|거주)',text):
                    add('text_residence','residence',{'regions':['전북 '+city]},target);break
            if re.search(r'농업경영체\s*등록\s*(?:및|하고|한|을)',text):
                add('text_registration','farm_registration',{'registered':True},target)
        # Age words without a reference date are displayable, never decidable.
        age=re.search(r'만\s*(\d{1,2})\s*[~∼～]\s*(\d{1,2})\s*세',text)
        if age:add('text_age','age',{'min':int(age[1]),'max':int(age[2]),'min_inclusive':True,'max_inclusive':True,'basis_date':'unknown','age_basis':'international'},target)
    if added:
        base['logic']={'op':'AND','children':[base.get('logic',{'op':'UNKNOWN','children':[]}),*added]}
    base['conditions']=conditions
    return base

