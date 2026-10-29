"""Bounded RDA youth-farmer discovery using the site's public search form.

Reuses the permitted senior row/link parsing approach and MUNONGSA transport,
fact extraction and review storage. No approval or publication is performed.
"""
import re
from urllib.parse import urlencode, urljoin
from bs4 import BeautifulSoup
from . import boards, periods, enrichment

BOARD='https://www.rda.go.kr/young/custom.do'


def list_url(page=1):
    # These fields and values are present in the official form and its script.
    return BOARD+'?'+urlencode({'search_ingState':'진행중','search_category':'자금,창업,주거,일자리,농지,네트워크,컨설팅,판로',
        'search_sort':'applEdDt','cp':str(page)})


def rows(body):
    soup=BeautifulSoup(body,'html.parser');found={}
    for tr in soup.select('tbody tr'):
        for a in tr.select('a[href]'):
            hit=re.fullmatch(r"javascript:fn_detailView\('policy',\s*'(\d+)'\);?",a['href'])
            if not hit:continue
            cells=[boards.clean(td.get_text(' ',strip=True)) for td in tr.select('td')]
            stamp=re.search(r'20\d{2}-\d{2}-\d{2}',cells[-1] if cells else '')
            ident=hit[1]
            found[ident]={'original_id':'policy:'+ident,'title':boards.clean(a.get_text(' ',strip=True)),
                'original_url':urljoin(BOARD,'/young/custom/policy/view.do')+'?'+urlencode({'sId':ident,'cp':'1'}),
                # This table's final date is a deadline, NOT a publication date.
                'published_at':None,'list_deadline':stamp[0] if stamp else None,
                'list_region':cells[2] if len(cells)>2 else 'unknown','source_status':'진행중',
                'board_category':'공식 사업 안내','department':'unknown','list_excerpt':''}
    return list(found.values())


def detail_lines(body):
    soup=BeautifulSoup(body,'html.parser');node=soup.select_one('.viewArea .viewBody')
    if node is None:return []
    result=[]
    labels=r'(?:신청기한|신청기간|접수기간|신청자격|신청장소|지원대상|지원조건|지원내용|지원한도|지원기간|제출서류|제외대상|신청방법)\s*[:：]'
    for tr in node.select('tr'):
        th=tr.find('th');td=tr.find('td')
        if th is None or td is None:continue
        label=boards.clean(th.get_text(' ',strip=True));text=boards.clean(td.get_text(' ',strip=True))
        if not text or label=='첨부파일':continue
        if label in ('요약내용','사업요약내용'):
            # Paragraph boundaries and explicit subheadings only; no invented facts.
            text=re.sub(r'\s+(?=\d{1,2}[.)]\s*[가-힣])','\n',text)
            for part in re.split(r'\n|(?='+labels+r')',text):
                if part and not re.fullmatch(labels,part):result.append(part)
        else:result.append(label+' : '+text)
    return list(dict.fromkeys(result))


def collect(source,now,known=None,detail_policy=None):
    from . import discovery
    t=discovery.Transport(source);t.fact_enricher=lambda lines,url:enrichment.extra_facts(lines,url)
    group={'kind':source['kind'],'city':source['city'],'analyses':[],'errors':[],'list_count':0,'candidate_count':0,
        'state':'연결 미완료','attempts':[],'requests':0}
    try:
        t.get('https://'+t.host+'/robots.txt',True)
        body=t.get(list_url());listed=rows(body)
        seen_ids={row['original_id'] for row in listed}
        for page in range(2,min(int(source.get('max_pages',2)),3)+1):
            if len(rows(body))<10:break
            try:body=t.get(list_url(page))
            except Exception as error:
                group['errors'].append({'stage':'additional_list_page','error':boards.error_name(error)});break
            for row in rows(body):
                if row['original_id'] not in seen_ids:listed.append(row);seen_ids.add(row['original_id'])
        items=[row for row in listed if boards.classify(row)!='excluded']
        group.update(list_count=len(listed),list_rows=items,candidate_count=len(items),scope_excluded_count=len(listed)-len(items),state='연결 성공')
        group['attempts'].append({'url':list_url(),'purpose':'공식 진행중·사업 필터 및 마감일 정렬; 게시일 제한 없음'})
        # Prefer Jeonbuk, then other regions. Keep distinct source IDs as such.
        items.sort(key=lambda r:((source['kind'],r['original_id']) in (known or {}),'전북' not in r['list_region'],'청년농' not in r['title'],r['title']))
        unique=[];seen=set()
        for row in items:
            signature=(row['title'],row['list_region'],row['list_deadline'])
            if signature in seen:
                group.setdefault('duplicate_candidates',[]).append(row);continue
            seen.add(signature);unique.append(row)
        for row in unique[:min(int(source.get('detail_limit',4)),8)]:
            prior=(known or {}).get((source['kind'],row['original_id']))
            fetch=True
            if detail_policy:fetch,prior=detail_policy(source['kind'],row,prior,now)
            if not fetch and prior:
                group['analyses'].append(dict(prior,metadata=row,detail_fetched=False));continue
            entry=discovery.analyse({'kind':source['kind'],'metadata':row},t,now)
            entry['detail_fetched']=True
            actual=entry.get('recruitment',{}).get('period') or {}
            deadline=(actual.get('end') or {}).get('date')
            if row['list_deadline'] and deadline and row['list_deadline']!=deadline:
                entry['recruitment'].update(status='unknown',reason='공식 목록과 상세의 신청 마감일 충돌')
            entry['unknown_fields']=list(dict.fromkeys(entry.get('unknown_fields',[])+['최신 정정·조기 종료 전수 확인','공개 재이용 범위']))
            group['analyses'].append(entry)
    except Exception as error:
        group['errors'].append({'error':boards.error_name(error)});group['state']='연결 미완료'
    group['requests']=t.count
    return group
