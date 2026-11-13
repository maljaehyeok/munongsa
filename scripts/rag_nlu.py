"""Bounded question interpretation only. No notices, answers, tools or credentials in IPC."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime,timezone,timedelta
import urllib.request
import urllib.error

MODEL='gpt-6-luna'
QUEUE=Path('/run/munongsa-nlu')
WAIT=6.5
TIMEOUT=5.5
MAX_OUTPUT=512
DAILY_CALLS=30
MINUTE_CALLS=6
FIELDS=('region','farm_region','age','applicant','group_size','farm_registered','farming_years','planned','cultivating','facility_sqm','crop')
INTENTS=('discover','eligibility','deadline','documents','funding','greeting','thanks','help','context','independent_management','rephrase','correction','next_step','compare','open_notices','other')
SCHEMA={'type':'object','additionalProperties':False,'properties':{
 'intent':{'type':'string','enum':list(INTENTS)},'hypothetical':{'type':'boolean'},'reference_previous':{'type':'boolean'},
 'facts':{'type':'array','maxItems':6,'items':{'type':'object','additionalProperties':False,'properties':{
  'field':{'type':'string','enum':list(FIELDS)},'value':{'type':'string'},'quote':{'type':'string'}},'required':['field','value','quote']}},
 'uncertain':{'type':'array','maxItems':4,'items':{'type':'string','enum':list(FIELDS)}}},
 'required':['intent','hypothetical','reference_previous','facts','uncertain']}
INSTRUCTIONS='''Interpret Korean agricultural-support questions only. Never answer eligibility, grant amounts, deadlines or official conditions. Output the schema only.
Extract ONLY explicit self-reported facts supported by a short exact quote from the current question. Prior profile is context, never new evidence. Do not infer age, business registration, independent farming, residence or parcel eligibility.
Hypothetical registration (등록하면), assumptions, and questions are not actual profile updates. Mark hypothetical=true. Parents' farming assistance never establishes independent management; use independent_management intent.
Use reference_previous only for an explicit follow-up (그 사업, 아까, 그럼). Distinguish residence(region) and farming location(farm_region). Use supported area/crop names only. Registration values yes/no; applicant individual_farmer/group/agricultural_corporation/business; booleans true/false as strings, other numbers as plain numeric strings. Unknown facts are omitted and may be named uncertain. No tools, notice text or external knowledge.'''
INSTRUCTIONS+=' Rephrasing a prior explanation uses rephrase; correcting a misunderstanding uses correction without invented facts; asking what to do next uses next_step; comparing listed businesses uses compare; asking which listed ones are within their dates uses open_notices. Never generate an explanation or business facts. previous_kind and previous_count are routing hints only.'

def packed(value):return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')
def digest(raw):return hashlib.sha256(raw).hexdigest()

def sanitize(question):
    # Conservative minimization: reject documents and redact common identifiers.
    if not isinstance(question,str) or not 1<=len(question)<=600 or question.count('\n')>3:return None
    q=re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[연락처 삭제]',question)
    q=re.sub(r'(?<!\d)(?:\+82[- .]?)?0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}(?!\d)|\b\d{6}[- ]?[1-8]\d{6}\b','[개인정보 삭제]',q)
    q=re.sub(r'\b(?:19|20)\d{2}[-/.년]\s*\d{1,2}[-/.월]\s*\d{1,2}일?','[생년월일 삭제]',q)
    q=re.sub(r'[가-힣0-9]+(?:대로|로|길)\s*\d+(?:-\d+)?(?:\s*\d+동\s*\d+호)?','[상세주소 삭제]',q)
    q=re.sub(r'[가-힣]+(?:읍|면|동|리)\s*\d+(?:-\d+)?(?:번지)?','[상세주소 삭제]',q)
    q=re.sub(r'(?:제?\s*이름은?|성명\s*[:：])\s*[가-힣]{2,5}','[이름 삭제]',q)
    if re.search(r'공고\s*전문|시행지침\s*전문|붙임\s*\d|제\s*\d+\s*조|API[_ -]?KEY|sk-(?:proj-)?[A-Za-z0-9_-]{10,}',q,re.I):return None
    return q.strip()

def make_request(question,context):
    import rag_dialogue
    q=sanitize(question)
    if not q:return None
    profile={k:v for k,v in context.items() if k in FIELDS}
    payload={'model':MODEL,'store':False,'max_output_tokens':MAX_OUTPUT,'reasoning':{'effort':'none'},
      'instructions':INSTRUCTIONS,'input':packed({'question':q,'profile':profile,'has_previous_business':bool(context.get('notice_ids')),'previous_kind':context.get('last_kind'),'previous_count':len(context.get('list_ids',[])),
       'supported_areas':list(rag_dialogue.AREAS),'supported_crops':list(rag_dialogue.CROPS)}).decode(),
      'text':{'format':{'type':'json_schema','name':'munongsa_question','strict':True,'schema':SCHEMA}}}
    raw=packed(payload)
    if len(raw)>12000:return None
    return payload

def validate(value,question):
    import rag_dialogue,rag_profile
    if not isinstance(value,dict) or set(value)!=set(SCHEMA['required']):raise ValueError('schema')
    if value['intent'] not in INTENTS or type(value['hypothetical']) is not bool or type(value['reference_previous']) is not bool:raise ValueError('intent')
    if not isinstance(value['facts'],list) or len(value['facts'])>6 or not isinstance(value['uncertain'],list) or len(value['uncertain'])>4 or any(v not in FIELDS for v in value['uncertain']):raise ValueError('facts')
    facts={}
    for item in value['facts']:
        if not isinstance(item,dict) or set(item)!={'field','value','quote'}:raise ValueError('fact')
        name,v,quote=item['field'],item['value'],item['quote']
        if name not in FIELDS or name in facts or not isinstance(v,str) or len(v)>24 or not isinstance(quote,str) or not 1<=len(quote)<=90 or quote not in question:raise ValueError('unsupported_fact')
        if name in ('region','farm_region'):
            if v not in rag_dialogue.AREAS or v not in rag_dialogue.normalized(quote):raise ValueError('area')
            stated,_=rag_profile.extract(question,rag_dialogue.AREAS,rag_dialogue.CROPS,rag_dialogue.normalized)
            if stated.get(name)!=v:continue  # A place in a business query is not the user's address.
        elif name=='crop':
            if v not in rag_dialogue.CROPS or v not in quote:raise ValueError('crop')
        elif name=='farm_registered':
            if v not in ('yes','no'):raise ValueError('registration')
        elif name in ('planned','cultivating'):
            if v not in ('true','false'):raise ValueError('boolean')
            v=v=='true'
        elif name in ('age','group_size'):
            if not re.fullmatch(r'\d{1,6}',v):raise ValueError('integer')
            v=int(v)
            if v not in [int(n) for n in re.findall(r'(?<!\d)\d+(?!\d)',quote)]:raise ValueError('number_not_grounded')
        elif name in ('farming_years','facility_sqm'):
            if not re.fullmatch(r'\d{1,9}(?:\.\d{1,4})?',v):raise ValueError('number')
            v=float(v)
            if v not in [float(n) for n in re.findall(r'\d+(?:\.\d+)?',quote.replace(',',''))]:raise ValueError('number_not_grounded')
        facts[name]=v
    if not rag_profile.valid_context(facts,rag_dialogue.AREAS):raise ValueError('bounds')
    # Grounding is not trust: rules retain precedence; speculative data cannot persist.
    hypothetical=value['hypothetical'] or rag_profile.hypothetical(question)
    return {'intent':value['intent'],'facts':facts,'hypothetical':hypothetical,
            'reference_previous':value['reference_previous'] and bool(re.search(r'그\s*사업|아까|앞서|그럼|이\s*사업',question)),
            'uncertain':value['uncertain']}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('redirect_denied')

def request_openai(payload,key):
    # Fixed origin/path, no proxies, tool calls, redirects or automatic retries.
    request=urllib.request.Request('https://api.openai.com/v1/responses',data=packed(payload),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(request,timeout=TIMEOUT) as response:
        raw=response.read(32769)
        if len(raw)>32768:raise ValueError('oversize_response')
        data=json.loads(raw)
    messages=[part['text'] for item in data.get('output',[]) if item.get('type')=='message' for part in item.get('content',[]) if part.get('type')=='output_text']
    if data.get('status')!='completed' or len(messages)!=1:raise ValueError('incomplete_response')
    return json.loads(messages[0]),{k:data.get('usage',{}).get(k,0) for k in ('input_tokens','output_tokens')}

def model_available(key):
    request=urllib.request.Request('https://api.openai.com/v1/models/'+MODEL,headers={'Authorization':'Bearer '+key})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(request,timeout=TIMEOUT) as r:return json.loads(r.read(65536)).get('id')==MODEL
    except Exception:return False

def atomic(path,value,mode=0o640):
    tmp=path.with_name('.'+uuid.uuid4().hex)
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    try:
        if hasattr(os,'fchmod'):os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as f:f.write(packed(value))
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)

def read_safe(path,limit=8192,uid=None):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or (uid is not None and st.st_uid!=uid) or st.st_size>limit:raise ValueError('unsafe_file')
        raw=f.read(limit+1)
        if len(raw)>limit:raise ValueError('size')
    return json.loads(raw)

def interpret(question,context,queue=QUEUE):
    """Filesystem IPC works without weakening PrivateNetwork or connect denial."""
    request=make_request(question,context)
    if not request:return None
    qfile=rfile=None
    try:
        status=read_safe(queue/'status.json',1024)
        if status.get('ready') is not True or status.get('model')!=MODEL:return None
        if len(list(queue.glob('q-*.json')))>=4:return None
        identity=uuid.uuid4().hex;qfile=queue/('q-'+identity+'.json');rfile=queue/('r-'+identity+'.json')
        question=json.loads(request['input'])['question']
        body={'id':identity,'question':question,'context':{k:v for k,v in context.items() if k in FIELDS or k=='last_kind'},'previous':bool(context.get('notice_ids')),'previous_count':len(context.get('list_ids',[])),'created':time.time()}
        atomic(qfile,body);deadline=time.monotonic()+WAIT
        while time.monotonic()<deadline:
            if rfile.exists():
                reply=read_safe(rfile)
                if reply.get('id')!=identity or reply.get('question_sha')!=digest(question.encode()):return None
                return validate(reply['result'],question) if reply.get('ok') else None
            time.sleep(.05)
    except (OSError,ValueError,KeyError,TypeError):return None
    finally:
        for path in (qfile,rfile):
            if path:
                try:path.unlink(missing_ok=True)
                except OSError:pass

def route(encoded,understood):
    """Map validated interpretation into the existing engine's bounded context."""
    import rag_dialogue,rag_profile
    question,context=rag_dialogue.decode(encoded)
    rules,error=rag_profile.extract(question,rag_dialogue.AREAS,rag_dialogue.CROPS,rag_dialogue.normalized)
    if error:return encoded,None,None
    facts={**understood['facts'],**rules};actual={**context,**facts} if not (understood['hypothetical'] or rag_profile.hypothetical(question)) else dict(context)
    evaluation={**context,**facts}
    if understood['hypothetical'] and re.search(r'등록\s*(?:하면|한다면|할\s*경우)',question):evaluation['farm_registered']='yes'
    canonical={'deadline':'그 사업 신청 대상 조건과 모집기간 마감은?','documents':'필요한 서류는?','funding':'지원금은?','eligibility':'그럼 신청 조건은?'}
    if understood['reference_previous'] and context.get('notice_ids') and understood['intent'] in canonical and not re.search(r'(?:첫|두|세|[1-3])\s*(?:번째|번)',question):question=canonical[understood['intent']]
    return rag_dialogue.PREFIX+json.dumps(evaluation,ensure_ascii=False)+rag_dialogue.SEPARATOR+question,actual,evaluation

