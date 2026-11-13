"""Read-only review triage. Classification never grants approval or changes DB."""
import json,re
from collections import Counter
from urllib.parse import urlsplit,parse_qsl,urlencode,urlunsplit
from support_runtime import periods,boards
import support_eligibility as eligibility
import support_monitor as monitor

LABELS={'application':'신청·모집 후보','reference':'시행지침·사업계획','duplicate':'중복 자료','elapsed':'기재 모집기간 경과','unrelated':'지원사업 외 자료','needs_check':'원문·조건 확인 필요'}
KINDS={'age':'연령','residence':'거주지','business_location':'영농·사업장 소재지','farming_experience':'영농 경력','farm_registration':'경영체 등록','crop':'작물','applicant':'신청 주체'}
def identity(value):
    p=urlsplit(value);q=dict(parse_qsl(p.query))
    # Only explicit official post IDs establish duplicates; titles alone do not.
    keys=[k for k in ('dataSid','dataUid','postUid','nttId','sId') if k in q]
    if keys:return p.hostname,p.path,q.get('boardId',q.get('boardUid','')),keys[0],q[keys[0]]
    return p.hostname,p.path,tuple(sorted((k,v) for k,v in q.items() if k not in ('cp','page','startPage','paging','searchType','keyword')))

def facts_for(record):
    hints=json.loads(record.get('hints_json') or '{}')
    return record.get('facts') or hints.get('objective_facts',{}),hints

def classify(record,now=None,duplicates=()):
    now=periods.as_of(now);facts,hints=facts_for(record);title=record['title']
    parsed=record.get('period_assessment') or hints.get('recruitment_assessment') or {}
    # Recalculate stored dates at KST now. Yesterday's open status is not current.
    period=periods.assess(facts,{'period':parsed.get('period')},now,hints.get('daily_checked_at'))
    kind=facts.get('official_document_kind',{}).get('value')
    non_support=bool(re.search(r'자문단|연구\s*참여자|효과검증|선정\s*결과|축제|박람회|설명회|수요조사|입찰|채용|평가위원|농기계|시설장비|농작업\s*편의장비',title))
    # A guideline attached to an explicit dated application letter can still be
    # a notice; the word '지침' alone must not erase its actual invitation.
    is_application=bool(re.search(r'모집|신청|접수|공모',title))
    is_reference=kind=='policy_reference' or bool(re.search(r'지침|시행계획|지원계획|사업계획',title) and not is_application)
    if duplicates:category='duplicate'
    elif non_support:category='unrelated'
    elif is_reference:category='reference'
    elif period['status']=='closed':category='elapsed'
    elif is_application:category='application'
    else:category='needs_check'
    def supported(name):
        f=facts.get(name,{})
        if f.get('value') in (None,'','unknown',[],{}):return False
        if name=='official_condition_candidates' and not any(c.get('presence')=='specified' for c in f['value'].get('conditions',[])):return False
        e=f.get('evidence',{})
        try:monitor.evidence_record(record,e.get('url'),e.get('location'))
        except (ValueError,monitor.MonitorError):return False
        return bool(e.get('url') and e.get('location') and e.get('quote'))
    available={
      '공식 링크':urlsplit(record.get('original_url','')).scheme=='https',
      '모집기간':bool(period.get('period') and (period['period'].get('start') or {}).get('date') and (period['period'].get('end') or {}).get('date')),
      '신청 대상':supported('target_description') or bool(record.get('target') not in (None,'unknown','')),
      '주요 자격조건':any(supported(k) for k in ('eligibility_description','official_eligibility_text','eligibility_clauses','official_condition_candidates')),
      '지원 내용':supported('support_description') or bool(record.get('support') not in (None,'unknown','')),
      '신청 방법':supported('application_method')}
    revision=record.get('structured_conditions',{});conditions=revision.get('payload',{}).get('conditions',[])
    verified=[c for c in conditions if c.get('status')=='verified' and not revision.get('needs_review')]
    unconfirmed=list(dict.fromkeys(KINDS.get(c['kind'],c['kind']) for c in conditions if c not in verified))
    blockers=[k+' 근거 확인 필요' for k,v in available.items() if not v]
    if category in ('reference','duplicate','unrelated','elapsed'):blockers.insert(0,LABELS[category]+' — 현재 신청 가능한 공고로 자동 승인하지 않음')
    blockers+=['공식 원문·최신 변경 확인','공개 이용 범위 확인','기존 절차의 명시적 승인 필요']
    unconfirmed=list(dict.fromkeys(unconfirmed+hints.get('unknown_fields',[])))[:15]
    if not unconfirmed:unconfirmed=['전체 세부 자격·예외·기준일 미검증']
    return {'notice_id':record['notice_id'],'title':title,'institution':record.get('institution','확인 필요'),
      'url':record['original_url'],'category':category,'category_label':LABELS[category],
      'period':period['status'],'period_label':period['reason'],'recorded_period':period.get('period'),'actual_reception_confirmed':False,
      'fact_fields':sorted(facts),'available_information':available,'verified_conditions':verified,'unconfirmed_conditions':unconfirmed,
      'publication':record.get('publication','review'),'approval':'보류 — 분류는 승인이 아님','hold_reasons':blockers,'duplicate_of':list(duplicates),
      'review_priority':'priority' if category=='application' and period['status']=='date_window_open' else 'archive' if category in ('elapsed','unrelated') else 'check',
      'basis':'저장 제목·발췌·검토 기록의 읽기 전용 분류. 공식 원문 재검증이나 자격 확정이 아님.'}

