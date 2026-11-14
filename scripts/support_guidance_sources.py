"""Reuse explicit article KOGL marks for unchanged metadata, not whole documents."""
import hashlib,json,re,time,urllib.request,urllib.robotparser
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
import support_monitor as m
import support_bizinfo as transport
from support_runtime import boards

# The present service is a free, non-advertising capstone service. Types 2/4
# MUST be disabled before any commercial reuse. No third-party attachments.
NONCOMMERCIAL_METADATA_ONLY=True
POLICY_ID='official-kogl-metadata-v1'
POLICY_URL='https://www.kogl.or.kr/info/licenseType4.do'
def norm(value):return re.sub(r'[^0-9a-z가-힣]','',re.sub(r'첨부파일\s*있음','',value).lower())
def article_sha(check):return hashlib.sha256(norm(check.get('article','')).encode()).hexdigest()
def apply_decisions(checks,decisions):
    for identity,decision in decisions.items():
        check=checks.get(identity);primary=checks.get(decision['primary'])
        if not check:continue
        if (primary and check.get('status')==primary.get('status')=='checked'
                and article_sha(check)==decision['article_sha'] and article_sha(primary)==decision['primary_article_sha']):check['duplicate_of']=decision['primary']
        else:check['decision_changed']=True
def license_types(soup):
    text=soup.get_text(' ',strip=True)
    kinds=set(re.findall(r'본\s*저작물.{0,150}?공공누리.{0,40}?제?\s*([1-4])\s*유형',text))
    for img in soup.find_all('img',alt=True):
        if '공공누리' in img['alt'] or '공공저작물' in img['alt']:kinds.update(re.findall(r'제?\s*([1-4])\s*유형',img['alt']))
    return sorted(kinds)
def article(raw,url):
    soup=BeautifulSoup(raw,'html.parser')
    host=urlsplit(url).hostname
    if host in ('www.bizinfo.go.kr','bizinfo.go.kr'):
        node=soup.select_one('.support_project_detail')
        if node:
            # Related announcements outside this node must not supply facts.
            return re.sub(r'\s+',' ',node.get_text(' ',strip=True))
    if host=='global.at.or.kr':
        node=soup.select_one('article.contentGroup')
        return re.sub(r'\s+',' ',node.get_text(' ',strip=True)) if node else ''
    selector='.viewArea .viewBody' if urlsplit(url).hostname=='www.rda.go.kr' else '.bbs_view .bbs_con, .border_view > .exp' if urlsplit(url).hostname=='www.gochang.go.kr' else '.view-con, .bbsview-con, .bbs_view_con, .view_content, .view_cont, .boardView table.view'
    node=soup.select_one(selector)
    return node.get_text(' ',strip=True) if node else ''
def source_hosts():
    registry=json.loads((m.ROOT/'config/collector_sources.json').read_text(encoding='utf-8'))['sources']
    return {s['source_id']:urlsplit(s['board_url']).hostname for s in registry}
def validate_item(row,check):
    if (not check or check.get('status')!='checked' or not check.get('title_match') or check.get('url')!=row['original_url']
        or urlsplit(row['original_url']).hostname!=source_hosts().get(row['source_id'])):return None
    kinds=check.get('licenses',[])
    if len(kinds)!=1 or kinds[0] not in ('1','2','3','4'):return None
    if kinds[0] in ('2','4') and not NONCOMMERCIAL_METADATA_ONLY:return None
    return {'id':POLICY_ID,'type':kinds[0],'evidence_url':row['original_url'],'scope':'unchanged_metadata_only',
            'noncommercial':kinds[0] in ('2','4'),'body_sha256':check['body_sha256']}
