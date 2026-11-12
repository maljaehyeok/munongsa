"""Bounded Jeonbuk official notice/guideline adapter. Private candidates only."""
import re
from datetime import timedelta
from urllib.parse import urljoin,urlsplit,parse_qsl,urlencode,urlunsplit
from bs4 import BeautifulSoup
from . import boards,discovery,enrichment,periods

ADAPTER='jeonbuk-official-v1'
FIELDS=('residence','business_location','age','farming_experience','farm_registration','crop','applicant')
AGRI=r'농업|농촌|농가|농민|귀농|청년농|후계농|스마트팜|스마트농업|농식품|영농|원예|축산'
EXCLUDED=r'채용|입찰|근로자|선정\s*결과|선발\s*결과|수상|평가위원|설명회|행사|축제|박람회|보도자료|홍보|수요조사|의견.*조회|농기계|편의장비|장비\s*지원'

def document_kind(title):
    if not re.search(AGRI,title) or re.search(EXCLUDED,title):return None
    if re.search(r'지침|시행계획|지원계획',title):return 'policy_reference'
    if re.search(r'모집|신청|접수|공모',title):return 'application_notice'
    return None

def candidates(lines,url):
    """Narrow predicates only; alternatives/tracks remain UNKNOWN and unapproved."""
    from .conditions import identity_url
    url=identity_url(url)
    rows=[];seen=set();raw=[]
    def add(kind,value,line):
        # A candidate is not verified and is never a no-restriction assertion.
        if len(line)>350:return
        signature=(kind,str(value),line)
        if signature in seen:return
        seen.add(signature)
        rows.append({'condition_id':'official_'+str(len(rows)+1),'kind':kind,'presence':'specified',
          'value':{**value,'scope_text':line},'evidence':{'url':url,'location':'공식 본문 자격 항목; 과정·예외 원문 함께 검토','quote':line}})
    scope=False;alternatives=False
    for line in lines:
        if re.search(r'응시\s*자격|신청\s*자격|지원\s*자격|신청\s*대상|지원\s*대상',line):scope=True
        elif re.search(r'전형방법|문의처|신청방법|제출서류|입학.*혜택',line):scope=False
        eligible=scope or bool(re.match(r'^[○❍□\s]*(?:대상\s*지역|재배\s*작물|거주\s*요건|영농\s*경력|연령\s*요건)\s*[:：]',line))
        if not eligible:continue
        if line.strip():raw.append(line[:350])
        complex_=bool(re.search(r'또는|다만|제외|예외|특별전형|과정\)',line))
        alternatives|=complex_
        names=re.findall(r'전북(?:특별자치도|자치도)?|전라북도|전남(?:특별자치도)?|전라남도|경기도|경상북도|경상남도|충청북도|충청남도|(?:전주|부안|고창|파주|포항|김제|익산|군산)(?:시|군)',line)
        if names and re.search(r'거주|주소',line):add('residence',{'regions':list(dict.fromkeys(names))},line)
        if names and re.search(r'(?:농지|영농지|재배지).*소재|소재.*(?:농지|영농지|재배지)',line):add('business_location',{'regions':list(dict.fromkeys(names)),'location_basis':'farm_land'},line)
        m=re.search(r'만\s*(\d{1,2})\s*세\s*(미만|이하|이상|초과)',line)
        if m:
            n=int(m[1]);upper=m[2] in ('미만','이하')
            add('age',{'min':None if upper else n,'max':n if upper else None,'min_inclusive':m[2]=='이상','max_inclusive':m[2]=='이하','basis_date':'unknown','age_basis':'international'},line)
        m=re.search(r'(?:영농\s*경력\s*)?(\d+(?:\.\d+)?)\s*년\s*(이상|초과|이하|미만).*영농\s*경력|영농\s*경력\s*(\d+(?:\.\d+)?)\s*년\s*(이상|초과|이하|미만)',line)
        if m:
            n=float(m[1] or m[3]);op=m[2] or m[4];upper=op in ('이하','미만')
            add('farming_experience',{'min':None if upper else n,'max':n if upper else None,'min_inclusive':op=='이상','max_inclusive':op=='이하','unit':'years','basis_date':'unknown'},line)
        if not complex_:
            if re.search(r'농업경영체\s*(?:등록한|등록된|등록을\s*완료한|등록\s*농업인)',line):add('farm_registration',{'registered':True},line)
            if re.search(r'(?:신청|지원)\s*대상\s*[:：]\s*(?:개인\s*)?농업인\s*$',line):add('applicant',{'one_of':['individual_farmer']},line)
            m=re.search(r'재배\s*작물\s*[:：]\s*([가-힣,· ]+)$',line)
            if m and not re.search(r'등|및|그\s*외',m[1]):add('crop',{'any_of':[v.strip() for v in re.split('[,·]',m[1]) if v.strip()]},line)
    # Missing, disjunctive, historical or multi-track criteria cannot become true.
    for kind in FIELDS:
        if not any(c['kind']==kind for c in rows):rows.append({'condition_id':'unknown_'+kind,'kind':kind,'presence':'unknown','value':None,'evidence':{}})
    rows.append({'condition_id':'official_remaining','kind':'other_required','presence':'unknown','value':None,'evidence':{}})
    return {'conditions':rows,'logic':{'op':'UNKNOWN','children':[{'condition_id':c['condition_id']} for c in rows],
      'note':'과정·선택 조건·기준일·예외와 나머지 요건을 관리자 검토하기 전 결합 판정 금지'}},list(dict.fromkeys(raw))[:12]

