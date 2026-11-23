"""Condition-state contracts: facts, search snapshots, resets and references."""
import unittest,json
import test_search_reset as fixture
import rag_turn as t,rag_catalogue as cat

class ConditionState(unittest.TestCase):
 ask=fixture.SearchReset.ask
 def setUp(self):fixture.SearchReset.setUp(self)
 def submit(self,c,**values):
  clean={k:v for k,v in c.items() if k not in t.SEARCH_KEYS|t.REFERENCE_KEYS}
  return self.ask('선택한 검색 조건으로 찾아줘',{**clean,'search_mode':'custom','search_action':'replace',**values})[0]
 def test_natural_transition_sequence(self):
  profile={'region':'전주','farm_region':'김제','crop':'벼','cultivating':True,'farm_registered':'no'};c=dict(profile)
  for q,scope,crop,purpose in [('익산 지원사업 찾아줘.','익산',None,''),('딸기 지원사업 찾아줘.','익산','딸기',''),('익산뿐 아니라 전국의 마늘 지원사업 찾아줘.','전국','마늘',''),('이번에는 전북 지역의 토마토 지원사업.','전북','토마토',''),('지역 제한 없이 농업 교육 지원사업.',None,None,'education'),('다시 익산에서 전체 농업 지원사업.','익산',None,'')]:
   out,_=self.ask(q,c);c=out['conversation']
   self.assertEqual(c.get('search_scope'),scope,q);self.assertEqual(cat.discovery_crop(c['search_query'],c),crop,q);self.assertEqual(c.get('search_purpose'),purpose,q)
   for k,v in profile.items():self.assertEqual(c[k],v,q)
 def test_form_is_complete_search_snapshot(self):
  profile={'region':'전주','farm_region':'김제','crop':'마늘','farm_registered':'no'}
  c=self.ask('충남 딸기 시설 지원사업 찾아줘',profile)[0]['conversation']
  for values,scope,crop in [({'search_scope':'전북','search_crop':'미나리'},'전북','미나리'),({'search_crop':'미나리'},None,'미나리'),({'search_crop':'마늘'},None,'마늘'),({'search_scope':'전북'},'전북',None),({},None,None)]:
   out=self.submit(c,**values);c=out['conversation']
   self.assertEqual(c.get('search_scope'),scope);self.assertEqual(cat.discovery_crop(c['search_query'],c),crop)
   self.assertNotIn('시설',c['search_query']);self.assertNotIn('충남',c['search_query'])
   for k,v in profile.items():self.assertEqual(c[k],v)
 def test_current_search_uses_slots_not_old_free_text(self):
  c=self.submit({},search_scope='전북',search_crop='미나리',search_purpose='education')['conversation']
  out,_=self.ask('현재 검색 조건으로 다시 검색',{**c,'search_query':'충남 딸기 수출 지원사업 알려줘'})
  self.assertEqual(out['conversation']['search_query'],'전북 미나리 농업 교육 지원사업 알려줘')
  out,_=self.ask('7개로 보여줘',out['conversation']);self.assertEqual(out['conversation']['search_limit'],7)
  self.assertIn('전북 미나리 농업 교육',out['conversation']['search_query'])
 def test_reset_roles_and_new_conversation(self):
  c=self.ask('전국 농업 교육 지원사업 10개 보여줘',{'farm_region':'김제','crop':'마늘','farm_registered':'no'})[0]['conversation'];c['tech_crop']='딸기'
  out,_=self.ask('검색 조건 초기화',c);empty=out['conversation']
  self.assertEqual(out['reset_scope'],'search');self.assertEqual(empty['crop'],'마늘');self.assertFalse(t.SEARCH_KEYS.intersection(empty)-{'search_mode'})
  self.assertNotIn('notice_ids',empty);self.assertNotIn('tech_crop',empty)
  out,_=self.ask('현재 검색 조건으로 다시 검색',empty);self.assertIsNone(cat.discovery_crop(out['conversation']['search_query'],out['conversation']))
  out,_=self.ask('실제 영농 프로필 초기화',c);self.assertFalse(t.PROFILE_KEYS.intersection(out['conversation']));self.assertEqual(out['conversation']['search_scope'],'전국')
  out,_=self.ask('새 대화',c);self.assertEqual(out['conversation']['crop'],'마늘');self.assertNotIn('search_query',out['conversation']);self.assertNotIn('notice_ids',out['conversation'])
  out,_=self.ask('영농 조건과 상담 모두 초기화',c);self.assertEqual(out['reset_scope'],'all');self.assertFalse(t.PROFILE_KEYS.intersection(out['conversation']))
 def test_service_switch_and_reference_invalidation(self):
  out,_=self.ask('전국 농업 교육 지원사업 10개 보여줘',{});old=out['conversation'];self.assertTrue(old.get('list_ids'))
  for q in ('농업금융 알려줘','딸기 병해충 정보 알려줘'):
   switched=self.ask(q,old)[0]['conversation'];new=self.submit(switched,search_crop='미나리')['conversation']
   self.assertNotIn('notice_ids',new);self.assertNotIn('search_offset',new);self.assertNotIn('tech_crop',new)
   answer,_=self.ask('그중 두 번째 사업은?',new);self.assertFalse(answer['programs'])
 def test_bounded_state_and_reset_confirmation(self):
  for c in ({'search_limit':True},{'search_limit':11},{'search_purpose':'invented'},{'search_action':'approve'}):self.assertFalse(t.valid(c))
  out,_=self.ask('전체 초기화',{'crop':'마늘'});self.assertEqual(out['kind'],'clarify');self.assertEqual(out['conversation']['crop'],'마늘')
 def test_period_and_finance_purpose_survive_current_search(self):
  out,_=self.ask('전국 융자 지원사업 찾아줘',{})
  out,_=self.ask('융자 말고 보조금은?',out['conversation']);self.assertEqual(out['conversation']['search_purpose'],'grant')
  out,_=self.ask('변경 없이 검색',out['conversation']);self.assertIn('보조금',out['conversation']['search_query']);self.assertNotIn('융자',out['conversation']['search_query'])
  out=self.submit({},search_purpose='education',search_period='current')
  out,_=self.ask('현재 검색 조건으로 다시 검색',out['conversation']);self.assertEqual(out['conversation']['search_period'],'current');self.assertIn('신청기간이 남은',out['conversation']['search_query'])

if __name__=='__main__':unittest.main()
