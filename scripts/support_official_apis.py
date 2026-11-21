"""Bounded authorized Bizinfo APIs. Credentials and raw responses never persist."""
import json,multiprocessing,os,re,time,urllib.parse,urllib.request,xml.etree.ElementTree as ET
import support_bizinfo as biz
PORTAL='https://apis.data.go.kr/1421000/bizinfo/pblancBsnsService'
KEYS={'bizinfo':'BIZINFO_API_KEY','data_go_kr_bizinfo':'DATA_GO_KR_BIZINFO_API_KEY'}

class ApiError(Exception):
    def __init__(self,code):
        self.code=code if code in {'missing_key','invalid_key','invalid_parameters','authentication_failed','permission_denied','quota_exceeded','invalid_request','provider_error','schema_error','size_limit','transport_error','pagination_incomplete','pagination_conflict'} else 'provider_error'
        super().__init__(self.code)

def key_for(provider,environ=None):
    value=(os.environ if environ is None else environ).get(KEYS[provider],'').strip().strip('\"\'')
    if not value:raise ApiError('missing_key')
    # Decode once, never unquote_plus: '+' belongs to the key.
    if provider=='data_go_kr_bizinfo' and re.search(r'%[0-9A-Fa-f]{2}',value):value=urllib.parse.unquote(value)
    # Official contract defines an opaque String, not a base64-only alphabet.
    # URL encoding safely handles printable punctuation; controls remain forbidden.
    if not re.fullmatch(r'[!-~]{1,2048}',value):raise ApiError('invalid_key')
    return value

REGION_TAGS=('서울','부산','대구','인천','전남광주','대전','울산','세종','경기','강원','충북','충남','전북','경북','경남','제주')

def rotating_regions(now=None,count=3):
    """Discovery only. The provider combines Jeonnam/Gwangju into one tag."""
    from datetime import datetime,timezone,timedelta
    if type(count) is not int or not 0<=count<=3:raise ApiError('invalid_parameters')
    at=now or datetime.now(timezone.utc)
    if at.tzinfo is None:raise ApiError('invalid_parameters')
    start=at.astimezone(timezone(timedelta(hours=9))).date().toordinal()*3
    return [REGION_TAGS[(start+i)%len(REGION_TAGS)] for i in range(count)]

def discovery_pages(provider,source,now=None):
    pages=list(range(1,min(int(source.get('api_pages',1)),3)+1))
    depth=source.get('portal_rotating_page_limit',0)
    if provider=='data_go_kr_bizinfo' and depth and len(pages)>1:
        from datetime import datetime,timezone,timedelta
        if type(depth) is not int or not 2<=depth<=30:raise ApiError('invalid_parameters')
        day=(now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=9))).date().toordinal()
        # Keep the latest page every day, rotate the second bounded discovery page.
        # An empty/failed discovery page is never proof an existing notice vanished.
        pages=[1,2+day%(depth-1)]
    return pages

def prepare_request(provider,limit=50,page=1,environ=None,region=None):
    if provider not in KEYS or type(limit) is not int or not 1<=limit<=50 or type(page) is not int or not 1<=page<=10000:raise ApiError('invalid_parameters')
    if region is not None and (provider!='bizinfo' or region not in REGION_TAGS):raise ApiError('invalid_parameters')
    key=key_for(provider,environ)
    if provider=='bizinfo':
        params={'crtfcKey':key,'dataType':'json','searchCnt':str(limit),'pageUnit':str(limit),'pageIndex':str(page)};endpoint=biz.ENDPOINT
    else:
        params={'serviceKey':key,'dataType':'json','pageNo':str(page),'numOfRows':str(limit)};endpoint=PORTAL
    if region is not None:params['hashtags']=region
    return urllib.request.Request(endpoint+'?'+urllib.parse.urlencode(params),headers={'User-Agent':biz.monitor.USER_AGENT,'Accept':'application/json'})

