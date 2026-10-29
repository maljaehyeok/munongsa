"""Small offline tests for the official board adapter, no external requests."""
import unittest
from unittest.mock import patch
from support_runtime import koat, discovery, periods


class KoatTests(unittest.TestCase):
    def test_actual_navigation_shape_and_posting_date(self):
        rows = koat.rows('<table><tbody><tr><td><a onclick="postLink(123)">2027년 창업 지원 모집</a></td><td>2026-10-22</td></tr></tbody></table>')
        self.assertEqual(rows[0]['original_url'], 'https://www.koat.or.kr/board/business/123/view.do')
        self.assertEqual(rows[0]['published_at'], '2026-10-22')
        self.assertNotIn('application_deadline', rows[0])

    def test_missing_publication_date_is_not_today(self):
        rows = koat.rows('<tbody><tr><td><a onclick="postLink(124)">모집</a></td></tr></tbody>')
        self.assertIsNone(rows[0]['published_at'])

    def test_non_business_rows_excluded(self):
        for title in ('교육생 선정 결과', '전문인력 교육기관 모집', '농기계 지원 모집'):
            self.assertFalse(koat.candidate({'title': title}))

    def test_extension_remains_candidate_without_inventing_deadline(self):
        self.assertTrue(koat.candidate({'title': '2026년 실증단지 입주모집연장공고'}))

    def test_existing_dispatcher_reused(self):
        with patch.object(koat, 'collect', return_value={'analyses': []}) as collect:
            self.assertEqual(discovery.search_source({'kind': 'koat'}, periods.as_of()), {'analyses': []})
            collect.assert_called_once()

    def test_failed_source_is_not_zero_success(self):
        with patch.object(discovery.Transport, 'get', side_effect=ValueError('offline fixture')):
            group = koat.collect({'kind': 'koat', 'city': 'national', 'official_hosts': ['www.koat.or.kr']}, periods.as_of())
        self.assertTrue(group['errors'])
        self.assertNotEqual(group['state'], '연결 성공')


if __name__ == '__main__':
    unittest.main()
