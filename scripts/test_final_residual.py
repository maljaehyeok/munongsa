import unittest,json
from unittest.mock import patch
import rag_nlu as n,rag_api as api,rag_dialogue as d

class EducationalAreaTests(unittest.TestCase):
 q='농업경영체 등록을 가상의 농업인이 1ha를 재배한다고 가정한 예로 쉽게 설명해줘.'
 reply='가상의 농업인이 1ha에서 작물을 기른다고 가정해 볼게요. 어떤 작물을 어느 규모로 기르는지 영농 현황을 등록해 관리하는 것이 농업경영체 등록이에요.'
 def value(self,reply=None):return {'intent':'knowledge','facts':[],'hypothetical':True,'reference_previous':False,'uncertain':[],'reply':reply or self.reply,'topic':'농업경영체 등록'}
 def test_user_supplied_area_only(self):
  self.assertTrue(n.concept_request(self.q));self.assertEqual(n.safe_conversation_reply(self.value(),self.q),self.reply)
  self.assertTrue(n.safe_conversation_reply(self.value(self.reply.replace('1ha','1헥타르')),self.q))
 def test_no_invented_numbers_or_eligibility(self):
  for reply in [self.reply.replace('1ha','2ha'),self.reply+' 3년간 관리해요.',self.reply+' 1ha 이상이면 등록 가능해요.',self.reply+' 1%로 지원해요.',self.reply+' 수익은 100만원이에요.']:
   self.assertEqual(n.safe_conversation_reply(self.value(reply),self.q),'')
 def test_official_threshold_not_educational(self):
  for q in ['이 사업의 공식 최소 면적은 1ha인가?','올해 신청하려면 농업경영체 등록 1ha가 필수야?','1ha인 내가 지원받을 수 있어?','가상으로 연 2% 대출이면?']:
   self.assertFalse(n.educational_area_example(q));self.assertFalse(n.concept_request(q))
 def test_no_extra_units_or_implicit_example(self):
  for q in [self.q+' 2026년에?',self.q.replace('1ha','1억원'),self.q.replace('1ha','10000㎡')]:self.assertFalse(n.educational_area_example(q))
  self.assertEqual(n.safe_conversation_reply(self.value('농업인은 1ha를 등록해요.'),self.q),'')
 def test_ordinary_model_numbers_still_blocked(self):
  self.assertEqual(n.safe_conversation_reply(self.value('예를 들어 2년 거치한 뒤 원금을 갚아요.'),'거치기간의 예를 들어줘'),'')
 def test_hypothetical_never_updates_profile_or_second_call(self):
  context={'crop':'마늘','farm_area_ha':0.09,'farm_registered':'no'}
  v=n.validate(self.value(),self.q);self.assertTrue(v['hypothetical']);self.assertEqual(v['facts'],{})
  encoded=d.PREFIX+json.dumps(context,ensure_ascii=False)+d.SEPARATOR+self.q
  with patch.object(api,'load_api_corpus',return_value={'documents':{},'sync_generation':'test','sync_verified':True}),patch.object(n,'interpret',return_value=v) as model:
   out=api.local_pipeline(encoded)
  self.assertEqual(model.call_count,1);self.assertEqual(out['answer'],self.reply)
  for k,v in context.items():self.assertEqual(out['conversation'][k],v)
 def test_no_personal_profile_in_model_concept_payload(self):
  payload=json.loads(n.make_request(self.q,{'farm_registered':'no','farm_region':'익산','crop':'마늘'})['input'])
  self.assertEqual(payload['profile'],{});self.assertEqual(payload['supported_crops'],[])
 def test_existing_basic_concepts_recover_on_worker_failure(self):
  for q in ['농업경영체 등록이 뭐야?','거치기간은 무슨 뜻이야?']:
   with patch.object(api,'load_api_corpus',return_value={'documents':{},'sync_generation':'test','sync_verified':True}),patch.object(n,'interpret',return_value=None) as model:
    out=api.local_pipeline(q)
   self.assertEqual(model.call_count,1);self.assertEqual(out['understanding'],'rules');self.assertEqual(out['status'],'answered')
   self.assertIn(out['conversation']['conversation_topic'],['농업경영체 등록','거치기간'])

if __name__=='__main__':unittest.main()