def report(records,now=None,public=(),decisions=None):
    now=periods.as_of(now);seen={identity(p.get('original_url',p.get('url',''))):p.get('notice_id',p.get('id')) for p in public}
    decisions=decisions or {};by_id={r.get('notice_id',r.get('id')):r for r in [*records,*public]}
    output=[]
    for record in records:
        key=identity(record['original_url']);duplicate=[seen[key]] if key in seen and seen[key]!=record['notice_id'] else []
        decision=decisions.get(record['notice_id'],{})
        checked=False
        if (decision.get('content_hash') and decision['content_hash']==record.get('content_hash') and decision.get('url')==record['original_url']
            and decision.get('duplicate_of') in by_id and decision.get('primary_hash')==by_id[decision['duplicate_of']].get('content_hash') and decision.get('evidence_note')):
            duplicate=[decision['duplicate_of']];checked=True
        row=classify(record,now,duplicate)
        if checked:row['duplicate_basis']=decision['evidence_note']
        output.append(row);seen.setdefault(key,record['notice_id'])
    order={'priority':0,'check':1,'archive':2};output.sort(key=lambda r:(order[r['review_priority']],-sum(r['available_information'].values()),r['title']))
    counts=Counter(r['category'] for r in output)
    return {'as_of_kst':now.isoformat(),'read_only':True,'total_pending':len(output),'counts':{LABELS[k]:counts[k] for k in LABELS},
      'application_candidates':counts['application'],'date_window_candidates':sum(r['review_priority']=='priority' for r in output),
      'automatic_approval':False,'candidates':output,'duplicate_note':'동일 공식 게시물 ID만 확정 중복 분류. 제목이 비슷한 다른 지역·회차·수정 공고는 병합하지 않음.'}

def from_database(db,now=None,decisions=None):
    records=[];public=[]
    for row in db.execute('SELECT n.*,s.institution FROM discovered_notices n LEFT JOIN monitor_sources s ON n.source_id=s.source_id ORDER BY first_collected_at,notice_id'):
        r=dict(row)
        if r['publication'] in ('approved','approved_reference'):public.append(r);continue
        r.update(monitor.notice_record(db,r['notice_id']));r['structured_conditions']=eligibility.show(db,r['notice_id']);records.append(r)
    return report(records,now,public,decisions)

def source_status(registry,latest,source_rows):
    rows={r['source_id']:dict(r) for r in source_rows};last={r['source_id']:r for r in latest.get('sources',[])};output=[]
    for source in registry:
        identity=source['source_id'];row=rows.get(identity,{})
        if not source['enabled']:label='의도적 비활성';reason=source.get('disabled_reason','설정상 비활성')
        elif identity in last:
            run=last[identity];label='정상 수집' if run['status']=='completed' else '수집 실패' if run['status']=='failed' else '실행 결과 확인 필요'
            reason='정기 실행 기록: '+str(latest.get('run_id',''))
            if run.get('errors'):reason+=' / '+', '.join(run['errors'])+' — 상세 접근 원인은 별도 로그 확인 필요'
        elif row.get('last_success_at') and not row.get('last_error') and row.get('last_attempt_at')==row['last_success_at']:
            label='정상 수집';reason='신규 출처 최초 수집 성공 기록. 전체 정기 실행 성공을 뜻하지 않음.'
        elif row.get('last_error'):label='수집 실패';reason=str(row['last_error'])
        else:label='신규 등록 후 실행 결과 미확인';reason='성공한 수집 실행 근거 없음'
        output.append({'source_id':identity,'institution':source['institution'],'status':label,'reason':reason,'last_attempt_at':row.get('last_attempt_at'),'last_success_at':row.get('last_success_at')})
    return {'latest_regular_run':latest.get('run_id'),'counts':dict(Counter(r['status'] for r in output)),'sources':output}
