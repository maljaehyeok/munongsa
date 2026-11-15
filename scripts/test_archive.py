import copy,unittest,json
from datetime import datetime,timezone,timedelta
import rag_catalogue as catalogue
import support_notice_review as review

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.item={'id':'NOTICE-test','title':'가상 농업 지원사업','institution':'가상 기관','url':'https://www.rda.go.kr/young/custom/policy/view.do?sId=1',
          'source_id':'rda-young-official','publication':'official_guidance','verification_status':'basics_only','recommendation_eligible':False,'rights':{'public_display':'allowed'},
          'freshness':'current','last_checked_at':self.now.isoformat(),'guidance_expires_at':(self.now+timedelta(days=1)).isoformat()}
        self.past={**self.item,'id':'NOTICE-past','title':'가상 과수 지원사업','reference_application_dates':{'start':{'date':'2025-01-01'},'end':{'date':'2025-02-01'}}}
        self.feed={'schema_version':'munongsa-support-public-v1','notices':[self.item,self.past]}
    def test_default_excludes_elapsed_keeps_unknown(self):
        self.assertEqual([n['id'] for n in catalogue.matches('전체 공고',self.feed,now=self.now)],['NOTICE-test'])
    def test_past_request(self):
        self.assertEqual([n['id'] for n in catalogue.matches('지난 공고',self.feed,now=self.now)],['NOTICE-past'])
    def test_exact_name_keeps_past(self):
        self.assertEqual(catalogue.matches(self.past['title'],self.feed,now=self.now)[0]['id'],'NOTICE-past')
        out=catalogue.respond(self.past['title'],{'documents':{},'guidance_feed':self.feed},explicit=True)
        self.assertEqual([p['id'] for p in out['programs']],['NOTICE-past'])
    def test_past_has_caution(self):
        p=catalogue.program(self.past,self.feed,self.now)
        self.assertEqual(p['card']['period_state'],'elapsed');self.assertIn('현재 신청에 적용할 수 없습니다',p['application_period']['description'])
    def test_published_date_not_used(self):
        self.item['published_at']='2000-01-01';self.assertEqual(review.notice_state(self.item,self.now),'unknown')
    def test_invalid_range_stays_unknown(self):
        item={**self.item,'reference_application_dates':{'start':{'date':'2050-01-01'},'end':{'date':'2020-01-01'}}}
        self.assertEqual(review.notice_state(item,self.now),'unknown')
    def test_future_and_standing_kept(self):
        self.item['reference_application_dates']={'start':{'date':'2050-01-01'},'end':{'date':'2051-01-01'}}
        self.assertEqual(review.notice_state(self.item,self.now),'upcoming')
        self.assertEqual(len(catalogue.matches('전체 공고',self.feed,now=self.now)),1)
        self.item['reference_application_dates']={};self.item['standing_application']=True
        self.assertEqual(review.notice_state(self.item,self.now),'standing')
    def test_verified_cancellation_wins_over_future_deadline(self):
        item={**self.item,'verification_status':'verified','publication':'approved_reference','application_status':'cancelled_verified','reference_application_dates':{'end':{'date':'2050-01-01'}}}
        self.assertEqual(review.notice_state(item,self.now),'elapsed')
        item['verification_status']='basics_only';self.assertEqual(review.notice_state(item,self.now),'unknown')
    def test_current_extension_over_old_dates(self):
        observation={'schema':review.SCHEMA,'basis':review.binding(self.past),'official_url':self.past['url'],'checked_at':self.now.isoformat(),'expires_at':(self.now+timedelta(hours=1)).isoformat(),
            'reference_application_dates':{'start':{'date':'2020-01-01'},'end':{'date':'2050-01-01'}},'reception_checked_at':self.now.isoformat(),'actual_reception':'operator_notice'}
        self.assertEqual(review.notice_state(review.project(self.past,observation,self.now),self.now),'window')
        observation['basis']['title']='다른 사업';self.assertEqual(review.notice_state(review.project(self.past,observation,self.now),self.now),'elapsed')
    def test_paging_stays_in_archive_scope(self):
        self.feed['notices']=[{**self.past,'id':'NOTICE-'+str(i),'title':'가상 과수 사업 '+str(i)} for i in range(7)]+[self.item]
        corpus={'documents':{},'guidance_feed':self.feed};out=catalogue.respond('지난 공고',corpus);seen=[]
        while True:
            seen.extend(p['id'] for p in out['programs']);self.assertEqual(out['catalogue_scope'],'past')
            if not out.get('catalogue_next'):break
            out=catalogue.respond(catalogue.PAGE_PREFIX+json.dumps(out['catalogue_next'],ensure_ascii=False),corpus)
        self.assertEqual(len(seen),7);self.assertNotIn('NOTICE-test',seen)
if __name__=='__main__':unittest.main()
