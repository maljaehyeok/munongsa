"""Recommendation decisions over synthetic evidence; never changes approvals."""
import copy,json,unittest
from datetime import datetime,timedelta,timezone
import rag_profile,rag_dialogue,rag_catalogue
from support_recommendation_readiness import decision

URL='https://www.rda.go.kr/young/custom/policy/view.do?sId=1'
def condition(identity,kind,value):
    return {'condition_id':identity,'kind':kind,'value':value,'status':'verified','presence':'specified',
            'evidence':{'url':URL,'location':'가상 검증 자료','fact_confirmed':True}}
def document(conditions,logic=None):
    return {'public':{'eligibility':{'conditions':conditions,'logic':logic or {'op':'AND','children':[{'condition_id':c['condition_id']} for c in conditions]}}},'record':{'fields':{}}}
def compare(d,p):return rag_profile.compare(d,p,lambda u:u==URL,rag_dialogue.AREAS)

class RecommendationAccuracyTests(unittest.TestCase):
    def test_registration_alone_never_regional_match(self):
        c=compare(document([condition('r','farm_registration',{'registered':True})]),{'farm_registered':'yes'})
        self.assertEqual(decision(c)['label'],'지역 확인 필요');self.assertEqual(decision(c)['category'],'B')

    def test_farm_and_residence_are_separate(self):
        d=document([condition('f','business_location',{'regions':['경기 파주시'],'location_basis':'farm_land'})])
        self.assertEqual(compare(d,{'region':'파주','farm_region':'전주'})['region_state'],'mismatch')
        self.assertEqual(compare(d,{'region':'전주','farm_region':'파주'})['region_state'],'match')

    def test_province_does_not_prove_city(self):
        d=document([condition('r','residence',{'regions':['경기 파주시']})])
        self.assertEqual(compare(d,{'region':'경기'})['region_state'],'check')
        self.assertEqual(compare(d,{'region':'안산'})['label'],'조건 불일치')

    def test_business_address_is_not_inferred_from_farm(self):
        d=document([condition('r','business_location',{'regions':['경기'],'location_basis':'business_office'})])
        self.assertEqual(compare(d,{'farm_region':'경기','region':'경기'})['region_state'],'check')

    def test_mismatch_cannot_be_overturned_by_other_match(self):
        d=document([condition('r','residence',{'regions':['경기']}),condition('f','farm_registration',{'registered':True})])
        self.assertEqual(decision(compare(d,{'region':'제주','farm_registered':'yes'}))['category'],'C')

    def test_alternative_clause_not_invented_as_mandatory_region(self):
        c=[condition('r','residence',{'regions':['경기']}),condition('a','applicant',{'one_of':['individual_farmer']})]
        result=compare(document(c,{'op':'OR','children':[{'condition_id':'r'},{'condition_id':'a'}]}),{'region':'제주','applicant':'individual_farmer'})
        self.assertNotEqual(decision(result)['category'],'C');self.assertEqual(result['region_state'],'check')

    def test_national_requires_explicit_verified_flag(self):
        result=compare(document([]),{})
        self.assertEqual(decision(result)['category'],'D')
        self.assertEqual(decision(result,national=True)['label'],'추가 자격 확인 필요')

    def test_complete_other_conditions_do_not_prove_unknown_region(self):
        result=compare(document([condition('a','applicant',{'one_of':['individual_farmer']})]),{'applicant':'individual_farmer'})
        self.assertNotEqual(decision(result,complete=True)['category'],'A')

    def test_personal_search_excludes_mismatch_but_full_browse_preserves(self):
        now=datetime.now(timezone.utc)
        item={'id':'NOTICE-synthetic','title':'가상 농업 지원사업','institution':'가상 기관','url':URL,
              'publication':'approved_reference','verification_status':'verified','freshness':'current','last_checked_at':now.isoformat(),
              'rights':{'public_display':'allowed'},'eligibility':document([condition('r','residence',{'regions':['경기']})])['public']['eligibility']}
        feed={'schema_version':'munongsa-support-public-v1','notices':[item]};before=copy.deepcopy(feed)
        self.assertEqual(rag_catalogue.matches('선택한 조건으로 지원사업을 찾아주세요.',feed,{'region':'제주'}),[])
        self.assertEqual(len(rag_catalogue.matches(item['title'],feed,{'region':'제주'})),1)
        self.assertEqual(feed,before)
        program=rag_catalogue.program(item,feed,now,{'region':'제주'})
        self.assertEqual(program['card']['label'],program['comparison']['decision']['label'])

if __name__=='__main__':unittest.main()
