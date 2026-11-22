import unittest,json
import rag_dialogue,rag_profile,rag_nlu

class PracticalDialogue(unittest.TestCase):
    def test_generated_reply_boundary(self):
        value={'intent':'other','facts':{},'hypothetical':False,'reply':'잠깐 쉬며 좋아하는 음악을 들어보면 어떨까요?'}
        self.assertTrue(rag_nlu.safe_conversation_reply(value,'기분 전환하고 싶어요'))
        for q in ['대출 받을 수 있어?','오늘 기온은?','계약을 해지해도 돼?','약품을 추천해줘']:
            self.assertFalse(rag_nlu.safe_conversation_reply(value,q))
        for text in ['지원금 받아요','금리는 낮아요','이번 주 모집 중이에요','https://example.com','백만원 대출 가능해요']:
            self.assertFalse(rag_nlu.safe_conversation_reply({**value,'reply':text},'기분 전환'))
    def test_shared_municipality(self):
        facts,_=rag_profile.extract('경기도 하남시에 살고 제주에서 농사짓고 있어요',rag_dialogue.AREAS,rag_dialogue.CROPS,rag_dialogue.normalized)
        self.assertEqual(facts['region'],'경기 하남시')
        self.assertEqual(facts['farm_region'],'제주')
        c={'region':'경남 산청군','farm_region':'제주','applicant':'agricultural_corporation'}
        q=rag_dialogue.PREFIX+json.dumps(c,ensure_ascii=False)+rag_dialogue.SEPARATOR+'안녕'
        self.assertEqual(rag_dialogue.decode(q)[1],c)
        self.assertEqual(rag_profile.region_state(c['region'],['경남 산청군'],rag_dialogue.AREAS),'match')
        self.assertEqual(rag_profile.region_state(c['farm_region'],['경남 산청군'],rag_dialogue.AREAS),'mismatch')
        self.assertFalse(rag_profile.valid_area('경기 산청군',rag_dialogue.AREAS))
    def test_smalltalk_no_recommendations(self):
        for q in ['점심 뭐 먹지','피곤해','오늘 날씨 어때','농담해줘']:
            out=rag_dialogue.service_response(q,{'documents':{}})
            self.assertEqual(out['programs'],[])
            self.assertEqual(out['kind'],'context')
    def test_finance_actual_and_hypothetical(self):
        out=rag_dialogue.service_response('전주에 살고 경영체 미등록인데 대출은?',{'documents':{}})
        self.assertEqual(out['conversation']['region'],'전주')
        self.assertEqual(out['conversation']['farm_registered'],'no')
        self.assertFalse(out['programs'])
        out=rag_dialogue.service_response('만약 경영체 등록하면 대출 받을 수 있나요?',{'documents':{}})
        self.assertNotIn('farm_registered',out['conversation'])

if __name__=='__main__':unittest.main()
