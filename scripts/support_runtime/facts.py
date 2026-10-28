"""Promoted from the working local collector (2026-10-28).
Senior project row/link/date parsing reused with the operator's permission.
No trial data, automatic approval or publication side effects.
"""
"""Extract objective labelled facts, never persist a full article or attachment."""
import re
from datetime import date
from decimal import Decimal
from bs4 import BeautifulSoup

def plain(node):return ' '.join(node.get_text(' ',strip=True).split())

def extract(body,url):
    soup=BeautifulSoup(body,'html.parser');content=soup.select_one('.basicView .conText')
    if not content:raise ValueError('공식 본문 영역 미확인: 전체 페이지로 대체하지 않음')
    # Read in memory only. Copyright indicators govern reproduction separately;
    # absence of a free-use mark does not erase date/amount/entity facts.
    nodes=content.select('p,li,tr') or [content]
    lines=list(dict.fromkeys(plain(n) for n in nodes if plain(n)))
    facts={};uncertain=[]
    def add(name,value,line,anchor=''):
        # Evidence is the necessary short factual span, never the full article.
        pos=line.find(anchor) if anchor else 0
        quote=line[max(0,pos-25):max(0,pos-25)+180]
        proof={'url':url,'location':'CSS .basicView .conText; '+name,'quote':quote}
        if name in facts and facts[name]['value']!=value:
            uncertain.append(name+' 복수 값 충돌');facts[name]={'value':'unknown','evidence':proof};return
        facts[name]={'value':value,'evidence':proof}
    dates=re.compile(r'(?P<y>20\d{2})\s*[.년/-]\s*(?P<m>\d{1,2})\s*[.월/-]\s*(?P<d>\d{1,2})(?:\s*[.일])?')
    for line in lines:
        if re.search(r'(?:신청|접수|제출)\s*(?:기간|기한|마감)',line) or ('까지' in line and re.search(r'신청|접수|제출',line)):
            values=[]
            for hit in dates.finditer(line):
                try:values.append(date(int(hit['y']),int(hit['m']),int(hit['d'])).isoformat())
                except ValueError:uncertain.append('신청 날짜 형식 오류')
            if len(values)==1:add('application_deadline',{'date':values[0],'time':'unknown','timezone':'Asia/Seoul'},line,values[0][:4])
            elif len(values)==2 and values[0]<=values[1]:
                add('application_start',{'date':values[0],'time':'unknown','timezone':'Asia/Seoul'},line)
                add('application_deadline',{'date':values[1],'time':'unknown','timezone':'Asia/Seoul'},line)
        if re.search(r'지원\s*대상|신청\s*대상|모집\s*대상',line):
            label=re.split(r'(?:지원|신청|모집)\s*대상\s*[:：]?',line,maxsplit=1)[-1]
            entities=[t for t in ['영농법인','농업법인','농협','조공법인','김치가공업체','개인 농업인','개인농업인'] if t in label]
            if entities:add('target_entities',entities,line,entities[0])
        if re.search(r'(?:지원|신청)\s*자격|자격\s*요건',line):
            amt=re.search(r'(?:연간\s*(?:원예농산물\s*)?취급액(?:이)?|취급액(?:이)?\s*연간)\s*(\d+(?:\.\d+)?)\s*(억|천만|백만|만)?\s*원\s*(이상|초과|이하|미만)',line)
            if amt:
                factor={None:1,'억':100000000,'천만':10000000,'백만':1000000,'만':10000}[amt[2]]
                add('annual_handling_threshold',{'amount_krw':int(Decimal(amt[1])*factor),'comparison':amt[3],
                    'metric':'annual_horticultural_handling_amount' if '원예농산물' in line else 'annual_handling_amount','basis_year':'unknown'},line,amt[0])
            if re.search(r'법인(?:만)?[.。]?\s*$|법인(?:으로|에)\s*한정|법인만\s*(?:신청|지원|가능)',line) and not re.search(r'개인|예외|포함',line):
                add('legal_entity_required',True,line,'법인')
        ratios={}
        for key,label in [('province','도비'),('county','군비'),('self','자담|자부담')]:
            hit=re.search(r'(?:'+label+r')\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%',line)
            if hit and 0<=Decimal(hit[1])<=100:ratios[key]=str(Decimal(hit[1]))
        if ratios:
            add('funding_percentages',ratios,line)
            if len(ratios)==3 and sum(Decimal(v) for v in ratios.values())!=100:uncertain.append('재원 비율 합계가 100%가 아님')
        if re.search(r'지원\s*내용|사업\s*내용|지원\s*품목',line):
            items=[]
            for pattern,label in [(r'저온\s*시설','저온시설'),(r'저온\s*수송\s*차량','저온 수송차량'),(r'저온\s*저장고','저온저장고'),(r'선별기','선별기'),(r'포장기','포장기')]:
                if re.search(pattern,line):items.append(label)
            if re.search(r'수송\s*차량',line) and '저온 수송차량' not in items:items.append('수송차량')
            if '선별장' in line:items.append('선별장')
            if items:add('support_items',items,line,items[0].replace(' ',''))
    # These categories remain explicitly unknown without an applicable clause.
    missing=[k for k in ['application_start','application_deadline','target_entities','annual_handling_threshold','funding_percentages','support_items'] if k not in facts]
    return {'facts':facts,'unknown_fields':missing+['사업장 소재지 자격','주민등록상 거주지 자격','연령','영농경력','제외 조건','정정·조기마감·연장 여부'],
            'warnings':uncertain,'body_stored':False,'republication_permission':'unknown','automatic_approval':False}
