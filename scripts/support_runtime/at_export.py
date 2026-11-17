"""Bounded official aT recruitment metadata. No login, attachments or approval.

The home page explicitly publishes recruitment cards. Dates remain list-level
facts, not a verified ability to apply. Full article access is a separate review.
"""
import re
from urllib.parse import urljoin,urlsplit,parse_qs,urlencode
from bs4 import BeautifulSoup
from . import boards,periods

HOST='global.at.or.kr'
BOARD='https://'+HOST+'/'
LIST=BOARD+'front/bizReq/brList.do?_mtype=B&_dept1=3'


def board_rows(raw):
    """Official public list; intentionally excludes staff names and contacts."""
    output={}
    for tr in BeautifulSoup(raw,'html.parser').select('table.boardList tbody tr'):
        category=tr.select_one('td.category');a=tr.select_one('td.subject a[href]')
        if not a or category is None or category.get_text(strip=True)=='수산물':continue
        match=re.fullmatch(r"Javascript:goViewPage\('(\d{1,9})','(\d{1,9})'\);?",a['href'],re.I)
        if not match:continue
        title=boards.clean(a.get_text(' ',strip=True));stamp=tr.select_one('td.date2')
        if not title:continue
        ident='project:'+match[1]+':'+match[2]
        output[ident]={'original_id':ident,'title':title,'published_at':None,
            'original_url':BOARD+'front/bizReq/brView.do?'+urlencode({'proj_id':match[1],'proj_detail_id':match[2]}),
            'list_period':boards.clean(stamp.get_text(' ',strip=True)) if stamp else '',
            'title_may_be_truncated':title.endswith(('...','…'))}
    return list(output.values())

def rows(raw):
    output={}
    for a in BeautifulSoup(raw,'html.parser').select('.slider .item a[href]'):
        u=urljoin(BOARD,a['href']);p=urlsplit(u);q=parse_qs(p.query)
        if p.scheme!='https' or p.netloc!=HOST or p.path!='/front/bizReq/brView.do':continue
        if len(q.get('proj_id',[]))!=1 or not re.fullmatch(r'\d{1,9}',q['proj_id'][0]):continue
        if len(q.get('proj_detail_id',[]))!=1 or not re.fullmatch(r'\d{1,9}',q['proj_detail_id'][0]):continue
        label=a.select_one('.tit .txt');title=a.select_one('.dottxt');stamp=a.select_one('.date')
        # A fisheries-only listing is not an agricultural funding opportunity.
        if label is None or label.get_text(strip=True)=='수산물' or title is None:continue
        name=boards.clean(title.get_text(' ',strip=True));dates=boards.clean(stamp.get_text(' ',strip=True)) if stamp else ''
        if not name:continue
        ident='project:'+q['proj_id'][0]+':'+q['proj_detail_id'][0]
        # Search/UI parameters are not article identity. No synthesized IDs.
        link=BOARD+'front/bizReq/brView.do?'+urlencode({k:q[k][0] for k in ('proj_id','proj_detail_id')})
        output[ident]={'original_id':ident,'title':name,'original_url':link,'published_at':None,
          'list_period':dates,'title_may_be_truncated':name.endswith('...')}
    return list(output.values())

def collect(source,now,known=None,detail_policy=None):
    from .discovery import Transport
    t=Transport(source);group={'kind':source['kind'],'city':source['city'],'analyses':[],
      'errors':[],'list_count':0,'candidate_count':0,'requests':0,'state':'연결 미완료'}
    try:
        if source.get('official_hosts')!=[HOST] or source['board_url']!=BOARD:raise ValueError('unexpected_source')
        policy=t.get(BOARD+'robots.txt',True)
        if re.search(br'<(?:html|script|!doctype)',policy,re.I):raise boards.Blocked('robots policy unreadable')
        listing=source.get('discovery_url',BOARD)
        if listing not in (BOARD,LIST):raise ValueError('unexpected_listing')
        found=(board_rows if listing==LIST else rows)(t.get(listing))
        if listing==LIST:
            seen={r['original_id'] for r in found}
            for page in range(2,min(int(source.get('max_pages',1)),2)+1):
                more=board_rows(t.get(LIST+'&page='+str(page)))
                added=[r for r in more if r['original_id'] not in seen]
                if not added:break
                found.extend(added);seen.update(r['original_id'] for r in added)
        duplicates=set(source.get('existing_official_ids',[]))
        items=[r for r in found if r['original_id'] not in duplicates]
        group.update(list_count=len(found),candidate_count=len(items),
          duplicate_skips=[r['original_id'] for r in found if r['original_id'] in duplicates])
        for row in items[:min(int(source.get('max_items',8)),20 if listing==LIST else 8)]:
            proof={'url':listing,'location':'공식 모집 목록; 상세 공고 검증 아님','quote':row['list_period']}
            facts={'official_document_kind':{'value':'recruitment_listing','evidence':{**proof,'quote':row['title']}}}
            match=re.fullmatch(r'(20\d{2}-\d{2}-\d{2})\s*~\s*(20\d{2}-\d{2}-\d{2})',row['list_period'])
            if match:
                for key,value in [('application_start',match[1]),('application_deadline',match[2])]:
                    facts[key]={'value':{'date':value,'time':'unknown','timezone':'Asia/Seoul'},'evidence':dict(proof)}
            entry={'kind':source['kind'],'metadata':row,'facts':facts,'status':'partial',
              'checked_at':boards.m.utc_now(),'detail_fetched':False,'automatic_approval':False,
              'unknown_fields':['신청 대상·지역 자격·세부 지원·신청 방법·서류·공개 이용 범위 미검증',
                '목록 제목 생략 가능; 최신 상세 원문·변경·실제 접수 가능 여부 별도 확인'],
              'warnings':['공식 모집 목록만 확보. 개별 원문 자동 접근 HTTP 400으로 상세 수집하지 않음.']}
            entry['recruitment']=periods.assess(facts,now=now,checked_at=entry['checked_at'])
            group['analyses'].append(entry)
        group['state']='연결 성공'
    except Exception as error:group['errors'].append({'stage':'official_at_listing','error':boards.error_name(error)})
    group['requests']=t.count
    return group
