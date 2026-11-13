"""Focused, offline consultation tests. Synthetic corpus only; no OpenAI calls."""
import json,unittest
from unittest.mock import patch
import rag_api as api,rag_dialogue as d,rag_nlu as nlu
from test_region_accuracy import document

class ConsultationFlow(unittest.TestCase):
    def setUp(self):
        self.doc=document('jeonju','전북 전주시',scopes=['전북 전주시'])
        self.doc['record']['basis']={'dates':{'start':None,'end':None},'url':'https://www.rda.go.kr/','checked_at':'2026-11-13T09:00:00+09:00'}
        self.corpus={'documents':{'one':self.doc},'aliases':{},'sync_generation':'synthetic','sync_verified':True}
    def encoded(self,q,c=None):return d.PREFIX+json.dumps(c or {},ensure_ascii=False)+d.SEPARATOR+q
    def grounded(self,q,corpus,key):
        return {'mode':'local','status':'answered','answer':'가상 공고의 저장된 근거입니다.','sources':[],
          'programs':[{'id':self.doc['public']['id'],'name':self.doc['public']['title'],'application_period':{'description':'기간 미확인'},'required_conditions':[],'additional_checks':[]}]}
    def run_question(self,q,c=None,interpretation=None):
        with patch.object(api,'load_api_corpus',return_value=self.corpus),patch.object(api,'grounded_response',side_effect=self.grounded),patch.object(api,'decorate_cards'),patch.object(nlu,'interpret',return_value=interpretation) as model,patch.dict('os.environ',{},clear=True):
            out=api.local_pipeline(self.encoded(q,c));return out,model.call_count
    def test_intro_variants_use_no_model_and_no_fake_programs(self):
        for q in ('안녕','안녕, 너는 무슨 역할이 가능하니?','너는 누구야?','무농사는 어떤 서비스야?','어떤 도움을 줄 수 있어?','지원사업도 찾아줄 수 있어?','내가 어떤 정보를 알려주면 돼?'):
            with self.subTest(q=q):
                out,calls=self.run_question(q)
                self.assertEqual(calls,0);self.assertEqual(out['kind'],'help');self.assertEqual(out['programs'],[])
                self.assertIn('공식 농업 지원사업',out['answer']);self.assertLessEqual(len(out['followup_questions']),2)
    def test_known_conditions_not_reasked_or_lost(self):
        c={'region':'전주','farm_region':'김제','farm_registered':'no','notice_ids':['NOTICE-jeonju']}
        out,calls=self.run_question('내가 어떤 정보를 알려주면 돼?',c)
        self.assertTrue(all(out['conversation'][k]==v for k,v in c.items()));self.assertEqual(out['followup_questions'],[]);self.assertEqual(calls,0)
    def test_edit_offers_existing_ui_and_preserves_profile(self):
        out,calls=self.run_question('내 조건을 바꾸고 싶어.',{'region':'전주'})
        self.assertEqual(out['kind'],'condition_edit');self.assertEqual(out['conversation']['region'],'전주');self.assertEqual(calls,0)
    def test_gpt_help_intent_is_consumed_for_paraphrase(self):
        value={'intent':'help','facts':{},'hypothetical':False,'reference_previous':False,'uncertain':[]}
        out,calls=self.run_question('상담 기능 좀 소개해 줄래?',interpretation=value)
        self.assertEqual(out['kind'],'help');self.assertEqual(out['understanding'],'gpt');self.assertEqual(calls,1)
    def test_intro_does_not_swallow_specific_grant_question(self):
        self.assertIsNone(d.service_response('안녕, 전주 사업 신청 자격은?',self.corpus,'help'))
        self.assertIsNone(d.service_response('전주에 살고 김제에서 농사를 시작하려고 해.',self.corpus,'help'))
    def test_actual_sequence_and_hypothetical_registration(self):
        out,_=self.run_question('나는 전주에 살고 김제에서 농사를 시작하려고 해.')
        self.assertEqual(out['conversation']['region'],'전주');self.assertEqual(out['conversation']['farm_region'],'김제')
        out,_=self.run_question('아직 농업경영체 등록을 안 했어.',out['conversation'])
        self.assertEqual(out['conversation']['farm_registered'],'no')
        out,_=self.run_question('그럼 등록하면 받을 수 있는 사업은?',out['conversation'])
        self.assertEqual(out['conversation']['farm_registered'],'no');self.assertIn('가정',out['answer'])
    def test_other_region_query_keeps_actual_residence(self):
        out,_=self.run_question('나는 안산에 사는데 전주 사업도 신청할 수 있어?')
        self.assertEqual(out['conversation']['region'],'안산')
        self.assertEqual(out['programs'][0]['comparison']['label'],'조건 불일치')
    def test_unknown_general_question_is_bounded(self):
        out,calls=self.run_question('오늘 날씨 어때?')
        self.assertEqual(calls,0);self.assertEqual(out['programs'],[]);self.assertIn('안내 범위',out['answer'])
    def test_newcomer_can_search_without_full_profile(self):
        out,_=self.run_question('농업을 처음 시작하는데 지원받을 수 있을까?')
        self.assertTrue(out['programs']);self.assertNotIn('신청 가능합니다',out['answer'])
    def test_deadline_followup_retains_current_business(self):
        out,_=self.run_question('아까 말한 사업의 마감일은 언제야?',{'notice_ids':['NOTICE-jeonju']})
        self.assertEqual([p['id'] for p in out['programs']],['NOTICE-jeonju'])
    def test_failed_approval_gate_still_blocks_guidance(self):
        with patch.object(api,'load_api_corpus',return_value={**self.corpus,'sync_verified':False}),patch.object(nlu,'interpret') as m:
            with self.assertRaises(api.VerificationError):api.local_pipeline('안녕')
            m.assert_not_called()

if __name__=='__main__':unittest.main()
