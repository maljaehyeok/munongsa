"""Requested counts, search locality and displayed-list references; no network writes."""
import copy,json,unittest
from unittest.mock import patch
from test_consultation50 import Consultation50
import rag_catalogue as cat,rag_dialogue as d

class Consultation51(unittest.TestCase):
 ask=Consultation50.ask
 def setUp(self):
  Consultation50.setUp(self)
  template=self.items[0];self.items[:]=[]
  for i in range(14):
   self.items.append({**copy.deepcopy(template),'id':'NOTICE-start'+str(i),'title':('익산' if i<4 else '전북' if i<9 else '제주')+' 귀농 정착 지원사업 '+str(i),'url':template['url']+str(i)})
 def test_counts_pages_and_shortage(self):
  for count in ('5개','7개','10개','5~10개'):
   out,calls=self.ask('귀농 지원사업 '+count+' 추천해 줘')
   expected=10 if '~' in count else int(count[:-1]);ids=[]
   while True:
    ids.extend(p['id'] for p in out['programs']);self.assertEqual(calls,0)
    if not out.get('catalogue_next'):break
    out,calls=self.ask(cat.PAGE_PREFIX+json.dumps(out['catalogue_next'],ensure_ascii=False),out['conversation'])
   self.assertEqual(len(ids),expected);self.assertEqual(len(set(ids)),expected)
  self.items[:]=self.items[:2]
  out,_=self.ask('귀농 지원사업 10개 추천해 줘');self.assertEqual(out['catalogue_total'],2);self.assertIsNone(out['catalogue_next']);self.assertIn('부족',out['answer'])
 def test_scope_preserves_profile_and_replaces_reference(self):
  profile={'farm_region':'익산','region':'전주','crop':'마늘','farm_registered':'no','planned':True}
  out,_=self.ask('익산에서 농사를 시작하려는데 지원사업 5~10개 추천해 줘',profile)
  self.assertEqual(out['catalogue_total'],9) # local and province published signals, no 제주
  for q,scope,total in [('그럼 전북 전체로 넓혀줘.','전북',9),('전국 지원사업도 찾아줘.','전국',10)]:
   out,calls=self.ask(q,out['conversation']);self.assertEqual(calls,0);self.assertEqual(out['catalogue_total'],total)
   for k,v in profile.items():self.assertEqual(out['conversation'][k],v)
   self.assertEqual(out['conversation']['search_scope'],scope)
  listed=out['conversation'];ids=listed['list_ids']
  compared,_=self.ask('그중에서 내가 신청할 수 있는 건 뭐야?',listed)
  self.assertTrue(all(p['comparison']['decision']['category']!='A' for p in compared['programs']))
  out,calls=self.ask('두 번째 사업은 어떤 서류가 필요해?',compared['conversation']);self.assertEqual(calls,0)
  self.assertEqual([p['id'] for p in out['programs']],[ids[1]])
 def test_scope_page_is_bound_to_current_profile(self):
  out,_=self.ask('귀농 지원사업 7개 찾아줘',{'farm_region':'익산'})
  out,_=self.ask(cat.PAGE_PREFIX+json.dumps(out['catalogue_next']),{**out['conversation'],'farm_registered':'no'})
  self.assertFalse(out['programs']);self.assertIn('변경',out['answer'])

if __name__=='__main__':unittest.main()
