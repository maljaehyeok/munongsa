"""Synthetic notices, isolated DBs, no real approvals or external requests."""
import copy,hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
import support_monitor as monitor
import support_reference_review as review
import export_support_public as public
from test_support_monitor import SOURCE,feed

NOW=datetime(2026,10,28,3,0,tzinfo=timezone.utc)

class ReferenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name);self.db=monitor.connect(self.state);self.addCleanup(self.db.close)
        self.network=patch('socket.socket.connect',side_effect=AssertionError('network forbidden'));self.network.start();self.addCleanup(self.network.stop)
        monitor.register_sources(self.db,[SOURCE])
        monitor.collect_source(self.db,SOURCE,fetcher=lambda source:(feed(title='모의 농업 지원사업 · 시험 전용'),200,'text/xml'),force=True)
        self.nid=self.db.execute('SELECT notice_id FROM discovered_notices').fetchone()[0]
        self.record=review.db_record(self.db,self.nid);self.plan=review.draft(self.record)
        self.plan.update(basics_confirmed=True,support_notice_confirmed=True,public_use_confirmed=True)
        self.plan['notice_evidence']['location']='Synthetic official notice title and institution'
        self.plan['rights']={'public_display':'allowed','checked_at':'2026-10-28',
            'evidence_url':'https://www.mafra.go.kr/test-policy','scope_note':'Synthetic test permission only'}

    def prepare(self,plan=None):return review.prepare(self.db,plan or self.plan,{},'test reviewer','synthetic approval only',NOW)

    def dates(self,start=None,end=None):
        self.plan['reference_dates_confirmed']=True;self.plan['reference_dates']={}
        for key,value in (('start',start),('end',end)):
            if value:self.plan['reference_dates'][key]={'date':value,'evidence':{'url':self.record['original_url'],'location':'Synthetic date line'}}

    def test_draft_has_no_implicit_confirmation(self):
        draft=review.draft(self.record)
        self.assertFalse(draft['basics_confirmed']);self.assertFalse(draft['public_use_confirmed'])
        self.assertFalse(draft['reference_dates_confirmed'])

    def test_preview_does_not_modify_database(self):
        before=(self.state/'monitor.sqlite3').read_bytes();_,_,_,_,data,stats=self.prepare()
        self.assertEqual(before,(self.state/'monitor.sqlite3').read_bytes())
        self.assertEqual(stats['references'],1);self.assertFalse(data['notices'][0]['recommendation_eligible'])
        self.assertEqual(monitor.notice_record(self.db,self.nid)['publication'],'review')

    def test_each_human_confirmation_is_required(self):
        for field in ('basics_confirmed','support_notice_confirmed','public_use_confirmed'):
            plan=copy.deepcopy(self.plan);plan[field]=False
            with self.subTest(field=field),self.assertRaises(monitor.MonitorError):self.prepare(plan)

    def test_rights_cannot_be_inferred_from_official_url(self):
        self.plan['rights']['public_display']='unconfirmed'
        with self.assertRaises(monitor.MonitorError):self.prepare()

    def test_changed_content_rejects_stale_decision(self):
        with self.db:self.db.execute('UPDATE discovered_notices SET content_hash=?',('changed',))
        with self.assertRaises(monitor.MonitorError):self.prepare()

    def test_changed_review_rejects_stale_decision(self):
        monitor.review_notice(self.db,self.nid,'other reviewer','test',freshness='unknown')
        with self.assertRaises(monitor.MonitorError):self.prepare()

    def test_unknown_conditions_can_be_reference_never_recommendation(self):
        _,_,approved,_,data,_=self.prepare()
        self.assertEqual(approved['publication'],'approved_reference')
        item=data['notices'][0];self.assertEqual(item['target'],'unknown')
        self.assertEqual(item['guidance_level'],'official_notice');self.assertFalse(item['recommendation_eligible'])

    def test_date_only_window_does_not_invent_times_or_open_status(self):
        self.dates('2026-10-01','2026-10-30')
        item=self.prepare()[4]['notices'][0]
        self.assertEqual(item['reference_application_dates']['end']['date'],'2026-10-30')
        self.assertEqual(item['application_period'],{});self.assertEqual(item['application_status'],'unknown')
        self.assertFalse(item['recommendation_eligible'])

    def test_deadline_only_is_allowed_as_reference_fact(self):
        self.dates(end='2026-10-30')
        item=self.prepare()[4]['notices'][0]
        self.assertNotIn('start',item['reference_application_dates']);self.assertEqual(item['application_period'],{})

    def test_known_deadline_time_preserved_without_inventing_start_time(self):
        self.dates('2026-10-27','2026-11-11')
        self.plan['reference_dates']['end'].update(time='18:00',timezone='Asia/Seoul')
        item=self.prepare()[4]['notices'][0]
        self.assertEqual(item['reference_application_dates']['end']['time'],'18:00')
        self.assertNotIn('time',item['reference_application_dates']['start'])
        self.assertFalse(item['recommendation_eligible'])

    def test_invalid_time_rejected(self):
        self.dates(end='2026-11-11')
        for value in ('24:00','18:75'):
            self.plan['reference_dates']['end'].update(time=value,timezone='Asia/Seoul')
            with self.assertRaises(ValueError):self.prepare()

    def test_facts_only_export_keeps_comparison_but_not_original_quote(self):
        import support_eligibility as eligibility
        condition={'condition_id':'applicant','kind':'applicant','presence':'specified',
                   'value':{'one_of':['individual_farmer']},
                   'evidence':{'url':self.record['original_url'],'location':'Synthetic target line','quote':'Synthetic private proof only'}}
        eligibility.register(self.db,self.nid,{'conditions':[condition],'logic':{'condition_id':'applicant'}},'test','test')
        eligibility.review(self.db,self.nid,'applicant','verified','test','test')
        self.plan=review.draft(review.db_record(self.db,self.nid))|{k:self.plan[k] for k in ('basics_confirmed','support_notice_confirmed','public_use_confirmed','notice_evidence','rights')}
        self.plan['release_verified_conditions']=True;self.plan['rights']['facts_only']=True
        item=self.prepare()[4]['notices'][0];evidence=item['eligibility']['conditions'][0]['evidence']
        self.assertTrue(evidence['fact_confirmed']);self.assertNotIn('quote',evidence)
        self.assertFalse(item['recommendation_eligible'])

    def test_unconfirmed_extracted_dates_are_not_exported(self):
        self.dates('2026-10-01','2026-10-30');self.plan['reference_dates_confirmed']=False
        self.assertEqual(self.prepare()[4]['notices'][0]['reference_application_dates'],{})

    def test_invalid_date_and_missing_evidence_rejected(self):
        self.dates(end='2026-02-30')
        with self.assertRaises(ValueError):self.prepare()
        self.dates(end='2026-10-30');self.plan['reference_dates']['end']['evidence']['location']=''
        with self.assertRaises(ValueError):self.prepare()

    def test_date_manifest_is_bound_to_notice_hash(self):
        self.dates(end='2026-10-30');before,_,_,rights,_,_=self.prepare()
        rights[self.nid]['notice_content_hash']='old'
        self.assertEqual(public.reference_dates(rights[self.nid],before),{})

    def test_rights_review_date_uses_korea_calendar_day(self):
        now=datetime.fromisoformat('2026-10-28T00:30:00+09:00')
        self.assertIsNotNone(public.rights_for({self.nid:self.plan['rights']},self.nid,now.astimezone(timezone.utc)))

    def test_apply_needs_explicit_confirmation(self):
        with self.assertRaises(monitor.MonitorError):review.apply(self.state,self.plan,self.state/'publication-rights.json','test','test')

    def test_apply_records_two_events_and_writes_no_public_feed(self):
        result=review.apply(self.state,self.plan,self.state/'publication-rights.json','test reviewer','synthetic only',True,NOW)
        self.assertFalse(result['public_feed_written']);self.assertFalse(result['recommendation_eligible'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM review_events').fetchone()[0],2)
        self.assertEqual(monitor.notice_record(self.db,self.nid)['publication'],'approved_reference')
        self.assertTrue(list((self.state/'backups').glob('*.sqlite3')))
        self.assertFalse((self.state/'support-public.json').exists())

    def test_manifest_must_not_overwrite_db_or_runtime_files(self):
        for name in ('monitor.sqlite3','runtime.json','latest-run.json'):
            with self.subTest(name=name),self.assertRaises(monitor.MonitorError):
                review.apply(self.state,self.plan,self.state/name,'test','test',True,NOW)

    def test_failed_second_event_rolls_back_approval(self):
        original=monitor.save_review
        def save(db,before,after,action,actor,reason):
            actual=db.execute('PRAGMA database_list').fetchone()[2]
            if actual and action=='publication':raise RuntimeError('synthetic storage failure')
            return original(db,before,after,action,actor,reason)
        with patch.object(monitor,'save_review',side_effect=save),self.assertRaises(RuntimeError):
            review.apply(self.state,self.plan,self.state/'publication-rights.json','test','test',True,NOW)
        self.assertEqual(monitor.notice_record(self.db,self.nid)['publication'],'review')
        self.assertEqual(self.db.execute('SELECT count(*) FROM review_events').fetchone()[0],0)

    def test_classification_never_establishes_eligibility(self):
        record={**self.record,'facts':{},'period_assessment':{'status':'unknown'}}
        self.assertEqual(review.classify(record)['category'],'support_candidate')
        record['title']='청년자문단 모집 공고';self.assertEqual(review.classify(record)['category'],'general_notice')

if __name__=='__main__':unittest.main()
