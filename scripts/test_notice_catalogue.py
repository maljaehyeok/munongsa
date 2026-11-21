import copy,unittest
from datetime import datetime,timedelta,timezone
from bs4 import BeautifulSoup
import support_notice_review as review
import support_link_policy as links
import rag_catalogue

class NoticeReviewTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.item={'id':'NOTICE-test','title':'가상 농업 지원사업','institution':'가상 기관','url':'https://www.rda.go.kr/young/custom/policy/view.do?sId=1','source_id':'rda-young-official',
                   'publication':'official_guidance','verification_status':'basics_only','recommendation_eligible':False,'eligibility_complete':False,'freshness':'current',
                   'last_checked_at':self.now.isoformat(),'guidance_expires_at':(self.now+timedelta(days=1)).isoformat(),'rights':{'public_display':'allowed'}}
    def test_dates_not_business_period(self):
        row={'original_url':self.item['url']}
        text='사업기간 2026-01-01 ~ 2026-12-31 교육기간 2026-11-01 ~ 2026-11-30'
        self.assertEqual(review.observe(row,BeautifulSoup('', 'html.parser'),text,self.now)['reference_application_dates'],{})
    def test_conflicting_dates_blocked(self):
        text='신청기간 2026-11-01 ~ 2026-12-01 신청기간 2026-10-01 ~ 2026-10-05'
        self.assertFalse(review.observe({'original_url':self.item['url']},BeautifulSoup('', 'html.parser'),text,self.now)['reference_application_dates'])
    def test_version_binding_and_durable_history(self):
        o=review.observe({'original_url':self.item['url']},BeautifulSoup('', 'html.parser'),'신청기간 2026-11-01 ~ 2026-12-01',self.now);o['basis']=review.binding(self.item)
        self.assertTrue(review.valid(self.item,o,self.now));self.assertFalse(review.valid({**self.item,'title':'변경'},o,self.now))
        o.update(actual_reception='operator_notice',reception_checked_at=self.now.isoformat())
        for hours in (0,26,48,72):
            with self.subTest(hours=hours):
                at=self.now+timedelta(hours=hours)
                self.assertTrue(review.valid(self.item,o,at))
                shown=review.project(self.item,o,at)
                self.assertEqual(shown['reference_application_dates'],o['reference_application_dates'])
                self.assertEqual(shown['official_observation_at'],o['checked_at'])
                self.assertEqual(shown['actual_reception_state'],'unconfirmed' if hours else 'operator_notice')
    def test_reception_not_confirmed(self):
        o=review.observe({'original_url':self.item['url']},BeautifulSoup('', 'html.parser'),'신청기간 2026-11-01 ~ 2026-12-01 신청방법 방문신청',self.now)
        self.assertNotEqual(o['actual_reception'],'confirmed')
    def test_expired_and_duplicate_notices_excluded(self):
        feed={'schema_version':'munongsa-support-public-v1','notices':[self.item]}
        self.assertEqual(len(rag_catalogue.records(feed,self.now)),1)
        self.assertFalse(rag_catalogue.records({**feed,'notices':[self.item,self.item]},self.now))
        expired={**self.item,'guidance_expires_at':(self.now-timedelta(seconds=1)).isoformat()}
        self.assertFalse(rag_catalogue.records({**feed,'notices':[expired]},self.now))
    def test_basic_never_eligibility(self):
        feed={'schema_version':'munongsa-support-public-v1','notices':[self.item]}
        p=rag_catalogue.program(self.item,feed,self.now)
        self.assertTrue(p['guidance_only']);self.assertEqual(p['required_conditions'],[])
        self.assertEqual(p['comparison']['label'],'추가 확인 필요');self.assertFalse(p['application_period']['actual_reception_confirmed'])
    def test_local_review_item_cannot_escape_by_merging_into_regular_feed(self):
        draft={**self.item,'id':'NOTICE-private-draft','local_review_only':True}
        feed={'schema_version':'munongsa-support-public-v1','notices':[self.item,draft]}
        self.assertEqual([x['id'] for x in rag_catalogue.records(feed,self.now)],[self.item['id']])
    def test_truncated_title_only_from_label(self):
        html='<input name="proj_id" value="42"><input name="proj_detail_id" value="0"><article class="contentGroup"><table><tr><th>사업명<i>필수</i></th><td>가상 농업 지원사업 안내</td></tr></table></article>'
        soup=BeautifulSoup(html,'html.parser');norm=lambda v:''.join(v.split())
        url='https://global.at.or.kr/front/bizReq/brView.do?proj_id=42&proj_detail_id=0'
        self.assertEqual(links.recovered_title(soup,'가상 농업 지원사업 ...',url,norm),'가상 농업 지원사업 안내')
        self.assertIsNone(links.recovered_title(soup,'가상 농업 지원사업 ...',url.replace('42','43'),norm))
        self.assertIsNone(links.recovered_title(soup,'다른 사업 ...','https://global.at.or.kr/front/bizReq/brView.do',norm))
    def test_safe_source_and_no_body(self):
        feed={'schema_version':'munongsa-support-public-v1','notices':[{**self.item,'url':'https://attacker.example/a'}]}
        self.assertFalse(rag_catalogue.records(feed,self.now))
    def test_approved_name_can_fall_back_without_promoting_evidence(self):
        item={**self.item,'publication':'approved_reference','verification_status':'verified'}
        feed={'schema_version':'munongsa-support-public-v1','notices':[item]}
        corpus={'documents':{'test':{'public':item}},'guidance_feed':feed}
        self.assertIsNone(rag_catalogue.respond(item['title'],corpus,explicit=True))
        result=rag_catalogue.respond(item['title'],corpus,explicit=True,include_approved=True)
        self.assertEqual(result['programs'][0]['id'],item['id'])
        self.assertEqual(result['programs'][0]['evidence_level'],'공식 공고 기본 안내')
        self.assertTrue(result['programs'][0]['needs_verification'])
if __name__=='__main__':unittest.main()
