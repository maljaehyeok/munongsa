"""Promoted from the working local collector (2026-10-28).
Senior project row/link/date parsing reused with the operator's permission.
No trial data, automatic approval or publication side effects.
"""
import re,urllib.error,urllib.robotparser
from bs4 import BeautifulSoup
from . import boards as w, periods, facts, extractor

class Transport(w.Transport):
    def get(self,link,robots=False):
        p=w.url.urlsplit(link)
        link=w.url.urlunsplit((p.scheme,p.netloc,w.url.quote(p.path,safe='/%:@'),w.url.urlencode(w.url.parse_qsl(p.query,keep_blank_values=True)),''))
        try:return super().get(link,robots)
        except urllib.error.HTTPError as error:
            if robots and error.code==404:
                # RFC 9309 unavailable (4xx): no robots rules, not a prohibition.
                self.robot=urllib.robotparser.RobotFileParser();self.robot.parse([]);self.robots_note='robots.txt HTTP 404; 별도 금지 규칙 없음, 포괄 재이용 허가는 아님'
                return b''
            raise
    def post_search(self,link,fields):
        p=w.url.urlsplit(link)
        if p.scheme!='https' or p.hostname!=self.host or not re.search(r'list\.|index\.',p.path) or not self.robot.can_fetch(w.m.USER_AGENT,link):raise w.Blocked('공식 검색폼 POST 경로 제한')
        w.time.sleep(max(0,2-(w.time.monotonic()-self.last)));self.last=w.time.monotonic();self.count+=1
        owner=self
        class Redirect(w.m.OfficialRedirects):
            def redirect_request(self,req,fp,code,msg,headers,newurl):
                if not owner.robot.can_fetch(w.m.USER_AGENT,newurl):raise w.Blocked('검색 응답 리디렉션 정책 제한')
                return super().redirect_request(req,fp,code,msg,headers,newurl)
        request=w.http.Request(link,data=w.url.urlencode(fields).encode(),headers={'User-Agent':w.m.USER_AGENT,'Content-Type':'application/x-www-form-urlencoded'},method='POST')
        with w.http.build_opener(Redirect([self.host])).open(request,timeout=12) as response:
            raw=response.read(w.m.MAX_BYTES+1)
            if len(raw)>w.m.MAX_BYTES:raise ValueError('검색 응답 크기 제한')
            return raw


def content_lines(body,result):
    soup=BeautifulSoup(body,'html.parser');selector=result.get('content_selector');node=soup.select_one(selector) if selector else None
    if node is None:return []
    for x in node.select('script,style'):x.decompose()
    marker='\u241e'
    # Malformed editor HTML can give a br children; replacement would delete facts.
    for x in list(node.select('br')):x.insert_before(marker);x.unwrap()
    for x in node.select('p,div,tr,li'):x.insert_before(marker);x.insert_after(marker)
    # Editor source newlines are formatting, not paragraph boundaries.
    return [w.clean(x) for x in node.get_text(' ',strip=True).split(marker) if x.strip()]


def analyse(entry,t,now):
    row=entry['metadata'];checked=w.m.utc_now()
    try:body=t.get(row['original_url'])
    except Exception as error:
        result=dict(entry,status='failed',failure_stage='access',error=w.error_name(error))
        # Failed retrieval never erases the previous factual version.
        result['recruitment']=periods.assess(entry.get('facts',{}),now=now,checked_at=entry.get('checked_at'))
        result['recruitment']['fetch_status']='failed';return result
    try:
        result=w.extract(body,row['original_url']);lines=content_lines(body,result)
        import html
        normalized=[re.sub(r'^\s*[가-하][.．)]\s*','',x) for x in lines]
        wrapped='<div class="basicView"><div class="conText">'+''.join('<p>'+html.escape(x)+'</p>' for x in normalized)+'</div></div>'
        repaired=extractor.extract(wrapped,row['original_url'],facts.extract)
        for fact in repaired['facts'].values():
            fact['evidence']['location']='공식 상세 CSS '+result['content_selector']+'; 정규화한 사실 문구'
            for raw,norm in zip(lines,normalized):
                if fact['evidence']['quote'] in norm:fact['evidence']['quote']=raw[:180];break
        result.update({k:v for k,v in repaired.items() if k!='content_selector'})
        if getattr(t,'fact_enricher',None):result['facts'].update(t.fact_enricher(lines,row['original_url']))
        parsed=periods.extract(lines,row['original_url']);period=parsed.get('period') or {}
        if parsed.get('period'):
            for key,part in [('application_start','start'),('application_deadline','end')]:
                if period.get(part):result['facts'][key]={'value':period[part],'evidence':period['evidence']}
        result['warnings']=list(dict.fromkeys(result.get('warnings',[])+parsed['warnings']))
        result['recruitment']=periods.assess(result.get('facts',{}),parsed,now,checked)
        result['period_parse']=parsed;return dict(entry,**result,checked_at=checked)
    except Exception as error:
        result=dict(entry,status='failed',failure_stage='extraction',error=w.error_name(error))
        result['recruitment']=periods.assess(entry.get('facts',{}),now=now,checked_at=entry.get('checked_at'));result['recruitment']['fetch_status']='extraction_failed';return result


