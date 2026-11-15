"""Bounded official fact observations, separate from approval and eligibility."""
from datetime import datetime,timedelta,timezone
import hashlib,re
from urllib.parse import urlsplit

SCHEMA='munongsa-notice-observation-v1'
KST=timezone(timedelta(hours=9))

def norm(value):return re.sub(r'\s+','',value)
def binding(item):return {k:item.get(k) for k in ('id','title','url','source_id')}
def day(value):
    try:return datetime.strptime(value,'%Y-%m-%d').date().isoformat()
    except (ValueError,TypeError):return None

def state(dates,now):
    today=now.astimezone(KST).date().isoformat();a=dates.get('start',{});b=dates.get('end',{})
    start,end=day(a.get('date')),day(b.get('date'))
    if start and end and start>end:return 'unknown'
    if end and end<today:return 'elapsed'
    if end==today and b.get('time'):
        try:
            if now>=datetime.fromisoformat(end+'T'+b['time']+'+09:00'):return 'elapsed'
        except ValueError:return 'unknown'
    if start and start>today:return 'upcoming'
    if start and end and start<=today<=end:return 'window'
    return 'unknown'

def observe(row,soup,text,now):
    """Read explicit labelled dates only; business year never supplies missing dates."""
    host=urlsplit(row['original_url']).hostname
    result={'schema':SCHEMA,'checked_at':now.isoformat(),'expires_at':(now+timedelta(hours=26)).isoformat(),
            'official_url':row['original_url'],'article_sha':hashlib.sha256(norm(text).encode()).hexdigest(),
            'reference_application_dates':{},'actual_reception':'unconfirmed','method':None,
            'published_at':None,'condition_review':'본문·첨부의 전체 자격은 별도 확인 필요'}
    pattern=None
    if host=='www.rda.go.kr':pattern=r'신청기간\s+(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})'
    elif host in ('www.bizinfo.go.kr','bizinfo.go.kr'):pattern=r'신청기간\s+(\d{4}\.\d{2}\.\d{2})\s*~\s*(\d{4}\.\d{2}\.\d{2})'
    elif host=='global.at.or.kr':pattern=r'접수기간\s+필수\s+(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}:\d{2}))?'
    matches=list(re.finditer(pattern,text)) if pattern else []
    pairs={(m[1].replace('.','-'),m[2].replace('.','-'),m[3] if m.lastindex==3 else None) for m in matches}
    if len(pairs)==1:
        start,end,cutoff=next(iter(pairs))
        if day(start) and day(end) and start<=end:
            result['reference_application_dates']={'start':{'date':start,'time':None,'timezone':'Asia/Seoul'},'end':{'date':end,'time':cutoff,'timezone':'Asia/Seoul'}}
    # Only adjacent labelled application-method text supplies a coarse method.
    method=re.search(r'(?:사업신청\s*방법|신청방법|접수방법|접수처|신청장소)\s*[:：]?\s*(.{0,100})',text)
    if method and not re.search(r'불가|금지|않|제외',method[1]):
        options=[label for token,label in [('방문','방문 신청'),('이메일','이메일 신청'),('전자우편','이메일 신청'),('팩스','팩스 신청'),('온라인','온라인 신청')] if token in method[1]]
        if re.search(r'(?<!전자)우편',method[1]):options.append('우편 신청')
        if options:result['method']=' · '.join(dict.fromkeys(options))+' · 접수처·서식은 공식 원문 확인'
    header=soup.select_one('.bbs_vtop, .view_top, .basicView, .support_project_detail')
    if header:
        date=re.search(r'(?:작성일|등록일자|게시일)\s*[:：]?\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})',header.get_text(' ',strip=True))
        if date:result['published_at']=day(f'{int(date[1]):04}-{int(date[2]):02}-{int(date[3]):02}')
    if not text:result['condition_review']='공식 페이지 연결 확인 · 본문 구조 또는 첨부 조건 확인 필요'
    elif '첨부' in text or '붙임' in text:result['condition_review']='본문의 일부 조건 확인 가능 · 첨부·예외·전체 자격 미검증'
    if state(result['reference_application_dates'],now)=='window':
        if host=='global.at.or.kr' and '로그인이 필요한 서비스' in text:result['actual_reception']='login_unverified'
        elif result['method'] and re.search(r'신청|모집|접수',text):result['actual_reception']='operator_notice'
    result['reception_checked_at']=now.isoformat()
    return result

def attach(feed,checks,now,plans=None):
    result={}
    for item in feed['notices']:
        c=checks.get(item['id'],{});o=c.get('observation')
        if c.get('status')!='checked' or not c.get('title_match') or c.get('url')!=item['url'] or not o:continue
        value={**o,'basis':binding(item)}
        plan=(plans or {}).get(item['id'])
        if plan and plan.get('url')==item['url'] and plan.get('article_sha')==o['article_sha']:
            if all(norm(f) in norm(c.get('article','')) for f in plan.get('fragments',[])):
                dates=plan.get('dates',{})
                if all(not v or day(v.get('date')) for v in (dates.get('start'),dates.get('end'))):
                    value['reference_application_dates']=dates
                    value['period_location']='공식 본문의 운영자 대조 신청기간'
                    if plan.get('standing') is True:value['standing']=True
                    if plan.get('method'):value['method']=plan['method']
                    preparation=plan.get('preparation')
                    if isinstance(preparation,dict) and set(preparation)<= {'method','target_note','documents_note','entry_url','entry_kind','office_note'}:
                        if all(isinstance(v,str) and 0<len(v)<=250 and not re.search(r'[<>\x00-\x1f]',v) for v in preparation.values()):
                            # Entry is the checked official page, not a guessed form URL.
                            if preparation.get('entry_url') in (None,item['url']):value['preparation']=preparation
                    if state(dates,now)=='window' and value.get('method'):
                        value['actual_reception']='operator_notice'
        result[item['id']]=value
    return result

def valid(item,value,now):
    try:
        a=datetime.fromisoformat(value['checked_at']);b=datetime.fromisoformat(value['expires_at'])
        return value.get('schema')==SCHEMA and value.get('basis')==binding(item) and value.get('official_url')==item['url'] and a<=now<b and timedelta(0)<b-a<=timedelta(hours=26)
    except (KeyError,TypeError,ValueError):return False

def project(item,value,now):
    if not value or not valid(item,value,now):return item
    reception=value.get('actual_reception','unconfirmed')
    try:age=(now-datetime.fromisoformat(value['reception_checked_at'])).total_seconds()
    except (ValueError,KeyError,TypeError):age=float('inf')
    if not 0<=age<86400:reception='unconfirmed'
    return {**item,'reference_application_dates':value.get('reference_application_dates') or item.get('reference_application_dates',{}),
            'standing_application':value.get('standing') is True,
            'official_observation_at':value['checked_at'],'actual_reception_state':reception,
            'application_method':value.get('method') or item.get('application_method'),
            'application_preparation':value.get('preparation',{}),
            'published_at':value.get('published_at') or item.get('published_at')}
