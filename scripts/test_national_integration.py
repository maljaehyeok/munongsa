"""Synthetic integration boundary tests; no operating DB, API or browser calls."""
import copy,json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from prepare_national_integration import integrate
from test_national_candidates import row,group
from collect_national_candidates import prepare
from run_support_collection import hold_new_guidance


class IntegrationTests(unittest.TestCase):
    def candidate(self,ident):
        item=prepare([group(row(ident))],{'notices':[]})['candidates'][0]
        item['basic_release_review']={'status':'candidate','approved':False,
            'allowed_fields':['title','institution','official_url'],'requires_operator_approval':True}
        return item

    def inventory(self):return {'notices':[],'public_feed':{'notices':[]}}

    def test_two_batches_preserve_facts_and_do_not_approve(self):
        a,b=self.candidate(1),self.candidate(2);b['title']='다른 농업 지원 신청'
        batches=[{'candidates':[a]},{'candidates':[b]}];before=copy.deepcopy(batches)
        result=integrate(batches,self.inventory());self.assertEqual(batches,before)
        self.assertEqual(result['summary']['basic_approval_candidates'],2)
        self.assertEqual(result['summary']['readiness_categories'],{'D':2})
        self.assertEqual(result['summary']['actual_approved'],0)

    def test_known_id_and_repeat_removed_without_title_merging(self):
        a,b=self.candidate(1),self.candidate(2);inv=self.inventory()
        inv['notices']=[{'original_url':a['official_url'],'title':a['title']}]
        r=integrate([{'candidates':[a,b,b]}],inv)['summary']
        self.assertEqual(r['operating_id_duplicates'],1);self.assertEqual(r['within_batch_duplicates'],1)
        self.assertEqual(r['distinct_official_notice_ids'],1)
        self.assertEqual(r['cross_source_duplicate_suspects'],1);self.assertEqual(r['basic_approval_candidates'],0)

    def test_conflicting_same_id_is_held_and_not_overwritten(self):
        a=self.candidate(1);b=copy.deepcopy(a);b['title']='충돌 공고'
        result=integrate([{'candidates':[a,b]}],self.inventory())
        self.assertEqual(result['candidates'][0]['title'],a['title'])
        self.assertEqual(result['summary']['conflicting_batches'],1)
        self.assertEqual(result['summary']['basic_approval_candidates'],0)

    def test_changed_notice_is_not_a_new_confirmed_program(self):
        a=self.candidate(1);a['title']='농업 지원 신청기간 연장 공고'
        r=integrate([{'candidates':[a]}],self.inventory())['summary']
        self.assertEqual(r['changed_notice_review'],1);self.assertEqual(r['basic_approval_candidates'],0)

    def test_actual_approval_cannot_enter_review_batch(self):
        for field,value in [('publication','approved'),('recommendation_eligible',True)]:
            a=self.candidate(1);a[field]=value
            with self.assertRaises(ValueError):integrate([{'candidates':[a]}],self.inventory())

    def test_collector_manifest_contains_new_runtime_dependencies(self):
        root=Path(__file__).resolve().parents[1]
        listed=set((root/'deploy/collector/release-files.txt').read_text().splitlines())
        for name in ('core_facts','api_core','regional'):
            self.assertIn('scripts/support_runtime/'+name+'.py',listed)

    def test_release_fence_retains_existing_and_independent_approvals(self):
        prior={'notices':[{'id':'existing'},{'id':'revoked'}]}
        before=copy.deepcopy(prior)
        data={'notices':[{'id':'existing','publication':'official_guidance'},
            {'id':'new','publication':'official_guidance'},
            {'id':'manual','publication':'approved_reference'}]}
        self.assertEqual(hold_new_guidance(data,prior),1)
        self.assertEqual([n['id'] for n in data['notices']],['existing','manual'])
        self.assertEqual(prior,before)

    def test_no_previous_feed_does_not_grant_new_guidance(self):
        data={'notices':[{'id':'new','publication':'official_guidance'}]}
        self.assertEqual(hold_new_guidance(data,{'notices':[]}),1)
        self.assertEqual(data['notices'],[])

    def test_export_fence_is_applied_after_existing_rights_gate(self):
        import run_support_collection as runtime
        from support_runtime.periods import as_of
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/'private';output=Path(tmp)/'public';rights=state/'rights.json'
            runtime.execute(state,output,rights,runtime.sources(),groups=[],now=as_of())
            rights.write_text('{}');(state/'official-guidance.json').write_text('{}')
            (output/'support-public.json').write_text(json.dumps({'notices':[{'id':'existing'}]}))
            def append(db,feed,*args):
                feed['notices'].extend([{'id':'existing','publication':'official_guidance'},
                    {'id':'new','publication':'official_guidance'}]);return 2
            with patch.dict('os.environ',{'MUNONGSA_GUIDANCE_EXISTING_ONLY':'1'}),patch('support_guidance.append',side_effect=append):
                stats=runtime.export_public(state,output,rights)
            self.assertEqual(stats['new_guidance_held'],1)
            self.assertEqual([n['id'] for n in json.loads((output/'support-public.json').read_text())['notices']],['existing'])


if __name__=='__main__':unittest.main()
