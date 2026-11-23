"""Focused search-intent transitions. Fictional fixtures; no collection or approval."""
import unittest,copy
import test_consultation51 as fixture
import rag_turn,rag_catalogue as cat

class SearchReset(unittest.TestCase):
 ask=fixture.Consultation51.ask
 def setUp(self):
  fixture.Consultation51.setUp(self)
  template=copy.deepcopy(self.items[0]);self.items[:]=[]
  for i,title in enumerate(('익산 농업 교육 지원사업','김제 마늘 농작물재해보험','충남 시설하우스 설치 지원사업','전주 농업 교육 지원사업','군산 농업 교육 지원사업')):
   self.items.append({**copy.deepcopy(template),'id':'NOTICE-reset'+str(i),'title':title,'url':template['url']+str(i)})
 def test_reported_three_turns(self):
  out,_=self.ask('익산 딸기 지원사업 있어?',{})
  self.assertFalse(out['programs']);self.assertEqual(out['conversation']['search_crop'],'딸기')
  out,_=self.ask('익산 지역 지원사업!',out['conversation'])
  self.assertTrue(out['programs']);self.assertEqual(out['conversation']['search_mode'],'regional')
  self.assertNotIn('search_crop',out['conversation']);self.assertNotIn('딸기',out['conversation']['search_query'])
  out,_=self.ask('선택한 조건으로 검색',out['conversation'])
  self.assertEqual(out['kind'],'clarify');self.assertIn('선택된 지역·작물이 없',out['answer'])
  self.assertFalse(out['programs']);self.assertNotIn('search_scope',out['conversation']);self.assertNotIn('search_query',out['conversation'])
 def test_profile_is_used_only_on_selection(self):
  profile={'region':'전주','farm_region':'김제','crop':'마늘','cultivating':True,'farm_registered':'no'}
  out,_=self.ask('익산 딸기 시설 지원사업 찾아줘',profile)
  out,_=self.ask('익산 지역 지원사업!',out['conversation'])
  self.assertTrue(any('교육' in p['name'] for p in out['programs']))
  self.assertIsNone(cat.discovery_crop(out['conversation']['search_query'],out['conversation']))
  out,_=self.ask('입력한 영농 조건으로 찾아줘',out['conversation'])
  c=out['conversation'];self.assertEqual(c['search_scope'],'김제');self.assertEqual(c['search_crop'],'마늘')
  self.assertNotIn('시설',c['search_query']);self.assertNotIn('익산',c['search_query'])
  for k,v in profile.items():self.assertEqual(c[k],v)
 def test_short_scope_keeps_crop_but_explicit_regional_search_resets(self):
  out,_=self.ask('익산 딸기 시설 지원사업 찾아줘',{})
  out,_=self.ask('충남은?',out['conversation'])
  self.assertEqual(out['conversation']['search_crop'],'딸기');self.assertIn('시설',out['conversation']['search_query'])
  out,_=self.ask('충남 지역 지원사업 알려줘',out['conversation'])
  self.assertNotIn('search_crop',out['conversation']);self.assertNotIn('시설',out['conversation']['search_query'])
 def test_other_places_crops_and_explicit_crop_release(self):
  for area,crop in (('전주','토마토'),('군산','참다래')):
   out,_=self.ask(area+' '+crop+' 지원사업 있어?',{})
   out,_=self.ask(area+' 지역 지원사업 찾아줘',out['conversation'])
   self.assertTrue(out['programs']);self.assertNotIn('search_crop',out['conversation'])
   self.assertTrue(all(area in p['name'] for p in out['programs']))
  out,_=self.ask('익산 딸기 지원사업 찾아줘',{})
  out,_=self.ask('작물 제한 없이 지원사업 찾아줘',out['conversation'])
  self.assertEqual(out['conversation']['search_scope'],'익산');self.assertTrue(out['programs'])
 def test_empty_search_provides_actions_without_relaxing_facts(self):
  self.items[:]=[]
  c={'region':'전주','farm_region':'김제','crop':'마늘','farm_registered':'no'}
  first,_=self.ask('익산 딸기 지원사업 있어?',c)
  second,_=self.ask('익산 딸기 지원사업 있어?',first['conversation'])
  self.assertNotEqual(first['answer'],second['answer']);self.assertIn('같은 탐색 조건',second['answer'])
  self.assertEqual(len(second['suggestions']),3);self.assertFalse(second['programs'])
  third,_=self.ask('더 찾아줘',second['conversation']);self.assertEqual(len(third['suggestions']),3)
  for k,v in c.items():self.assertEqual(third['conversation'][k],v)
  first,_=self.ask('군산 지역 지원사업 찾아줘',c)
  second,_=self.ask('군산 지역 지원사업 찾아줘',first['conversation'])
  self.assertIn('같은 탐색 조건',second['answer']);self.assertFalse(second['programs'])
 def test_finance_and_technology_do_not_restore_stale_search_crop(self):
  c={'farm_region':'김제','crop':'마늘','farm_registered':'no'}
  out,_=self.ask('전주 토마토 지원사업 찾아줘',c)
  out,_=self.ask('농업금융 알려줘',out['conversation']);self.assertEqual(out['conversation']['service'],'finance')
  out,_=self.ask('선택한 조건으로 검색',out['conversation']);self.assertEqual(out['conversation']['service'],'support');self.assertEqual(out['conversation']['search_crop'],'마늘')
  out,_=self.ask('전주 지역 지원사업!',out['conversation']);self.assertNotIn('search_crop',out['conversation'])
  out,_=self.ask('딸기 병해충 정보 알려줘',out['conversation']);self.assertEqual(out['cultivation']['crop'],'딸기')
  out,_=self.ask('군산 지역 지원사업!',out['conversation']);self.assertTrue(out['programs']);self.assertNotIn('search_crop',out['conversation'])
  out,_=self.ask('선택한 조건으로 검색',out['conversation']);self.assertEqual(out['conversation']['search_crop'],'마늘')
  for k,v in c.items():self.assertEqual(out['conversation'][k],v)
 def test_bounded_state(self):
  self.assertFalse(rag_turn.valid({'search_mode':'approve'}));self.assertFalse(rag_turn.valid({'empty_search':'arbitrary'}))

if __name__=='__main__':unittest.main()
