"""Promoted from the working local collector (2026-10-28).
Senior project row/link/date parsing reused with the operator's permission.
No trial data, automatic approval or publication side effects.
"""
"""Evidence-based application periods. No publication or eligibility approval."""
import re
from datetime import date,datetime,time,timedelta,timezone
KST=timezone(timedelta(hours=9))
STATES=('confirmed_open','date_window_open','upcoming','unknown','closed','ongoing')
DATE=r'(?:(20\d{2})\s*[.년/\-]\s*)?(\d{1,2})\s*[.월/\-]\s*(\d{1,2})\s*[.일]?'
RANGE=re.compile(DATE+r'\s*(?:\([^)]{0,10}\))?[,\s]*(?:(\d{1,2})\s*[:시]\s*(\d{1,2})?\s*분?)?\s*(?:~|∼|～|부터|–|—)\s*'+DATE+r'\s*(?:\([^)]{0,10}\))?[,\s]*(?:(\d{1,2})\s*[:시]\s*(\d{1,2})?\s*분?)?')

def as_of(value=None):
    if value is None:return datetime.now(KST)
    if isinstance(value,str):
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):return datetime.combine(date.fromisoformat(value),time(12),KST)
        value=datetime.fromisoformat(value)
    if value.tzinfo is None:raise ValueError('판정 시각에 시간대 필요')
    return value.astimezone(KST)

def value(day,hour=None,minute=None):
    return {'date':day.isoformat(),'time':f'{int(hour):02d}:{int(minute or 0):02d}' if hour is not None else 'unknown','timezone':'Asia/Seoul'}


def notice_context(title,source_url):
    """Descriptive notice context, never a fallback application year."""
    result={};proof={'url':source_url,'location':'공식 공고 제목','quote':title[:220]}
    year=re.search(r'(20\d{2})\s*년',title)
    round_=re.search(r'제?\s*(\d{1,2})\s*차',title)
    if year:result['project_year']={'value':int(year[1]),'evidence':dict(proof)}
    if round_:result['recruitment_round']={'value':int(round_[1]),'evidence':dict(proof)}
    flags=[name for name,pattern in [('extension',r'연장'),('correction',r'정정|변경'),('reannouncement',r'재공고'),('additional',r'추가\s*(?:모집|신청|접수)')] if re.search(pattern,title)]
    if flags:result['notice_update_flags']={'value':flags,'evidence':dict(proof)}
    return result


def extract_attachment(path,source_url):
    """Explicitly selected local official PDF/HWPX only; no downloads or storage.

    The existing bounded attachment pilot handles size/page/archive limits.
    Legacy HWP is left unsupported instead of being reported as an empty success.
    """
    from pathlib import Path
    try:from support_attachment_pilot import extract_document
    except ImportError:raise ValueError('선택한 첨부파일 판독 모듈 미설치; 본문 근거와 구분해 추가 확인 필요') from None
    if Path(path).suffix.lower() not in ('.pdf','.hwpx'):raise ValueError('PDF/HWPX만 지원; HWP 변환 근거 별도 필요')
    pages=extract_document(Path(path));lines=[]
    for page in pages:
        lines.extend(page['text'].splitlines())
    result=extract(lines,source_url)
    for proof in ([result['period']['evidence']] if result.get('period') else []):
        proof['location']='선택한 공식 첨부파일; '+next((p['location'] for p in pages if proof['quote'] in ' '.join(p['text'].split())),'정확한 페이지 추가 확인 필요')
    result['attachment_processed']=True;result['body_stored']=False
    return result

