"""Bounded agricultural conversation regressions. No network or operating writes."""
import copy,json,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import rag_api as api,rag_catalogue as cat,rag_dialogue as d,rag_nlu as nlu

class Consultation50(unittest.TestCase):
 def setUp(self):
  now=datetime.now(timezone.utc);self.items=[]
  for i in range(3):
   self.items.append({'id':'NOTICE-guide'+str(i),'title':['가상 유기농업자재 지원사업','가상 면세유 가격안정 지원사업','가상 시설현대화 지원사업'][i],'institution':'공식 기관','url':'https://www.rda.go.kr/young/custom/policy/view.do?sId='+str(i),'publication':'official_guidance','verification_status':'basics_only','recommendation_eligible':False,'eligibility_complete':False,'freshness':'current','last_checked_at':now.isoformat(),'guidance_expires_at':(now+timedelta(days=1)).isoformat(),'rights':{'public_display':'allowed'}})
  self.feed={'schema_version':'munongsa-support-public-v1','notices':self.items};self.corpus={'documents':{},'guidance_feed':self.feed,'sync_generation':'test','sync_verified':True}
 def ask(self,q,c=None,nlu_result=None):
  with patch.object(api,'load_api_corpus',return_value=self.corpus),patch.object(nlu,'interpret',return_value=nlu_result) as model,patch.dict('os.environ',{},clear=True):
   out=api.local_pipeline(d.PREFIX+json.dumps(c or {},ensure_ascii=False)+d.SEPARATOR+q)
  return out,model.call_count
 def listed(self):return self.ask('전체 지원사업',{'farm_region':'김제','farm_registered':'no'})[0]['conversation']
 def test_metadata_second_then_followup_uses_selected_not_whole_list(self):
  c=self.listed();self.assertEqual(len(c['list_ids']),3);self.assertEqual(len(c['list_versions']),3)
  out,calls=self.ask('두 번째 거',c);self.assertEqual(calls,0);self.assertEqual([p['id'] for p in out['programs']],[c['list_ids'][1]])
  for q in ('그 사업은?','그럼 나는 신청할 수 있어?','그게 무슨 뜻이야?','그럼 어떻게 해야 돼?','다시 설명해 줘.'):
   out,calls=self.ask(q,out['conversation']);self.assertEqual(calls,0);self.assertEqual([p['id'] for p in out['programs']],[c['list_ids'][1]])
 def test_ambiguous_missing_and_changed_reference_clarify(self):
  c=self.listed();out,calls=self.ask('그 사업은?',c);self.assertEqual(calls,0);self.assertFalse(out['programs']);self.assertEqual(len(out['suggestions']),3)
  out,calls=self.ask('아까 전에 말했던 지원사업 기억나지?');self.assertEqual(calls,0);self.assertFalse(out['programs']);self.assertIn('확인할 수 없',out['answer'])
  self.items[1]['title']+=' 수정';out,calls=self.ask('두 번째 거',c);self.assertEqual(calls,0);self.assertFalse(out['programs']);self.assertIn('변경',out['answer'])
 def test_actual_change_and_hypothetical_do_not_reuse_old_comparison(self):
  c=self.listed();chosen,_=self.ask('첫 번째 거',c)
  changed,calls=self.ask('농업경영체 등록했어',chosen['conversation']);self.assertEqual(changed['conversation']['farm_registered'],'yes');self.assertEqual(changed['conversation']['notice_ids'],chosen['conversation']['notice_ids']);self.assertEqual(calls,0)
  before=copy.deepcopy(changed['conversation']);out,calls=self.ask('등록하면 달라져?',{**before,'farm_registered':'no'});self.assertEqual(calls,0);self.assertEqual(out['conversation']['farm_registered'],'no');self.assertIn('가정',out['answer'])
 def test_scope_no_model_keeps_business_for_return(self):
  c=self.listed()
  for q in ('저녁 메뉴 추천해줘','게임 추천해줘','아이돌 이야기하자'):
   out,calls=self.ask(q,c);self.assertEqual(calls,0);self.assertFalse(out['programs']);self.assertEqual(out['conversation']['list_ids'],c['list_ids']);c=out['conversation']
  self.assertNotIn('중심으로 상담',out['answer'])
  out,calls=self.ask('두 번째 거',c);self.assertEqual(calls,0);self.assertEqual(len(out['programs']),1)
 def test_unclear_and_failure_recover_without_inventing(self):
  c=self.listed();out,calls=self.ask('ㅁㄴㅇㄹ',c);self.assertEqual(calls,0);self.assertFalse(out['programs'])
  out,calls=self.ask('조금 쉽게 풀어 줄래?',c,None);self.assertLessEqual(calls,1);self.assertEqual(out['conversation'].get('farm_registered'),'no')
  out,calls=self.ask('두 번째 거',out['conversation']);self.assertEqual(calls,0);self.assertEqual(len(out['programs']),1)
 def test_correction_and_new_named_subject(self):
  c=self.listed();out,calls=self.ask('아니, 내 말은 그게 아니라',c);self.assertEqual(calls,0);self.assertFalse(out['programs'])
  out,calls=self.ask('면세유 가격안정 지원 조건은?',c);self.assertEqual(calls,0);self.assertEqual([p['id'] for p in out['programs']],['NOTICE-guide1'])
 def test_cultivation_and_finance_are_bounded_service_links(self):
  c=self.listed()
  out,calls=self.ask('마늘 병해충 공식 자료를 보고 싶어',c);self.assertEqual(calls,0);self.assertEqual(out['kind'],'cultivation');self.assertFalse(out['programs'])
  out,calls=self.ask('농업금융 상담: 운영 자금이 부족해',c);self.assertEqual(calls,0);self.assertFalse(out['programs']);self.assertIn('금융',out['answer'])
  out,calls=self.ask('두 번째 지원사업은?',out['conversation']);self.assertEqual(calls,0);self.assertEqual(len(out['programs']),1)

if __name__=='__main__':unittest.main()