def inspect(rows,*,seconds=120):
    """One bounded pass; blocked/unknown robots never bypassed or retried."""
    start=time.monotonic();result={};robots={}
    for row in rows:
        if time.monotonic()-start>seconds:break
        url=row['original_url'];host=urlsplit(url).hostname
        if host not in robots:
            try:
                raw,status,_=transport.probe_transport(urllib.request.Request('https://'+host+'/robots.txt',headers={'User-Agent':m.USER_AGENT}),timeout=6)
                parser=urllib.robotparser.RobotFileParser()
                if status in (404,410):parser.parse([])
                elif status==200 and not raw.lstrip().startswith(b'<'):parser.parse(raw.decode('utf-8-sig').splitlines())
                else:raise ValueError()
                robots[host]=parser
            except Exception:robots[host]=None
        check={'id':row['notice_id'],'url':url,'source_id':row['source_id'],'status':'access_policy_unconfirmed'}
        if robots[host] and robots[host].can_fetch(m.USER_AGENT,url):
            try:
                time.sleep(.5)
                raw,status,_=transport.probe_transport(urllib.request.Request(url,headers={'User-Agent':m.USER_AGENT}),timeout=6)
                soup=BeautifulSoup(raw,'html.parser')
                check.update(status='checked' if status==200 else 'http_'+str(status),title_match=norm(row['title']) in norm(soup.get_text(' ',strip=True)),
                             licenses=license_types(soup),body_sha256=hashlib.sha256(raw).hexdigest(),article=article(raw,url))
            except Exception:check['status']='request_failed'
        result[row['notice_id']]=check
    return result

def reviewed_facts(feed,plans,checks,now):
    """Version-bound facts; never turn a basic listing into eligibility approval."""
    items={n['id']:n for n in feed['notices']};result={}
    for p in plans:
        item=items.get(p.get('id'));c=checks.get(p.get('id'),{})
        if not item or comparison_basis(item)!=p.get('basis'):continue
        if c.get('status')!='checked' or not c.get('title_match') or c.get('url')!=item['url']:continue
        if article_sha(c)!=p.get('article_sha') or not c.get('article'):continue
        if not all(norm(x) in norm(c['article']) for x in p.get('required_fragments',[])):continue
        fields=p.get('fields',{})
        # Fixed operator-reviewed fact fields only; no HTML or arbitrary rule graph.
        allowed={'reference_application_dates','application_method','target','support','geographic_scope','scope_note'}
        if not isinstance(fields,dict) or set(fields)-allowed:continue
        if any(isinstance(x,str) and (len(x)>600 or '<' in x or '>' in x) for x in fields.values()):continue
        for key in ('start','end'):
            value=fields.get('reference_application_dates',{}).get(key,{})
            if value and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value.get('date','')):break
        else:
            reception=p.get('reception',{})
            verified_at=reception.get('checked_at','')
            try:age=(now-datetime.fromisoformat(verified_at)).total_seconds()
            except (ValueError,TypeError):age=float('inf')
            # Reception is an observation, not a claim renewed by merely fetching dates.
            reception=reception if 0<=age<86400 and reception.get('status')=='open_notice_verified' else {}
            result[item['id']]={'basis':p['basis'],'fields':fields,'checked_at':now.isoformat(),
                'expires_at':(now+timedelta(hours=26)).isoformat(),'complete':False,
                'evidence':{'url':item['url'],'location':p['location'],'fact_confirmed':True},
                'reception':reception,'unknown':p.get('unknown',[])}
            conditions=p.get('conditions',[])
            if conditions and all(c.get('kind') in ('farm_registration','residence','business_location','crop','scale','applicant') for c in conditions):
                result[item['id']]['conditions']=[{**c,'presence':'specified','status':'verified',
                    'evidence':{'url':item['url'],'location':p['location'],'fact_confirmed':True,'checked_at':now.isoformat()}} for c in conditions]
    return result

def comparison_basis(item):
    return {k:item.get(k) for k in ('id','title','url','target','region','reference_application_dates','application_period','eligibility')}
def verified_comparisons(feed,plans,checks,now):
    """Operator-reviewed necessary conditions, never a complete eligibility rule."""
    result={};items={n['id']:n for n in feed['notices']}
    for plan in plans:
        item=items.get(plan['id']);check=checks.get(plan['id'],{})
        if not item or item['publication'] not in ('approved','approved_reference') or comparison_basis(item)!=plan['basis']:continue
        if check.get('status')!='checked' or not check.get('title_match') or check.get('url')!=item['url']:continue
        text=norm(check.get('article',''))
        if not text or not all(norm(q) in text for q in plan['required_fragments']):continue
        conditions=[]
        for c in plan['conditions']:
            conditions.append({**c,'presence':'specified','status':'verified','evidence':{'url':item['url'],'location':plan['location'],
                                'fact_confirmed':True,'checked_at':now.isoformat()}})
        result[item['id']]={'basis':plan['basis'],'conditions':conditions,'checked_at':now.isoformat(),
                           'expires_at':(now+timedelta(days=3)).isoformat(),'complete':False,
                           'note':'확인된 필수조건 일부 비교 · 나머지 자격·예외·접수 여부는 추가 확인'}
    return result