def enrich(entry,body):
    """Only the previously supported article selector, never whole-page text."""
    url=entry['metadata']['original_url'];parsed=boards.extract(body,url);lines=discovery.content_lines(body,parsed)
    facts={**entry.get('facts',{}),**enrichment.extra_facts(lines,url),**enrichment.rate_facts(lines,url)}
    payload,clauses=candidates(lines,url)
    facts['official_condition_candidates']={'value':payload,'evidence':{'url':url,'location':'공식 본문 자격 항목; 관리자 미검토','quote':clauses[0] if clauses else ''}}
    if clauses:facts['official_eligibility_text']={'value':clauses,'evidence':{'url':url,'location':'공식 본문 과정별 응시·지원 자격','quote':clauses[0]}}
    normalized=[re.sub(r"['’](\d{2})(?=\s*[.년])",lambda m:'20'+m[1],v) for v in lines]
    period=periods.extract(normalized,url)
    if period.get('period'):
        proof=period['period']['evidence'];quote=proof.get('quote','')
        original=next((old for old,new in zip(lines,normalized) if quote in new),None)
        if original:proof['quote']=original;proof['location']='공식 본문 모집기간; 명시된 두 자리 연도 정규화'
        for key,part in [('application_start','start'),('application_deadline','end')]:
            if period['period'].get(part):facts[key]={'value':period['period'][part],'evidence':dict(proof)}
    entry.update(facts=facts,period_parse=period,unknown_fields=list(dict.fromkeys(entry.get('unknown_fields',[])+['자격조건 관리자 검토 대기','원문 첨부·정정·실제 접수 여부 별도 확인'])))
    return entry

