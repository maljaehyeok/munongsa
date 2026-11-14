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

if __name__=='__main__':unittest.main()
