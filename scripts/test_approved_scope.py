import unittest
from datetime import datetime,timedelta,timezone
import support_guidance as guidance
import support_guidance_sources as sources
import rag_profile,rag_dialogue
from unittest.mock import patch
from test_recommendation_accuracy import condition,document,compare
from support_recommendation_readiness import decision

class ApprovedScope(unittest.TestCase):
    def test_changed_revision_cannot_keep_partial_approval(self):
        binding={'notice_content_hash':'same','eligibility_revision_id':1,'condition_ids':['r']}
        record={'content_hash':'same'}
        revision={'revision_id':2,'needs_review':False,'payload':{'conditions':[{'condition_id':'r','status':'verified'}]}}
        with patch('support_monitor.notice_record',return_value=record),patch('support_eligibility.show',return_value=revision):
            self.assertFalse(guidance.condition_binding_current(None,'x',binding))
            revision['revision_id']=1
            self.assertTrue(guidance.condition_binding_current(None,'x',binding))
            revision['payload']['conditions'][0]['status']='candidate'
            self.assertFalse(guidance.condition_binding_current(None,'x',binding))
    def test_official_city_parent_mapping(self):
        for city,parent in [('화성시','경기'),('산청군','경남'),('함안군','경남')]:
            self.assertEqual(rag_profile.region_state('제주',[city],rag_dialogue.AREAS),'mismatch')
            self.assertEqual(rag_profile.region_state(parent,[city],rag_dialogue.AREAS),'check')
            self.assertEqual(rag_profile.region_state(city,[city],rag_dialogue.AREAS),'match')
    def test_unknown_mandatory_conditions_remain_partial(self):
        conditions=[condition('r','residence',{'regions':['화성시']}),
            {'condition_id':'sex_year','kind':'other_required','presence':'unknown','value':None,'status':'unverified','evidence':{}}]
        self.assertEqual(decision(compare(document(conditions),{'region':'화성'}))['category'],'B')
        self.assertEqual(decision(compare(document(conditions),{'region':'제주'}))['category'],'C')
    def test_metadata_grant_never_inherits_extracted_details(self):
        now=datetime.now(timezone.utc)
        item={'id':'x','metadata_only':True,'url':'https://www.rda.go.kr/young/custom/policy/view.do?sId=1'}
        basis=sources.comparison_basis(item)
        annotation={'basis':basis,'complete':False,'checked_at':now.isoformat(),'fields':{'support':'미승인 금액'},'conditions':[]}
        manifest={'verified_facts':{'x':annotation},'verified_comparisons':{'x':annotation},'notice_observations':{}}
        feed={'notices':[item]};guidance.annotations(feed,manifest,now)
        self.assertEqual(feed['verified_facts'],{})
        self.assertEqual(feed['verified_comparisons'],{})
    def test_unaffected_existing_annotation_survives(self):
        now=datetime.now(timezone.utc);item={'id':'old'};basis=sources.comparison_basis(item)
        annotation={'basis':basis,'complete':False,'checked_at':now.isoformat(),'fields':{}}
        feed={'notices':[item]};guidance.annotations(feed,{'verified_facts':{'old':annotation}},now)
        self.assertEqual(feed['verified_facts']['old'],annotation)

if __name__=='__main__':unittest.main()
