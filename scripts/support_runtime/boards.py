"""Promoted from the working local collector (2026-10-28).
Senior project row/link/date parsing reused with the operator's permission.
No trial data, automatic approval or publication side effects.
"""
import re,time,urllib.error,urllib.robotparser
import urllib.parse as url
import urllib.request as http
from datetime import date,datetime,timedelta
from bs4 import BeautifulSoup
import support_monitor as m
from . import facts,extractor,gochang
CITIES=['전주시', '군산시', '익산시', '정읍시', '남원시', '김제시', '완주군', '진안군', '무주군', '장수군', '임실군', '순창군', '고창군', '부안군']
IDS=('dataSid','dataUid','postUid','nttId','b_idx','board_no','idx','wr_id','articleId')


class Blocked(Exception):pass


def clean(v):return ' '.join(v.split())


def error_name(error):return 'HTTP '+str(error.code) if isinstance(error,urllib.error.HTTPError) else type(error).__name__


class Transport:
    def __init__(self,source):self.host=source['official_hosts'][0];self.count=0;self.last=0;self.robot=None;self.blocked=False
    def get(self,link,robots=False):
        p=url.urlsplit(link)
        if p.scheme!='https' or p.hostname!=self.host or p.username or p.password or p.port not in (None,443) or re.search(r'download|upload|login|logout|SynapViewer',p.path,re.I):raise Blocked('허용된 공개 경로 밖 요청')
        if self.blocked:raise Blocked('이전 접근 제한 이후 요청 중단')
        if not robots and (not self.robot or not self.robot.can_fetch(m.USER_AGENT,link)):raise Blocked('robots 접근 금지 또는 미확인')
        time.sleep(max(0,2-(time.monotonic()-self.last)));self.last=time.monotonic();self.count+=1
        owner=self
        class Redirect(m.OfficialRedirects):
            def redirect_request(self,req,fp,code,msg,headers,newurl):
                if not robots and (not owner.robot.can_fetch(m.USER_AGENT,newurl) or re.search(r'download|login|upload',url.urlsplit(newurl).path,re.I)):raise Blocked('리디렉션 접근 정책 차단')
                return super().redirect_request(req,fp,code,msg,headers,newurl)
        try:
            with http.build_opener(Redirect([self.host])).open(http.Request(link,headers={'User-Agent':m.USER_AGENT}),timeout=12) as response:
                data=response.read(m.MAX_BYTES+1)
                if len(data)>m.MAX_BYTES:raise ValueError('응답 크기 초과')
        except urllib.error.HTTPError as error:
            if error.code in (401,403,429):self.blocked=True
            raise
        if robots:
            self.robot=urllib.robotparser.RobotFileParser();self.robot.parse(data.decode('utf8','replace').splitlines())
        return data


def canonical(link,host):
    p=url.urlsplit(link)
    if p.scheme!='https' or p.hostname!=host or p.username or p.password or p.port not in (None,443):return None
    q=url.parse_qs(p.query)
    # Official search fields such as keyword are not authentication credentials.
    secrets={'key','servicekey','crtfckey','apikey','token','accesstoken','refreshtoken','password','passwd','session','sessionid','jsessionid','authorization','auth','secret','clientsecret','accesskey','privatekey'}
    if any(re.sub(r'[^a-z]','',k.lower()) in secrets for k in q):return None
    return url.urlunsplit((p.scheme,p.netloc,p.path,url.urlencode(sorted((k,v) for k,values in q.items() for v in values)),''))


