"""Synthetic preparation facts; no official requests, private corpus or LLM."""
import unittest
from unittest.mock import patch
import support_preparation as preparation
import review_support_details as review
import rag_search
import rag_catalogue

class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.basis={'id':'test','title':'가상 지원사업','url':'https://www.rda.go.kr/young/custom/policy/view.do?sId=1'}
        self.stamp='2026-11-17T10:00:00+00:00'
    def html(self,body):
        return ('<section class="viewArea"><h3>가상 지원사업</h3><table><tr><th>요약내용</th><td>'+body+'</td></tr></table></section>').encode()
    def test_labelled_conditions_and_office_keep_distinct_roles(self):
        r=preparation.extract(self.basis,self.html('▪ 신청대상 : 농업경영체 등록 농업인 ▪ 신청방법 : 방문신청(농지소재지 읍면 사무소) ▪ 지원비율 : 자부담50%'),self.stamp)
        self.assertEqual(r['fields']['target']['value'],'농업경영체 등록 농업인')
        self.assertIn('농지소재지',r['fields']['office']['value'])
        self.assertNotIn('region',r['fields'])
        self.assertEqual(r['fields']['self_payment']['value'],'자부담50%')
    def test_business_period_and_attachment_reference_not_promoted(self):
        r=preparation.extract(self.basis,self.html('사업기간 2027-01-01 ~ 2027-12-31 ▪ 제출서류 : 붙임파일 참조'),self.stamp)
        self.assertNotIn('period',r['fields']);self.assertNotIn('documents_required',r['fields']);self.assertNotIn('target',r['fields'])
    def test_unsupported_source_or_title_rejected(self):
        with self.assertRaises(ValueError):preparation.extract({**self.basis,'url':'https://attacker.example/a'},self.html(''),self.stamp)
        with self.assertRaises(ValueError):preparation.extract({**self.basis,'title':'다른 회차'},self.html(''),self.stamp)
    def test_repeated_label_and_numbered_sections_are_not_split_inside_values(self):
        r=preparation.extract(self.basis,self.html('다. 신청대상 : 신청대상 농지가 가상시에 있는 농가 라. 신청장소 : 읍면 사무소(※동지역은 센터) 마. 지원내용 : 자재 지원'),self.stamp)
        self.assertEqual(r['fields']['target']['value'],'신청대상 농지가 가상시에 있는 농가')
        self.assertEqual(r['fields']['office']['value'],'읍면 사무소(※동지역은 센터)')
        r=preparation.extract(self.basis,self.html('1. 신청대상 : 등록 농업인 2. 지원내용 : 자재 3. 신청장소 : 산업팀 4. 신청서류 : 신청서'),self.stamp)
        self.assertEqual(r['fields']['target']['value'],'등록 농업인')
        self.assertEqual(r['fields']['office']['value'],'산업팀')
    def test_required_documents_do_not_include_next_consent_step(self):
        r=preparation.extract(self.basis,self.html('1. 필수제출서류 : 신청서, 계좌 사본 2. 무역통계제공 동의 필수 : 기관 확인'),self.stamp)
        self.assertEqual(r['fields']['documents_required']['value'],'신청서, 계좌 사본')
    def test_preview_never_enters_approved_rag(self):
        r=preparation.extract(self.basis,self.html('지원대상 : 가상 농업인'),self.stamp)
        preview=review.build({'schema':'munongsa-support-details-plan-v1','records':[r]},'test','synthetic')
        self.assertTrue(preview['preview']);self.assertEqual(preview['records'][0]['approval']['state'],'preview')
        with patch.object(rag_search,'read_json',return_value=preview),self.assertRaises(ValueError):rag_search.load_corpus()
        self.assertEqual(rag_catalogue.records({'schema_version':'munongsa-support-public-v1','local_review_only':True,'notices':[]}),[])

    def test_append_preserves_existing_records_and_link_history(self):
        old={'schema':'munongsa-support-details-v1','preview':False,'records':[{'basis':{'id':'old'},'fields':{'summary':'unchanged'}}],
             'link_reviews':[{'basis':{'id':'old'},'state':'official_detail'}],'operator_metadata':{'preserve':True}}
        addition={'schema':old['schema'],'preview':True,'records':[{'basis':{'id':'new'}}]}
        merged=review.merge_append(old,addition)
        self.assertEqual(merged['link_reviews'],old['link_reviews'])
        self.assertEqual(merged['operator_metadata'],old['operator_metadata'])
        self.assertEqual(merged['records'][0],old['records'][0])
        self.assertTrue(merged['preview']);self.assertEqual(len(old['records']),1)

    def test_append_still_rejects_existing_notice_replacement(self):
        old={'records':[{'basis':{'id':'same'}}]}
        with self.assertRaises(ValueError):review.merge_append(old,{'records':[{'basis':{'id':'same'}}]})

    def factual_record(self):
        r=preparation.extract(self.basis,self.html('지원내용 : 가상 종자 지원'),self.stamp)
        r['fields']={'summary':r['fields']['summary']}
        r['rights'].update(display_scope=review.FACT_SCOPE,public_fields=['summary'],audience='detail_display_only',
            eligibility_approval=False,body_redistribution=False,attachment_redistribution=False,
            use_basis={'kind':'independent_facts','urls':['https://www.law.go.kr/LSW/precInfoP.do?precSeq=197742']})
        return r

    def test_field_approval_is_created_only_when_explicit_build_requests_it(self):
        plan={'schema':'munongsa-support-details-plan-v1','records':[self.factual_record()]}
        draft=review.build(plan,'synthetic','test')
        self.assertEqual(draft['records'][0]['field_approvals']['summary']['state'],'preview')
        approved=review.build(plan,'synthetic','test',approved=True)
        self.assertEqual(approved['records'][0]['field_approvals']['summary'],approved['records'][0]['approval'])
        self.assertNotIn('approval',plan['records'][0])

    def test_fact_scope_rejects_unlisted_or_eligibility_fields(self):
        r=self.factual_record();r['rights']['public_fields']=[]
        with self.assertRaises(AssertionError):review.validate({'schema':'munongsa-support-details-plan-v1','records':[r]})
        r=self.factual_record();r['fields']['conditions']=r['fields'].pop('summary');r['rights']['public_fields']=['conditions']
        with self.assertRaises(AssertionError):review.validate({'schema':'munongsa-support-details-plan-v1','records':[r]})

    def test_display_facts_cannot_become_rag_evidence(self):
        import rag_sync
        r=self.factual_record()
        with self.assertRaisesRegex(rag_sync.SyncError,'display_only_not_rag_approval'):
            rag_sync.validate_record(r,{},None)
        doc=review.build({'schema':'munongsa-support-details-plan-v1','records':[r]},'synthetic','test',approved=True)
        feed={'schema_version':'munongsa-support-public-v1','notices':[{'id':r['basis']['id']}]}
        with patch.object(rag_search,'read_json',side_effect=[doc,feed]):
            corpus=rag_search.load_corpus(specs_override={'test':{'id':r['basis']['id']}},aliases_override={})
        self.assertEqual(corpus['documents'],{});self.assertEqual(len(corpus['excluded']),1)

if __name__=='__main__':unittest.main()
