import json,unittest,tempfile,subprocess,urllib.error
from pathlib import Path
from unittest.mock import patch
import rag_nlu as n,rag_dialogue as d
from test_consultation50 import Consultation50

class Concepts53(unittest.TestCase):
 ask=Consultation50.ask
 def setUp(self):Consultation50.setUp(self)
 def knowledge(self,reply='농업경영체 등록은 영농 현황을 등록하는 절차이고, 사업 선정은 심사를 거쳐 대상자를 뽑는 과정입니다. 등록만으로 선정되는 것은 아닙니다.',topic='농업경영체 등록과 선정'):
  return {'intent':'knowledge','facts':{},'hypothetical':False,'reference_previous':False,'uncertain':[],'reply':reply,'topic':topic}
 def test_general_vs_official_and_profiles(self):
  for q in ('윤작이란?','독립경영이란?','농업경영체 등록은 무엇인가?','보조금과 융자의 차이는?','스마트팜과 일반 시설재배의 차이는?','농업경영체 등록과 청년후계농 선정은 같은가?'):
   self.assertTrue(n.concept_request(q),q)
   out,calls=self.ask(q,{'crop':'마늘','farm_registered':'no','planned':True},self.knowledge())
   self.assertEqual(calls,1);self.assertEqual(out['understanding'],'gpt');self.assertFalse(out['programs']);self.assertEqual(out['conversation']['farm_registered'],'no');self.assertTrue(out['conversation']['planned'])
  for q in ('내가 올해 청년후계농에 선정될 수 있어?','그 사업에서 독립경영 몇 년까지 인정해?','익산 거주자는 신청 가능해?','현재 접수 중이야?','지원 한도는 얼마야?','아까 말한 지원사업에서는 등록이 필수야?','융자의 뜻을 설명하고 마늘 관련 지원사업도 찾아줘.'):
   self.assertFalse(n.concept_request(q,{'conversation_topic':'경영체 등록'}),q)
 def test_followup_purpose_and_previous_notice(self):
  c=self.ask('전체 지원사업')[0]['conversation'];before=c.copy()
  out,_=self.ask('농업경영체 등록은 무엇인가?',c,self.knowledge())
  self.assertEqual(out['conversation']['notice_ids'],before['notice_ids']);self.assertEqual(out['conversation']['list_ids'],before['list_ids'])
  for q in ('그게 왜 필요한데?','쉽게 예를 들어 설명해 줘.'):
   self.assertTrue(n.concept_request(q,out['conversation']))
   out,calls=self.ask(q,out['conversation'],self.knowledge());self.assertEqual(calls,1);self.assertFalse(out['programs'])
  out,calls=self.ask('그럼 농업금융도 알려줘.',out['conversation'])
  self.assertEqual(calls,0);self.assertFalse(out['programs']);self.assertIn('농업금융',out['answer']);self.assertNotIn('conversation_topic',out['conversation']);self.assertEqual(out['conversation']['notice_ids'],before['notice_ids'])
 def test_diagnostic_and_guard(self):
  for e,code in [(subprocess.TimeoutExpired('private',5),'timeout'),(urllib.error.HTTPError('private',429,'private',{},None),'rate_limit'),(n.NluFailure('output_limit'),'output_limit'),(ValueError('schema'),'schema_validation')]:self.assertEqual(n.failure_code(e,'validation'),code)
  for r in ('지원금은 백만원입니다','금리는 연 삼 퍼센트','독립경영 삼년 이내가 대상입니다','신청 가능해요','농약을 희석하세요','https://example.org'):
   self.assertFalse(n.safe_conversation_reply(self.knowledge(r),'보조금과 융자의 차이는?'))
  self.assertTrue(n.safe_conversation_reply(self.knowledge(),'농업경영체 등록은 무엇인가?'))
  payload=n.make_request('윤작이란?',{'crop':'마늘','farm_registered':'no'});h=json.loads(payload['input']);self.assertEqual(h['profile'],{});self.assertEqual(h['supported_crops'],[])
  out,calls=self.ask('저녁 메뉴 추천해 줘.',{'crop':'마늘'});self.assertEqual(calls,0);self.assertFalse(out['programs'])
  out,calls=self.ask('농업경영체 등록은 무엇인가?',{'farm_registered':'no'},None);self.assertEqual(calls,1);self.assertEqual(out['status'],'needs_verification');self.assertFalse(out['programs'])

 def test_api_failure_categories_without_network_or_sensitive_logging(self):
  for data,code in [({'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'}},'output_limit'),({'status':'incomplete'},'incomplete'),({'status':'completed','output':[{'type':'message','content':[{'type':'refusal'}]}]},'refusal')]:
   with patch.object(n.urllib.request,'build_opener') as opener:
    opener.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(data).encode()
    with self.assertRaises(n.NluFailure) as caught:n.request_openai({},'not-a-real-key')
    self.assertEqual(str(caught.exception),code)
  with tempfile.TemporaryDirectory() as directory:
   n.diagnostic(Path(directory),'timeout',n.time.monotonic());data=json.loads((Path(directory)/'diagnostics.json').read_text())
   self.assertEqual(set(data),{'counts','last','at','duration_ms'});self.assertEqual(data['counts'],{'timeout':1})

if __name__=='__main__':unittest.main()
