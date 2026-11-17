"""Independent synthetic 19-record fixtures only; never apply an operational plan."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import supplement_support_details as s
import review_support_details as review
import rag_search

class SupplementTests(unittest.TestCase):
    def setUp(self):
        work=Path(__file__).resolve().parents[1]/'work/supplement-tests';work.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=work);self.root=Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(work.resolve()))
        self.asset=self.root/'synthetic.json';self.backups=self.root/'backups'
        ids=sorted(s.TARGET_IDS)+['NOTICE-synthetic-'+str(i) for i in range(12)]
        stamp='2026-11-17T00:00:00+00:00';self.items=[];records=[]
        for identity in ids:
            item={'id':identity,'title':'Synthetic agricultural notice '+identity,'url':'https://www.rda.go.kr/young/custom/policy/view.do?sId=1',
                  'region':'unknown','target':'unknown','publication':'approved_reference','verification_status':'verified',
                  'freshness':'current','rights':{'public_display':'allowed'}}
            self.items.append(item);proof={'url':item['url'],'location':'synthetic fixture','checked_at':stamp}
            records.append({'basis':rag_search.basis(item),'rights':{'facts_only':True,'policy_url':item['url']},
                            'approval':{'state':'approved','reviewer':'synthetic-old','reference':'fixture','checked_at':stamp},
                            'fields':{'summary':{'value':'Synthetic original summary','evidence':proof},
                                      'conditions':{'value':['Synthetic original condition'],'evidence':proof},
                                      'unconfirmed':{'value':['Synthetic unknown'],'evidence':proof}}})
        self.doc={'schema':'munongsa-support-details-v1','preview':False,'records':records,'link_reviews':[{'preserve':'synthetic link history'}]}
        self.raw=s.encoded(self.doc);self.asset.write_bytes(self.raw);add=[]
        for old in records[:7]:
            r=copy.deepcopy(old);r.pop('approval');r['fields']={'contact':{'value':'SYNTHETIC-SUPPLEMENT-ONLY','evidence':copy.deepcopy(old['fields']['summary']['evidence'])}}
            r['rights'].update(display_scope=review.FACT_SCOPE,public_fields=['contact'],audience='detail_display_only',
                 eligibility_approval=False,body_redistribution=False,attachment_redistribution=False,use_basis={'kind':'independent_facts','urls':['https://www.law.go.kr/']})
            add.append(r)
        self.plan={'schema':s.SCHEMA,'base_asset_sha256':s.sha(self.raw),'base_record_versions':{r['basis']['id']:s.version(r) for r in records},'replacements':[],'records':add}
        self.plan_raw=s.encoded(self.plan);self.digest=s.sha(self.plan_raw)
    def tearDown(self):self.temp.cleanup()
    def apply_synthetic(self):return s.apply_file(self.asset,self.plan_raw,self.digest,'synthetic-test','synthetic approval only',self.backups)
    def test_read_only_preparation(self):
        _,changes,done=s.prepare(self.raw,self.plan,self.digest)
        self.assertFalse(done);self.assertEqual(len(changes),7);self.assertEqual(self.asset.read_bytes(),self.raw)
        self.assertFalse(self.backups.exists())
    def test_preserve_nineteen_and_back_up_exact_bytes(self):
        result=self.apply_synthetic();doc=json.loads(self.asset.read_bytes())
        self.assertEqual(doc['records'],self.doc['records']);self.assertEqual(doc['link_reviews'],self.doc['link_reviews'])
        self.assertEqual({r['basis']['id'] for r in doc['detail_supplements']},s.TARGET_IDS)
        self.assertEqual(result['added_fields'],7);backup=Path(result['backup'])
        self.assertEqual((backup/'original.json').read_bytes(),self.raw)
        audit=json.loads((backup/'audit.json').read_text(encoding='utf8'));self.assertEqual(audit['after_file_sha256'],s.sha(self.asset.read_bytes()))
    def test_repeated_execution_is_byte_identical(self):
        self.apply_synthetic();after=self.asset.read_bytes();result=self.apply_synthetic()
        self.assertEqual(result['status'],'already_applied');self.assertEqual(self.asset.read_bytes(),after)
        self.assertEqual(len(list(self.backups.iterdir())),1)
    def test_wrong_approval_or_original_hash_stops(self):
        with self.assertRaisesRegex(ValueError,'explicit_exact_approval_required'):
            s.apply_file(self.asset,self.plan_raw,'wrong','synthetic','test',self.backups)
        self.asset.write_bytes(self.raw+b' ')
        with self.assertRaisesRegex(ValueError,'original_file_hash_mismatch'):self.apply_synthetic()
        self.assertFalse(self.backups.exists())
    def test_existing_value_or_target_change_stops(self):
        p=copy.deepcopy(self.plan);r=p['records'][0];r['fields']={'summary':r['fields']['contact']};r['rights']['public_fields']=['summary']
        with self.assertRaisesRegex(ValueError,'replacement_forbidden'):s.prepare(self.raw,p,s.version(p))
        p=copy.deepcopy(self.plan);p['records'][0]['basis']['id']='NOTICE-not-authorized'
        with self.assertRaisesRegex(ValueError,'exact_seven'):s.prepare(self.raw,p,s.version(p))
        p=copy.deepcopy(self.plan);p['replacements']=['summary']
        with self.assertRaisesRegex(ValueError,'no_replacement'):s.prepare(self.raw,p,s.version(p))
    def test_existing_approval_changes_and_replay_corruption_stop(self):
        changed=copy.deepcopy(self.doc);changed['records'][0]['approval']['reference']='changed'
        with self.assertRaisesRegex(ValueError,'existing_record_version_changed'):s.prepare(s.encoded(changed),self.plan,self.digest)
        self.apply_synthetic();changed=json.loads(self.asset.read_bytes());changed['detail_supplements'][0]['fields']['contact']['value']='tampered'
        with self.assertRaisesRegex(ValueError,'applied_state_changed'):s.prepare(s.encoded(changed),self.plan,self.digest)
    def test_replace_failure_preserves_original_and_backup(self):
        with patch.object(s.os,'replace',side_effect=OSError('synthetic failure')),self.assertRaises(OSError):self.apply_synthetic()
        self.assertEqual(self.asset.read_bytes(),self.raw)
        self.assertEqual(len(list(self.backups.glob('*/original.json'))),1)
    def test_gpt_still_uses_only_original_record(self):
        first=self.doc['records'][0];specs={'synthetic':{'id':first['basis']['id'],'record_sha':rag_search.record_sha(first),'summary_only':True}}
        feed={'schema_version':'munongsa-support-public-v1','notices':self.items}
        self.apply_synthetic();after=json.loads(self.asset.read_bytes())
        def load(details):
            with patch.object(rag_search,'read_json',side_effect=[details,feed]):
                return rag_search.load_corpus(specs_override=specs,aliases_override={})
        before_corpus=load(self.doc);after_corpus=load(after)
        self.assertTrue(before_corpus['chunks']);self.assertEqual(before_corpus,after_corpus)
        self.assertNotIn('SYNTHETIC-SUPPLEMENT-ONLY',json.dumps(after_corpus))

if __name__=='__main__':unittest.main()