def extract(lines,source_url):
    hits=[];deadlines=[];warnings=[];open_signals=[];closed_signals=[];ongoing=[];unresolved=[]
    # Join a label and a value separated by editor paragraph formatting.
    combined=[]
    for i,line in enumerate(lines):
        if re.search(r'(?:신청|접수|모집).*[:：]\s*$',line) and i+1<len(lines):
            tail=[]
            for nextline in lines[i+1:i+6]:
                if re.match(r'\s*(?:서류|면접|선정|발표|계약|사업기간|지원대상|신청자격)',nextline):break
                tail.append(nextline)
                if RANGE.search(' '.join([line]+tail)):break
            if tail:combined.append(' '.join([line]+tail))
    lines=list(lines)+combined
    for line in lines:
        line=' '.join(line.split())
        if not line:continue
        original=line
        # Only an explicit abbreviated year with an apostrophe is expanded.
        # A project year or publication year is never an application-year default.
        line=re.sub(r"['’‘](\d{2})(?=\s*[.년/\-])",lambda m:'20'+m[1],line)
        if re.search(r'(?:현재|지금)\s*(?:신청|접수|모집)\s*중',line):open_signals.append(line[:180])
        if re.search(r'(?:신청|접수|모집)\s*(?:이\s*)?(?:마감되었습니다|종료되었습니다|조기\s*마감|마감\s*완료)',line):closed_signals.append(line[:180])
        relevant=bool(re.search(r'(?:신\s*청|접\s*수|모\s*집)\s*(?:공고\s*(?:및|·)\s*접수|기\s*간|기\s*한|마\s*감|일\s*시|공고\s*및\s*접수|[:：])',line))
        if not relevant:continue
        # YY.MM.DD is a complete abbreviated date, not a missing-year MM.DD.
        # Restrict to 20..39 (which cannot be a month), and keep the source quote.
        line=re.sub(r'(?<!\d)(2\d|3\d)(?=\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2}(?!\d))',lambda m:'20'+m[1],line)
        if re.search(r'(?:상시|연중)\s*(?:신청|접수|모집)|(?:신청|접수|모집)\s*(?:기간\s*[:：]?\s*)?(?:상시|연중)',line):
            ongoing.append({'url':source_url,'location':'공식 상시 모집 문구','quote':original[:220]})
        if re.search(r'예산\s*소진|선착순|별도\s*공고|추후\s*공지',line) and ongoing:
            warnings.append('상시 모집의 종료 조건·예산 잔여 여부 확인 필요')
        for match in RANGE.finditer(line):
            sy,sm,sd,sh,smin,ey,em,ed,eh,emin=match.groups()
            if not sy:
                unresolved.append({'url':source_url,'quote':original[:220],'reason':'신청 연도 생략; 게시일·사업연도로 확정하지 않음'})
                continue
            try:
                start=date(int(sy),int(sm),int(sd));end=date(int(ey or sy),int(em),int(ed))
                if end<start:raise ValueError()
                if sh is not None:time(int(sh),int(smin or 0))
                if eh is not None:time(int(eh),int(emin or 0))
                hits.append({'start':value(start,sh,smin),'end':value(end,eh,emin),'evidence':{'url':source_url,'location':'공식 신청·접수·모집 기간 문구','quote':original[max(0,match.start()-30):match.end()+30][:220]},
                    'extension':bool(re.search(r'연장|변경\s*후|정정\s*후',line))})
            except ValueError:warnings.append('기간 날짜·시각 또는 순서 오류')
        if not RANGE.search(line):
            dated=list(re.finditer(DATE,line))
            explicit=[d for d in dated if d[1]]
            if len(explicit)==1:
                d=explicit[0]
                clock=re.match(r'\s*(?:\([^)]{0,10}\))?\s*(?:(\d{1,2})\s*[:시]\s*(\d{1,2})?\s*분?)?',line[d.end():])
                hour,minute=clock.groups()
                try:
                    if hour is not None:time(int(hour),int(minute or 0))
                    deadlines.append({'end':value(date(int(d[1]),int(d[2]),int(d[3])),hour,minute),'evidence':{'url':source_url,'location':'공식 신청기한 문구; 시작일 미확인','quote':original[:220]}})
                except ValueError:warnings.append('마감 날짜 오류')
            elif dated and not explicit:
                unresolved.append({'url':source_url,'quote':original[:220],'reason':'신청 연도 생략; 추가 근거 필요'})
    # Never choose the longest deadline from distinct schemes or contradictory lines.
    distinct={}
    for h in sorted(hits,key=lambda h:len(h['evidence']['quote']),reverse=True):distinct[str((h['start'],h['end']))]=h
    extension=[h for h in distinct.values() if h['extension']]
    chosen=extension[0] if len(extension)==1 else next(iter(distinct.values())) if len(distinct)==1 else None
    if len(distinct)>1 and not chosen:warnings.append('복수 신청기간: 사업별·회차별 구분 필요')
    if not chosen and not distinct and len({str(d['end']) for d in deadlines})==1:chosen=deadlines[0]
    if len({str(d['end']) for d in deadlines})>1:warnings.append('복수 신청 마감일: 정정·회차 확인 필요')
    if chosen and any(d['end']['date']!=chosen['end']['date'] or (d['end']['time']!='unknown' and chosen['end']['time']!='unknown' and d['end']['time']!=chosen['end']['time']) for d in deadlines):
        warnings.append('신청기간과 별도 마감일 충돌');chosen=None
    return {'period':chosen,'warnings':list(dict.fromkeys(warnings)),'open_signals':open_signals,'closed_signals':closed_signals,
        'ongoing_evidence':ongoing,'unresolved_dates':unresolved,
        'extension_checked':'explicit_notice_line' if extension else 'not_exhaustive','verification_status':'unverified'}

