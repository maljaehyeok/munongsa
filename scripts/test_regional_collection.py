"""Synthetic fixtures for one official regional board; no network or approval."""
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from support_runtime import regional, discovery, periods, conditions
from support_source_registry import url
import support_link_policy as links


HTML='''<table class="p-table"><tbody><tr><td><a href="./selectBbsNttView.do?bbsNo=140&amp;key=1709&amp;nttNo=42">
가상 농업 지원사업 신청 알림 <span class="new">새글</span></a></td><td>2026-11-18</td></tr></tbody></table>'''


class RegionalTests(unittest.TestCase):
    def test_parser_exact_board_and_no_invented_title(self):
        r=regional.rows(HTML)[0]
        self.assertEqual(r['title'],'가상 농업 지원사업 신청 알림')
        self.assertEqual(r['original_id'],'nttNo:42')
        self.assertEqual(regional.rows(HTML.replace('bbsNo=140','bbsNo=999')),[])

    def test_navigation_key_exception_is_exact_and_no_token_bypass(self):
        value=regional.rows(HTML)[0]['original_url']
        self.assertEqual(url(value),value)
        for invalid in (value+'&token=bad',value+'&token=',value.replace('1709','1708'),value.replace('www.hongcheon.go.kr','example.com')):
            with self.assertRaises(Exception):url(invalid)

    def test_types_do_not_promote_reference_or_equipment(self):
        for title in ['농작업재해 예방 법률 의견조회','농업 수요조사 안내','농업기계 지원사업 신청']:
            self.assertFalse(regional.candidate({'title':title}))
        self.assertTrue(regional.candidate({'title':'청년 정착형 한우 임대 축사 운영 사업 신청'}))

    def test_registration_only_explicit_all_required_section(self):
        clause='- 농업경영체에 농업경영정보를 등록한 농업인 및 농업법인'
        lines=['4. 사업대상자: 다음 요건을 모두 충족하는 농업인 및 농업법인',clause,'5. 선정 우선순위']
        link=regional.rows(HTML)[0]['original_url'];facts=regional.fact_candidates(lines,link)
        self.assertTrue(facts['farm_registration_required']['value'])
        self.assertNotIn('farm_registration_required',regional.fact_candidates([clause],link))
        self.assertNotIn('farm_registration_required',regional.fact_candidates([lines[0],clause+' 또는 미등록 농업인'],link))
        payload=conditions.payload_for(facts,{})
        self.assertTrue(any(c['kind']=='farm_registration' and c['presence']=='specified' for c in payload['conditions']))
        self.assertTrue(any(c['presence']=='unknown' for c in payload['conditions']))

    def test_exact_title_check_not_menu_text(self):
        title='가상 농업 지원사업 신청 알림'
        self.assertTrue(links.title_check(BeautifulSoup('<span class="p-table__subject_text">'+title+'</span>','html.parser'),title,lambda v:v.strip()))
        self.assertFalse(links.title_check(BeautifulSoup('<nav>'+title+'</nav>','html.parser'),title,lambda v:v.strip()))

    def test_robots_failure_prevents_listing_and_details(self):
        source={'kind':'hongcheon','city':'강원 홍천','board_url':regional.BOARD,'official_hosts':[regional.HOST]}
        with patch.object(discovery.Transport,'get',side_effect=ValueError('blocked')) as get:
            result=regional.collect(source,periods.as_of())
        self.assertEqual(get.call_count,1);self.assertTrue(result['errors'])
        self.assertEqual(result['analyses'],[])

    def test_existing_dispatcher(self):
        with patch.object(regional,'collect',return_value={'analyses':[]}) as collect:
            discovery.search_source({'adapter':'hongcheon-agri-v1','kind':'hongcheon'},periods.as_of())
        collect.assert_called_once()


if __name__=='__main__':unittest.main()