class CommonList:
    """Senior row/link/date algorithm, parameterized for official board families."""
    def parse(self,soup,base):
        host=url.urlsplit(base).hostname;rows={}
        for a in soup.select('a[href]'):
            if a['href'].startswith('#'):continue
            link=canonical(url.urljoin(base,a['href']),host)
            if not link:continue
            p=url.urlsplit(link);q=url.parse_qs(p.query)
            expected=url.parse_qs(url.urlsplit(base).query).get('boardId')
            if expected and q.get('boardId')!=expected:continue
            identity=next(((k,q[k][0]) for k in IDS if q.get(k)),None)
            path_id=re.search(r'/view/(\d+)$',p.path)
            if path_id and not p.path.startswith(url.urlsplit(base).path.rstrip('/')+'/view/'):continue
            if not identity and path_id:identity=('path_id',path_id[1])
            if not identity or not re.search(r'view|index\.',p.path,re.I):continue
            node=a.select_one('strong,.subject,.title,.tit') or a
            title=clean(node.get_text(' ',strip=True))
            if len(title)<5 or title in ('상세보기','바로가기','새창열기') or re.search(r'download|SynapViewer',p.path,re.I):continue
            parent=a.find_parent(['tr','li','dd','article']) or a.parent
            # Some public boards use span/div rows instead of a table.
            for _ in range(3):
                if parent is not None and parent.name=='tr':break
                if parent is None or re.search(r'20\d{2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{1,2}',parent.get_text(' ',strip=True)):break
                upper=parent.parent
                if upper is None or len(upper.select('a[href*="view"]'))>2:break
                parent=upper
            text=clean(parent.get_text(' ',strip=True)) if parent else title
            hit=re.search(r'(?<!\d)(20\d{2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})(?!\d)',text)
            published=None
            if hit:
                try:published=date(*map(int,hit.groups())).isoformat()
                except ValueError:pass
            date_raw=None
            if not hit and host in ('www.buan.go.kr','www.gunsan.go.kr') and parent.name=='tr':
                # Both live boards expose a dedicated YY.MM.DD cell, not a title year.
                stamp=next((clean(td.get_text(' ',strip=True)) for td in parent.find_all('td',recursive=False) if re.fullmatch(r'\d{2}[.]\d{2}[.]\d{2}',clean(td.get_text(' ',strip=True)))),None)
                if stamp:
                    try:published=datetime.strptime(stamp,'%y.%m.%d').date().isoformat();date_raw=stamp
                    except ValueError:pass
            board=q.get('boardId',q.get('boardUid',['unknown']))[0]
            excerpt=a.select_one('.exp,.summary')
            row={'original_id':board+':'+identity[0]+':'+identity[1],'title':title,'original_url':link,'published_at':published,
                'board_category':'공식 공고','department':'unknown','title_truncated':bool(re.search(r'\.{2,}|…',title)),
                'list_excerpt':clean(excerpt.get_text(' ',strip=True))[:200] if excerpt else ''}
            if date_raw:row['published_at_raw']=date_raw;row['publication_date_format']='YY.MM.DD dedicated date cell'
            if row['original_id'] in rows and rows[row['original_id']]!=row:continue
            rows[row['original_id']]=row
        return list(rows.values())


def classify(row):
    text=row['title']+' '+row.get('list_excerpt','')
    if re.search(r'채용|입찰|합격자|기간제.*근로|선정결과|대상자.*명단|축제|행사|박람회|수요조사|법률.*의견|의견.*조회|등록정보.*공개',text):return 'excluded'
    if not re.search(r'농업|농가|농산물|농촌|귀농|귀촌|원예|스마트팜|농기계|청년농|후계농|축산|양봉|꿀벌|식품기업|노지|시설하우스',text):return 'unknown'
    if re.search(r'교육|연수|아카데미|수강',text):return 'education' if re.search(r'모집|신청|접수',text) else 'unknown'
    return 'agriculture_support' if re.search(r'지원사업|보조사업|지원.*(?:신청|모집|공고)|신청|모집|융자|공모|시범사업',text) else 'unknown'


def extract(body,link):
    soup=BeautifulSoup(body,'html.parser')
    if soup.select_one('.border_view > .exp'):return gochang.extract_gochang(body,link)
    selectors=['.bbsview-con','.bdvCntWrap .se-contents','.bdvCntWrap','.bbsviewcont','.bbsviewcontent','.bbsview_con','.bbs_view_con','.bbs_view .bbs_con','.basicView .conText','.board_view .view_cont','.board-view .view-content','.view_content','.view_cont','.bbs_view_cont','.bbs_content','.board_view_con','.board_view .con','#boardContents','.view_txt','.board_view .view-con','.board_view .cont','.bbsV_cont','.view-con','.conText','.viewContent','.board_view_content','.view_con','.view-contents','.board-view-content','.board-view-contents','.board-view__content','#bbsContents','.contentBody']
    selector=next((s for s in selectors if soup.select_one(s)),None)
    if not selector:raise ValueError('지원되지 않는 본문 영역')
    node=soup.select_one(selector)
    for x in node.select('script,style'):x.decompose()
    for x in node.select('br'):x.replace_with('\n')
    for x in node.select('p,div,li,tr'):x.insert_before('\n');x.insert_after('\n')
    lines=[clean(x) for x in node.get_text('',strip=False).splitlines() if x.strip()]
    wrapped='<div class="basicView"><div class="conText">'+''.join('<p>'+html.escape(x)+'</p>' for x in lines)+'</div></div>'
    result=extractor.extract(wrapped,link,facts.extract)
    for fact in result['facts'].values():fact['evidence']['location']='공식 상세 CSS '+selector+'; '+fact['evidence']['location'].split(';')[-1].strip()
    clauses=[]
    for line in lines:
        cities=[city for city in CITIES if city in line]
        if cities and re.search(r'대상\s*지역|거주|소재|관내',line):
            key='region_clause'
            if key not in result['facts']:result['facts'][key]={'value':{'text':line[:140],'region_names':cities},'evidence':{'url':link,'location':'공식 상세 CSS '+selector+'; 지역 표현','quote':line[:180]}}
        if re.match(r'^[○ㅇ□❍◎\d.()\-\s]*(?:지원\s*자격|신청\s*자격|제외\s*대상|제외\s*조건)\s*[:：]',line):clauses.append(line[:180])
    if clauses:result['facts']['eligibility_clauses']={'value':clauses[:8],'evidence':{'url':link,'location':'공식 상세 CSS '+selector+'; 자격·제외 조건','quote':clauses[0]}}
    result['content_selector']=selector
    return result

