"""Promoted from the working local collector (2026-10-28).
Senior project row/link/date parsing reused with the operator's permission.
No trial data, automatic approval or publication side effects.
"""
import re, html
from bs4 import BeautifulSoup
from . import facts, extractor

def extract_gochang(body,url):
    soup=BeautifulSoup(body,'html.parser');content=soup.select_one('.border_view > .exp')
    if not content:raise ValueError('공식 상세 본문 영역 미확인')
    # Read only in memory; preserve inline spans, separate actual block boundaries.
    for n in content.select('script,style'):n.decompose()
    for n in content.select('br'):n.replace_with('\n')
    for n in content.select('p,div,tr,li'):n.insert_before('\n');n.insert_after('\n')
    lines=[' '.join(x.split()) for x in content.get_text('',strip=False).splitlines() if x.strip()]
    import html
    normalized=[re.sub(r'^[❍◎●]\s*','○ ',x) for x in lines]
    wrapped='<div class="basicView"><div class="conText">'+''.join('<p>'+html.escape(x)+'</p>' for x in normalized)+'</div></div>'
    result=extractor.extract(wrapped,url,facts.extract)
    for f in result['facts'].values():
        f['evidence']['location']='공식 상세 CSS .border_view > .exp; '+f['evidence']['location'].split(';')[-1].strip()
        for original,norm in zip(lines,normalized):
            if f['evidence']['quote'] in norm:f['evidence']['quote']=original[:180];break
    result['unknown_fields']=list(dict.fromkeys(result['unknown_fields']+['첨부파일 세부 요건','공고 읍면과 신청자 지역 관계']))
    title=soup.select_one('.border_view > .subject')
    if title:result['official_title']=' '.join(title.get_text(' ',strip=True).split())
    result['content_selector']='.border_view > .exp';return result

