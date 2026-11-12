"""Synthetic routing regressions; no official documents, DB or network."""
import unittest
import rag_dialogue as dialogue


class TitleRouting(unittest.TestCase):
    def corpus(self, region='경기 파주시'):
        def document(identity, title, area):
            return {'public': {'id': identity, 'title': title, 'region': area,
                               'target': '', 'support': ''}, 'record': {'fields': {}}}
        return {'documents': {
            'old': document('NOTICE-SYNTHETIC-OLD', '가상 고추비가림 지원사업', '경기 파주시'),
            'new': document('NOTICE-SYNTHETIC-NEW', '가상 유기질비료 지원사업 신청 안내', region)},
            'aliases': {'old': ['파주', '비가림'], 'new': ['가상 유기질비료 지원사업 신청 안내']}}

    def ask(self, question, region='경기 파주시'):
        def grounded(question, key):
            return dialogue.response('가상 검증 결과', {}, programs=[{'id': key}])
        return dialogue.basic_response(question, self.corpus(region), grounded)

    def test_specific_title_overrides_broad_city_alias(self):
        self.assertEqual(self.ask('파주 유기질비료 신청 조건')['programs'], [{'id': 'new'}])

    def test_other_region_is_not_a_matching_business(self):
        out = self.ask('전주 유기질비료 신청 조건')
        self.assertEqual(out['programs'], [])
        self.assertTrue(out['scope_not_found'])

    def test_unconfirmed_region_is_not_declared_mismatch(self):
        self.assertEqual(self.ask('전주 유기질비료 신청 조건', 'unknown')['programs'], [{'id': 'new'}])

    def test_existing_business_alias_is_preserved(self):
        self.assertEqual(self.ask('파주 비가림 신청 조건')['programs'], [{'id': 'old'}])


if __name__ == '__main__':
    unittest.main()
