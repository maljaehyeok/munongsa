"""Core facts from the documented Bizinfo overview, never from publisher tags.

These are private review candidates. No approval, public export or GPT access.
"""
import re
from bs4 import BeautifulSoup


def overview(description, url):
    text=BeautifulSoup(description,'html.parser').get_text(' ',strip=True) if '<' in description else description
    parts=[re.sub(r'\s+',' ',s).strip() for s in text.split('☞')]
    facts={}
    # The provider's explicit target/benefit pair, not an arbitrary paragraph.
    if len(parts)!=3 or not all(0<len(p)<=900 for p in parts[1:]):return facts
    target,support=parts[1:]
    if not re.search(r'농업인|농업법인|농가|농업경영체|농어업인|생산자단체|예비농',target):return facts
    if not re.search(r'지원',support):return facts
    def add(name,value,quote):
        facts[name]={'value':value,'evidence':{'url':url,'quote':quote,
            'location':'공식 API 사업개요의 대상·지원 구분; 관리자 미승인'}}
    add('target_description',target,target)
    add('support_description',support,support)
    if len(support)<=350:add('support_summary',support,support)
    # Do not turn alternatives/exceptions into independent mandatory clauses.
    if re.search(r'또는|다만|제외|예외|미등록|예비|예정|등록.*(?:무관|불필요|필요하지|않|없어도|필수.*아님)',target):return facts
    if re.search(r'농업경영정보를\s*등록한|농업경영체\s*등록(?:한|된|\s+(?:농업인|농가|농업법인)|\s*\d+\s*년\s*이상)',target):
        add('farm_registration_required',True,target)
    if re.fullmatch(r'농업경영정보를\s*등록한\s*농업인\s*(?:및|·|ㆍ)\s*농업법인',target):
        add('applicant_types',['individual_farmer','agricultural_business'],target)
    locations=[]
    # A joint address AND farmland requirement must survive as two clauses.
    joint=re.search(r'([가-힣]{2,10}(?:시|군|구))에\s*주소\s*및\s*농지를\s*둔',target)
    if joint:
        for kind,basis in [('residence','residence'),('business_location','farm_land')]:
            locations.append({'kind':kind,'regions':[joint[1]],'location_basis':basis})
    else:
        for kind,basis,pattern in [
            ('residence','residence',r'([가-힣]{2,10}(?:시|군|구))\s*(?:관내\s*|에\s*)(?:주소(?:지)?를\s*둔|거주하는)'),
            ('business_location','farm_land',r'([가-힣]{2,10}(?:시|군|구))에\s*농지를\s*둔'),
            ('business_location','business_office',r'([가-힣]{2,10}(?:시|군|구))에\s*사업장을\s*둔')]:
            for m in re.finditer(pattern,target):
                locations.append({'kind':kind,'regions':[m[1]],'location_basis':basis})
    if locations:
        add('location_requirements',locations,target)
        add('geographic_scope',{'scope':'municipality',
            'regions':list(dict.fromkeys(p for loc in locations for p in loc['regions'])),
            'basis':'multiple' if len(locations)>1 else locations[0]['location_basis']},target)
    # No expansion of 관내, tags or the publisher's jurisdiction into eligibility.
    if re.match(r'^전국(?:의|\s)',target):
        add('geographic_scope',{'scope':'national','regions':['전국'],'basis':'unknown'},target)
    return facts
