"""Synthetic facts only. No network, production DB or private evidence."""
import unittest
from datetime import datetime,timedelta,timezone
import rag_api,rag_dialogue


class ResultCards(unittest.TestCase):
    def document(self,identity,registration=True,elapsed=False):
        today=datetime.now(timezone.utc).date()
        dates={'start':{'date':str(today-timedelta(days=10))},'end':{'date':str(today+timedelta(days=-1 if elapsed else 10))}}
        evidence={'url':'https://www.rda.go.kr/example','location':'가상 검증 위치','checked_at':'2026-11-12T00:00:00+09:00'}
        return {'public':{'id':identity,'title':'가상 지원사업 '+identity,'region':'경기 파주시','target':'등록 농업인','support':'가상 지원 내용','institution':'가상 기관'},
                'record':{'basis':{'dates':dates,'url':evidence['url']},'fields':{'conditions':{'value':['농업경영체 등록 필요'] if registration else [],'evidence':evidence},'unconfirmed':{'value':['세부 자격 확인 필요']}}}}

    def result(self,document):
        return {'id':document['public']['id'],'required_conditions':[],'additional_checks':[],'application_period':{}}

    def test_mismatch_is_not_highlighted_as_related(self):
        d=self.document('NOTICE-SYNTHETIC');out={'programs':[self.result(d)],'conversation':{'farm_registered':'no','region':'파주'}}
        rag_api.decorate_cards(out,{'documents':{'one':d}})
        self.assertEqual(out['programs'][0]['card']['group'],'mismatch')

    def test_elapsed_and_eligibility_are_separate(self):
        d=self.document('NOTICE-SYNTHETIC',elapsed=True);out={'programs':[self.result(d)],'conversation':{'farm_registered':'yes'}}
        rag_api.decorate_cards(out,{'documents':{'one':d}})
        self.assertEqual(out['programs'][0]['card']['group'],'elapsed')
        self.assertEqual(out['programs'][0]['comparison']['label'],'관련 가능성 있음')

    def test_live_candidate_precedes_expired_candidate(self):
        old=self.document('NOTICE-OLD',elapsed=True);new=self.document('NOTICE-NEW');corpus={'documents':{'old':old,'new':new}}
        self.assertLess(rag_dialogue.candidate_order('new',corpus,{},1),rag_dialogue.candidate_order('old',corpus,{},3))

    def test_region_relevance_never_confirms_eligibility(self):
        d=self.document('NOTICE-SYNTHETIC');out={'programs':[self.result(d)],'conversation':{'farm_registered':'yes','region':'전주'}}
        rag_api.decorate_cards(out,{'documents':{'one':d}})
        self.assertEqual(out['programs'][0]['card']['group'],'check')

    def test_missing_or_unverified_funding_is_not_filled_in(self):
        d=self.document('NOTICE-SYNTHETIC');d['record']['fields']['funding']={'value':['999억원']}
        out={'programs':[self.result(d)],'conversation':{}};rag_api.decorate_cards(out,{'documents':{'one':d}})
        self.assertEqual(out['programs'][0]['card']['facts']['funding'],[])
        self.assertLessEqual(len(out['followup_questions']),2)


if __name__=='__main__':unittest.main()
