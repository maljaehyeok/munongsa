"""Offline tests, synthetic listings only; no credentials or official raw HTML."""
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from support_runtime import at_export

def card(identity='42',category='농식품',period='2026-11-01 ~ 2026-12-01'):
    return '<div class="slider"><div class="item"><a href="/front/bizReq/brView.do?proj_id='+identity+'&amp;proj_detail_id=0"><p class="tit"><span class="txt">'+category+'</span></p><span class="dottxt">가상 모집공고 ...</span><span class="date">'+period+'</span></a></div></div>'

class ATSourceTests(unittest.TestCase):
    def test_identity_and_unknown_publication(self):
        r=at_export.rows(card())[0]
        self.assertEqual(r['original_id'],'project:42:0');self.assertIsNone(r['published_at'])
        self.assertTrue(r['title_may_be_truncated'])
    def test_fisheries_excluded(self):self.assertEqual(at_export.rows(card(category='수산물')),[])
    def test_untrusted_identity_excluded(self):self.assertEqual(at_export.rows(card(identity='http://evil')),[])
    def test_duplicates_same_identity(self):self.assertEqual(len(at_export.rows(card()+card())),1)
    def test_readonly_capture_has_no_eligibility(self):
        class T:
            count=2
            def __init__(self,source):pass
            def get(self,url,robots=False):return b'User-agent: *\nAllow: /' if robots else card().encode()
        source={'kind':'at_export','city':'test','board_url':at_export.BOARD,'official_hosts':[at_export.HOST]}
        with patch('support_runtime.discovery.Transport',T):g=at_export.collect(source,datetime.now(timezone.utc))
        e=g['analyses'][0];self.assertFalse(e['automatic_approval']);self.assertFalse(e['detail_fetched'])
        self.assertNotIn('target_description',e['facts']);self.assertNotIn('region',e['facts'])
    def test_existing_official_ids_not_collected_again(self):
        class T:
            count=2
            def __init__(self,source):pass
            def get(self,url,robots=False):return b'User-agent: *\nAllow: /' if robots else card().encode()
        source={'kind':'at_export','city':'test','board_url':at_export.BOARD,'official_hosts':[at_export.HOST],'existing_official_ids':['project:42:0']}
        with patch('support_runtime.discovery.Transport',T):g=at_export.collect(source,datetime.now(timezone.utc))
        self.assertEqual(g['analyses'],[]);self.assertEqual(g['duplicate_skips'],['project:42:0'])

    def test_public_list_excludes_staff_and_keeps_full_title(self):
        raw='''<table class="boardList"><tbody><tr><td class="category">농식품</td>
        <td class="subject"><a href="Javascript:goViewPage('42','1');">가상 농식품 지원 모집</a></td>
        <td class="date2">2026-11-01~2026-12-31</td><td class="writer">가상 담당자</td>
        <td class="tel">000-000-0000</td></tr></tbody></table>'''
        r=at_export.board_rows(raw)[0]
        self.assertEqual(r['original_id'],'project:42:1')
        self.assertEqual(r['title'],'가상 농식품 지원 모집')
        self.assertNotIn('writer',r);self.assertNotIn('tel',r)
        self.assertEqual(at_export.board_rows(raw.replace('농식품</td>','수산물</td>')),[])

    def test_board_pagination_stops_on_repeated_ids(self):
        raw='''<table class="boardList"><tbody><tr><td class="category">농식품</td>
        <td class="subject"><a href="Javascript:goViewPage('42','0');">가상 지원 모집</a></td>
        <td class="date2">2026-11-01~2026-12-31</td></tr></tbody></table>'''
        class T:
            count=0
            def __init__(self,source):pass
            def get(self,url,robots=False):
                self.count+=1
                return b'User-agent: *\nAllow: /' if robots else raw.encode()
        source={'kind':'at_export','city':'unknown','board_url':at_export.BOARD,
                'official_hosts':[at_export.HOST],'discovery_url':at_export.LIST,'max_pages':99}
        with patch('support_runtime.discovery.Transport',T):g=at_export.collect(source,datetime.now(timezone.utc))
        self.assertEqual(g['requests'],3);self.assertEqual(len(g['analyses']),1)

    def test_v2_uses_existing_runtime_dispatcher(self):
        from support_runtime import discovery
        with patch.object(at_export,'collect',return_value={'analyses':[]}) as collect:
            discovery.search_source({'adapter':'at-official-listing-v2','kind':'at_export'},datetime.now(timezone.utc))
        collect.assert_called_once()

if __name__=='__main__':unittest.main()