def broker(queue,budget,client_uid):
    for private in ('/var/lib/munongsa/monitor.sqlite3','/etc/munongsa/collector.env','/opt/munongsa-chat-host','/var/lib/munongsa-rag-refresh'):
        try:fd=os.open(private,os.O_RDONLY)
        except (PermissionError,FileNotFoundError):continue
        else:os.close(fd);raise RuntimeError('broker_private_material_accessible')
    key=os.environ.get('OPENAI_API_KEY','');ready=bool(key) and model_available(key)
    queue.mkdir(exist_ok=True);queue.chmod(0o2770)
    atomic(queue/'status.json',{'ready':ready,'model':MODEL})
    recent=[]
    while True:
        for path in sorted(queue.glob('q-*.json'))[:4]:
            identity=path.stem[2:]
            if not re.fullmatch('[a-f0-9]{32}',identity):continue
            reply={'id':identity,'ok':False}
            try:
                item=read_safe(path,8192,client_uid)
                if item['id']!=identity or not 0<=time.time()-item['created']<WAIT:continue
                q=sanitize(item['question'])
                if q!=item['question']:continue
                context=item['context'];context['notice_ids']=['NOTICE-previous'] if item['previous'] else []
                count=item.get('previous_count',0)
                if type(count) is not int or not 0<=count<=3:raise ValueError('previous_count')
                import rag_dialogue
                # Do not trust the queue producer's context either.
                rag_dialogue.decode(rag_dialogue.PREFIX+json.dumps(context,ensure_ascii=False)+rag_dialogue.SEPARATOR+q)
                request=make_request(q,context)
                if request:
                    hints=json.loads(request['input']);hints['previous_count']=count;request['input']=packed(hints).decode()
                reply['question_sha']=digest(q.encode())
                now=time.monotonic();recent=[t for t in recent if now-t<60]
                day=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
                ledger=reserve(budget,recent,day,now) if ready and request else None
                if ledger:
                    value,usage=bounded_call(request,key);validate(value,q)
                    for k,v in usage.items():ledger[k]+=v
                    atomic(budget,ledger,0o600);reply.update(ok=True,result=value)
            except Exception:pass  # No questions, keys, remote bodies or tracebacks in logs.
            finally:
                path.unlink(missing_ok=True)
                if 'question_sha' in reply:atomic(queue/('r-'+identity+'.json'),reply)
        # Only bounded transient files are retained, never question history.
        for path in queue.glob('r-*.json'):
            try:
                if time.time()-path.stat().st_mtime>10:path.unlink()
            except OSError:pass
        for path in queue.glob('.*'):
            try:
                if re.fullmatch(r'\.[a-f0-9]{32}',path.name) and time.time()-path.stat().st_mtime>10:path.unlink()
            except OSError:pass
        time.sleep(.1)

