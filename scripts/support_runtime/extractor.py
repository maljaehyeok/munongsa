"""Promoted from the working local collector (2026-10-28).
Senior project row/link/date parsing reused with the operator's permission.
No trial data, automatic approval or publication side effects.
"""
"""Small multi-notice extension of the existing fact parser; no full body output."""
import re
import html
from datetime import date
from bs4 import BeautifulSoup

def extract(body,url,base_extract):
    soup=BeautifulSoup(body,'html.parser')
    selector=next((s for s in ['.basicView .conText','.board_view .view_cont','.board-view .view-content'] if soup.select_one(s)),None)
    if not selector:raise ValueError('공식 본문 전용 영역 미확인')
    content=soup.select_one(selector)
    nodes=content.select('p,li,tr') or [content]
    nodes=[n for n in nodes if not n.select('p,li,tr')]
    lines=list(dict.fromkeys(' '.join(n.get_text(' ',strip=True).split()) for n in nodes if n.get_text(strip=True)))
    label_only=re.compile(r'^[○ㅇ□\-*•·※\d.()\s]*(?:지원\s*대상|사업\s*대상(?:자)?|신청\s*대상|모집\s*대상|지원\s*내용|사업\s*내용|(?:신청|접수|모집)\s*기간)[)\s:：]*$')
    lines=[line+' '+lines[i+1] if label_only.fullmatch(line) and i+1<len(lines) and not label_only.fullmatch(lines[i+1]) else line for i,line in enumerate(lines)]
    # Normalize only a verified content container for the reused parser.
    wrapped='<div class="basicView"><div class="conText">'+''.join('<p>'+html.escape(line)+'</p>' for line in lines)+'</div></div>'
    result=base_extract(wrapped,url);facts=result['facts']
    def add(key,value,line):
        proof={'url':url,'location':'공식 본문 '+selector+'; '+key,'quote':line[:180]}
        if key in facts and facts[key]['value']!=value:
            result['warnings'].append(key+' 복수 값 충돌');facts[key]={'value':'unknown','evidence':proof}
        elif key not in facts:facts[key]={'value':value,'evidence':proof}
    for line in lines:
        if re.search(r'(?:신청|접수|모집|제출)\s*(?:기간|기한|마감)',line):
            # A short end date may inherit the year ONLY within an explicit range.
            r=re.search(r'(20\d{2})\s*[.년/-]\s*(\d{1,2})\s*[.월/-]\s*(\d{1,2})\s*[.일]?\s*(?:\([^)]{0,8}\))?\s*[~∼～]\s*(?:(20\d{2})\s*[.년/-]\s*)?(\d{1,2})\s*[.월/-]\s*(\d{1,2})',line)
            if r:
                try:
                    start=date(int(r[1]),int(r[2]),int(r[3]));end=date(int(r[4] or r[1]),int(r[5]),int(r[6]))
                    if start>end:raise ValueError()
                    previous=facts.get('application_deadline',{})
                    if (isinstance(previous.get('value'),dict) and previous['value'].get('date')==start.isoformat()
                        and previous.get('evidence',{}).get('quote','') in line):
                        facts.pop('application_deadline')
                    add('application_start',{'date':start.isoformat(),'time':'unknown','timezone':'Asia/Seoul'},line)
                    add('application_deadline',{'date':end.isoformat(),'time':'unknown','timezone':'Asia/Seoul'},line)
                except ValueError:
                    for key in ('application_start','application_deadline'):
                        if facts.get(key,{}).get('evidence',{}).get('quote','') in line:
                            facts.pop(key,None)
                    result['warnings'].append('신청 기간 순서·날짜 추가 확인')
        target=re.match(r'^[○ㅇ□\-*•·※\d.()\s]*(?:지원\s*대상|사업\s*대상(?:자)?|신청\s*대상|모집\s*대상)(?:\s*[:：)]\s*|\s+)(.+)',line)
        if target and len(target[1].strip())>=3:
            text=target[1].strip()[:140]
            if not re.search(r'@|0\d{1,2}[-)]\d{3,4}[-]\d{4}',text):add('target_description',text,line)
            # Extract explicit business-location wording; never use an office address.
            region=re.search(r'(전북특별자치도|전라북도|진안군|부안군|고창군|완주군)\s*(?:내|관내)?\s*소재',target[1])
            if region:add('business_location_text',region[0],line)
        support=re.match(r'^[○ㅇ□\-*•·※\d.()\s]*(?:지원\s*내용|사업\s*내용|지원\s*품목)(?:\s*[:：)]\s*|\s+)(.+)',line)
        if support and len(support[1].strip())>=3:
            text=support[1].strip()[:140]
            if not re.search(r'@|0\d{1,2}[-)]\d{3,4}[-]\d{4}',text):add('support_description',text,line)
    # Preserve the original unknowns unless this specific fact was actually found.
    if 'business_location_text' in facts:
        result['unknown_fields']=[k for k in result['unknown_fields'] if k!='사업장 소재지 자격']
    result['unknown_fields']=[k for k in result['unknown_fields'] if not (k=='application_start' and 'application_start' in facts) and not (k=='application_deadline' and 'application_deadline' in facts)]
    known=lambda k:k in facts and facts[k]['value']!='unknown'
    groups={'period':known('application_deadline'),'target':known('target_entities') or known('target_description'),
            'support':known('support_items') or known('support_description')}
    result['coverage']=groups
    result['status']='success' if all(groups.values()) and not result['warnings'] else 'partial' if facts else 'no_facts'
    result['success_definition']='신청기간·대상·지원내용 3범주 추출; 자격 검증·승인이 아님'
    result['content_selector']=selector
    return result