def assess(facts,parsed=None,now=None,checked_at=None):
    now=as_of(now);parsed=parsed or {};period=parsed.get('period')
    if not period and parsed.get('warnings'):
        return {'status':'unknown','as_of':now.isoformat(),'period':None,'checked_at':checked_at,'reason':'신청기간 충돌 또는 날짜 오류; 원문 추가 확인 필요',
            'eligibility_separate':True,'verification_status':'unverified','changes_checked':'제한 조회 범위'}
    if not period:
        def known(k):
            v=facts.get(k,{}).get('value');return v if isinstance(v,dict) and v.get('date') else None
        a,z=known('application_start'),known('application_deadline')
        if a or z:period={'start':a,'end':z,'evidence':facts.get('application_deadline',facts.get('application_start',{})).get('evidence',{})}
    result={'status':'unknown','as_of':now.isoformat(),'period':period,'checked_at':checked_at,'reason':'신청기간 정보 부족',
        'eligibility_separate':True,'changes_checked':'제한 조회 범위; 정정·연장·조기마감 전수 확인 아님','verification_status':'unverified'}
    if parsed.get('closed_signals'):
        result.update(status='closed',reason='공식 본문에 접수 종료·조기 마감 명시',status_evidence=parsed['closed_signals']);return result
    if not period:
        if parsed.get('ongoing_evidence'):
            result.update(status='ongoing',reason='공식 상시 모집 문구 확인; 예산·종료·변경 여부 별도 확인 필요',status_evidence=parsed['ongoing_evidence'])
        return result
    a,z=period.get('start'),period.get('end')
    try:
        start=date.fromisoformat(a['date']) if a else None;end=date.fromisoformat(z['date']) if z else None
        if start and end and start>end:raise ValueError()
        current=now.date()
        if end and current>end:result.update(status='closed',reason='기재 신청기한 경과; 연장·재공고 추가 확인 필요')
        elif end and current==end and z.get('time') in (None,'unknown'):result.update(status='unknown',reason='마감일 당일이나 종료 시각 미확인; 접수처 확인 필요')
        elif end and current==end and now.time().replace(tzinfo=None)>=time.fromisoformat(z['time']):result.update(status='closed',reason='기재 접수 종료 시각 경과')
        elif start and current<start:result.update(status='upcoming',reason='기재 신청 시작일 전')
        elif start and end:
            if current==start and a.get('time') not in (None,'unknown') and now.time().replace(tzinfo=None)<time.fromisoformat(a['time']):result.update(status='upcoming',reason='기재 접수 시작 시각 전')
            elif current==end and z.get('time') not in (None,'unknown') and now.time().replace(tzinfo=None)>time.fromisoformat(z['time']):result.update(status='closed',reason='기재 접수 종료 시각 경과')
            else:
                result.update(status='date_window_open',reason='공식 기재 신청기간 내; 별도 조기마감·변경 확인 필요')
                # A stale or generic headline alone never establishes current acceptance.
                if parsed.get('current_status_verified') and parsed.get('open_signals') and checked_at and as_of(checked_at).date()==current:
                    result.update(status='confirmed_open',reason='오늘 확인한 공식 본문에 현재 접수 중 명시',status_evidence=parsed['open_signals'])
        elif end:result['reason']='기재 마감일 전이나 신청 시작일 미확인'
        elif start:result['reason']='신청 시작일만 확인, 종료 조건 미확인'
    except (ValueError,TypeError,KeyError):result.update(status='unknown',reason='기간 형식 또는 날짜 충돌')
    return result