def reserve(budget,recent,day,now):
    ledger=read_safe(budget,4096) if budget.exists() else {'day':day,'calls':0,'input_tokens':0,'output_tokens':0}
    if set(ledger)!={'day','calls','input_tokens','output_tokens'} or any(type(ledger[k]) is not int or ledger[k]<0 for k in ('calls','input_tokens','output_tokens')):raise ValueError('budget_invalid')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',ledger['day']):raise ValueError('budget_day')
    if ledger['day']!=day:ledger={'day':day,'calls':0,'input_tokens':0,'output_tokens':0}
    if ledger['calls']>=DAILY_CALLS or len(recent)>=MINUTE_CALLS:return None
    ledger['calls']+=1;atomic(budget,ledger,0o600);recent.append(now)
    return ledger

def bounded_call(payload,key):
    env={k:v for k,v in os.environ.items() if k in ('SYSTEMROOT','WINDIR','PATH','TEMP','TMP')}
    env.update(OPENAI_API_KEY=key,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--call'],input=packed(payload),capture_output=True,timeout=TIMEOUT,env=env)
    if result.returncode or len(result.stdout)>16384:raise ValueError('nlu_call_failed')
    value=json.loads(result.stdout)
    return value['result'],value['usage']

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--call',action='store_true');parser.add_argument('--queue',type=Path);parser.add_argument('--budget',type=Path);parser.add_argument('--client-uid',type=int)
    args=parser.parse_args()
    if args.call:
        try:
            value,usage=request_openai(json.load(sys.stdin),os.environ['OPENAI_API_KEY']);print(json.dumps({'result':value,'usage':usage}))
        except Exception:raise SystemExit(2)
    elif args.queue and args.budget and args.client_uid is not None:broker(args.queue,args.budget,args.client_uid)
    else:parser.error('broker paths and client uid required')
