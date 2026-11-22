"""Conversation routing regressions: synthetic corpus, no API or database."""
import json,unittest
from unittest.mock import patch
import rag_api as api,rag_dialogue as d,rag_nlu as n

class ConversationRouting(unittest.TestCase):
    def run_question(self,q,c=None,value=None):
        encoded=d.PREFIX+json.dumps(c or {},ensure_ascii=False)+d.SEPARATOR+q
        corpus={'documents':{},'aliases':{},'sync_verified':True,'sync_generation':'synthetic'}
        with patch.object(api,'load_api_corpus',return_value=corpus),patch.object(n,'interpret',return_value=value) as model,patch.dict('os.environ',{},clear=True):
            out=api.local_pipeline(encoded)
        self.assertLessEqual(model.call_count,1)
        return out
    def knowledge(self,reply='농업은 작물과 가축을 길러 먹거리와 생활에 필요한 재료를 얻는 활동이에요.',topic='농업의 의미'):
        return {'intent':'knowledge','facts':{},'hypothetical':False,'reference_previous':False,'uncertain':[],'reply':reply,'topic':topic}
    def test_new_subject_clears_business_not_profile(self):
        c={'crop':'토마토','farm_region':'김제','farm_registered':'no','planned':True,'notice_ids':['NOTICE-old'],'list_ids':[],'list_versions':[],'last_kind':'results'}
        out=self.run_question('농업이 뭐야?',c,self.knowledge())
        self.assertFalse(out['programs']);self.assertIn('작물과 가축',out['answer'])
        for k in ('crop','farm_region','farm_registered','planned'):self.assertEqual(out['conversation'][k],c[k])
        self.assertNotIn('notice_ids',out['conversation'])
        follow=self.run_question('그게 무슨 뜻이야?',out['conversation'],self.knowledge('쉽게 말해, 먹거리와 여러 재료를 얻기 위해 식물을 기르거나 동물을 돌보는 일이에요.'))
        self.assertFalse(follow['programs']);self.assertNotIn('토마토 관련 공고',follow['answer'])
        hints=json.loads(n.make_request('그게 무슨 뜻이야?',out['conversation'])['input'])
        self.assertEqual(hints['conversation_topic'],'농업의 의미');self.assertFalse(hints['has_previous_business'])
    def test_unavailable_model_never_restores_crop_search(self):
        out=self.run_question('농업이 뭐야?',{'crop':'토마토','notice_ids':['NOTICE-old']})
        self.assertEqual(out['status'],'needs_verification');self.assertFalse(out['programs'])
        self.assertNotIn('notice_ids',out['conversation'])
        follow=self.run_question('그게 무슨 뜻이야?',out['conversation'])
        self.assertFalse(follow['programs']);self.assertNotIn('토마토 관련 공고',follow['answer'])
    def test_safety_blocks_official_and_actionable_facts(self):
        for reply in ('신청 가능해요','지원금은 백만원이에요','농약을 살포하세요','내일 모집 중이에요','https://example.com','삼십 퍼센트 보조금이에요'):
            value=self.knowledge(reply)
            self.assertFalse(n.safe_conversation_reply(value,'농업이 뭐야?'))
        for topic in ('<script>','https://example.com','연락처 01000000000'):
            with self.assertRaises(ValueError):d.decode(d.PREFIX+json.dumps({'conversation_topic':topic})+d.SEPARATOR+'안녕')
    def test_smalltalk_replaces_topic_and_keeps_conditions(self):
        v={**self.knowledge('좋아하는 음악이나 가볍게 쉬는 이야기를 나눠도 좋아요.','음악 이야기'),'intent':'other'}
        out=self.run_question('음악 이야기하자',{'crop':'토마토','conversation_topic':'농업의 의미'},v)
        self.assertEqual(out['conversation']['conversation_topic'],'음악 이야기');self.assertFalse(out['programs'])
    def test_budget_and_schema_stay_bounded(self):
        self.assertEqual((n.DAILY_CALLS,n.MINUTE_CALLS,n.MAX_OUTPUT),(30,6,512))
        raw={**self.knowledge(),'facts':[]}
        self.assertEqual(n.validate(raw,'농업이 뭐야?')['topic'],'농업의 의미')
        with self.assertRaises(ValueError):n.validate({**raw,'topic':'x'*81},'농업이 뭐야?')
    def test_unavailable_smalltalk_does_not_resume_old_crop(self):
        out=self.run_question('음악 이야기하자',{'crop':'토마토','notice_ids':['NOTICE-old']})
        self.assertEqual(out['kind'],'context');self.assertFalse(out['programs'])
        self.assertNotIn('notice_ids',out['conversation'])

if __name__=='__main__':unittest.main()
