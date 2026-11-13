"""Synthetic follow-up tests; no model/network/operating database access."""
import copy,json,unittest
from unittest.mock import patch
import rag_api as api,rag_dialogue as d,rag_nlu as nlu
from test_region_accuracy import document

class FollowupContext(unittest.TestCase):
    def setUp(self):
        self.docs={}
        for i in range(3):
            doc=document(str(i+1),'전국',scopes=['전국'])
            doc['public']['title']='가상 사업 '+str(i+1)
            doc['record']['basis']={'dates':{'start':{'date':'2020-01-01'},'end':{'date':'2099-12-31' if i!=1 else '2020-12-31'}},'url':'https://www.rda.go.kr/'}
            self.docs[str(i+1)]=doc
        self.corpus={'documents':self.docs,'aliases':{},'sync_generation':'synthetic','sync_verified':True}
    def grounded(self,q,corpus,key):
        doc=self.docs[key]
        return d.response('가상 근거 '+key+' / '+q,{},programs=[{'id':doc['public']['id'],'name':doc['public']['title'],'application_period':{'description':'날짜 기준 · 접수 미확인'},'required_conditions':[],'additional_checks':[]}])
    def run_q(self,q,c=None,value=None):
        encoded=d.PREFIX+json.dumps(c or {},ensure_ascii=False)+d.SEPARATOR+q
        with patch.object(api,'load_api_corpus',return_value=self.corpus),patch.object(api,'grounded_response',side_effect=self.grounded),patch.object(api,'decorate_cards'),patch.object(nlu,'interpret',return_value=value) as mock,patch.dict('os.environ',{},clear=True):
            out=api.local_pipeline(encoded);return out,mock.call_count
    def listed(self):
        ps=[self.grounded('',self.corpus,k)['programs'][0] for k in self.docs]
        return d.remember(d.response('가상 목록',{'region':'전주','farm_region':'김제','farm_registered':'no'},'recommendation',programs=ps),self.corpus)['conversation']
    def test_greeting_and_service_reexplanation_cost_zero(self):
        out,_=self.run_q('안녕')
        for q in ('응?','무슨 뜻이야?','다시 설명해 줘.'):
            out,calls=self.run_q(q,out['conversation']);self.assertEqual(calls,0);self.assertIn('쉽게 말해',out['answer']);self.assertFalse(out['programs'])
    def test_repeat_keeps_list_order_and_versions(self):
        c=self.listed();out,calls=self.run_q('다시 설명해 줘.',c)
        self.assertEqual([p['id'] for p in out['programs']],c['list_ids']);self.assertEqual(out['conversation']['list_versions'],c['list_versions']);self.assertEqual(calls,0)
    def test_second_deadline_scopes_to_exact_id(self):
        c=self.listed();out,calls=self.run_q('두 번째 사업의 마감일은?',c)
        self.assertEqual([p['id'] for p in out['programs']],['NOTICE-2']);self.assertIn('모집기간 마감',out['answer']);self.assertEqual(out['conversation']['list_ids'],c['list_ids']);self.assertEqual(calls,0)
    def test_first_third_comparison_preserves_original_order(self):
        out,_=self.run_q('첫 번째랑 세 번째 사업을 비교해 줘.',self.listed())
        self.assertEqual([p['id'] for p in out['programs']],['NOTICE-1','NOTICE-3']);self.assertTrue(all('comparison' in p for p in out['programs']))
    def test_group_eligibility_is_not_certification(self):
        out,_=self.run_q('그중 내가 신청할 수 있는 건?',self.listed())
        self.assertEqual(len(out['programs']),3);self.assertIn('확정하지',out['answer'])
    def test_recorded_period_filter_does_not_mean_reception(self):
        out,_=self.run_q('아까 알려준 사업 중 모집 중인 건?',self.listed())
        self.assertEqual([p['id'] for p in out['programs']],['NOTICE-1','NOTICE-3']);self.assertIn('실제 접수',out['answer'])
    def test_missing_changed_or_removed_list_holds(self):
        out,_=self.run_q('두 번째 사업의 마감일은?');self.assertFalse(out['programs'])
        c=self.listed();self.docs['2']['public']['target']='변경된 가상 대상'
        out,_=self.run_q('두 번째 사업의 마감일은?',c);self.assertFalse(out['programs']);self.assertIn('변경',out['answer'])
        del self.docs['2'];out,_=self.run_q('첫 번째 사업은 얼마야?',c);self.assertFalse(out['programs'])
    def test_correction_and_unclear_question_do_not_edit_profile(self):
        c=self.listed();out,calls=self.run_q('아니, 내 말은 그게 아니라.',c)
        for key in ('region','farm_region','farm_registered'):self.assertEqual(out['conversation'][key],c[key])
        self.assertFalse(out['programs']);self.assertEqual(calls,0)
    def test_hypothetical_and_actual_changes_still_use_original_pipeline(self):
        c=self.listed();out,_=self.run_q('그럼 등록하면 받을 수 있는 사업은?',c)
        self.assertEqual(out['conversation']['farm_registered'],'no');self.assertIn('가정',out['answer'])
        out,_=self.run_q('안산에 살고 김제에서 농사 시작할 예정이야.',c)
        self.assertEqual(out['conversation']['region'],'안산');self.assertEqual(out['conversation']['farm_region'],'김제')
    def test_model_paraphrase_uses_same_bounded_reexplanation(self):
        v={'intent':'rephrase','facts':{},'hypothetical':False,'reference_previous':False,'uncertain':[]}
        out,calls=self.run_q('조금 쉽게 풀어 줄래?',self.listed(),v)
        self.assertEqual(calls,1);self.assertEqual(len(out['programs']),3)
    def test_model_input_has_only_count_and_kind_not_businesses(self):
        c=self.listed();p=nlu.make_request('조금 쉽게 풀어 줄래?',c);text=json.dumps(p,ensure_ascii=False)
        self.assertNotIn('NOTICE-',text);self.assertNotIn('가상 사업',text);self.assertNotIn(c['list_versions'][0],text)
        self.assertEqual(json.loads(p['input'])['previous_count'],3)
    def test_malformed_versions_rejected(self):
        c=self.listed();c['list_versions'][0]='invalid'
        with self.assertRaises(ValueError):d.decode(d.PREFIX+json.dumps(c)+d.SEPARATOR+'응?')
    def test_ambiguous_business_and_next_step_request_selection(self):
        for q in ('그 사업의 서류는?','그럼 어떻게 해야 해?'):
            out,_=self.run_q(q,self.listed());self.assertFalse(out['programs']);self.assertEqual(out['kind'],'clarify');self.assertTrue(out['suggestions'])
    def test_explicit_fresh_selection_replaces_stale_list(self):
        c=self.listed();self.docs['2']['public']['target']='변경된 가상 대상'
        out=d.remember(d.response('새로 선택한 공고',c,'answer',programs=[self.grounded('',self.corpus,'2')['programs'][0]]),self.corpus)
        self.assertEqual(out['conversation']['list_ids'],['NOTICE-2'])

if __name__=='__main__':unittest.main()
