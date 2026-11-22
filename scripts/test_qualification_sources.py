import unittest
from support_runtime import core_facts,discovery
from support_runtime.conditions import payload_for
from support_runtime.qualification_guards import explicit_locations

URL='https://www.rda.go.kr/young/custom/policy/view.do?sId=1'

class QualificationSources(unittest.TestCase):
    def test_bullet_boundaries_do_not_swallow_documents_and_contact(self):
        f=core_facts.extract(['□ 신청대상: 농업경영정보를 등록한 농업인 및 농업법인 □ 사업내용: 자재 일부 지원 □ 신청방법: 방문 신청 □ 제출서류 - 신청서, 동의서 □ 문의처: 기관 전화'],URL)
        self.assertEqual(f['required_documents']['value'],'신청서, 동의서')
        self.assertNotIn('제출서류',f['application_method']['value'])
        self.assertTrue(f['farm_registration_required']['value'])

    def test_target_bullet_registration_is_reused(self):
        f=core_facts.extract(['☞ 농업경영정보를 등록하고, 토양검정 결과를 제출한 농업인 ☞ 유기농업자재 구입비 지원'],URL)
        self.assertTrue(f['farm_registration_required']['value'])
        p=payload_for(f,{})
        self.assertTrue(any(c['kind']=='farm_registration' for c in p['conditions']))
        self.assertTrue(any(c['presence']=='unknown' for c in p['conditions']))
        for text in ['☞ 농업경영정보를 등록하고 토양검정 결과를 제출한 농업인 ☞ 녹비작물 종자, 유기농업자재',
                     '☞ 농업경영체에 등록된 농업인 및 농업법인 중 품목별 요건 충족자 ☞ 토양검정ㆍ시비처방 등 컨설팅']:
            self.assertTrue(core_facts.extract([text],URL)['farm_registration_required']['value'])

    def test_land_registration_is_not_person_registration(self):
        f=core_facts.extract(['사업대상: 농업경영정보에 등록한 농지(토지)'],URL)
        self.assertNotIn('farm_registration_required',f)

    def test_named_business_address_is_not_residence(self):
        places=explicit_locations('청도군에 소재(본사, 공장 기준)한 중소기업')
        self.assertEqual(places,[{'kind':'business_location','regions':['청도군'],'location_basis':'business_office'}])
        self.assertEqual(explicit_locations('관내 소재한 기업'),[])
        self.assertEqual(explicit_locations('파주시에 사업장을 둔 자 또는 이전 예정자'),[])

    def test_snapshot_keeps_document_changes_but_not_outer_page_counters(self):
        a=b'<div class="body"><p>condition</p><a href="a.pdf">document</a></div><aside>1</aside>'
        b=a.replace(b'<aside>1',b'<aside>2')
        self.assertEqual(discovery.source_snapshot(a,'.body'),discovery.source_snapshot(b,'.body'))
        self.assertNotEqual(discovery.source_snapshot(a,'.body'),discovery.source_snapshot(a.replace(b'a.pdf',b'b.pdf'),'.body'))
        self.assertIsNone(discovery.source_snapshot(a,'.absent'))
        self.assertFalse(discovery.source_snapshot('<div class="body">첨부파일</div>','.body')['attachments_present'])
        self.assertTrue(discovery.source_snapshot('<div class="body">붙임 문서 참고</div>','.body')['attachments_present'])

if __name__=='__main__':unittest.main()
