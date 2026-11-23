import json,copy,unittest,sys
from pathlib import Path
from unittest.mock import patch
import test_consultation51 as previous
import rag_profile as p,rag_dialogue as d,rag_crops,rag_api,rag_nlu
import support_http_projection as projection,rag_search

class Practical52(unittest.TestCase):
 ask=previous.Consultation51.ask
 def setUp(self):previous.Consultation51.setUp(self)
 def test_information_is_not_personal_production(self):
  context={'farm_region':'익산','crop':'마늘','planned':True,'farm_registered':'no'}
  for q in ['마늘 재배 방법 알려줘.','토마토 병해충 정보 알려줘.','배추에 사용할 수 있는 농약을 찾고 싶어.','키위 재배 방법 알려줘.']:
   out,calls=self.ask(q,context);self.assertEqual(calls,0);self.assertEqual(out['kind'],'cultivation')
   for key,value in context.items():self.assertEqual(out['conversation'][key],value)
   self.assertNotIn('cultivating',out['conversation'])
  for q in ['마늘을 재배하면 어떻게 돼?','마늘 재배 중인가요?','마늘을 키울 예정이야','만약 마늘을 재배하고 있다면?']:
   facts,_=p.extract(q,d.AREAS,d.CROPS,d.normalized);self.assertNotIn('cultivating',facts,q)
  facts,_=p.extract('저는 마늘을 재배하고 있어요.',d.AREAS,d.CROPS,d.normalized);self.assertTrue(facts['cultivating']);self.assertEqual(facts['crop'],'마늘')
 def test_count_change_more_and_ordinal_keep_intent(self):
  context={'farm_region':'익산','region':'전주','crop':'마늘','farm_registered':'no','planned':True}
  out,_=self.ask('익산에서 농사를 시작하려는데 지원사업 찾아줘.',context)
  out,calls=self.ask('10개 추천해 줘.',out['conversation']);self.assertEqual(calls,0);self.assertEqual(out['catalogue_requested'],10)
  self.assertEqual(out['catalogue_total'],9)
  for k,v in context.items():self.assertEqual(out['conversation'][k],v)
  first={i['id'] for i in out['programs']};out,calls=self.ask('더 보여줘.',out['conversation']);self.assertEqual(calls,0);self.assertFalse(first&{i['id'] for i in out['programs']})
  ids=out['conversation']['list_ids'];out,_=self.ask('그중 두 번째는?',out['conversation']);self.assertEqual([i['id'] for i in out['programs']],[ids[1]])
  out,_=self.ask('7개로 보여줘.',out['conversation']);self.assertEqual(out['catalogue_requested'],7);self.assertEqual(out['catalogue_total'],7)
 def test_topic_crop_directory_and_safe_names(self):
  self.assertEqual(len(rag_crops.catalogue()),67);self.assertEqual(rag_crops.find('키위 재배 방법'),'참다래');self.assertIsNone(rag_crops.find('재배 방법'))
  for crop in rag_crops.catalogue():self.assertEqual(rag_crops.find(crop+' 재배 방법'),crop)
  out,_=self.ask('배추에 사용할 수 있는 농약을 찾고 싶어.',{});self.assertEqual(out['cultivation'],{'crop':'배추','topic':3,'resource':'pesticide'})
  out,_=self.ask('익산에서 마늘 농사를 시작하려는데 재배기술도 알려줘.',{});self.assertTrue(out['conversation']['planned']);self.assertNotIn('cultivating',out['conversation'])
 def test_gpt_cannot_restore_unstated_production(self):
  value={'intent':'knowledge','hypothetical':False,'reference_previous':False,'facts':[{'field':'cultivating','value':'true','quote':'마늘 재배 방법'},{'field':'crop','value':'마늘','quote':'마늘'}],'uncertain':[],'reply':'','topic':''}
  # Validate the same schema used by the worker; quoted topic words are not facts.
  result=rag_nlu.validate(value,'마늘 재배 방법 알려줘.')
  self.assertNotIn('cultivating',result['facts']);self.assertNotIn('crop',result['facts'])

 def test_http_projection_revocation_and_revision(self):
  item={'id':'approved','title':'original','url':'https://official.example/1','publication':'approved','verification_status':'verified'}
  record={'basis':rag_search.basis(item),'fields':{'summary':'approved fact'}}
  source={'records':[record],'withheld_ids':['blocked'],'link_reviews':[]}
  def run(items):
   with patch.object(projection.rag_catalogue,'records',return_value=items),patch.object(projection.Path,'read_text',side_effect=[json.dumps({}),json.dumps(source)]):return projection.payload('details')
  self.assertEqual(len(run([item])['records']),1)
  self.assertEqual(run([])['records'],[])
  self.assertEqual(run([{**item,'title':'changed'}])['records'],[])
  self.assertEqual(run([{**item,'publication':'pending'}])['records'],[])
  self.assertEqual(run([])['withheld_ids'],[])

 def test_explicit_farming_change_without_gpt(self):
  context={'farm_region':'익산','crop':'마늘','planned':True,'farm_registered':'no','list_ids':['NOTICE-stale'],'list_versions':['0'*64],'notice_ids':['NOTICE-stale']}
  out,calls=self.ask('마늘 농사를 이미 짓고 있어.',context)
  self.assertEqual(calls,0);self.assertTrue(out['conversation']['cultivating']);self.assertFalse(out['conversation']['planned'])
  self.assertFalse(out['conversation'].get('list_ids'));self.assertNotIn('farming_years',out['conversation'])
  for q in ('마늘을 재배하고 있나요?','마늘 농사를 이미 짓고 있어?','만약 마늘 농사를 짓고 있다면?','마늘 재배 방법 알려줘.','관심 작물은 마늘','마늘을 재배하고 싶어.'):
   facts,_=p.extract(q,d.AREAS,d.CROPS,d.normalized);self.assertNotIn('cultivating',facts,q);self.assertNotIn('planned',facts,q)

if __name__=='__main__':unittest.main()
