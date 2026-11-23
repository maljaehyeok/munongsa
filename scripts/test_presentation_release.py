"""Isolated load/limits/cache checks. No network, OpenAI, or operational writes."""
import io,json,sys,tempfile,threading,time,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy/chatbot'))
import chat_wsgi,rag_nlu as nlu

class Presentation(unittest.TestCase):
 def test_independent_budget_caps_and_restart(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'budget.json'
   with patch.object(nlu,'DAILY_CALLS',2):
    self.assertIsNotNone(nlu.reserve(p,[],'2026-11-24',0));self.assertIsNotNone(nlu.reserve(p,[],'2026-11-24',61));self.assertIsNone(nlu.reserve(p,[],'2026-11-24',122))
   for setting,value in [('DAILY_INPUT_TOKENS',1),('DAILY_OUTPUT_TOKENS',1),('DAILY_COST_CENTS',0)]:
    with patch.object(nlu,setting,value):self.assertIsNone(nlu.reserve(p,[],'2026-11-25',183))
   with patch.object(nlu,'MINUTE_CALLS',1):self.assertIsNone(nlu.reserve(p,[1],'2026-11-25',20))

 def test_only_standalone_concepts_cache_without_profiles(self):
  c=nlu.ConceptCache();q='윤작이 뭐야?';v={'intent':'knowledge','facts':[],'hypothetical':False,'reference_previous':False,'reply':'같은 땅에 서로 다른 종류의 작물을 번갈아 기르는 방법이에요.','uncertain':[],'topic':'윤작'}
  c.put(q,v,1);self.assertEqual(c.get(q,2),v);self.assertIsNone(c.get(q,1802))
  self.assertEqual(nlu.validate(c.get(q,2),q)['facts'],{})
  got=c.get(q,2);got['facts'].append({'field':'crop'});self.assertEqual(c.get(q,2)['facts'],[])
  for question in ['그게 왜 필요해?','내가 신청할 수 있어?','올해 금리는?','나는 윤작 중인데 설명해 줘']:
   self.assertIsNone(c.key(question))
  c.put('독립경영이 뭐야?',{**v,'facts':[{'field':'crop','value':'마늘'}]},2);self.assertIsNone(c.get('독립경영이 뭐야?',3))

 def test_isolated_10_20_40_clients_and_recovery(self):
  results=[]
  for total in (10,20,40):
   def pipeline(q):time.sleep(.025);return {'mode':'local','answer':q,'programs':[],'sources':[]}
   app=chat_wsgi.Application(pipeline=pipeline,ready=True)
   def ask(i):
    q=f'사용자 {i}의 독립 상태';raw=json.dumps({'question':q}).encode();seen=[]
    def start(s,h):seen.append((int(s.split()[0]),dict(h)))
    env={'PATH_INFO':'/api/chat','REQUEST_METHOD':'POST','HTTP_HOST':'munongsa.duckdns.org','HTTP_ORIGIN':chat_wsgi.ORIGIN,'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)}
    began=time.perf_counter();body=json.loads(b''.join(app(env,start)));return i,seen[0][0],time.perf_counter()-began,body,seen[0][1]
   started=time.perf_counter()
   with ThreadPoolExecutor(max_workers=total) as pool:responses=list(pool.map(ask,range(total)))
   busy=[r for r in responses if r[1]==503]
   self.assertTrue(all(r[1] in (200,503) for r in responses))
   self.assertTrue(all(r[3]['answer']==f'사용자 {r[0]}의 독립 상태' for r in responses if r[1]==200))
   self.assertTrue(all(r[4]['Retry-After']=='5' for r in busy))
   for r in busy:self.assertEqual(ask(r[0])[1],200)
   results.append({'clients':total,'first_success':total-len(busy),'503':len(busy),'429':sum(r[1]==429 for r in responses),'timeout':0,'recovered':len(busy),'initial_p95_ms':round(sorted(r[2] for r in responses)[int(total*.95)-1]*1000,2),'total_with_recovery_ms':round((time.perf_counter()-started)*1000,2)})
  print('isolated_load='+json.dumps(results))

 def test_broker_cache_reuses_only_valid_wire_reply(self):
  class StopLoop(Exception):pass
  with tempfile.TemporaryDirectory() as d:
   directory=Path(d);queue=directory/'queue';queue.mkdir();budget=directory/'budget.json';q='윤작이 뭐야?'
   value={'intent':'knowledge','facts':[],'hypothetical':False,'reference_previous':False,'reply':'같은 땅에 서로 다른 작물을 번갈아 기르는 방법이에요.','uncertain':[],'topic':'윤작'}
   for i,region in enumerate(['전주','익산']):
    identity=f'{i:032x}';nlu.atomic(queue/('q-'+identity+'.json'),{'id':identity,'question':q,'context':{'region':region},'previous':False,'previous_count':0,'created':time.time()})
   with patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic-not-a-key'}),patch.object(nlu,'model_available',return_value=True),patch.object(nlu,'bounded_call',return_value=(value,{'input_tokens':100,'output_tokens':30})) as call,patch.object(nlu.time,'sleep',side_effect=StopLoop):
    with self.assertRaises(StopLoop):nlu.broker(queue,budget,0)
   self.assertEqual(call.call_count,1);self.assertEqual(json.loads(budget.read_text('utf8'))['calls'],1)
   replies=[json.loads(p.read_text('utf8')) for p in queue.glob('r-*.json')];self.assertEqual(len(replies),2)
   for reply in replies:self.assertEqual(nlu.validate(reply['result'],q)['facts'],{})
   self.assertEqual(json.loads((queue/'diagnostics.json').read_text('utf8'))['counts']['cache_hit'],1)

if __name__=='__main__':unittest.main()
