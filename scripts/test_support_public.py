"""Publication boundary tests: temporary DB only, no real approvals or network."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import support_monitor as monitor
import support_eligibility as eligibility
import export_support_public as public
from test_support_monitor import SOURCE, feed
from test_support_eligibility import leaf, payload

NOW = datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc)


class PublicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = monitor.connect(self.temp.name)
        monitor.register_sources(self.db, [SOURCE])
        self.block = patch('socket.socket.connect', side_effect=AssertionError('network forbidden'))
        self.block.start()
        monitor.collect_source(self.db, SOURCE, fetcher=lambda _: (feed(title='모의 사업 · 시험 전용'), 200, 'text/xml'), force=True)
        self.identity = self.db.execute('SELECT notice_id FROM discovered_notices').fetchone()[0]
        self.rights = {self.identity: {'public_display': 'allowed', 'checked_at': '2026-10-25',
            'evidence_url': 'https://www.mafra.go.kr/home/5331/subview.do'}}

    def tearDown(self):
        self.block.stop()
        self.db.close()
        self.temp.cleanup()

    def conditions(self):
        data = payload([leaf('applicant', 'applicant', {'one_of':['individual_farmer']}),
                        leaf('region', 'residence', {'regions':['전북특별자치도 김제시']})])
        eligibility.register(self.db, self.identity, data, 'fixture', 'test only')
        for c in data['conditions']:
            eligibility.review(self.db, self.identity, c['condition_id'], 'verified', 'fixture', 'test only')
        self.bind_conditions()

    def bind_conditions(self):
        revision = eligibility.show(self.db, self.identity)
        self.rights[self.identity].update(eligibility_revision_id=revision['revision_id'],
            notice_content_hash=monitor.notice_record(self.db,self.identity)['content_hash'])

    def approve(self, reference=False, period=True):
        values = {'target':'모의 개인 농업인', 'region':'전북특별자치도 김제시', 'support':'모의 지원 내용',
                  'verification_status':'verified', 'freshness':'current',
                  'evidence_url':'https://www.mafra.go.kr/test', 'evidence_location':'모의 p.1',
                  'conditions_verified':True, 'now':NOW}
        if period:
            values.update(period_start='2026-10-01T00:00:00+09:00',period_end='2026-10-31T18:00:00+09:00',
                          application_period_verified=True,application_status='open')
        monitor.review_notice(self.db, self.identity, 'fixture', 'test only', **values)
        monitor.publish_notice(self.db, self.identity, 'approved_reference' if reference else 'approved', 'fixture', 'test only', now=NOW)

    def run_export(self, rights=None, now=NOW):
        with closing(monitor.connect(self.temp.name, readonly=True)) as db:
            db.execute('BEGIN')
            return public.export(db, self.rights if rights is None else rights, now)

    def test_unapproved_rows_never_export(self):
        self.assertEqual(self.run_export()[0]['notices'], [])

    def test_basic_notice_can_be_reference_with_all_eligibility_unknown(self):
        monitor.review_notice(self.db, self.identity, 'fixture', 'basic facts only',
            verification_status='verified', freshness='current', notice_basics_verified=True,
            evidence_url='https://www.mafra.go.kr/test', evidence_location='모의 공식 공고 제목·기관')
        monitor.publish_notice(self.db, self.identity, 'approved_reference', 'fixture', 'test only', now=NOW)
        item = self.run_export()[0]['notices'][0]
        self.assertEqual(item['guidance_level'], 'official_notice')
        self.assertFalse(item['recommendation_eligible'])
        self.assertFalse(item['eligibility_complete'])
        self.assertEqual(item['application_status'], 'unknown')
        self.assertEqual(item['target'], 'unknown')

    def test_basic_verification_alone_does_not_publish(self):
        monitor.review_notice(self.db, self.identity, 'fixture', 'basic facts only',
            verification_status='verified', freshness='current', notice_basics_verified=True,
            evidence_url='https://www.mafra.go.kr/test', evidence_location='모의 제목')
        self.assertEqual(self.run_export()[0]['notices'], [])

    def test_basic_notice_still_requires_public_rights(self):
        monitor.review_notice(self.db, self.identity, 'fixture', 'basic facts only',
            verification_status='verified', freshness='current', notice_basics_verified=True,
            evidence_url='https://www.mafra.go.kr/test', evidence_location='모의 제목')
        monitor.publish_notice(self.db, self.identity, 'approved_reference', 'fixture', 'test only', now=NOW)
        self.assertEqual(self.run_export(rights={})[0]['notices'], [])

    def test_basic_notice_is_not_sufficient_for_strong_approval(self):
        monitor.review_notice(self.db, self.identity, 'fixture', 'basic facts only',
            verification_status='verified', freshness='current', notice_basics_verified=True,
            evidence_url='https://www.mafra.go.kr/test', evidence_location='모의 제목')
        with self.assertRaises(monitor.MonitorError):
            monitor.publish_notice(self.db, self.identity, 'approved', 'fixture', 'test only', now=NOW)

    def test_basic_verification_without_location_rejected(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.review_notice(self.db, self.identity, 'fixture', 'test only',
                verification_status='verified', notice_basics_verified=True, evidence_url='https://www.mafra.go.kr/test')

    def test_partial_conditions_keep_verified_comparison_and_unknown(self):
        data = payload([leaf('applicant','applicant',{'one_of':['individual_farmer']}),
                        leaf('region','residence',{'regions':['전북특별자치도 김제시']})])
        eligibility.register(self.db,self.identity,data,'fixture','test only')
        eligibility.review(self.db,self.identity,'applicant','verified','fixture','test only')
        self.bind_conditions();self.approve(reference=True,period=False)
        item = self.run_export()[0]['notices'][0]
        self.assertEqual([c['status'] for c in item['eligibility']['conditions']], ['verified','unverified'])
        self.assertFalse(item['recommendation_eligible'])
        node=os.environ.get('NODE_BINARY') or shutil.which('node')
        if node:
            code="""const fs=require('fs'),vm=require('vm'),ctx={URL};vm.runInNewContext(fs.readFileSync('assets/support-public.js','utf8'),ctx);const item=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(['individual','municipality','unknown'].map(applicant=>ctx.MunongsaSupport.evaluate(item,{applicant}).conditionStatus)));"""
            r=subprocess.run([node,'-e',code],input=json.dumps(item,ensure_ascii=False),text=True,capture_output=True,encoding='utf8',cwd=monitor.ROOT)
            self.assertEqual(r.returncode,0);self.assertEqual(json.loads(r.stdout),['check','mismatch','check'])

    def test_reference_never_recommendation(self):
        self.conditions(); self.approve(reference=True)
        data, stats = self.run_export()
        self.assertEqual(stats['references'], 1)
        self.assertFalse(data['notices'][0]['recommendation_eligible'])

    def test_current_approved_and_verified_conditions_export(self):
        self.conditions(); self.approve()
        data, stats = self.run_export()
        self.assertEqual(stats['recommendations'], 1)
        item = data['notices'][0]
        self.assertEqual(item['eligibility']['logic']['op'], 'AND')
        self.assertEqual(item['eligibility']['conditions'][0]['evidence']['location'], '모의 첨부 p.2 신청자격')
        self.assertEqual(item['application_status'], 'open_verified')
        for private in ('approved_by','reviewer','review_json','hints_json','content_hash'):
            self.assertNotIn(private, item)

    def test_rights_missing_or_restricted_prevents_export(self):
        self.conditions(); self.approve()
        for rights in ({}, {self.identity:{'public_display':'restricted'}},
                       {self.identity:{'public_display':'allowed','checked_at':'2099-01-01'}}):
            self.assertEqual(self.run_export(rights)[0]['notices'], [])

    def test_missing_structured_conditions_blocks_recommendation(self):
        self.approve()
        item = self.run_export()[0]['notices'][0]
        self.assertFalse(item['recommendation_eligible'])

    def test_candidate_values_are_redacted(self):
        data = payload([leaf('crop','crop',{'any_of':['후보 작물 · 미확인']})])
        eligibility.register(self.db,self.identity,data,'fixture','test only')
        self.bind_conditions()
        self.approve(reference=True)
        item=self.run_export()[0]['notices'][0]
        self.assertIsNone(item['eligibility']['conditions'][0]['value'])
        self.assertNotIn('후보 작물',json.dumps(item,ensure_ascii=False))

    def test_ended_period_is_not_current_recommendation(self):
        self.conditions();self.approve()
        item=self.run_export(now=datetime(2026,11,2,tzinfo=timezone.utc))[0]['notices'][0]
        self.assertFalse(item['recommendation_eligible'])
        self.assertEqual(item['application_status'],'period_elapsed')

    def test_missing_period_is_unknown_not_open(self):
        self.approve(reference=True,period=False)
        item=self.run_export()[0]['notices'][0]
        self.assertEqual(item['application_status'],'unknown')
        self.assertEqual(item['application_period'],{})

    def test_changed_source_cannot_carry_approval(self):
        self.conditions();self.approve()
        monitor.collect_source(self.db,SOURCE,fetcher=lambda _:(feed(description='수정된 모의 내용'),200,'text/xml'),force=True)
        self.assertEqual(self.run_export()[0]['notices'],[])

    def test_changed_link_invalidates_structured_conditions(self):
        self.conditions();self.approve()
        self.db.execute("INSERT INTO programs VALUES ('fixture','fixture','fixture')")
        self.db.execute("INSERT INTO application_rounds(round_id,program_id,label) VALUES ('fixture-round','fixture','fixture')")
        self.db.execute("UPDATE discovered_notices SET program_id='fixture', round_id='fixture-round'")
        self.db.commit()
        item=self.run_export()[0]['notices'][0]
        self.assertFalse(item['recommendation_eligible'])
        self.assertEqual(item['eligibility']['conditions'],[])

    def test_new_eligibility_revision_cannot_inherit_export_permission(self):
        self.conditions(); self.approve()
        eligibility.review(self.db,self.identity,'applicant','verified','fixture','later condition review')
        item = self.run_export()[0]['notices'][0]
        self.assertFalse(item['recommendation_eligible'])
        self.assertEqual(item['eligibility']['conditions'],[])

    def test_contact_or_secret_url_omits_record(self):
        self.conditions();self.approve()
        for text in ('mock@example.invalid','010-0000-0000'):
            self.db.execute('UPDATE discovered_notices SET title=?',(text,));self.db.commit()
            self.assertEqual(self.run_export()[0]['notices'],[])
        self.db.execute("UPDATE discovered_notices SET title='fixture',original_url='https://www.mafra.go.kr/?serviceKey=MOCK'")
        self.db.commit()
        self.assertEqual(self.run_export()[0]['notices'],[])

    def test_readonly_export_does_not_change_database_bytes(self):
        self.conditions();self.approve()
        path=Path(self.temp.name)/'monitor.sqlite3'
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        self.run_export()
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_exported_json_is_consumed_by_actual_browser_matching_module(self):
        node=os.environ.get('NODE_BINARY') or shutil.which('node')
        if not node:
            self.skipTest('Node absent; set NODE_BINARY to run cross-language integration')
        self.conditions();self.approve()
        data=self.run_export()[0]
        code="""
