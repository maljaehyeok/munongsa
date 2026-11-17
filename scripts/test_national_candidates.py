"""Focused offline safety tests; never writes approvals or calls the network."""
import unittest
from unittest.mock import patch

from collect_national_candidates import identity, prepare
from support_runtime import rda


def row(ident, region='경기 안산', title='2027년 농업 지원사업 신청'):
    return {'original_id': 'policy:'+str(ident), 'list_region': region,
            'list_deadline': '2026-12-31', 'title': title,
            'original_url': 'https://www.rda.go.kr/young/custom/policy/view.do?sId='+str(ident)+'&cp=1'}


def group(*rows):
    return {'kind': 'rda_young', 'analyses': [
        {'metadata': r, 'status': 'partial', 'facts': {}, 'recruitment': {}} for r in rows]}


class NationalTests(unittest.TestCase):
    def test_regions_rotate_without_jeonbuk_priority(self):
        rows = [row(1), row(2), row(3, '전북 부안'), row(4, '전남 진도')]
        self.assertEqual([r['original_id'] for r in rda.balanced_candidates(rows)],
                         ['policy:1', 'policy:3', 'policy:4', 'policy:2'])

    def test_repeated_page_stops_and_same_title_ids_survive(self):
        from support_runtime import discovery, periods
        class Transport:
            host = 'www.rda.go.kr'
            count = 0
            def get(self, *_):
                self.count += 1
                return b'fixture'
        transport = Transport()
        source = {'kind': 'rda_young', 'city': 'unknown', 'max_pages': 3, 'detail_limit': 2}
        with patch.object(discovery, 'Transport', return_value=transport), \
             patch.object(rda, 'rows', return_value=[row(i) for i in range(10)]), \
             patch.object(discovery, 'analyse', side_effect=lambda e, *_: dict(e, facts={}, recruitment={})):
            result = rda.collect(source, periods.as_of())
        self.assertEqual(transport.count, 3)  # robots, first page, repeated second page
        self.assertEqual(len(result['analyses']), 2)
        self.assertNotEqual(result['analyses'][0]['metadata']['original_id'],
                            result['analyses'][1]['metadata']['original_id'])

    def test_new_before_known_within_region(self):
        rows = [row(1), row(2)]
        self.assertEqual(rda.balanced_candidates(rows, {('rda_young', 'policy:1'): {}})[0]['original_id'], 'policy:2')

    def test_url_identity_ignores_only_nonidentity_controls(self):
        a = row(1)['original_url']
        self.assertEqual(identity(a), identity(a.replace('cp=1', 'cp=3')))
        self.assertNotEqual(identity(a), identity(row(2)['original_url']))

    def test_public_and_run_duplicates_excluded(self):
        result = prepare([group(row(1), row(2), row(2))], {'notices': [
            {'url': row(1)['original_url'], 'title': row(1)['title']}]})
        self.assertEqual(result['summary']['duplicates_excluded'], 2)
        self.assertEqual(len(result['candidates']), 1)

    def test_same_title_different_notice_not_silently_deleted(self):
        result = prepare([group(row(1), row(2))], {'notices': []})
        self.assertEqual(len(result['candidates']), 2)
        self.assertEqual(result['candidates'][0]['related_versions'], ['policy:2'])

    def test_region_hint_never_becomes_eligibility_or_publication(self):
        result = prepare([group(row(1))], {'notices': []})['candidates'][0]
        self.assertFalse(result['recommendation_eligible'])
        self.assertEqual(result['publication'], 'private')
        self.assertTrue(all(c['presence'] == 'unknown' for c in result['eligibility_candidate']['conditions']))

    def test_unproved_and_other_notice_facts_excluded(self):
        g = group(row(1))
        g['analyses'][0]['facts'] = {
            'age': {'value': 25},
            'target_description': {'value': '농업인', 'evidence': {
                'url': row(2)['original_url'], 'quote': '지원대상: 농업인', 'location': '본문'}}}
        result = prepare([g], {'notices': []})['candidates'][0]
        self.assertEqual(result['facts'], {})

    def test_unofficial_url_fails_closed(self):
        r = row(1); r['original_url'] = 'https://example.com/fake'
        with self.assertRaises(Exception):
            prepare([group(r)], {'notices': []})

    def test_body_title_requires_repair(self):
        r = row(1, title='본문' * 100)
        result = prepare([group(r)], {'notices': []})
        self.assertEqual(result['summary']['title_repair_required'], 1)
        self.assertEqual(result['summary']['facts_ready_for_review'], 0)

    def test_failed_detail_never_becomes_candidate(self):
        g = group(row(1)); g['analyses'][0]['status'] = 'failed'
        result = prepare([g], {'notices': []})
        self.assertEqual(result['summary']['detail_failures'], 1)
        self.assertEqual(result['candidates'], [])

    def test_explicit_registration_shared_by_person_and_entity(self):
        g = group(row(1))
        g['analyses'][0]['facts'] = {'target_description': {
            'value': '농업경영정보를 등록한 농업경영체(농업인 및 농업법인)',
            'evidence': {'url': row(1)['original_url'], 'location': '신청대상',
                         'quote': '농업경영정보를 등록한 농업경영체(농업인 및 농업법인)'}}}
        item = prepare([g], {'notices': []})['candidates'][0]
        clauses = item['eligibility_candidate']['conditions']
        self.assertEqual([c['value'] for c in clauses if c['kind'] == 'farm_registration'], [{'registered': True}])
        self.assertTrue(any(c['presence'] == 'unknown' for c in clauses))
        self.assertFalse(item['recommendation_eligible'])

    def test_registration_exception_not_flattened(self):
        g = group(row(1))
        g['analyses'][0]['facts'] = {'target_description': {
            'value': '농업경영정보를 등록한 농업경영체 또는 미등록 예비농업인',
            'evidence': {'url': row(1)['original_url'], 'location': '본문', 'quote': '등록 또는 미등록'}}}
        item = prepare([g], {'notices': []})['candidates'][0]
        self.assertFalse(any(c['kind'] == 'farm_registration' for c in item['eligibility_candidate']['conditions']))


if __name__ == '__main__':
    unittest.main()
