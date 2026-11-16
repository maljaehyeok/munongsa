"""Clock-only regressions; synthetic evidence, no network or production writes."""
import copy, unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import support_notice_review as r
import support_guidance as g
from test_support_guidance import row, origin, NOW

class ExpiryTests(unittest.TestCase):
    def setUp(self):
        self.now=NOW
        self.item={'id':'test-1','title':'Synthetic','url':'https://agency.go.kr/notice/1','source_id':'test'}
        self.value={'schema':r.SCHEMA,'basis':r.binding(self.item),'official_url':self.item['url'],
                    'checked_at':self.now.isoformat(),'expires_at':(self.now+timedelta(hours=26)).isoformat(),
                    'article_sha':'a'*64,'reference_application_dates':{'start':{'date':'2026-11-01'},'end':{'date':'2026-11-15'}},
                    'actual_reception':'operator_notice','reception_checked_at':self.now.isoformat()}
    def test_clock_preserves_dates_not_reception(self):
        for hours in (0,26,48,72):
            with self.subTest(hours=hours):
                now=self.now+timedelta(hours=hours);shown=r.project(self.item,self.value,now)
                self.assertEqual(shown['reference_application_dates'],self.value['reference_application_dates'])
                self.assertEqual(shown['official_observation_at'],self.value['checked_at'])
                if hours:self.assertEqual(shown['actual_reception_state'],'unconfirmed')
                if hours>=48:self.assertEqual(r.notice_state(shown,now),'elapsed')
    def test_changed_binding_hash_and_review(self):
        self.assertNotIn('official_observation_at',r.project({**self.item,'url':'https://agency.go.kr/2'},self.value,self.now))
        self.assertNotIn('official_observation_at',r.project(self.item,{**self.value,'article_sha':'bad'},self.now))
        self.assertNotIn('official_observation_at',r.project(self.item,{**self.value,'review_required':True},self.now))
    def test_failed_fetch_retains_history_without_current_claim(self):
        result=r.merge_observations({'notices':[self.item]},{'test-1':self.value},{},{},self.now)
        shown=r.project(self.item,result['test-1'],self.now)
        self.assertEqual(shown['actual_reception_state'],'unconfirmed')
        self.assertIn('reference_application_dates',shown)
    def test_changed_document_blocks_and_preserves_previous(self):
        new={**self.value,'article_sha':'b'*64}
        v=r.merge_observations({'notices':[self.item]},{'test-1':self.value},{'test-1':new},{},self.now)['test-1']
        self.assertTrue(v['review_required']);self.assertEqual(v['previous_fact'],self.value)
        self.assertNotIn('official_observation_at',r.project(self.item,v,self.now))
    def test_explicit_cancellation_supersedes_calendar(self):
        shown=r.project({**self.item,'verification_status':'verified','application_status':'cancelled_verified'},self.value,self.now)
        self.assertEqual(r.notice_state(shown,self.now),'elapsed')
    def test_reviewed_extension_supersedes_previous_date(self):
        new={**self.value,'article_sha':'b'*64,'reviewed_article_sha':'b'*64,
             'reference_application_dates':{'start':{'date':'2026-11-01'},'end':{'date':'2026-12-01'}}}
        v=r.merge_observations({'notices':[self.item]},{'test-1':self.value},{'test-1':new},{},self.now)['test-1']
        self.assertFalse(v['review_required'])
        self.assertEqual(r.project(self.item,v,self.now)['reference_application_dates']['end']['date'],'2026-12-01')
    def test_export_retains_expired_bound_observation(self):
        # No review rows required: isolate the export projection and unchanged policy gate.
        manifest=g.select([row()],[origin()],lambda u:True,self.now)
        manifest['items']=[]
        manifest['notice_observations']={'test-1':self.value}
        for hours in (0,26,48,72):
            feed={'notices':[copy.deepcopy(self.item)]}
            g.append(None,feed,manifest,self.now+timedelta(hours=hours))
            self.assertEqual(feed['notice_observations']['test-1'],self.value)
    def test_future_observation_not_accepted_early(self):
        self.assertFalse(r.valid(self.item,self.value,self.now-timedelta(seconds=1)))
        self.assertTrue(r.valid(self.item,self.value,self.now))
    def test_refresh_uses_completed_observation_time(self):
        late={**self.value,'checked_at':(self.now+timedelta(minutes=2)).isoformat(),
              'expires_at':(self.now+timedelta(hours=26,minutes=2)).isoformat()}
        check={'status':'checked','title_match':True,'url':self.item['url'],'observation':late}
        strict={'notices':[self.item]}
        with tempfile.TemporaryDirectory() as directory,patch.object(g,'records',return_value=[]),patch.object(g.public,'export',return_value=(strict,{})),patch.object(g,'append'):
            result=g.refresh(None,Path(directory),now=self.now,portal=[],link_check=lambda u:True,source_checks={'test-1':check})
        finished=datetime.fromisoformat(result['generated_at'])
        self.assertTrue(r.valid(self.item,result['notice_observations']['test-1'],finished))
    def test_historical_fact_not_expired_comparison(self):
        basis={k:self.item.get(k) for k in ('id','title','url','target','region','reference_application_dates','application_period','eligibility')}
        value={'basis':basis,'complete':False,'checked_at':self.now.isoformat(),'fields':{'reference_application_dates':self.value['reference_application_dates']},'evidence':{'url':self.item['url'],'fact_confirmed':True}}
        self.assertIn('reference_application_dates',r.fact_project(self.item,value,self.now+timedelta(hours=72)))
        self.assertEqual(r.fact_project(self.item,{**value,'review_required':True},self.now),self.item)
    def test_newer_verified_period_wins_over_old_observation(self):
        item={**self.item,'verified_period_at':(self.now+timedelta(minutes=1)).isoformat(),'reference_application_dates':{'end':{'date':'2026-12-31'}}}
        shown=r.project(item,self.value,self.now+timedelta(minutes=2))
        self.assertEqual(shown['reference_application_dates']['end']['date'],'2026-12-31')
        self.assertEqual(shown['actual_reception_state'],'unconfirmed')

if __name__=='__main__':unittest.main()