const fs=require('node:fs'),vm=require('node:vm');
const data=JSON.parse(fs.readFileSync(0,'utf8')),ctx={URL};
vm.runInNewContext(fs.readFileSync('assets/support-public.js','utf8'),ctx);
const api=ctx.MunongsaSupport,p={applicant:'individual',residenceRegion:'전북',residenceDistrict:'김제시'};
const now=Date.parse('2026-10-26T00:00:00Z');
const cases=[p,{...p,residenceRegion:'전남',residenceDistrict:'나주시'},{...p,residenceRegion:'',residenceDistrict:''}];
console.log(JSON.stringify(cases.map(profile=>{const r=api.explore(data,profile,now);return {recommended:r.recommendations.length,excluded:r.excluded.length,status:api.evaluate(data.notices[0],profile).conditionStatus}})));
"""
        result=subprocess.run([node,'-e',code],input=json.dumps(data,ensure_ascii=False),text=True,
                              capture_output=True,cwd=monitor.ROOT,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0)
        actual=json.loads(result.stdout)
        self.assertEqual([r['status'] for r in actual],['match','mismatch','check'])
        self.assertEqual([r['recommended'] for r in actual],[1,0,1])
        self.assertEqual([r['excluded'] for r in actual],[0,1,0])

    def test_actual_operational_db_and_public_files_preserved(self):
        # Read-only inspection: never approve, initialize or collect in the real DB.
        path=monitor.ROOT/'work/support-monitor/monitor.sqlite3'
        if not path.is_file():
            self.skipTest('operational DB absent')
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        with closing(monitor.connect(path.parent,readonly=True)) as db:
            data,stats=public.export(db,{},NOW)
        self.assertEqual(data['notices'],[])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)


if __name__=='__main__':
    unittest.main()
