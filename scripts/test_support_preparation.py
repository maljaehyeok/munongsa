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
    def test_preview_never_enters_approved_rag(self):
        r=preparation.extract(self.basis,self.html('지원대상 : 가상 농업인'),self.stamp)
        preview=review.build({'schema':'munongsa-support-details-plan-v1','records':[r]},'test','synthetic')
        self.assertTrue(preview['preview']);self.assertEqual(preview['records'][0]['approval']['state'],'preview')
        with patch.object(rag_search,'read_json',return_value=preview),self.assertRaises(ValueError):rag_search.load_corpus()
        self.assertEqual(rag_catalogue.records({'schema_version':'munongsa-support-public-v1','local_review_only':True,'notices':[]}),[])

if __name__=='__main__':unittest.main()
