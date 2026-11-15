"""Synthetic data only: verified relevance, paging and application boundaries."""
import copy,json,unittest
from datetime import datetime,timedelta,timezone
from bs4 import BeautifulSoup
import rag_catalogue as catalogue
import support_notice_review as review

class PracticalityTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.item={'id':'NOTICE-example','title':'가상 친환경 자재 지원','institution':'가상 기관','url':'https://www.rda.go.kr/young/custom/policy/view.do?sId=1','source_id':'rda-young-official',
            'publication':'official_guidance','verification_status':'basics_only','recommendation_eligible':False,'freshness':'current','last_checked_at':self.now.isoformat(),
            'guidance_expires_at':(self.now+timedelta(days=1)).isoformat(),'rights':{'public_display':'allowed'}}
        self.feed={'schema_version':'munongsa-support-public-v1','notices':[self.item],'verified_facts':{}}
        basis={k:self.item.get(k) for k in ('id','title','url','target','region','reference_application_dates','application_period','eligibility')}
        c={'condition_id':'registration','kind':'farm_registration','value':{'registered':True},'status':'verified','presence':'specified',
            'evidence':{'url':self.item['url'],'location':'가상 조건','fact_confirmed':True}}
        self.fact={'basis':basis,'complete':False,'checked_at':self.now.isoformat(),'expires_at':(self.now+timedelta(hours=1)).isoformat(),'conditions':[c]}
        self.feed['verified_facts'][self.item['id']]=self.fact
    def test_verified_condition_search(self):
        self.assertEqual(len(catalogue.matches('경영체 등록 지원사업',self.feed,now=self.now)),1)
    def test_expired_condition_not_searched(self):
        self.fact['expires_at']=(self.now-timedelta(seconds=1)).isoformat()
        self.assertFalse(catalogue.matches('경영체 등록 지원사업',self.feed,now=self.now))
    def test_changed_basis_not_searched(self):
        self.item['title']='변경된 가상 사업'
        self.assertFalse(catalogue.matches('경영체 등록 지원사업',self.feed,now=self.now))
    def test_unverified_text_not_searched(self):
        self.item['target']='마늘 재배 농업인'
        self.assertFalse(catalogue.matches('마늘 지원사업',self.feed,now=self.now))
    def test_no_full_eligibility_or_reception_claim(self):
        p=catalogue.program(self.item,self.feed,self.now,{'farm_registered':'yes'})
        self.assertTrue(p['needs_verification']);self.assertFalse(p['application_period']['actual_reception_confirmed'])
    def test_registration_mismatch(self):
        self.assertEqual(catalogue.program(self.item,self.feed,self.now,{'farm_registered':'no'})['comparison']['label'],'조건 불일치')
    def test_paging_all_results_without_repeat(self):
        self.feed['notices']=[{**self.item,'id':'NOTICE-'+str(i),'title':'가상 농업 지원 '+str(i)} for i in range(8)]
        corpus={'documents':{},'guidance_feed':self.feed};out=catalogue.respond('전체 공식 공고',corpus);seen=[]
        while out:
            seen += [p['id'] for p in out['programs']]
            if not out.get('catalogue_next'):break
            out=catalogue.respond(catalogue.PAGE_PREFIX+json.dumps(out['catalogue_next'],ensure_ascii=False),corpus)
        self.assertEqual(len(seen),8);self.assertEqual(len(set(seen)),8)
    def test_changed_list_restarts_not_stale_page(self):
        self.feed['notices']=[{**self.item,'id':'NOTICE-'+str(i),'title':'가상 농업 지원 '+str(i)} for i in range(5)]
        corpus={'documents':{},'guidance_feed':self.feed};out=catalogue.respond('전체 공식 공고',corpus)
        token=out['catalogue_next'];self.feed['notices'].pop()
        out=catalogue.respond(catalogue.PAGE_PREFIX+json.dumps(token,ensure_ascii=False),corpus)
        self.assertEqual(out['kind'],'clarify');self.assertFalse(out['programs'])
    def test_bad_page_input_rejected(self):
        for p in ({'query':'전체 공고','offset':True,'fingerprint':'0'*64},{'query':'전체 공고','offset':-3,'fingerprint':'0'*64}):
            with self.assertRaises(ValueError):catalogue.page_request(catalogue.PAGE_PREFIX+json.dumps(p))
    def test_preparation_bound_to_original_hash(self):
        observation=review.observe({'original_url':self.item['url']},BeautifulSoup('','html.parser'),'신청방법 방문신청',self.now)
        check={'status':'checked','title_match':True,'url':self.item['url'],'article':'신청방법 방문신청','observation':observation}
        plan={'url':self.item['url'],'article_sha':observation['article_sha'],'fragments':['신청방법'],'dates':{},'preparation':{'entry_url':self.item['url'],'entry_kind':'notice_instructions','method':'방문 접수'}}
        out=review.attach(self.feed,{self.item['id']:check},self.now,{self.item['id']:plan})
        self.assertEqual(out[self.item['id']]['preparation']['method'],'방문 접수')
        plan['article_sha']='0'*64
        self.assertNotIn('preparation',review.attach(self.feed,{self.item['id']:check},self.now,{self.item['id']:plan})[self.item['id']])
    def test_arbitrary_application_url_rejected(self):
        observation=review.observe({'original_url':self.item['url']},BeautifulSoup('','html.parser'),'신청방법 방문신청',self.now)
        check={'status':'checked','title_match':True,'url':self.item['url'],'article':'신청방법 방문신청','observation':observation}
        plan={'url':self.item['url'],'article_sha':observation['article_sha'],'fragments':['신청방법'],'dates':{},'preparation':{'entry_url':'https://attacker.example/','method':'신청'}}
        self.assertNotIn('preparation',review.attach(self.feed,{self.item['id']:check},self.now,{self.item['id']:plan})[self.item['id']])
if __name__=='__main__':unittest.main()