def search_source(source,now,known=None,refresh_details=False,detail_policy=None,fact_enricher=None):
    t=Transport(source);kind=source['kind'];rows={};attempts=[]
    t.fact_enricher=fact_enricher
    group={'kind':kind,'city':source['city'],'checked_at':w.m.utc_now(),'list_count':0,'candidate_count':0,'analyses':[],'errors':[],
        'state':'연결 미완료','requests':0,'attempts':attempts}
    try:
        t.get('https://'+t.host+'/robots.txt',True)
        entry='https://www.sunchang.go.kr/farm' if kind=='sunchang' else source['board_url']
        soup=BeautifulSoup(t.get(entry),'html.parser');attempts.append({'url':entry,'purpose':'공식 진입 및 목록 확인'})
        if kind=='sunchang':
            board=w.url.parse_qs(w.url.urlsplit(source['board_url']).query).get('boardUid')
            link=next((w.url.urljoin(entry,a['href']) for a in soup.select('a[href]') if '/board/post/list.do' in a['href'] and w.url.parse_qs(w.url.urlsplit(a['href']).query).get('boardUid')==board),None)
            if not link:raise ValueError('농업기술센터 실제 목록 링크 미확인')
            entry=link;soup=BeautifulSoup(t.get(entry),'html.parser');attempts.append({'url':entry,'purpose':'공식 더보기 링크 자동 발견'})
        parser=w.CommonList()
        for row in parser.parse(soup,entry):rows[row['original_id']]=row
        if kind=='jeongeup' and rows:
            # Department home embeds five posts; discover its real full-list backlink.
            try:
                detail=BeautifulSoup(t.get(next(iter(rows.values()))['original_url']),'html.parser')
                back=next((w.canonical(w.url.urljoin(entry,a['href']),t.host) for a in detail.select('a[href]') if '목록' in a.get_text() and 'list.' in a['href']),None)
                if back:
                    more=BeautifulSoup(t.get(back),'html.parser');found=parser.parse(more,back)
                    for row in found:rows[row['original_id']]=row
                    soup=more;entry=back;attempts.append({'url':back,'purpose':'최신 목록 항목의 공식 목록 버튼을 통한 전체 게시판 연결','records':len(found)})
            except Exception as error:group['errors'].append({'error':w.error_name(error),'stage':'부서 전체 목록 연결'})
        alternatives=[]
        for a in soup.select('a[href]'):
            label=a.get_text(' ',strip=True)+' '+a.get('title','')
            link=w.canonical(w.url.urljoin(entry,a['href']),t.host)
            if link and (('귀농귀촌' in label and 'list.' in link) or ('더보기' in label and '/board/list.' in link)) and link not in alternatives:alternatives.append(link)
        for link in alternatives[:2]:
            try:
                more=BeautifulSoup(t.get(link),'html.parser')
                found=parser.parse(more,link);attempts.append({'url':link,'purpose':'공식 관련 게시판 더보기/귀농 탭','records':len(found)})
                for row in found:rows[row['original_id']]=row
            except Exception as error:group['errors'].append({'error':w.error_name(error),'stage':'대체 공식 목록'})
        # Use real form names and option values, not guessed site parameters.
        forms=[]
        for form in soup.select('form'):
            names={x.get('name') for x in form.select('input,select')}
            keyword=next((x for x in ('keyword','searchKeyword','searchKrwd') if x in names),None)
            if not keyword:continue
            action=w.url.urljoin(entry,form.get('action') or entry)
            if w.url.urlsplit(action).hostname!=t.host:continue
            fields={x.get('name'):x.get('value','') for x in form.select('input[name]') if x.get('name') in ('boardUid','boardId','contentUid','menuCd','menuUid','codeUids','searchType','page','startPage','keyword','searchKeyword','searchKrwd')}
            select=form.select_one('select[name="searchType"]')
            if select:
                choice=next((x for x in select.select('option') if '제목' in x.get_text()),None)
                if choice:fields['searchType']=choice.get('value','')
            if any(k in fields for k in ('boardUid','boardId')) or 'board' in w.url.urlsplit(action).path:forms.append((action,fields,keyword,form.get('method','get').lower()))
        for action,fields,key,method in forms[:1]:
            for term in ('농업','지원'):
                query=dict(fields);query[key]=term
                for page in ('page','startPage'):
                    if page in query:query[page]='1'
                parts=w.url.urlsplit(action);params=dict(w.url.parse_qsl(parts.query));params.update(query)
                link=w.url.urlunsplit((parts.scheme,parts.netloc,parts.path,w.url.urlencode(params),''))
                try:searched=BeautifulSoup(t.get(link),'html.parser');found=parser.parse(searched,link)
                except Exception as error:
                    if getattr(error,'code',None)==404 and method=='post':
                        try:
                            searched=BeautifulSoup(t.post_search(action,query),'html.parser');found=parser.parse(searched,action)
                            attempts.append({'url':action,'purpose':'공식 검색폼의 POST 방식 재시험','term':term,'records':len(found)})
                        except Exception as second:
                            group['errors'].append({'error':w.error_name(second),'stage':'공식 검색폼 GET 404 후 POST 재시험'});continue
                    else:
                        group['errors'].append({'error':w.error_name(error),'stage':'공식 검색 요청'});continue
                attempts.append({'url':link,'purpose':'실제 검색폼 제목 검색','term':term,'records':len(found)})
                for row in found:rows[row['original_id']]=row
                # One real next page per search, not unbounded pagination.
                nextlink=next((w.url.urljoin(link,a['href']) for a in searched.select('a[href]') if any(w.url.parse_qs(w.url.urlsplit(a['href']).query).get(p)==['2'] for p in ('page','startPage'))),None)
                if nextlink and w.url.urlsplit(nextlink).hostname==t.host:
                    q=w.url.parse_qs(w.url.urlsplit(nextlink).query)
                    if q.get(key)==[term]:
                        try:
                            for row in parser.parse(BeautifulSoup(t.get(nextlink),'html.parser'),nextlink):rows[row['original_id']]=row
                        except Exception as error:group['errors'].append({'error':w.error_name(error),'stage':'추가 검색 페이지'})
        group['list_count']=len(rows);group['list_rows']=list(rows.values())
        chosen=[]
        for row in rows.values():
            if w.classify(row) not in ('agriculture_support','education'):continue
            posted=row.get('published_at');recent=bool(posted and posted>=(now.date()-w.timedelta(days=90)).isoformat())
            carry=bool(re.search(r'상시|연장|재공고|추가모집|2027',row['title']))
            if recent or carry:chosen.append(row)
        chosen.sort(key=lambda r:r.get('published_at') or '',reverse=True)
        group['candidate_count']=len(chosen);group['state']='연결 성공' if chosen else '관련 공고 미발견'
        for row in chosen[:12]:
            prior=(known or {}).get((kind,row['original_id']))
            fetch=not(prior and prior.get('status')!='failed' and not refresh_details)
            if detail_policy:
                fetch,prior=detail_policy(kind,row,prior,now)
            if not fetch:
                if prior:group['analyses'].append(dict(prior,metadata=dict(row),detail_fetched=False))
                else:group['analyses'].append({'kind':kind,'metadata':dict(row),'status':'pending_detail','facts':{},'unknown_fields':['상세 재확인 대기'],'warnings':[],'detail_fetched':False})
            else:group['analyses'].append(dict(analyse({'kind':kind,'metadata':row},t,now),detail_fetched=True))
    except Exception as error:
        group['state']='접근 제한' if isinstance(error,w.Blocked) or getattr(error,'code',None) in (401,403,429) else '연결 미완료'
        group['reason']=w.error_name(error);group['errors']=[{'error':w.error_name(error)}]
    group['requests']=t.count
    if hasattr(t,'robots_note'):group['robots_note']=t.robots_note
    return group

