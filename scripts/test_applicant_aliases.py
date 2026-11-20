import unittest
import rag_profile,rag_dialogue
URL='https://www.rda.go.kr/young/custom/policy/view.do?sId=47120&cp=1'
class ApplicantAliases(unittest.TestCase):
 def result(self,actual,allowed,status='verified'):
  item={'eligibility':{'conditions':[{'condition_id':'applicant','kind':'applicant','presence':'specified','value':{'one_of':allowed},'status':status,'evidence':{'url':URL,'location':'공식 신청대상','quote':'농업인 및 농업법인'}}],
    'logic':{'op':'AND','children':[{'condition_id':'applicant'},{'op':'UNKNOWN','children':[]}]}}}
  return rag_profile.compare({'public':item,'record':{'fields':{}}},{'applicant':actual},lambda u:u==URL,rag_dialogue.AREAS)
 def test_corporation_legacy_schema_alias(self):
  r=self.result('agricultural_corporation',['individual_farmer','agricultural_business']);self.assertNotEqual(r['label'],'조건 불일치');self.assertIn('신청자 유형',' '.join(r['reasons']))
 def test_explicit_individual_only_excludes_corporation(self):self.assertEqual(self.result('agricultural_corporation',['individual_farmer'])['label'],'조건 불일치')
 def test_generic_business_is_unknown(self):self.assertEqual(self.result('business',['individual_farmer','agricultural_business'])['label'],'추가 확인 필요')
 def test_legacy_business_permission(self):self.assertNotEqual(self.result('business',['business'])['label'],'조건 불일치')
 def test_group_alias(self):self.assertNotEqual(self.result('group',['institution_group'])['label'],'조건 불일치')
 def test_group_does_not_become_agricultural_corporation(self):self.assertEqual(self.result('group',['individual_farmer','agricultural_business'])['label'],'조건 불일치')
 def test_pending_does_not_compare(self):self.assertEqual(self.result('agricultural_corporation',['individual_farmer'],status='candidate')['verified_condition_count'],0)
 def test_invalid_options_stay_unknown(self):self.assertEqual(self.result('agricultural_corporation',[{'bad':'value'}])['label'],'추가 확인 필요')
 def test_matching_type_does_not_complete_eligibility(self):self.assertEqual(self.result('individual_farmer',['individual_farmer'])['structured_state'],'check')
if __name__=='__main__':unittest.main()
