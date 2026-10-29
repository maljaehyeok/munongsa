"""Small read-only official fact check for an explicitly selected release plan."""
import re
from bs4 import BeautifulSoup
from support_runtime import discovery,periods

def normalized(text):return re.sub(r'\s+','',text)

def verify(plans):
    reports=[]
    for plan in plans:
        url=plan['notice_evidence']['url']
        from urllib.parse import urlsplit
        host=urlsplit(url).hostname;t=discovery.Transport({'official_hosts':[host]})
        t.get('https://'+host+'/robots.txt',True);body=t.get(url)
        from support_runtime import boards
        result=boards.extract(body,url);lines=discovery.content_lines(body,result);text=normalized(' '.join(lines))
        assert lines,'official_content_missing'
        if plan.get('metadata'):
            title=normalized(plan['metadata']['title']).replace('첨부파일있음','')
            assert title in normalized(BeautifulSoup(body,'html.parser').get_text(' ',strip=True)),'official_title_changed'
        dates=plan['reference_dates'];parsed=periods.extract(lines,url)
        assert parsed.get('period') and not parsed['warnings'],'period_not_unambiguous'
        for part in ('start','end'):
            assert parsed['period'][part]['date']==dates[part]['date'],'application_dates_changed'
            if dates[part].get('time'):assert parsed['period'][part].get('time')==dates[part]['time'],'deadline_time_changed'
            assert normalized(dates[part]['evidence']['quote']) in text,'approved_date_evidence_changed'
        assert not parsed['closed_signals'],'explicit_early_closure_requires_review'
        if plan.get('exclude_individual_only'):
            assert re.search(r'5인\s*이상',text) and re.search(r'법인|모임',text),'group_requirement_changed'
        else:
            assert all(term in text for term in ('전주시','농업경영체','주소')),'residence_or_registration_changed'
        record={'notice_id':plan['notice_id'],'url':url,'checked_at':boards.m.utc_now(),
            'period':parsed['period'],'limited_correction_check':'selected official notice only; no exhaustive extension search',
            'body_stored':False,'automatic_approval':False,'fact_lines':lines}
        if plan.get('metadata'):
            from support_runtime import enrichment
            class Cached:
                fact_enricher=staticmethod(lambda rows,link:{**enrichment.extra_facts(rows,link),**enrichment.rate_facts(rows,link)})
                def get(self,link):
                    assert link==url,'unexpected_detail_request'
                    return body
            record['analysis']=dict(discovery.analyse({'kind':plan['kind'],'metadata':plan['metadata']},Cached(),periods.as_of()),detail_fetched=True)
            assert record['analysis']['status']!='failed','official_fact_extraction_failed'
        if plan.get('board_url'):
            from urllib.parse import parse_qs
            def identity(link):
                q=parse_qs(urlsplit(link).query)
                return next((q[k][0] for k in ('dataUid','dataSid') if k in q),link)
            listed=boards.CommonList().parse(BeautifulSoup(t.get(plan['board_url']),'html.parser'),plan['board_url'])
            term='면세유' if '면세유' in plan['metadata']['title'] else '기술창업'
            suspects=[row for row in listed if identity(row['original_url'])!=identity(url) and term in row['title']
                and re.search(r'연장|정정|변경|조기.*마감|재공고',row['title'])
                and (not row.get('published_at') or row['published_at']>=plan['metadata']['published_at'])]
            assert not suspects,'possible_correction_notice_requires_review'
            record['limited_correction_check']='selected official detail and one latest official board page; not exhaustive'
        reports.append(record)
    return reports
