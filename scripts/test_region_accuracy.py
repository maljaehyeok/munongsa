"""Offline synthetic qualification cases; no real grants or API calls."""
import json,unittest
from unittest.mock import patch
import rag_dialogue as d,rag_profile as p,rag_nlu as nlu
URL='https://www.rda.go.kr/young/custom/policy/view.do?sId=999999'
def document(name,region,kind='residence',scopes=None,basis=None,verified=True):
    c={'condition_id':'geo','kind':kind,'status':'verified' if verified else 'candidate','presence':'specified' if scopes is not None else 'unknown',
      'value':{'regions':scopes,'location_basis':basis} if scopes is not None else None,'evidence':{'url':URL,'location':'가상 근거','quote':'가상 지역 조건'}}
    return {'public':{'id':'NOTICE-'+name,'title':name+' 농업지원사업','region':region,'target':'가상 농업인','support':'가상 지원','eligibility':{'conditions':[c],'logic':{'condition_id':'geo'}}},
      'record':{'fields':{'conditions':{},'unconfirmed':{'value':['실제 공고가 아닌 테스트 자료']}}}}
class RegionAccuracy(unittest.TestCase):
    def compare(self,doc,context):return p.compare(doc,context,lambda u:u==URL,d.AREAS)
    def test_ansan_residence_match_and_jeonju_mismatch(self):
        self.assertEqual(self.compare(document('ansan','경기 안산시',scopes=['경기 안산시']),{'region':'안산'})['label'],'관련 가능성 있음')
        self.assertEqual(self.compare(document('jeonju','전북 전주시',scopes=['전북 전주시']),{'region':'안산'})['label'],'조건 불일치')
    def test_farm_land_not_residence_or_office(self):
        c={'region':'전주','farm_region':'김제'}
        self.assertEqual(self.compare(document('kimje','전북 김제시','business_location',['전북 김제시'],'farm_land'),c)['label'],'관련 가능성 있음')
        self.assertEqual(self.compare(document('office','전북 김제시','business_location',['전북 김제시'],'business_site'),c)['label'],'추가 확인 필요')
    def test_no_profile_national_and_unknown(self):
        self.assertEqual(self.compare(document('national','전국',scopes=['전국']),{})['label'],'관련 가능성 있음')
        self.assertEqual(self.compare(document('unknown','확인 필요'),{'region':'안산'})['label'],'추가 확인 필요')
        self.assertEqual(p.region_state('전북',['전북 김제시'],d.AREAS),'check')
        self.assertEqual(p.region_state('안산',['농업기술센터 접수'],d.AREAS),'check')
    def test_distinct_clauses_and_hypothesis(self):
        facts,error=p.extract('전주에 거주하고 김제에서 영농할 예정',d.AREAS,d.CROPS,d.normalized)
        self.assertIsNone(error);self.assertEqual(facts['region'],'전주');self.assertEqual(facts['farm_region'],'김제')
        query=d.PREFIX+json.dumps({'region':'전주'},ensure_ascii=False)+d.SEPARATOR+'안산으로 이사하면?'
        understood={'facts':{},'intent':'discover','hypothetical':True,'reference_previous':False}
        routed,actual,evaluation=nlu.route(query,understood)
        self.assertEqual(actual['region'],'전주');self.assertEqual(evaluation['region'],'안산')
        facts,_=p.extract('안산 거주 제한 사업 조건은?',d.AREAS,d.CROPS,d.normalized)
        self.assertNotIn('region',facts)
    def test_explicit_other_region_search_not_blocked(self):
        doc=document('jeonju','전북 전주시',scopes=['전북 전주시']);corpus={'documents':{'one':doc},'aliases':{}}
        def grounded(q,key):return {'mode':'local','status':'answered','answer':'가상 근거','sources':[],'programs':[{'id':doc['public']['id'],'name':doc['public']['title'],'application_period':{'description':'기간 미확인'}}]}
        q=d.PREFIX+json.dumps({'region':'안산'},ensure_ascii=False)+d.SEPARATOR+'전주 농업지원사업 신청 조건'
        out=d.respond(q,corpus,grounded)
        self.assertEqual(len(out['programs']),1);self.assertEqual(out['programs'][0]['comparison']['label'],'조건 불일치');self.assertEqual(out['conversation']['region'],'안산')
    def test_actual_ansan_query_scope_excludes_paju_keyword_clone(self):
        docs={'ansan':document('ansan','안산시농업기술센터 접수 공고. 지역 요건 확인 필요'), 'paju':document('paju','경기 파주시 농지 소재지')}
        for x in docs.values():x['public']['title']='유기농업자재 지원사업'
        def grounded(q,key):
            x=docs[key]['public'];return {'mode':'local','status':'answered','answer':'가상 근거','sources':[],'programs':[{'id':x['id'],'name':x['title'],'application_period':{'description':'기간 미확인'}}]}
        out=d.respond('안산 유기농업자재 지원사업 신청 조건',{'documents':docs,'aliases':{}},grounded)
        self.assertEqual([x['id'] for x in out['programs']],['NOTICE-ansan'])
    def test_or_does_not_become_and(self):
        doc=document('or','전북 전주시',scopes=['전북 전주시']);c=doc['public']['eligibility']['conditions'][0]
        doc['public']['eligibility']['conditions'].append({**c,'condition_id':'national','value':{'regions':['전국']}})
        doc['public']['eligibility']['logic']={'op':'OR','children':[{'condition_id':'geo'},{'condition_id':'national'}]}
        self.assertNotEqual(self.compare(doc,{'region':'안산'})['label'],'조건 불일치')
if __name__=='__main__':unittest.main()
