import copy
import json
import sqlite3
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import support_guidance as g

NOW=datetime(2026,11,14,9,tzinfo=timezone.utc)
URL='https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_123456'

def row(**kw):
    return dict(notice_id='test-1',source_id='bizinfo-support-api',original_url=URL,
                title='농업 창업 지원사업 모집',institution='중소벤처기업부·기업마당',
                content_hash='a'*64,publication='review',hints_json='{}',**kw)

def origin():
    return {'title':row()['title'],'original_url':URL,'description':'농업 창업 지원','api_fields':{}}

class Tests(unittest.TestCase):
    def plan(self,rows=None,portal=None,valid=True):
        return g.select(rows or [row()],portal or [origin()],lambda u:valid,NOW)
    def test_minimal_metadata_not_eligibility(self):
        p=self.plan();self.assertEqual(len(p['items']),1)
        self.assertNotIn('description',p['items'][0]);self.assertEqual(p['summary']['pending_examined'],1)
    def test_missing_conditions_do_not_block(self):
        self.assertEqual(self.plan()['summary']['new_guidance'],1)
    def test_unknown_source_rights_hold(self):
        r=row();r['source_id']='other-source'
        p=self.plan([r]);self.assertEqual(p['decisions'][0]['hold_reason'],'source_reuse_policy_unconfirmed')
    def test_bad_link_and_changed_title_hold(self):
        self.assertFalse(self.plan(valid=False)['items'])
        o=origin();o['title']='다른 사업';self.assertFalse(self.plan(portal=[o])['items'])
    def test_duplicate_and_unrelated_hold(self):
        r=row();r['notice_id']='test-2'
        self.assertEqual(len(self.plan([row(),r])['items']),1)
        r=row();r['title']='농업 채용 공고';self.assertFalse(self.plan([r])['items'])
    def test_unsafe_data_hold(self):
        r=row();r['title']='농업 지원 user@example.com';o=origin();o['title']=r['title']
        self.assertFalse(self.plan([r],[o])['items'])
    def test_export_hash_expiry_revoke_and_no_db_write(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE discovered_notices(notice_id,publication,content_hash,title,original_url,source_id)')
        r=row();db.execute('INSERT INTO discovered_notices VALUES(?,?,?,?,?,?)',tuple(r[k] for k in ('notice_id','publication','content_hash','title','original_url','source_id')))
        p=self.plan();feed={'notices':[]};n=db.total_changes
        self.assertEqual(g.append(db,feed,p,NOW),1);self.assertEqual(db.total_changes,n)
        item=feed['notices'][0];self.assertFalse(item['recommendation_eligible']);self.assertEqual(item['application_status'],'unknown')
        self.assertEqual(item['eligibility']['conditions'],[])
        self.assertEqual(g.append(db,{'notices':[]},p,NOW+timedelta(days=4)),0)
        db.execute("UPDATE discovered_notices SET content_hash='changed'")
        self.assertEqual(g.append(db,{'notices':[]},p,NOW),0)
        db.execute("UPDATE discovered_notices SET content_hash=?,publication='hidden'",(r['content_hash'],))
        self.assertEqual(g.append(db,{'notices':[]},p,NOW),0)
    def test_license_cannot_be_silently_replaced(self):
        p=self.plan();p['policy']['license']='free'
        self.assertEqual(g.append(None,{'notices':[]},p,NOW),0)
        self.assertNotEqual(g.POLICY['license'],'free')

if __name__=='__main__':unittest.main()
