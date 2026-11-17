"""Existing authorized API's public article, with exact title and field boundaries."""
import copy,re
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
from . import api_core,boards,periods


def enrich(entry,body,now=None):
    result=copy.deepcopy(entry);url=entry['metadata']['original_url']
    soup=BeautifulSoup(body,'html.parser');node=soup.select_one('.support_project_detail')
    title=node.select_one('h2.title') if node else None
    if title is None or boards.clean(title.get_text(' ',strip=True))!=boards.clean(entry['metadata']['title']):
        return dict(result,status='failed',failure_stage='official_title_match',automatic_approval=False)
    fields={}
    for li in node.select('.view_cont > ul > li'):
        label=li.select_one('.s_title');value=li.select_one('.txt')
        if label and value:fields[boards.clean(label.get_text())]=boards.clean(value.get_text(' ',strip=True))
    facts=api_core.overview(fields.get('사업개요',''),url)
    for label,key in [('사업신청 방법','application_method')]:
        value=fields.get(label)
        if value and len(value)<=900:facts[key]={'value':value,'evidence':{
            'url':url,'quote':value,'location':'공식 상세 본문 '+label+' 항목; 관리자 미승인'}}
    parsed=periods.extract(['신청기간 : '+fields.get('신청기간','')],url)
    period=parsed.get('period') or {}
    for key,part in [('application_start','start'),('application_deadline','end')]:
        if period.get(part):facts[key]={'value':period[part],'evidence':dict(period['evidence'])}
    conflicts=[]
    for key,fact in facts.items():
        old=result['facts'].get(key)
        if old and re.sub(r'\s+','',str(old['value']))!=re.sub(r'\s+','',str(fact['value'])):
            conflicts.append(key);result['facts'].pop(key,None)
        else:result['facts'][key]=fact
    if conflicts:
        # A disagreement is not resolved by arbitrarily preferring either page.
        for key in ('location_requirements','geographic_scope','farm_registration_required','applicant_types'):
            result['facts'].pop(key,None)
        result['fact_conflicts']=conflicts
        result.setdefault('unknown_fields',[]).append('공식 API·본문 내용 충돌: 관리자 확인 필요')
    result.update(detail_fetched=True,automatic_approval=False,period_parse=parsed,
        checked_at=boards.m.utc_now(),recruitment=periods.assess(result['facts'],parsed,now=now))
    if conflicts:result['recruitment']={'status':'unknown','reason':'공식 API·본문 충돌: 판단 보류'}
    original=node.select_one('a#barogagi[href]')
    if original:
        link=urljoin(url,original['href']);p=urlsplit(link)
        if p.scheme=='https' and not p.username and not p.password:
            result['publisher_original_link']=link  # Link only; never fetched without a source policy.
    return result
