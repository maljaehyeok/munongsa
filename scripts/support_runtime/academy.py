"""Official agricultural education Atom discovery; original-table facts only.

No student forms/comments, attachments, approval or external LLM requests.
"""
import re,xml.etree.ElementTree as ET
from datetime import date,timedelta
from urllib.parse import urlsplit,parse_qs,urlencode,urlunsplit
from bs4 import BeautifulSoup
from . import boards,discovery,periods,official_expansion

HOST='agriacademy.jeonbuk.go.kr'
NS={'a':'http://www.w3.org/2005/Atom'}
AGRI=r'농업|농촌|농가|농식품|농산물|영농|귀농|스마트팜|후계농'
EXCLUDE=r'입찰|채용|공모전|행사|이벤트|선정\s*결과|농기계|트랙터|건설기계|로더|예취기|용접|어촌|어업'

def official_url(value):
    p=urlsplit(value);q=parse_qs(p.query)
    if p.scheme!='https' or p.hostname!=HOST or p.netloc!=HOST or p.path!='/bbs/board.php' or set(q)!={'bo_table','wr_id'}:raise ValueError('unapproved_article_path')
    if any(len(v)!=1 for v in q.values()) or q['bo_table'][0]!='ad_02_01' or not re.fullmatch(r'\d{1,8}',q['wr_id'][0]):raise ValueError('unapproved_board')
    return urlunsplit(('https',HOST,p.path,urlencode({'bo_table':q['bo_table'][0],'wr_id':q['wr_id'][0]}),''))

def parse_feed(raw,now):
    if re.search(br'<!DOCTYPE|<!ENTITY',raw,re.I):raise ValueError('xml_declaration_denied')
    root=ET.fromstring(raw)
    if root.tag!='{http://www.w3.org/2005/Atom}feed':raise ValueError('not_atom')
    rows={}
    for e in root.findall('a:entry',NS)[:100]:
        category=e.find('a:category',NS)
        if category is None or category.get('term')!='ad_02_01':continue
        title=boards.clean(e.findtext('a:title','',NS));summary=e.findtext('a:summary','',NS)
        if not title or re.search(EXCLUDE,title) or not re.search(AGRI,title+' '+summary):continue
        link=e.find('a:link[@rel="alternate"]',NS)
        if link is None:continue
        try:url=official_url(link.get('href',''))
        except ValueError:continue
        stamp=e.findtext('a:updated','',NS) or e.findtext('a:published','',NS)
        try:updated=periods.as_of(stamp)
        except (ValueError,TypeError):continue
        if updated>now+timedelta(days=1) or updated<now-timedelta(days=90):continue
        ident='ad_02_01:'+parse_qs(urlsplit(url).query)['wr_id'][0]
        rows[ident]={'original_id':ident,'title':title,'original_url':url,'published_at':None,'feed_updated_at':stamp}
    return list(rows.values())

def detail(raw,row):
    """Allowlisted course table only. Never harvest registration comments/PII."""
    soup=BeautifulSoup(raw,'html.parser');root=soup.select_one('#sub_ctn_2')
    if root is None:raise ValueError('course_article_missing')
    labels={'교육 과정명','교육 기간 및 시간','교육 대상','인원','교육 내용','신청 기한'};fields={}
    for tr in root.select('tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)!=3 or cells[0].find(['table','form']):continue
        label=re.sub(r'^[-\s]+','',cells[0].get_text(' ',strip=True));value=boards.clean(cells[2].get_text(' ',strip=True))
        if label in labels and value:
            if label in fields and fields[label]!=value:raise ValueError('conflicting_course_fields')
            fields[label]=value
    if not fields.get('교육 과정명') or fields['교육 과정명']!=row['title'] or not fields.get('교육 대상'):raise ValueError('course_identity_or_target_missing')
    text=root.get_text(' ',strip=True);posted=re.search(r'Date\s*:\s*(20\d{2}-\d{2}-\d{2})',text)
    metadata={k:v for k,v in row.items() if k!='feed_updated_at'}
    metadata['published_at']=posted[1] if posted else None
    url=row['original_url'];facts={}
    def fact(key,value,label):
        facts[key]={'value':value,'evidence':{'url':url,'location':'공식 월별교육과정 표: '+label,'quote':fields[label]}}
    fact('target_description',fields['교육 대상'],'교육 대상')
    fact('support_description',fields.get('교육 내용',fields['교육 과정명']),'교육 내용' if fields.get('교육 내용') else '교육 과정명')
    # A course date is never an application deadline or posting date.
    deadline=fields.get('신청 기한','')
    match=re.search(r"(?:[‘’'](\d{2})|(20\d{2}))\s*[.년]\s*(\d{1,2})\s*[.월]\s*(\d{1,2})\s*[.일]",deadline)
    if match:
        year=int(match[2] or '20'+match[1]);day=date(year,int(match[3]),int(match[4])).isoformat()
        fact('application_deadline',{'date':day,'time':'unknown','timezone':'unknown'},'신청 기한')
    if deadline:fact('application_method',deadline,'신청 기한')
    lines=['신청 대상: '+fields['교육 대상']]
    payload,_=official_expansion.candidates(lines,url)
    facts['official_condition_candidates']={'value':payload,'evidence':{'url':url,'location':'공식 교육 대상; 미검토 조건 후보','quote':fields['교육 대상']}}
    facts['official_document_kind']={'value':'education_notice','evidence':{'url':url,'location':'공식 교육 과정명; 지원금 사업 접수 공고와 구분','quote':fields['교육 과정명']}}
    return {'kind':'jeonbuk_academy','metadata':metadata,'facts':facts,'status':'partial','checked_at':boards.m.utc_now(),'detail_fetched':True,
      'unknown_fields':['교육 신청 시작일·실제 잔여석·접수 가능 여부','세부 자격·비용·필수 서류·지역 기준 관리자 확인','교육 모집이며 같은 이름의 지원금 사업 모집이 아님'],
      'warnings':['Atom 갱신일은 공고 게시일이 아님. 원문 게시일만 사용.','교육 일정으로 신청기간을 추정하지 않음.']}

def collect(source,now,known=None,detail_policy=None):
    transport=discovery.Transport(source);group={'kind':source['kind'],'analyses':[],'errors':[],'list_count':0,'candidate_count':0,'requests':0,'state':'연결 미완료'}
    try:
        if source['official_hosts']!=[HOST] or source.get('discovery_url')!='https://'+HOST+'/ai/feed.xml':raise ValueError('unexpected_source')
        robots=transport.get('https://'+HOST+'/robots.txt',True)
        if re.search(br'<(?:html|script|!doctype)',robots,re.I):raise boards.Blocked('robots 정책 미확인')
        rows=parse_feed(transport.get(source['discovery_url']),now);group.update(list_count=len(rows),candidate_count=len(rows))
        for row in rows[:min(int(source.get('detail_limit',4)),4)]:
            prior=(known or {}).get((source['kind'],row['original_id']))
            fetch,prior=detail_policy(source['kind'],row,prior,now) if detail_policy else (True,prior)
            if not fetch and prior:group['analyses'].append(dict(prior,detail_fetched=False));continue
            try:
                entry=detail(transport.get(row['original_url']),row);entry['recruitment']=periods.assess(entry['facts'],now=now,checked_at=entry['checked_at']);group['analyses'].append(entry)
            except Exception as error:group['errors'].append({'stage':'detail','error':boards.error_name(error)})
        group['state']='연결 성공' if not group['errors'] else '부분 실패'
    except Exception as error:group['errors'].append({'stage':'source','error':boards.error_name(error)})
    group['requests']=transport.count
    return group