def parse_response(raw,provider,limit=50):
    if len(raw)>biz.monitor.MAX_BYTES:raise ApiError('size_limit')
    try:
        text=raw.decode('utf-8-sig')
        if text.lstrip().startswith('<'):
            if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ApiError('schema_error')
            root=ET.fromstring(text);codes=[v.text or '' for v in root.iter() if v.tag in ('returnReasonCode','resultCode')]
            code=next((c for c in codes if c not in ('0','00','0000')),None)
            if code:raise ApiError({'20':'permission_denied','22':'quota_exceeded','30':'authentication_failed','31':'authentication_failed','32':'authentication_failed','10':'invalid_request','11':'invalid_request'}.get(code,'provider_error'))
            if root.tag=='response':
                if root.findtext('./header/resultCode') not in ('0','00','0000') or root.find('body') is None:raise ApiError('schema_error')
                if root.find('./body/items') is None and root.findtext('./body/totalCount')!='0':raise ApiError('schema_error')
                data={'jsonArray':[{v.tag:''.join(v.itertext()) for v in n} for n in root.findall('./body/items/item')]}
            else:raise ApiError('schema_error')
        else:data=json.loads(text)
        if provider=='data_go_kr_bizinfo' and isinstance(data,dict) and 'response' in data:
            response=data['response'];header=response.get('header',{})
            if str(header.get('resultCode')) not in ('0','00','0000'):raise ApiError('provider_error')
            body=response.get('body')
            if not isinstance(body,dict) or ('items' not in body and str(body.get('totalCount'))!='0'):raise ApiError('schema_error')
            rows=body.get('items',[])
            if isinstance(rows,dict):rows=rows.get('item',[])
            if isinstance(rows,dict):rows=[rows]
            data={'jsonArray':rows or []}
        if isinstance(data,dict) and data.get('jsonArray')==[]:return []
        return biz.parse_response(json.dumps(data).encode(),{'allowed_hosts':['www.bizinfo.go.kr','bizinfo.go.kr'],'max_items':limit})
    except ApiError:raise
    except Exception:raise ApiError('schema_error') from None

def fetch(provider,limit=50,page=1,environ=None,transport=None,region=None,timeout=12):
    if not 0<timeout<=12:raise ApiError('invalid_parameters')
    secret=key_for(provider,environ);request=prepare_request(provider,limit,page,environ,region)
    try:raw,status,_=(transport or biz.probe_transport)(request,timeout=timeout)
    except Exception:raise ApiError('transport_error') from None
    finally:del request
    if status in (401,403):raise ApiError('authentication_failed')
    if status==429:raise ApiError('quota_exceeded')
    if status!=200:raise ApiError('provider_error')
    records=parse_response(raw,provider,limit)
    paging={}
    if provider=='data_go_kr_bizinfo':
        try:
            text=raw.decode('utf-8-sig')
            if text.lstrip().startswith('<'):
                body=ET.fromstring(text).find('body');meta={e.tag:e.text for e in body} if body is not None else {}
            else:meta=json.loads(text).get('response',{}).get('body',{})
            for key,label in [('totalCount','total_count'),('pageNo','page_number'),('numOfRows','page_size')]:
                if key in meta:
                    if not re.fullmatch(r'\d{1,10}',str(meta[key])):raise ValueError()
                    paging[label]=int(meta[key])
        except (ValueError,TypeError,AttributeError):raise ApiError('schema_error') from None
    return biz.redact(records,secret),{'http_status':status,'authentication':'accepted_response','records':len(records),'requests':1,**paging}

def _scan_worker(channel,provider,limit,options):
    """Isolate slow network reads so the parent can enforce a wall-clock limit."""
    try:channel.send(('ok',_scan_pages(provider,limit,**options)))
    except ApiError as error:channel.send(('error',error.code))
    except Exception:channel.send(('error','transport_error'))
    finally:channel.close()


def fetch_pages(provider,limit=50,*,wanted_ids=None,max_pages=30,max_seconds=150,fetcher=None):
    if (provider not in KEYS or type(limit) is not int or not 1<=limit<=50
            or type(max_pages) is not int or not 1<=max_pages<=30
            or type(max_seconds) not in (int,float) or not 0<max_seconds<=150):
        raise ApiError('invalid_parameters')
    options={'wanted_ids':wanted_ids,'max_pages':max_pages,'max_seconds':max_seconds}
    # Offline fixtures run in-process; live I/O always has a killable deadline.
    if fetcher is not None:return _scan_pages(provider,limit,fetcher=fetcher,**options)
    started=time.monotonic();context=multiprocessing.get_context('spawn')
    receiver,sender=context.Pipe(duplex=False)
    worker=context.Process(target=_scan_worker,args=(sender,provider,limit,options),daemon=True)
    try:
        worker.start();sender.close()
        remaining=max_seconds-(time.monotonic()-started)
        if remaining<=0 or not receiver.poll(remaining):raise ApiError('pagination_incomplete')
        try:status,result=receiver.recv()
        except EOFError:raise ApiError('transport_error') from None
        if time.monotonic()-started>=max_seconds:raise ApiError('pagination_incomplete')
        if status!='ok':raise ApiError(result)
        return result
    finally:
        sender.close();receiver.close()
        if worker.pid is not None:
            if worker.is_alive():worker.terminate()
            worker.join(timeout=0.1)
            if worker.is_alive():worker.kill();worker.join(timeout=0.1)
            worker.close()


