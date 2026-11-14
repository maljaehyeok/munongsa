"""Bounded authorized Bizinfo APIs. Credentials and raw responses never persist."""
import json,os,re,time,urllib.parse,urllib.request,xml.etree.ElementTree as ET
import support_bizinfo as biz
PORTAL='https://apis.data.go.kr/1421000/bizinfo/pblancBsnsService'
KEYS={'bizinfo':'BIZINFO_API_KEY','data_go_kr_bizinfo':'DATA_GO_KR_BIZINFO_API_KEY'}

class ApiError(Exception):
    def __init__(self,code):
        self.code=code if code in {'missing_key','invalid_key','invalid_parameters','authentication_failed','permission_denied','quota_exceeded','invalid_request','provider_error','schema_error','size_limit','transport_error'} else 'provider_error'
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

def prepare_request(provider,limit=50,page=1,environ=None):
    if provider not in KEYS or type(limit) is not int or not 1<=limit<=50 or type(page) is not int or not 1<=page<=3:raise ApiError('invalid_parameters')
    key=key_for(provider,environ)
    if provider=='bizinfo':
        params={'crtfcKey':key,'dataType':'json','searchCnt':str(limit),'pageUnit':str(limit),'pageIndex':str(page)};endpoint=biz.ENDPOINT
    else:
        params={'serviceKey':key,'dataType':'json','pageNo':str(page),'numOfRows':str(limit)};endpoint=PORTAL
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
            if root.tag=='response':data={'jsonArray':[{v.tag:''.join(v.itertext()) for v in n} for n in root.findall('./body/items/item')]}
            else:raise ApiError('schema_error')
        else:data=json.loads(text)
        if provider=='data_go_kr_bizinfo' and isinstance(data,dict) and 'response' in data:
            response=data['response'];header=response.get('header',{})
            if str(header.get('resultCode')) not in ('0','00','0000'):raise ApiError('provider_error')
            rows=response.get('body',{}).get('items',[])
            if isinstance(rows,dict):rows=rows.get('item',[])
            if isinstance(rows,dict):rows=[rows]
            data={'jsonArray':rows or []}
        if isinstance(data,dict) and data.get('jsonArray')==[]:return []
        return biz.parse_response(json.dumps(data).encode(),{'allowed_hosts':['www.bizinfo.go.kr','bizinfo.go.kr'],'max_items':limit})
    except ApiError:raise
    except Exception:raise ApiError('schema_error') from None

def fetch(provider,limit=50,page=1,environ=None,transport=None):
    secret=key_for(provider,environ);request=prepare_request(provider,limit,page,environ)
    try:raw,status,_=(transport or biz.probe_transport)(request,timeout=12)
    except Exception:raise ApiError('transport_error') from None
    finally:del request
    if status in (401,403):raise ApiError('authentication_failed')
    if status==429:raise ApiError('quota_exceeded')
    if status!=200:raise ApiError('provider_error')
    records=parse_response(raw,provider,limit)
    return biz.redact(records,secret),{'http_status':status,'authentication':'accepted_response','records':len(records),'requests':1}

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
    meta={k:v for k,v in row.items() if k!='description'}
    return {'kind':kind,'metadata':meta,'facts':facts,'status':'partial','checked_at':biz.monitor.utc_now(),
      'detail_fetched':False,'api_response_fetched':True,'automatic_approval':False,
      'unknown_fields':['세부 자격조건','실제 접수 가능 여부','최신 변경·조기마감 여부']}

def collect(source,environ=None,fetcher=None):
    """One canonical source with two authorized providers; independent failures."""
    group={'kind':source['kind'],'analyses':[],'errors':[],'requests':0,'list_count':0,'api_results':{},'state':'연결 미완료'}
    all_rows=[]
    for provider in source.get('api_providers',['bizinfo']):
        metrics={'requests':0,'records':0,'status':'success'}
        try:
            for page in range(1,min(int(source.get('api_pages',1)),3)+1):
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
    merged,duplicates,conflicts=merge(all_rows);group['list_count']=len(merged);group['duplicate_count']=len(duplicates);group['conflicting_count']=len(conflicts)
    # A disagreeing version is held rather than selecting arbitrary facts.
    if conflicts:group['errors'].append({'stage':'provider_comparison','error':'conflicting_versions_held'})
    group['analyses']=[entry(r,source['kind']) for r in merged if r['original_id'] not in conflicts and agricultural(r)]
    group['candidate_count']=len(group['analyses']);group['state']='부분 실패' if group['errors'] else '연결 성공'
    return group
