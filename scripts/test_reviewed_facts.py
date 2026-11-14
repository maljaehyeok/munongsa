import copy,unittest
from datetime import datetime,timezone,timedelta
import support_guidance_sources as s
class FactsTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,11,14,tzinfo=timezone.utc)
  self.item={'id':'x','title':'Official','url':'https://www.bizinfo.go.kr/notice','publication':'official_guidance'}
  self.check={'status':'checked','title_match':True,'url':self.item['url'],'article':'verified applicant period'}
  self.plan={'id':'x','basis':s.comparison_basis(self.item),'article_sha':s.article_sha(self.check),
   'required_fragments':['verified applicant'],'fields':{'target':'Verified facts only'},'location':'Official target',
   'reception':{'status':'open_notice_verified','checked_at':self.now.isoformat()}}
 def run_plan(self):return s.reviewed_facts({'notices':[self.item]},[self.plan],{'x':self.check},self.now)
 def test_verified_partial_never_approves(self):
  self.assertFalse(self.run_plan()['x']['complete']);self.assertNotIn('eligibility_complete',self.run_plan()['x']['fields'])
 def test_revoked_or_changed_notice_is_excluded(self):
  self.assertFalse(s.reviewed_facts({'notices':[]},[self.plan],{'x':self.check},self.now))
  self.item['title']='Changed';self.assertFalse(self.run_plan())
 def test_changed_source_or_failed_fetch_is_excluded(self):
  self.check['article']='different';self.assertFalse(self.run_plan())
  self.check['article']='verified applicant period';self.check['status']='http_403';self.assertFalse(self.run_plan())
 def test_unsafe_fields_and_markup_rejected(self):
  self.plan['fields']['recommendation_eligible']=True;self.assertFalse(self.run_plan())
  self.plan['fields']={'target':'<script>'};self.assertFalse(self.run_plan())
 def test_reception_observation_is_not_renewed_by_date_fetch(self):
  self.now+=timedelta(hours=24);self.assertEqual(self.run_plan()['x']['reception'],{})
 def test_no_reception_claim_for_date_only_plan(self):
  self.plan.pop('reception');self.assertEqual(self.run_plan()['x']['reception'],{})
if __name__=='__main__':unittest.main()
