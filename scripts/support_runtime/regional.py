"""Bounded public agricultural board; shares transport, facts and review gates."""
import re
from bs4 import BeautifulSoup
from urllib.parse import parse_qs, urlsplit, urljoin
from . import boards, discovery, enrichment

HOST='www.hongcheon.go.kr'
BOARD='https://'+HOST+'/www/selectBbsNttList.do?bbsNo=140&key=1709'


def rows(raw):
    output={}
    for tr in BeautifulSoup(raw,'html.parser').select('table.p-table tbody tr'):
        for a in tr.select('a[href]'):
            link=urljoin(BOARD,a['href']);p=urlsplit(link);q=parse_qs(p.query)
            if p.scheme!='https' or p.netloc!=HOST or p.path!='/www/selectBbsNttView.do':continue
            if q.get('bbsNo')!=['140'] or len(q.get('nttNo',[]))!=1 or not q['nttNo'][0].isdigit():continue
            # Remove visual "new" icons, not words from the official title.
            for badge in a.select('.p-icon,.skip,.new'):badge.decompose()
            title=boards.clean(a.get_text(' ',strip=True))
            if title.endswith(' 새글'):title=title[:-3].rstrip()
            date=re.search(r'20\d{2}[-.]\d{2}[-.]\d{2}',tr.get_text(' ',strip=True))
            ident=q['nttNo'][0]
            output[ident]={'original_id':'nttNo:'+ident,'title':title,
                'original_url':'https://'+HOST+'/www/selectBbsNttView.do?bbsNo=140&key=1709&nttNo='+ident,
                'published_at':date[0].replace('.','-') if date else None,
                'list_region':'강원 홍천','region_basis':'official_board_location_only'}
    return list(output.values())


def candidate(row):
    title=row['title']
    return boards.classify(row)!='excluded' and bool(re.search(r'농|귀농|한우|축사|종자|고구마|비료',title)) and bool(re.search(r'신청|모집|지원|분양',title))


def fact_candidates(lines,url):
    facts=enrichment.extra_facts(lines,url);required=False
    for line in lines:
        if re.search(r'사업대상자\s*[:：].*다음\s*요건을\s*모두\s*충족',line):required=True;continue
        if required and re.match(r'\s*\d+[.)]\s*',line):required=False
        if required and re.fullmatch(r'[-•\s]*농업경영체에\s*농업경영정보를\s*등록한\s*농업인\s*및\s*농업법인[.\s]*',line):
            facts['farm_registration_required']={'value':True,'evidence':{'url':url,
                'quote':line,'location':'사업대상자의 모두 충족 요건 중 경영체 등록 항목'}}
    return facts


def collect(source,now,known=None,detail_policy=None):
    t=discovery.Transport(source);t.fact_enricher=fact_candidates
    result={'kind':source['kind'],'city':source['city'],'analyses':[],'errors':[],
            'list_count':0,'candidate_count':0,'requests':0,'state':'연결 미완료'}
    try:
        if source['board_url']!=BOARD or source['official_hosts']!=[HOST]:raise ValueError('unexpected_board')
        t.get('https://'+HOST+'/robots.txt',True)
        listed=rows(t.get(BOARD));items=[r for r in listed if candidate(r)]
        result.update(list_count=len(listed),candidate_count=len(items),list_rows=items)
        for row in items[:min(int(source.get('detail_limit',3)),3)]:
            prior=(known or {}).get((source['kind'],row['original_id']))
            fetch,prior=detail_policy(source['kind'],row,prior,now) if detail_policy else (True,prior)
            if not fetch and prior:result['analyses'].append(dict(prior,metadata=row,detail_fetched=False));continue
            entry=discovery.analyse({'kind':source['kind'],'metadata':row},t,now)
            entry.update(detail_fetched=True,automatic_approval=False)
            entry['unknown_fields']=list(dict.fromkeys(entry.get('unknown_fields',[])+[
                '게시 기관 소재지와 거주·영농지 자격 구분 필요','공개 이용 범위','현재 실제 접수 가능 여부']))
            result['analyses'].append(entry)
        result['state']='연결 성공'
    except Exception as error:result['errors'].append({'error':boards.error_name(error)})
    result['requests']=t.count
    return result
