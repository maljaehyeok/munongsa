import unittest,json,copy
import rag_catalogue as cat,rag_dialogue as d,rag_turn
from test_consultation51 import Consultation51

class StateTests(unittest.TestCase):
 ask=Consultation51.ask
 def setUp(self):Consultation51.setUp(self)
 def test_search_slots_are_not_user_facts(self):
  c={'region':'전주','farm_region':'김제','crop':'마늘','farm_registered':'no'}
  out,_=self.ask('익산에서딸기농사를지으려고해요',c)
  for k,v in c.items():self.assertEqual(out['conversation'][k],v)
  self.assertEqual(out['conversation']['search_crop'],'딸기');self.assertEqual(out['conversation']['search_scope'],'익산');self.assertNotIn('cultivating',out['conversation'])
  out,_=self.ask('충남은요?',out['conversation']);self.assertEqual(out['conversation']['search_scope'],'충남');self.assertEqual(out['conversation']['region'],'전주')
  out,_=self.ask('수출 지원사업 찾아줘',c);out,_=self.ask('익산에서 딸기 농사를 준비 중이야',out['conversation'])
  self.assertNotIn('수출',out['conversation']['search_query']);self.assertIn('창업',out['conversation']['search_query'])
 def test_hard_relevance_boundaries(self):
  template=copy.deepcopy(self.items[0]);self.items[:]=[]
  for i,title in enumerate(('딸기 시설하우스 설치 지원사업','마늘 농작물재해보험','대일수출가공식품 사전등록 지원사업','농식품 기업 수출 지원사업','귀농 정착 지원사업','시설 담당자 간담회')):
   self.items.append({**copy.deepcopy(template),'id':'NOTICE-boundary'+str(i),'title':title})
  out,_=self.ask('전국 딸기 시설하우스 설치 지원사업 찾아줘',{'planned':True})
  self.assertEqual([p['name'] for p in out['programs']],['딸기 시설하우스 설치 지원사업'])
  out,_=self.ask('전국 딸기 농사를 준비 중이야',{'planned':True})
  self.assertTrue(all('마늘' not in p['name'] and '수출' not in p['name'] for p in out['programs']))
 def test_cursor_bound_to_interest_and_reference_cleared(self):
  out,_=self.ask('전국 귀농 지원사업 10개 보여줘',{'search_crop':'마늘','planned':True})
  self.assertTrue(out['catalogue_next'])
  page=cat.PAGE_PREFIX+json.dumps(out['catalogue_next'])
  changed={**out['conversation'],'search_crop':'딸기'};check,_=self.ask(page,changed);self.assertFalse(check['programs']);self.assertIn('변경',check['answer'])
  changed,_=self.ask('충남은?',out['conversation']);self.assertFalse(changed['conversation'].get('list_ids'))
  missing,_=self.ask('두 번째 사업은?',changed['conversation']);self.assertFalse(missing['programs'])
 def test_state_validation_and_pesticide_continuation(self):
  out,_=self.ask('선택한 조건으로 지원사업을 찾아주세요.',{'farm_region':'전북 김제시','crop':'마늘'})
  self.assertEqual(out['conversation']['search_scope'],'전북 김제시')
  item={**self.items[0],'title':'김제시 귀농 정착 지원사업'}
  self.assertEqual(cat.scope_relevance(item,{},__import__('datetime').datetime.now(__import__('datetime').timezone.utc),'전북 김제시'),2)
  self.assertEqual(cat.scope_relevance({**item,'title':'익산시 귀농 정착 지원사업'},{},__import__('datetime').datetime.now(__import__('datetime').timezone.utc),'전북 김제시'),-1)
  out,_=self.ask('익산에서 딸기 농사를 준비 중이야',{});out,_=self.ask('충남은?',out['conversation'])
  self.assertIn('창업',out['conversation']['search_query'])
  out,_=self.ask('농업금융 알려줘',out['conversation']);out,_=self.ask('아까 말한 사업으로 돌아가자.',out['conversation'])
  self.assertEqual(out['conversation']['service'],'support');self.assertEqual(out['conversation']['search_scope'],'충남')
  self.assertFalse(rag_turn.valid({'service':'arbitrary'}));self.assertFalse(rag_turn.valid({'tech_topic':True}));self.assertFalse(rag_turn.valid({'tech_resource':'prescription'}))
  out,_=self.ask('딸기 농약 정보 알려줘',{'crop':'마늘'});out,_=self.ask('그런데 토마토는?',out['conversation'])
  self.assertEqual(out['cultivation'],{'crop':'토마토','topic':3,'resource':'pesticide'});self.assertEqual(out['conversation']['crop'],'마늘')

if __name__=='__main__':unittest.main()
