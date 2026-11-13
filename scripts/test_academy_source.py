"""Synthetic education documents; no live service or personal data."""
import unittest,json,sqlite3,tempfile
from pathlib import Path
from contextlib import closing
from support_runtime import academy,periods,ingestion,official_expansion
import support_monitor as monitor

URL='https://agriacademy.jeonbuk.go.kr/bbs/board.php?bo_table=ad_02_01&wr_id=10'
ROW={'original_id':'ad_02_01:10','original_url':URL,'title':'모의 농업인 교육','published_at':None}
def html(deadline='거주지 읍·면·동 행정복지센터 ‘26.11.16.(월) 까지'):
    pairs=[('교육 과정명',ROW['title']),('교육 기간 및 시간','12.2.~12.3.'),('교육 대상','농업인 또는 교육희망자'),('신청 기한',deadline)]
    return ('<div id="sub_ctn_2">Date : 2026-10-01<table>'+''.join('<tr><td>- '+k+'</td><td>:</td><td>'+v+'</td></tr>' for k,v in pairs)+'</table><div id="commentContents">시험 개인정보 표본</div><form>가상 비밀번호</form></div>').encode()

class AcademyTests(unittest.TestCase):
    def test_course_dates_never_become_application_period(self):
        entry=academy.detail(html(),ROW)
        self.assertEqual(entry['facts']['application_deadline']['value']['date'],'2026-11-16')
        self.assertNotIn('application_start',entry['facts'])
        self.assertEqual(entry['metadata']['published_at'],'2026-10-01')
        self.assertEqual(periods.assess(entry['facts'],now='2026-11-17')['status'],'closed')
    def test_missing_deadline_not_inferred(self):
        entry=academy.detail(html('기관 문의'),ROW)
        self.assertNotIn('application_deadline',entry['facts'])
        self.assertEqual(periods.assess(entry['facts'],now='2026-11-13')['status'],'unknown')
    def test_comments_forms_not_captured(self):
        raw=json.dumps(academy.detail(html(),ROW),ensure_ascii=False)
        self.assertNotIn('시험 개인정보',raw);self.assertNotIn('가상 비밀번호',raw)
        self.assertEqual(academy.detail(html(),ROW)['facts']['official_condition_candidates']['value']['logic']['op'],'UNKNOWN')
    def test_only_exact_official_board_get_urls(self):
        for url in [URL.replace('agriacademy.jeonbuk.go.kr','evil.example'),URL+'&page=2',URL.replace('board.php','write.php'),URL.replace('ad_02_01','ad_04_01'),URL.replace('https:','http:')]:
            with self.assertRaises(ValueError):academy.official_url(url)
    def test_feed_filters_publicity_and_unrelated(self):
        def entry(title,url=URL):return '<entry><title>'+title+'</title><category term="ad_02_01"/><updated>2026-11-02T00:00:00+09:00</updated><summary>농업인</summary><link rel="alternate" href="'+url.replace('&','&amp;')+'"/></entry>'
        raw=('<feed xmlns="http://www.w3.org/2005/Atom">'+entry('농업인 모집 입찰')+entry('모의 농업인 교육')+'</feed>').encode()
        rows=academy.parse_feed(raw,periods.as_of('2026-11-13'));self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['published_at'])
        with self.assertRaises(ValueError):academy.parse_feed(b'<!DOCTYPE feed><feed/>',periods.as_of())
    def test_candidate_insert_and_duplicate_preserve_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            with closing(monitor.connect(Path(tmp))) as db:
                source={'source_id':'synthetic-academy','kind':'jeonbuk_academy','institution':'모의 기관','board_url':URL,'method':'html','enabled':True,'official_hosts':['agriacademy.jeonbuk.go.kr'],'minimum_interval_hours':24,'reuse_policy':'unknown'}
                ingestion.SOURCES['jeonbuk_academy']=source
                one=official_expansion.import_new(db,[academy.detail(html(),ROW)])
                events=db.execute('SELECT count(*) FROM review_events').fetchone()[0]
                two=official_expansion.import_new(db,[academy.detail(html(),ROW)])
                self.assertEqual(one['new'],1);self.assertEqual(two['new'],0);self.assertEqual(len(two['duplicates']),1)
                row=db.execute('SELECT publication,verification_status FROM discovered_notices').fetchone()
                self.assertEqual(row['publication'],'review');self.assertNotEqual(row['verification_status'],'verified')
                self.assertEqual(db.execute('SELECT count(*) FROM review_events').fetchone()[0],events)
if __name__=='__main__':unittest.main()
