import json,unittest
from unittest.mock import patch
import rag_catalogue,rag_dialogue

class EmptyRecommendation(unittest.TestCase):
    def test_selected_conditions_preserved_without_stale_list(self):
        context={'region':'제주','farm_registered':'no','notice_ids':['NOTICE-old'],'last_kind':'results'}
        question=rag_dialogue.PREFIX+json.dumps(context,ensure_ascii=False)+rag_dialogue.SEPARATOR+'선택한 조건으로 지원사업을 찾아주세요.'
        with patch.object(rag_catalogue,'matches',return_value=[]):
            result=rag_catalogue.respond(question,{'guidance_feed':{'notices':[]},'documents':{}})
        self.assertEqual(result['status'],'no_evidence')
        self.assertEqual(result['programs'],[])
        self.assertEqual(result['sources'],[])
        self.assertEqual(result['conversation']['region'],'제주')
        self.assertNotIn('notice_ids',result['conversation'])
        self.assertIn('신청 자격이 없다는 뜻은 아닙니다',result['answer'])

    def test_other_intent_keeps_existing_routing(self):
        with patch.object(rag_catalogue,'matches',return_value=[]):
            self.assertIsNone(rag_catalogue.respond('감자 재배 방법',{'guidance_feed':{'notices':[]},'documents':{}}))

    def test_changed_conditions_do_not_reuse_previous_list(self):
        context={'region':'제주','notice_ids':['NOTICE-old'],'last_kind':'results'}
        question=rag_dialogue.PREFIX+json.dumps(context,ensure_ascii=False)+rag_dialogue.SEPARATOR+'선택한 조건으로 지원사업을 찾아주세요.'
        notice={'id':'NOTICE-new','title':'새 공고','url':'https://www.rda.go.kr/young/custom/policy/view.do?sId=1'}
        card={'name':'새 공고','card':{'label':'지역 확인 필요','period_state':'unknown'},'comparison':{'checks':['지역 확인'],'decision':{'region_state':'check','tier':2}},'source_url':notice['url'],'checked_at':'2026-11-22T00:00:00Z'}
        with patch.object(rag_catalogue,'matches',return_value=[notice]),patch.object(rag_catalogue,'program',return_value=card):
            result=rag_catalogue.respond(question,{'guidance_feed':{'notices':[]},'documents':{}})
        self.assertEqual(result['conversation']['notice_ids'],['NOTICE-new'])
        self.assertEqual(result['catalogue_total'],1)

if __name__=='__main__':unittest.main()
