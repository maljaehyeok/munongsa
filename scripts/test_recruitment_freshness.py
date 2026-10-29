"""Offline regression cases: real date forms, conservative KST decisions, RDA."""
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace
from pathlib import Path
import tempfile
from support_runtime import periods,rda

URL='https://www.rda.go.kr/young/custom/policy/view.do?sId=1&cp=1'

class FreshnessTests(unittest.TestCase):
    def test_equipment_out_of_service_scope(self):
        from support_runtime.boards import classify
        for title in ['농기계 지원사업 신청','농업기계 등화장치 지원사업','원예농산물 시설장비 지원사업']:
            self.assertEqual(classify({'title':title}),'excluded')
    def parse(self,text):return periods.extract([text],URL)
    def state(self,text,now):return periods.assess({},self.parse(text),now)['status']
    def test_hyphen_range(self):
        self.assertEqual(self.state('신청기간 : 2026-10-26 ~ 2026-11-04','2026-10-29T12:00+09:00'),'date_window_open')
    def test_explicit_short_year(self):
        self.assertEqual(self.state("신청기한: '26. 10. 16.(금)",'2026-10-29T12:00+09:00'),'closed')
    def test_curly_short_year(self):
        self.assertEqual(self.parse('신청기간 : ’26. 10. 22. ~ 11. 20. 14:00')['period']['start']['date'],'2026-10-22')
    def test_complete_short_date(self):
        self.assertEqual(self.state('신청기한: ~ 26. 08. 28 (금)','2026-10-29T12:00+09:00'),'closed')
    def test_comma_before_clock(self):
        self.assertEqual(self.parse("신청기간: '26 년 5 월 13 일 ~ 6 월 17 일 (수), 18:00 까지")['period']['end']['time'],'18:00')
    def test_yearless_not_project_year(self):
        p=periods.extract(['사업명: 2027년 사업','신청기간: 10. 22. ~ 11. 20. 14:00'],URL)
        self.assertIsNone(p['period']);self.assertTrue(p['unresolved_dates'])
    def test_single_deadline_retains_clock(self):
        self.assertEqual(self.parse('신청기한: 2026. 10. 30.(금) 14:00 까지')['period']['end']['time'],'14:00')
    def test_single_deadline_after_clock(self):
        self.assertEqual(self.state('신청기한: 2026. 10. 30.(금) 14:00 까지','2026-10-30T14:00+09:00'),'closed')
    def test_deadline_day_unknown_clock(self):
        self.assertEqual(self.state('신청기간: 2026-10-26 ~ 2026-10-30','2026-10-30T08:00+09:00'),'unknown')
    def test_timezone_conversion(self):
        self.assertEqual(self.state('신청기간: 2026-10-26 ~ 2026-10-30 18:00','2026-10-30T09:00+00:00'),'closed')
    def test_static_open_words_do_not_confirm(self):
        p=self.parse('신청기간: 2026-10-26 ~ 2026-11-04 현재 접수 중')
        self.assertEqual(periods.assess({},p,'2026-10-29T12:00+09:00','2026-10-29T12:00+09:00')['status'],'date_window_open')
    def test_ongoing_explicit(self):
        self.assertEqual(self.state('신청기간: 상시 모집','2026-10-29T12:00+09:00'),'ongoing')
    def test_budget_limited_ongoing_not_confirmed(self):
        self.assertEqual(self.state('신청기간: 상시 모집, 예산 소진 시 종료','2026-10-29T12:00+09:00'),'unknown')
    def test_conflicting_dates(self):
        p=periods.extract(['신청기간: 2026-10-26 ~ 2026-11-04','신청기간: 2026-10-26 ~ 2026-11-05'],URL)
        self.assertEqual(periods.assess({},p,'2026-10-29T12:00+09:00')['status'],'unknown')
    def test_rda_navigation_and_no_fake_posted_date(self):
        body="<table><tbody><tr><td>진행중</td><td>사업</td><td>전북 남원</td><td><a href=\"javascript:fn_detailView('policy', '46824');\">농업 지원 신청</a></td><td>2026-10-31</td></tr></tbody></table>"
        row=rda.rows(body)[0]
        self.assertIn('view.do?sId=46824',row['original_url']);self.assertIsNone(row['published_at'])
        self.assertEqual(row['list_deadline'],'2026-10-31');self.assertEqual(row['list_region'],'전북 남원')
    def test_rda_table_and_subheadings(self):
        lines=rda.detail_lines('<article class="viewArea"><div class="viewBody"><table><tr><th>신청기간</th><td>2026-10-01 ~ 2026-11-30</td></tr><tr><th>사업요약내용</th><td>신청자격: 농업인 신청장소: 읍면사무소</td></tr></table></div></article>')
        self.assertIn('신청자격: 농업인 ',lines)
        self.assertEqual(periods.extract(lines,URL)['period']['end']['date'],'2026-11-30')
    def test_target_does_not_include_implementing_agency(self):
        lines=rda.detail_lines('<article class="viewArea"><div class="viewBody"><table><tr><th>사업요약내용</th><td>2. 지원대상: 유류 사용 농업경영체 3. 사업시행기관: 농협경제지주 4. 신청기간: 2026-10-01 ~ 2026-11-30</td></tr></table></div></article>')
        target=next(x for x in lines if x.startswith('지원대상'))
        self.assertNotIn('농협',target)
    def test_title_year_and_round_are_not_application_dates(self):
        f=periods.notice_context('2027년 사업 2차 추가모집',URL)
        self.assertEqual(f['project_year']['value'],2027)
        self.assertEqual(f['recruitment_round']['value'],2)
        self.assertNotIn('application_start',f)
    def test_selected_attachment_reuses_bounded_reader(self):
        pages=[{'location':'PDF p.2','text':'신청기간: 2026-10-01 ~ 2026-11-30'}]
        reader=Mock(return_value=pages)
        with patch.dict('sys.modules',{'support_attachment_pilot':SimpleNamespace(extract_document=reader)}):
            parsed=periods.extract_attachment(Path('selected.pdf'),URL)
        reader.assert_called_once();self.assertIn('PDF p.2',parsed['period']['evidence']['location'])
        self.assertFalse(parsed['body_stored'])
    def test_legacy_hwp_never_empty_success(self):
        with self.assertRaises(ValueError):periods.extract_attachment(Path('selected.hwp'),URL)
    def test_saved_live_notice_does_not_need_to_be_on_recent_list(self):
        from support_runtime import discovery
        source={'kind':'jinan','city':'진안군','official_hosts':['www.jinan.go.kr'],'board_url':'https://www.jinan.go.kr/board/list.jinan'}
        row={'original_id':'old','title':'농업 지원사업 신청','original_url':'https://www.jinan.go.kr/board/view.jinan?dataSid=1','published_at':'2025-01-01'}
        parsed=self.parse('신청기간: 2026-01-01 ~ 2026-11-30')['period']
        prior={'kind':'jinan','metadata':row,'facts':{'application_start':{'value':parsed['start']},'application_deadline':{'value':parsed['end']}}}
        with patch.object(discovery.Transport,'get',return_value=b'<html></html>'),patch.object(discovery,'analyse',side_effect=lambda e,*_:dict(e,status='partial',facts={})):
            g=discovery.search_source(source,periods.as_of('2026-10-29T12:00+09:00'),{('jinan','old'):prior},refresh_details=True)
        self.assertEqual(g['list_count'],0);self.assertEqual(g['candidate_count'],1)
        self.assertEqual(g['analyses'][0]['metadata']['original_id'],'old')
    def test_rda_bounded_paging_prioritizes_unseen_rows(self):
        from support_runtime import discovery
        def listing(ids):return '<table><tbody>'+''.join(f'<tr><td>진행중</td><td>사업</td><td>전북 남원</td><td><a href="javascript:fn_detailView(\'policy\', \'{i}\');">청년농 지원사업 신청 {i}</a></td><td>2026-11-30</td></tr>' for i in ids)+'</tbody></table>'
        source={'kind':'rda_young','city':'전국','official_hosts':['www.rda.go.kr'],'detail_limit':1,'max_pages':2}
        known={('rda_young','policy:1'):{'status':'partial'}}
        with patch.object(discovery.Transport,'get',side_effect=[b'',listing(range(1,11)),listing([11])]) as get,patch.object(discovery,'analyse',side_effect=lambda e,*_:dict(e,status='partial',facts={},recruitment={})):
            result=rda.collect(source,periods.as_of('2026-10-29'),known)
        self.assertEqual(result['list_count'],11);self.assertEqual(get.call_count,3)
        self.assertNotEqual(result['analyses'][0]['metadata']['original_id'],'policy:1')
    def test_rda_second_page_failure_preserves_first_page(self):
        from support_runtime import discovery
        body='<table><tbody>'+''.join(f'<tr><td>진행중</td><td>사업</td><td>전북</td><td><a href="javascript:fn_detailView(\'policy\', \'{i}\');">청년농 지원사업 신청 {i}</a></td><td>2026-11-30</td></tr>' for i in range(10))+'</tbody></table>'
        source={'kind':'rda_young','city':'전국','official_hosts':['www.rda.go.kr'],'detail_limit':1,'max_pages':2}
        with patch.object(discovery.Transport,'get',side_effect=[b'',body,TimeoutError()]),patch.object(discovery,'analyse',side_effect=lambda e,*_:dict(e,status='partial',facts={},recruitment={})):
            result=rda.collect(source,periods.as_of('2026-10-29'))
        self.assertEqual(result['list_count'],10);self.assertEqual(len(result['analyses']),1);self.assertEqual(result['errors'][0]['error'],'TimeoutError')

if __name__=='__main__':unittest.main()
