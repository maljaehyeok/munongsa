"""Synthetic regression cases from farmer scenarios; no LLM or network."""
import unittest
from datetime import datetime,timezone
import rag_profile,rag_dialogue,rag_catalogue

class FarmerQuality(unittest.TestCase):
    def extract(self,q):
        facts,error=rag_profile.extract(q,rag_dialogue.AREAS,rag_dialogue.CROPS,rag_dialogue.normalized)
        self.assertIsNone(error);return facts
    def test_residence_then_farm(self):
        f=self.extract('전주에 살고 농사는 김제에서 지어. 농업경영체 등록했어.')
        self.assertEqual(f['region'],'전주');self.assertEqual(f['farm_region'],'김제')
    def test_farm_then_residence(self):
        f=self.extract('김제에서 농사짓고 전주에 살고 있어.')
        self.assertEqual(f['region'],'전주');self.assertEqual(f['farm_region'],'김제')
    def test_explicit_labels(self):
        f=self.extract('거주지 전주 영농지 김제')
        self.assertEqual(f['region'],'전주');self.assertEqual(f['farm_region'],'김제')
    def test_business_location_is_not_residence(self):
        f=self.extract('고창 귀농 대출 이차보전 지원금은 얼마야?')
        self.assertNotIn('region',f);self.assertNotIn('farm_region',f)
    def test_locality_relevance_not_eligibility(self):
        url='https://www.rda.go.kr/young/custom/policy/view.do?sId=1'
        n={'id':'NOTICE-synthetic','title':'[가상] 고추비가림 지원사업','institution':'가상 공식 기관','url':url,'source_id':'synthetic','publication':'approved_reference','verification_status':'verified','freshness':'current','rights':{'public_display':'allowed'},'last_checked_at':'2026-11-01T00:00:00+09:00','reference_application_dates':{'end':{'date':'2026-11-04'}},'region':'파주 안내 · 거주지 요건은 확인 필요','evidence':{'region':{'url':url,'location':'승인된 안내 사실'}},'eligibility':{'conditions':[],'logic':{'op':'UNKNOWN','children':[]}}}
        feed={'schema_version':'munongsa-support-public-v1','notices':[n]};now=datetime(2026,11,15,tzinfo=timezone.utc)
        self.assertEqual([v['id'] for v in rag_catalogue.matches('지난 공고 중 파주 고추비가림 지원사업을 알려줘.',feed,now=now)],['NOTICE-synthetic'])
        self.assertEqual(rag_catalogue.matches('파주 고추비가림 지원사업',feed,now=now),[])
        self.assertEqual(rag_catalogue.program(n,feed,now,{'region':'부산'})['comparison']['label'],'추가 확인 필요')
        n['publication']='official_guidance';self.assertNotIn('파주',rag_catalogue.search_text(n,feed,now))

if __name__=='__main__':unittest.main()
