import unittest
from bs4 import BeautifulSoup
import support_link_policy as p
import support_guidance_sources as sources

def normal(v):return ''.join(c for c in v.lower() if c.isalnum())

class ScopedIdentityTests(unittest.TestCase):
    def test_oads_exact_id_and_title(self):
        url='https://www.oads.or.kr/board/annc/selectAnnounce.do?annc_seq=89'
        raw='<input name="annc_seq" value="89"><div class="bo_head"><h2>Official farming notice</h2></div>'
        soup=BeautifulSoup(raw,'html.parser')
        self.assertTrue(p.title_check(soup,'Official farming notice',normal,url))
        self.assertFalse(p.title_check(soup,'Official farming notice revised',normal,url))
        self.assertFalse(p.title_check(soup,'Official farming notice',normal,url.replace('89','90')))
        soup.append(BeautifulSoup('<input name="annc_seq" value="89">','html.parser'))
        self.assertFalse(p.title_check(soup,'Official farming notice',normal,url))

    def test_gunsan_attachment_record_binding(self):
        url='https://www.gunsan.go.kr/farm/m2500/view/12345'
        raw='<div class="bbsviewtitle">Official notice</div><div class="bbsviewdown"><a href="/_cms/board/eFileDownload/460/12345/abc12">guide</a></div>'
        self.assertTrue(p.title_check(BeautifulSoup(raw,'html.parser'),'Official notice',normal,url))
        self.assertFalse(p.title_check(BeautifulSoup(raw.replace('/12345/','/12346/'),'html.parser'),'Official notice',normal,url))
        self.assertFalse(p.title_check(BeautifulSoup(raw,'html.parser'),'Official notice',normal,url.replace('www.gunsan.go.kr','other.example')))

    def test_article_boundaries(self):
        raw='<nav>Unrelated regional restriction</nav><div class="bo_con">Application facts</div><aside>Other deadline</aside>'
        self.assertEqual(sources.article(raw,'https://www.oads.or.kr/board/annc/selectAnnounce.do?annc_seq=89'),'Application facts')
        self.assertEqual(sources.article('<main>Other notice</main>','https://www.oads.or.kr/board/annc/selectAnnounce.do?annc_seq=89'),'')

    def test_jeonju_return_route_binding(self):
        board='a'*32;record='b'*32
        url=f'https://www.jeonju.go.kr/planweb/board/view.9is?boardUid={board}&dataUid={record}'
        raw=f'<div id="board_wrap"><div class="view-table"><li><strong>제목</strong><span>Official notice</span></li></div></div><a href="/login?returnUrl=%2Fplanweb%2Fboard%2Fview.9is%3FboardUid%3D{board}%26dataUid%3D{record}">login</a>'
        self.assertTrue(p.title_check(BeautifulSoup(raw,'html.parser'),'Official notice',normal,url))
        self.assertFalse(p.title_check(BeautifulSoup(raw.replace(record,'c'*32),'html.parser'),'Official notice',normal,url))
        self.assertFalse(p.title_check(BeautifulSoup(raw,'html.parser'),'Official notice',normal,url+'&dataUid='+record))

    def test_generic_behavior_preserved(self):
        soup=BeautifulSoup('<h4 class="title">Known title</h4>','html.parser')
        self.assertTrue(p.title_check(soup,'Known title',normal))
        self.assertFalse(p.title_check(BeautifulSoup('<nav>Known title</nav>','html.parser'),'Known title',normal))

if __name__=='__main__':unittest.main()
