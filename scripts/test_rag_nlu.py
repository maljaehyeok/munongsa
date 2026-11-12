"""Offline synthetic checks; never calls OpenAI or reads operational data."""
import json
from pathlib import Path
import tempfile
import unittest
import threading,time
from unittest.mock import patch
import rag_nlu as nlu
import rag_dialogue as d

def output(intent='context',facts=(),hyp=False,previous=False):
    return {'intent':intent,'facts':list(facts),'hypothetical':hyp,'reference_previous':previous,'uncertain':[]}

class NluSafety(unittest.TestCase):
    def test_request_is_minimized_and_uses_only_the_pinned_model(self):
        p=nlu.make_request('전주에 살고 연락처 010-1234-5678 a@example.com 우림로 123입니다.',{'region':'전주','notice_ids':['NOTICE-private']})
        s=json.dumps(p,ensure_ascii=False)
        for hidden in ('010-1234-5678','a@example.com','우림로 123','NOTICE-private'):self.assertNotIn(hidden,s)
        self.assertEqual(p['model'],'gpt-6-luna');self.assertFalse(p['store']);self.assertNotIn('tools',p)
        self.assertLessEqual(len(nlu.packed(p)),12000)

    def test_numerical_hallucination_and_extra_fields_are_rejected(self):
        v=output(facts=[{'field':'age','value':'99','quote':'25살'}])
        with self.assertRaises(ValueError):nlu.validate(v,'25살입니다')
        with self.assertRaises(ValueError):nlu.validate({**output(),'eligibility':'approved'},'안녕')

    def test_hypothesis_does_not_update_actual_registration(self):
        c={'region':'전주','farm_registered':'no','notice_ids':['NOTICE-SYNTHETIC']}
        v=nlu.validate(output('eligibility',[{'field':'farm_registered','value':'yes','quote':'등록하면'}],True,True),'그럼 등록하면 가능해?')
        q=d.PREFIX+json.dumps(c,ensure_ascii=False)+d.SEPARATOR+'그럼 등록하면 가능해?'
        routed,actual,evaluation=nlu.route(q,v)
        self.assertEqual(actual['farm_registered'],'no');self.assertEqual(evaluation['farm_registered'],'yes')
        self.assertEqual(d.decode(routed)[1]['notice_ids'],c['notice_ids'])

    def test_stale_or_missing_broker_falls_back_without_network(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
                self.assertIsNone(nlu.interpret('전주 지원사업',{},Path(tmp)))

    def test_documents_and_keys_are_not_transmitted(self):
        for q in ('시행지침 전문을 붙입니다','API_KEY=example','x'*601):self.assertIsNone(nlu.make_request(q,{}))

    def test_unsupported_region_and_fact_evidence_are_rejected(self):
        with self.assertRaises(ValueError):nlu.validate(output(facts=[{'field':'region','value':'부산','quote':'전주'}]),'전주 거주')

    def test_daily_budget_is_reserved_before_call_and_survives_restart(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            budget=Path(tmp)/'budget.json'
            for i in range(30):self.assertIsNotNone(nlu.reserve(budget,[],'2026-11-12',i*61))
            self.assertIsNone(nlu.reserve(budget,[],'2026-11-12',9999))
            self.assertIsNone(nlu.reserve(budget,[1]*6,'2026-11-13',10000))

    def test_broker_api_error_returns_fallback_and_cleans_question(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            queue=Path(tmp);nlu.atomic(queue/'status.json',{'ready':True,'model':nlu.MODEL})
            def fail_reply():
                for _ in range(100):
                    files=list(queue.glob('q-*.json'))
                    if files:
                        request=json.loads(files[0].read_text(encoding='utf-8'))
                        nlu.atomic(queue/('r-'+request['id']+'.json'),{'id':request['id'],'question_sha':nlu.digest(request['question'].encode()),'ok':False});return
                    time.sleep(.01)
            t=threading.Thread(target=fail_reply);t.start()
            self.assertIsNone(nlu.interpret('전주 지원사업',{},queue));t.join()
            self.assertEqual(list(queue.glob('q-*.json')),[])

if __name__=='__main__':unittest.main()