def _scan_pages(provider,limit=50,*,wanted_ids=None,max_pages=30,max_seconds=150,fetcher=None):
    """Complete bounded scan or explicit failure, never a partial absence proof.

    Keep only requested identities when revalidating old metadata. No DB writes,
    credential storage or publication. A short/empty final page proves completion.
    """
    wanted=set(wanted_ids) if wanted_ids is not None else None
    started=time.monotonic();pages=set();seen=set();kept={};total=None
    for page in range(1,max_pages+1):
        if page>1:
            if max_seconds-(time.monotonic()-started)<=2:raise ApiError('pagination_incomplete')
            time.sleep(2)
        if time.monotonic()-started>=max_seconds:raise ApiError('pagination_incomplete')
        remaining=max_seconds-(time.monotonic()-started)
        rows,info=fetcher(provider,limit,page) if fetcher else fetch(provider,limit,page,timeout=min(12,remaining))
        if time.monotonic()-started>=max_seconds:raise ApiError('pagination_incomplete')
        if not isinstance(rows,list) or len(rows)>limit:raise ApiError('schema_error')
        if info.get('page_number',page)!=page:raise ApiError('pagination_conflict')
        size=info.get('page_size',limit)
        if type(size) is not int or not 1<=size<=limit:raise ApiError('schema_error')
        if 'total_count' in info:
            count=info['total_count']
            if type(count) is not int or count<0:raise ApiError('schema_error')
            if total is not None and total!=count:raise ApiError('pagination_conflict')
            total=count
        if not rows:
            if total is not None and len(seen)<total:raise ApiError('pagination_incomplete')
            return list(kept.values())
        ids=[r.get('original_id') for r in rows]
        if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):raise ApiError('pagination_conflict')
        fingerprint=tuple(sorted(ids))
        if fingerprint in pages or not set(ids)-seen:raise ApiError('pagination_incomplete')
        # Overlapping pages mean the index moved while scanning; do not infer absence.
        if seen.intersection(ids):raise ApiError('pagination_conflict')
        pages.add(fingerprint);seen.update(ids)
        for row in rows:
            if wanted is None or row['original_id'] in wanted:kept[row['original_id']]=row
        if total is not None:
            if len(seen)>total:raise ApiError('pagination_conflict')
            if len(seen)==total:return list(kept.values())
            if len(rows)<size:raise ApiError('pagination_incomplete')
        elif len(rows)<size:return list(kept.values())
    raise ApiError('pagination_incomplete')


def agricultural(row):
    text=' '.join([row.get('title',''),row.get('description',''),(row.get('api_fields') or {}).get('target','')])
    return bool(re.search(r'농업|농촌|농가|영농|농식품|농산물|청년농|귀농|스마트팜|스마트농업|축산|원예|농생명',text)) and not re.search(r'채용|선정\s*결과|입찰|평가위원',row.get('title',''))

def merge(records):
    """Both authorized APIs describe the same PBLN identity; never count twice."""
    result={};duplicates=[];conflicts=[]
    for row in records:
        old=result.get(row['original_id'])
        if old is None:result[row['original_id']]=row
        else:
            duplicates.append(row['original_id'])
            if any(old.get(k)!=row.get(k) for k in ('title','original_url','description','api_fields')):conflicts.append(row['original_id'])
    return list(result.values()),duplicates,list(dict.fromkeys(conflicts))

def entry(row,kind='bizinfo'):
    """Only API-supplied facts; generic SME labels never verify farmer eligibility."""
    fields=row.get('api_fields',{});url=row['original_url'];facts={}
    def add(name,value,location):
        if value:facts[name]={'value':value,'evidence':{'url':url,'location':location,'quote':str(value)[:180]}}
    add('support_description',row.get('description',''),'공식 API 사업개요; 세부 자격 검토 전')
    add('api_target_category',fields.get('target'),'공식 API 지원대상 분류; 전체 자격 아님')
    add('application_method',fields.get('application_method'),'공식 API 신청방법')
    hints=biz.extract_hints(row);period=hints.get('application_period')
    if isinstance(period,dict):
        for name,key in [('application_start','start'),('application_deadline','end')]:
            value=period.get(key)
            if value:
                add(name,{'date':value,'time':'unknown','timezone':'Asia/Seoul'},'공식 API 신청기간; 실제 접수 여부 미확인')
                facts[name]['evidence']['quote']=fields.get('application_period','')[:180]
    from support_runtime.api_core import overview
    facts.update(overview(row.get('description',''),url))
    from support_runtime import periods
    period_parse=periods.extract(['신청기간 : '+fields.get('application_period','')],url)
    meta={k:v for k,v in row.items() if k!='description'}
    return {'kind':kind,'metadata':meta,'facts':facts,'status':'partial','checked_at':biz.monitor.utc_now(),
      'period_parse':period_parse,'recruitment':periods.assess(facts,period_parse,checked_at=biz.monitor.utc_now()),
      'detail_fetched':False,'api_response_fetched':True,'automatic_approval':False,
      'unknown_fields':['세부 자격조건','실제 접수 가능 여부','최신 변경·조기마감 여부']}

