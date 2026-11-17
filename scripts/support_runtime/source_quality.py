"""Evidence yield for source selection and private detail-fetch prioritisation."""
from collections import Counter
from urllib.parse import urlsplit,parse_qs
from .conditions import clean_proof,identity_url

CORE=('target_description','geographic_scope','support_description','application_deadline')

def notice_key(url):
    p=urlsplit(url);q=parse_qs(p.query)
    if (p.hostname in ('bizinfo.go.kr','www.bizinfo.go.kr')
            and p.path in ('/sii/siia/selectSIIA200Detail.do','/web/lay1/bbs/S1T122C128/AS/74/view.do')
            and len(q.get('pblancId',[]))==1):
        return ('www.bizinfo.go.kr','pblancId',q['pblancId'][0])
    return identity_url(url)


def quality(entry):
    url=identity_url(entry['metadata']['original_url']);facts={}
    for key,fact in entry.get('facts',{}).items():
        if not isinstance(fact,dict) or fact.get('value') in (None,'unknown','',[],{}):continue
        proof=clean_proof(fact)
        if key=='support_description' and proof and proof['location']=='공식 API 사업개요; 세부 자격 검토 전':continue
        if proof and identity_url(proof['url'])==url:facts[key]=fact
    present=[k for k in CORE if k in facts]
    # Region and target outweigh a long summary or an institution's location.
    score=sum(3 if k in ('geographic_scope','target_description') else 1 for k in present)
    return {'core_fields':present,'score':score,'core_complete':len(present)==len(CORE),
        'condition_evidence':any(k in facts for k in ('location_requirement','location_requirements',
            'farm_registration_required','applicant_types')),
        'recommendation_eligible':False,'approval_required':True}


def detail_plan(entries, existing_urls=(), excluded_urls=(), limit=12):
    """Local acquisition only. Scheduled monitoring must still revisit old IDs."""
    from collect_national_candidates import identity
    existing={identity(u) for u in existing_urls};excluded={identity(u) for u in excluded_urls}
    buckets={};seen=set();counts=Counter()
    for entry in entries:
        row=entry['metadata'];key=identity(row['original_url'])
        if key in seen:counts['repeated']+=1;continue
        seen.add(key)
        if key in existing:counts['operating_duplicates']+=1;continue
        if key in excluded:counts['previous_review_excluded']+=1;continue
        buckets.setdefault(row.get('list_region') or 'unknown',[]).append(entry)
    for rows in buckets.values():rows.sort(key=lambda e:(-quality(e)['score'],e['metadata']['original_id']))
    chosen=[]
    while buckets and len(chosen)<max(0,min(int(limit),24)):
        for region in list(buckets):
            if len(chosen)>=max(0,min(int(limit),24)):break
            chosen.append(buckets[region].pop(0))
            if not buckets[region]:del buckets[region]
    return {'entries':chosen,'counts':dict(counts),'remaining':sum(map(len,buckets.values())),
        'region_basis':'discovery_only_not_eligibility'}


def source_report(group):
    entries=group.get('analyses',[]);rows=[quality(e) for e in entries]
    return {'kind':group['kind'],'sample_count':len(rows),
        'core_coverage':dict(Counter(k for r in rows for k in r['core_fields'])),
        'all_core_confirmed':sum(r['core_complete'] for r in rows),
        'condition_evidence':sum(r['condition_evidence'] for r in rows),
        'priority':'core_available' if any(r['core_complete'] for r in rows) else 'insufficient_region_or_target',
        'approved':0}
