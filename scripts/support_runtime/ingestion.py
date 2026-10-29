"""Promoted from the working local collector (2026-10-28).
Senior project row/link/date parsing reused with the operator's permission.
No trial data, automatic approval or publication side effects.
"""
import copy,json,os,re,sqlite3,unicodedata,uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import timedelta
from urllib.parse import urlsplit,parse_qs,parse_qsl
import support_monitor as m
import support_eligibility as eligibility
from . import periods,conditions,discovery,boards,enrichment
SCHEMA="daily-important-facts-v1"
SOURCES={}

def write_items(c,kind,items):
    source=SOURCES[kind]
    payload=m.packed(items).encode()
    def parser(body,_):
        rows=json.loads(body)
        for row in rows:m.canonical_url(row["original_url"],source.get("official_hosts",source.get("allowed_hosts",[])))
        return rows
    return m.collect_source(c,dict(source,method="rss"),fetcher=lambda _:(payload,200,"application/json"),parser=parser,extractor=m.extract_hints,force=True)

def atomic(path,data,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    if os.name!='nt':temp.chmod(mode)
    os.replace(temp,path)


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        f.seek(0,2)
        if f.tell()==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('already_running') from None
        else:
            import fcntl
            try:fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise RuntimeError('already_running') from None
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def identity(link):
    p=urlsplit(link);q=parse_qs(p.query)
    for key in ('dataSid','dataUid','postUid','nttId','articleId'):
        if q.get(key):return p.hostname,q.get('boardId',q.get('boardUid',['']))[0],key,q[key][0]
    return conditions.identity_url(link)


def norm(value):
    if isinstance(value,str):return re.sub(r'\s+','',unicodedata.normalize('NFKC',value))
    if isinstance(value,(list,tuple)):return [norm(v) for v in value]
    if isinstance(value,dict):return {k:norm(v) for k,v in sorted(value.items())}
    return value


def semantic(entry):
    row=entry['metadata'];facts={k:norm(f['value']) for k,f in entry.get('facts',{}).items() if f.get('value') not in (None,'unknown','')}
    if 'support_unit_rates' in facts:
        raw=entry['facts']['support_unit_rates']['value']
        rates=re.findall(r'([가-힣A-Za-z()0-9· ]+?)\s*(\d+)\s*원\s*/\s*[ℓLl]',raw)
        if rates:facts['support_unit_rates']=norm(rates);facts.pop('support_description',None)
    return {'schema':SCHEMA,'title':norm(row['title']),'published_at':row.get('published_at'),'notice_identity':identity(row['original_url']),'facts':facts}


def difference(old,new):
    changed=[k for k in ('title','published_at','notice_identity') if m.packed(old.get(k))!=m.packed(new.get(k))]
    changed+=['facts.'+k for k in old['facts'].keys()&new['facts'].keys() if old['facts'][k]!=new['facts'][k]]
    added=['facts.'+k for k in new['facts'].keys()-old['facts'].keys()]
    return changed,added


def should_fetch(kind,row,prior,now,first=False):
    if kind=='gimje':return False
    if prior is None:return True
    old=prior['metadata']
    if norm(old['title'])!=norm(row['title']) or old.get('published_at')!=row.get('published_at'):return True
    period=periods.assess(prior.get('facts',{}),{'period':prior.get('recruitment',{}).get('period')},now)['status']
    stamp=prior.get('checked_at')
    try:age=now-periods.as_of(stamp)
    except (ValueError,TypeError):return True
    if period in ('date_window_open','confirmed_open','upcoming','ongoing'):return first or periods.as_of(stamp).date()<now.date()
    posted=row.get('published_at') or '1900-01-01'
    return age>=timedelta(days=7 if posted>=(now.date()-timedelta(days=90)).isoformat() else 30)


def collect_source(source,entries,now,first=False):
    known={(e['kind'],e['metadata']['original_id']):e for e in entries};byurl={identity(e['metadata']['original_url']):e for e in entries}
    def policy(kind,row,prior,when):
        prior=prior or byurl.get(identity(row['original_url']))
        if prior:
            row['original_id']=prior['metadata']['original_id'];row['original_url']=prior['metadata']['original_url']
        return should_fetch(kind,row,prior,when,first),prior
    return discovery.search_source(source,now,known,detail_policy=policy,fact_enricher=lambda lines,url:{**enrichment.extra_facts(lines,url),**enrichment.rate_facts(lines,url)})


def central(source,kind):
    group={'kind':kind,'analyses':[],'errors':[],'requests':0,'list_count':0,'state':'연결 미완료'}
    if not source.get('enabled'):return dict(group,state='비활성 유지',skipped=True)
    try:
        source=copy.deepcopy(source);source['max_attempts']=1
        if kind=='mafra':raw,_,_=m.fetch_rss(source);rows=m.parse_rss(raw,source);group['requests']=2
        else:
            import support_bizinfo as biz
            request=biz.prepare_request(source,os.environ);raw,status,_=biz.probe_transport(request,timeout=15);group['requests']=1;del request
            biz.reject_status(status);rows=biz.parse_response(raw,source)
        group['list_count']=len(rows)
        for row in rows:
            if boards.classify(row) not in ('agriculture_support','education'):continue
            text=m.plain(row.get('description',''))[:400];row={k:v for k,v in row.items() if k!='description'}
            facts=enrichment.extra_facts([text],row['original_url'])
            group['analyses'].append({'kind':kind,'metadata':row,'facts':facts,'status':'no_facts' if not facts else 'partial','checked_at':m.utc_now(),'detail_fetched':False})
        group['state']='연결 성공'
    except Exception as error:group['errors']=[{'stage':'공식 RSS/API','error':boards.error_name(error)}]
    return group


def save(c,entry):
    kind=entry['kind'];row=entry['metadata'];source=SOURCES[kind]
    observed_url=row['original_url']
    # Keep the exact official board/document identity. Search controls are not
    # part of that identity and the existing public validator rejects "keyword".
    # Preserve the observed URL privately; never relax credential rejection.
    if boards.canonical(observed_url,urlsplit(observed_url).hostname) is None:
        raise m.MonitorError('unsafe official URL')
    row['original_url']=conditions.identity_url(observed_url)
    for fact in entry.get('facts',{}).values():
        proof=conditions.clean_proof(fact)
        if proof:fact['evidence']=proof
    m.register_sources(c,[source])
    nid=entry.get('id') or 'NOTICE-'+m.digest(source['source_id']+'\n'+row['original_id'])[:24]
    old=c.execute('SELECT * FROM discovered_notices WHERE notice_id=?',(nid,)).fetchone();h=json.loads(old['hints_json']) if old else {}
    before=h.get('daily_semantic');after=semantic(entry)
    changed,added=difference(before,after) if before else ([],[])
    # A parser's missing field is uncertainty, never proof of official deletion.
    if before:
        for key,value in before['facts'].items():after['facts'].setdefault(key,value)
    conflict=None
    if old and changed==['published_at'] and not added:
        conflict={'previous':before['published_at'],'observed':after['published_at'],'status':'needs_review; official change not established'}
        changed=[];after['published_at']=before['published_at'];row['published_at']=before['published_at']
    action='new' if not old else 'changed' if changed else 'enriched' if added else 'metadata_conflict' if conflict and h.get('daily_date_conflict')!=conflict else 'same'
    # Additional private operational facts are not edits to the approved notice.
    # Never extend this exception to dates, targets, conditions or exclusions.
    private_fields={'support_unit_rates','application_method','budget_total','project_year'}
    private_enrichment=bool(old and action=='enriched' and all(k.removeprefix('facts.') in private_fields for k in added))
    if action in ('new','changed','enriched') and not private_enrichment:
        stable={'original_id':row['original_id'],'title':row['title'],'published_at':row.get('published_at'),'original_url':row['original_url'],'important_facts':after['facts']}
        result=write_items(c,kind,[stable])
        if result['status']=='failed':raise RuntimeError('db_registration_failed')
        if not old:
            nid='NOTICE-'+m.digest(source['source_id']+'\n'+row['original_id'])[:24]
        fresh=c.execute('SELECT hints_json FROM discovered_notices WHERE notice_id=?',(nid,)).fetchone();h=json.loads(fresh[0])
    retained_facts={**h.get('objective_facts',{}),**entry.get('facts',{})}
    entry['facts']=retained_facts
    h.update(daily_semantic=after,daily_checked_at=entry.get('checked_at'),objective_facts=retained_facts,
             recruitment_assessment=entry.get('recruitment',{}),unknown_fields=entry.get('unknown_fields',[]))
    h['observed_original_url']=observed_url
    if conflict:h['daily_date_conflict']=conflict
    with c:
        c.execute('UPDATE discovered_notices SET hints_json=?,last_collected_at=? WHERE notice_id=?',(m.packed(h),m.utc_now(),nid))
        if private_enrichment:
            m.record_event(c,nid,'private_facts_enriched','collector','Private additive facts only; approved facts and conditions unchanged',
                {'facts':before['facts']},{'facts':after['facts'],'added_fields':added})
    condition_error=None
    if (action in ('new','changed','enriched') and not private_enrichment) or eligibility.latest(c,nid) is None:
        payload=conditions.payload_for(entry.get('facts',{}),conditions.make_payload(entry.get('facts',{})))
        for condition in payload['conditions']:condition.pop('status',None)
        try:
            eligibility.register(c,nid,payload,'정기 수집기','자동 추출 후보만 등록; 변경·보완 항목 재검토, 자동 승인 없음')
            h.pop('eligibility_extraction_error',None)
        except (m.MonitorError,ValueError,TypeError,KeyError):
            # Keep source facts private even if condition normalization fails.
            condition_error='condition_normalization_failed'
            h['eligibility_extraction_error']=condition_error
        with c:c.execute('UPDATE discovered_notices SET hints_json=? WHERE notice_id=?',(m.packed(h),nid))
    entry['id']=nid
    return {'id':nid,'action':action,'condition_error':condition_error,'changed_fields':changed,'added_fields':added,'date_conflict':conflict,'before':before if action!='same' else None,'after':after if action!='same' else None}