def collect(source,environ=None,fetcher=None,now=None):
    """One canonical source with two authorized providers; independent failures."""
    group={'kind':source['kind'],'analyses':[],'errors':[],'requests':0,'list_count':0,'api_results':{},'state':'연결 미완료'}
    all_rows=[]
    for provider in source.get('api_providers',['bizinfo']):
        metrics={'requests':0,'records':0,'status':'success'}
        try:
            for page in discovery_pages(provider,source,now):
                if metrics['requests']:time.sleep(2)
                # Missing/invalid keys cause no request. No automatic auth retries.
                key_for(provider,environ);metrics['requests']+=1;group['requests']+=1
                rows,info=(fetcher or fetch)(provider,min(int(source.get('max_items',50)),50),page,environ)
                if info.get('http_status') is not None:metrics['http_status']=info['http_status']
                if info.get('authentication'):metrics['authentication']=info['authentication']
                metrics['records']+=len(rows);all_rows+=rows
                if len(rows)<min(int(source.get('max_items',50)),50):break
        except ApiError as e:
            metrics.update(status='failed',error=e.code);group['errors'].append({'stage':provider,'error':e.code})
        except Exception:
            metrics.update(status='failed',error='transport_error');group['errors'].append({'stage':provider,'error':'transport_error'})
        group['api_results'][provider]=metrics
    regions=rotating_regions(now,min(int(source.get('regional_queries_per_run',0)),3))
    if regions:
        # The last national request and first regional request must also be spaced.
        if group['requests']:time.sleep(2)
        regional,checks=_regional_rows(source,regions,environ,fetcher)
        all_rows.extend(regional);group['regional_queries']=checks
        group['requests']+=sum(c.get('requests',0) for c in checks)
        group['errors'].extend({'stage':'regional_query','error':c['error']} for c in checks if c['status']=='failed')
    merged,duplicates,conflicts=merge(all_rows);group['list_count']=len(merged);group['duplicate_count']=len(duplicates);group['conflicting_count']=len(conflicts)
    # A disagreeing version is held rather than selecting arbitrary facts.
    if conflicts:group['errors'].append({'stage':'provider_comparison','error':'conflicting_versions_held'})
    group['analyses']=[entry(r,source['kind']) for r in merged if r['original_id'] not in conflicts and agricultural(r)]
    group['candidate_count']=len(group['analyses']);group['state']='부분 실패' if group['errors'] else '연결 성공'
    return group


def _regional_rows(source,regions,environ=None,fetcher=None):
    if (not isinstance(regions,list) or not 1<=len(regions)<=3
            or len(set(regions))!=len(regions) or any(r not in REGION_TAGS for r in regions)):
        raise ApiError('invalid_parameters')
    rows=[];checks=[]
    for region in regions:
        try:
            key_for('bizinfo',environ)
            if checks:time.sleep(2)
            batch,info=(fetcher or fetch)('bizinfo',min(int(source.get('max_items',50)),50),1,
                environ=environ,region=region)
            for row in batch:
                row=dict(row,list_region=region,region_basis='official_api_discovery_tag_only')
                rows.append(row)
            checks.append({'region':region,'status':'success','records':len(batch),'requests':1,**info})
        except ApiError as error:
            checks.append({'region':region,'status':'failed','error':error.code,'requests':0 if error.code in ('missing_key','invalid_key') else 1})
            if error.code in ('missing_key','invalid_key','authentication_failed','permission_denied','quota_exceeded'):break
        except Exception:checks.append({'region':region,'status':'failed','error':'transport_error','requests':1})
    return rows,checks


def collect_regions(source,regions,environ=None,fetcher=None):
    """Bounded regional discovery, shared by manual acquisition and daily runs.

    Region tags never establish residence, farm location or eligibility.
    """
    rows,checks=_regional_rows(source,regions,environ,fetcher)
    merged,duplicates,conflicts=merge(rows)
    return {'kind':source['kind'],'analyses':[entry(r,source['kind']) for r in merged
        if r['original_id'] not in conflicts and agricultural(r)],'list_count':len(merged),
        'duplicate_count':len(duplicates),'conflicting_count':len(conflicts),'regional_queries':checks,
        'automatic_approval':False,'state':'연결 성공' if all(c['status']=='success' for c in checks) else '부분 실패'}
