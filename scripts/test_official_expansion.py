"""Candidate extraction stays separate from official eligibility verification."""
import unittest
from support_runtime.official_expansion import candidates,document_kind
import support_eligibility as eligibility

URL='https://www.jeonbuk.go.kr/board/view.jeonbuk?boardId=BBS_0000005&dataSid=1'
class OfficialExpansionTest(unittest.TestCase):
    def test_news_events_and_equipment_excluded(self):
        for title in ['청년농업인 지원사업 성과 홍보','농업인 축제 신청 안내','농업 교육 설명회 모집','농업용 장비 지원사업 공고','농식품 기간제근로자 채용 공고']:
            self.assertIsNone(document_kind(title))
        self.assertEqual(document_kind('전북 농업마이스터대학 신입생 모집'),'application_notice')
        self.assertEqual(document_kind('2026년 청년농업인 영농정착지원사업 시행지침'),'policy_reference')

    def test_multi_track_exceptions_not_flattened(self):
        p,_=candidates(['응시자격','(마이스터과정) 전북자치도 거주 농업인으로서 5년 이상의 영농경력이 있음','영농경력 3년 이상 특별전형','(청년농과정) 만40세 미만','농업경영체 등록한 자 또는 농업인 확인서 발급이 가능한 자'],URL)
        self.assertEqual(p['logic']['op'],'UNKNOWN')
        self.assertFalse(any(c['presence']=='no_restriction' for c in p['conditions']))
        self.assertTrue(any(c['kind']=='residence' and c['presence']=='specified' for c in p['conditions']))
        self.assertFalse(any(c['kind']=='farm_registration' and c['presence']=='specified' for c in p['conditions']))
        for c in p['conditions']:eligibility.check_condition(c,{'original_url':URL})
        age=next(c for c in p['conditions'] if c['kind']=='age')
        with self.assertRaises(Exception):eligibility.check_condition(age,{'original_url':URL},verified=True)

    def test_farmland_not_residence(self):
        p,_=candidates(['대상 지역: 전북특별자치도 농지 소재지','재배 작물: 마늘, 벼'],URL)
        self.assertTrue(any(c['kind']=='business_location' and c['presence']=='specified' for c in p['conditions']))
        self.assertFalse(any(c['kind']=='residence' and c['presence']=='specified' for c in p['conditions']))
        self.assertTrue(any(c['kind']=='crop' and c['presence']=='specified' for c in p['conditions']))

    def test_missing_is_unknown(self):
        p,_=candidates(['지원사업 안내'],URL)
        self.assertTrue(all(c['presence']=='unknown' and c['value'] is None for c in p['conditions']))

if __name__=='__main__':unittest.main()