def collect(source,now,known=None,detail_policy=None):
    t=discovery.Transport(source);group={'kind':source['kind'],'analyses':[],'errors':[],'list_count':0,'candidate_count':0,'requests':0,'state':'연결 미완료'}
    try:
        policy=t.get('https://'+t.host+'/robots.txt',True)
        if re.search(br'<(?:html|script|!doctype)',policy,re.I):raise boards.Blocked('robots 응답이 정책 문서가 아님')
        link=source['board_url'];soup=BeautifulSoup(t.get(link),'html.parser');parser=boards.CommonList();rows={r['original_id']:r for r in parser.parse(soup,link)}
        form=next((f for f in soup.select('form') if f.select_one('input[name=boardId]') and f.select_one('input[name=keyword]')),None)
        if form:
            action=urljoin(link,form.get('action') or link)
            fields={n.get('name'):n.get('value','') for n in form.select('input[name]') if n.get('name') in ('menuCd','boardId')}
            option=form.select_one('select[name=searchType] option[value=DATA_TITLE]')
            if option and urlsplit(action).hostname==t.host:
                for term in source.get('search_terms',[])[:3]:
                    params={**dict(parse_qsl(urlsplit(action).query)),**fields,'searchType':option['value'],'keyword':term}
                    q=urlsplit(action);search=urlunsplit((q.scheme,q.netloc,q.path,urlencode(params),''))
                    for row in parser.parse(BeautifulSoup(t.get(search),'html.parser'),search):rows[row['original_id']]=row
        group['list_count']=len(rows)
        chosen=[]
        for row in rows.values():
            kind=document_kind(row['title']);posted=row.get('published_at') or '1900-01-01'
            if not kind:continue
            # Guidelines are reference documents, never live application notices.
            if posted<(now.date()-timedelta(days=90)).isoformat() and not (kind=='policy_reference' and str(now.year) in row['title']):continue
            row['document_kind']=kind;chosen.append(row)
        chosen.sort(key=lambda r:r.get('published_at') or '',reverse=True);group['candidate_count']=len(chosen)
        for row in chosen[:min(source.get('detail_limit',4),4)]:
            prior=(known or {}).get((source['kind'],row['original_id']))
            fetch,prior=detail_policy(source['kind'],row,prior,now) if detail_policy else (True,prior)
            if not fetch and prior:group['analyses'].append(dict(prior,metadata=row,detail_fetched=False));continue
            try:
                body=t.get(row['original_url']);entry=enrich({'kind':source['kind'],'metadata':row,'checked_at':boards.m.utc_now(),'status':'partial','detail_fetched':True},body)
                entry['facts']['official_document_kind']={'value':row['document_kind'],'evidence':{'url':row['original_url'],'location':'공식 게시판 제목 분류; 모집기간 별도 검토','quote':row['title']}}
                if row['document_kind']=='policy_reference':entry['recruitment']={'status':'unknown','reason':'정책·시행지침; 실제 모집공고 아님'}
                group['analyses'].append(entry)
            except Exception as error:group['errors'].append({'stage':'detail','error':boards.error_name(error)})
        group['state']='연결 성공' if not group['errors'] else '부분 실패'
    except Exception as error:group['errors'].append({'stage':'source','error':boards.error_name(error)})
    group['requests']=t.count
    return group

def import_new(connection,entries):
    """Initial expansion only: never modify any existing notice or approval."""
    from . import ingestion
    existing=list(connection.execute('SELECT notice_id,source_id,title,original_url FROM discovered_notices'))
    by_url={ingestion.identity(r['original_url']):r for r in existing};inserted=[];duplicates=[]
    for entry in entries:
        row=entry['metadata'];identity=ingestion.identity(row['original_url'])
        if identity in by_url:
            duplicates.append({'title':row['title'],'existing_id':by_url[identity]['notice_id'],'reason':'same_official_identity'});continue
        expected='NOTICE-'+boards.m.digest(ingestion.SOURCES[entry['kind']]['source_id']+'\n'+row['original_id'])[:24]
        if connection.execute('SELECT 1 FROM discovered_notices WHERE notice_id=?',(expected,)).fetchone():
            duplicates.append({'title':row['title'],'existing_id':expected,'reason':'same_notice_id'});continue
        result=ingestion.save(connection,entry)
        if result['action']!='new' or result['condition_error']:raise RuntimeError('candidate_import_validation_failed')
        item=connection.execute('SELECT * FROM discovered_notices WHERE notice_id=?',(result['id'],)).fetchone()
        if item['publication']!='review' or item['verification_status']=='verified':raise RuntimeError('unexpected_candidate_approval')
        by_url[identity]=item;inserted.append(result['id'])
    return {'new_ids':inserted,'new':len(inserted),'duplicates':duplicates,'automatic_approval':False}
