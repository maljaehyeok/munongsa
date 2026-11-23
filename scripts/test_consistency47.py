"""Named business routing uses only current public titles; never grants eligibility."""
import json,sys,unittest,copy
from pathlib import Path
from unittest.mock import patch
import rag_api,rag_catalogue as c,rag_dialogue as d,rag_nlu

class Consistency47(unittest.TestCase):
 def test_live_cases(self):
  folder=Path(sys.argv[1]) if len(sys.argv)>1 else None
  if not folder:self.skipTest('public feed fixture required')
  feed=json.loads((folder.parent/'practical46-20261123/feed.json').read_text('utf8'))
  corpus={'documents':{},'guidance_feed':feed,'sync_verified':True,'sync_generation':'isolated'}
  ids=['NOTICE-2593a32e903d2f3e3ac46fea','NOTICE-2d04d09f4e1eedb099cc718f','NOTICE-ad792916c9574b1c4b48e414']
  snapshot=copy.deepcopy(feed)
  for i,identity in enumerate(ids,1):
   case=json.loads((folder/f'case-{i}.json').read_text('utf8'))
   with patch.object(rag_api,'load_api_corpus',return_value=corpus),patch.object(rag_nlu,'interpret',side_effect=AssertionError('named titles do not need a model call')):
    response=rag_api.local_pipeline(case['request']['question'])
   self.assertEqual([p['id'] for p in response['programs']],[identity])
   decision=response['programs'][0]['comparison']['decision']
   self.assertFalse(decision['final_application_eligibility_confirmed'])
   self.assertFalse(response['programs'][0]['application_period']['actual_reception_confirmed'])
   if i==1:self.assertTrue(decision['excluded'])
  self.assertEqual(snapshot,feed)
 def test_generic_not_name_and_no_substring_identity(self):
  from datetime import datetime,timezone,timedelta
  now=datetime.now(timezone.utc)
  item={'id':'NOTICE-test','title':'농업용 면세유 가격안정 지원사업 신청 안내','institution':'전주시','url':'https://www.jeonju.go.kr/test','publication':'official_guidance','verification_status':'basics_only','recommendation_eligible':False,'freshness':'current','last_checked_at':now.isoformat(),'guidance_expires_at':(now+timedelta(days=1)).isoformat(),'rights':{'public_display':'allowed'}}
  feed={'schema_version':'munongsa-support-public-v1','notices':[item]}
  self.assertEqual(c.named_records('농업경영체 미등록인데 신청 가능한가요?',feed,now),[])
  self.assertEqual(c.named_records('지원사업 신청 방법 알려줘',feed,now),[])
  self.assertEqual(c.named_records('마늘 재해보험',feed,now),[])
  self.assertEqual(c.named_records('면세유 가격안정 지원에 해당하나요?',feed,now),[item])
  item['rights']['public_display']='pending'
  self.assertEqual(c.named_records('면세유 가격안정',feed,now),[])
 def test_named_pagination_keeps_subject(self):
  from datetime import datetime,timezone,timedelta
  now=datetime.now(timezone.utc)
  notices=[{'id':'NOTICE-page'+str(i),'title':'유기농업자재 지원사업 '+str(i)+'차 공고','institution':'공식 기관','url':'https://www.rda.go.kr/young/custom/policy/view.do?sId='+str(i),'publication':'official_guidance','verification_status':'basics_only','recommendation_eligible':False,'freshness':'current','last_checked_at':now.isoformat(),'guidance_expires_at':(now+timedelta(days=1)).isoformat(),'rights':{'public_display':'allowed'}} for i in range(4)]
  corpus={'documents':{},'guidance_feed':{'schema_version':'munongsa-support-public-v1','notices':notices}}
  first=c.named_response('유기농업자재 신청 조건을 알려주세요.',corpus)
  self.assertEqual(len(first['programs']),3)
  second=c.respond(c.PAGE_PREFIX+json.dumps(first['catalogue_next'],ensure_ascii=False),corpus)
  self.assertEqual(len(second['programs']),1)
  self.assertFalse({p['id'] for p in first['programs']}&{p['id'] for p in second['programs']})

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Consistency47)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 raise SystemExit(not result.wasSuccessful())
