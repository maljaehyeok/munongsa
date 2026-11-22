import unittest
from support_runtime.conditions import payload_for
from support_runtime.qualification_guards import explicit_locations
import support_eligibility as eligibility

def payload(text):
    return payload_for({'target_description':{'value':text,'evidence':{
        'url':'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127716',
        'quote':text,'location':'공식 API 신청 대상'}}},{})

class QualificationGuards(unittest.TestCase):
    def test_export_union_never_becomes_personal_only(self):
        for text in ['관내 농수산식품 농가 및 수출업체','수출농산물 생산농가, 수출상품 선별ㆍ포장 참여업체, 수출업체',
                     '농식품 수출업체 및 수출농가(법인)']:
            p=payload(text)
            self.assertFalse(any(c['kind']=='applicant' and c['presence']=='specified' for c in p['conditions']))
            self.assertTrue(any(c['condition_id'].startswith('target_review_') for c in p['conditions']))
    def test_women_age_and_birth_parity_remain_mandatory_unknown(self):
        p=payload('화성시에 거주하는 짝수년도 출생한 51~80세 여성농업인')
        self.assertTrue(any(c['kind']=='residence' and c['value']['regions']==['화성시'] for c in p['conditions']))
        self.assertTrue(any(c['presence']=='unknown' and '출생' in c.get('evidence',{}).get('location','') for c in p['conditions']))
        self.assertTrue(any(c['condition_id']=='remaining_unknown' for c in p['conditions']))
    def test_farmland_and_additional_application_not_discarded(self):
        p=payload('농업경영정보를 등록한 농업인으로 농업경영정보에 등록된 관내 농지 - 변경 신청이 필요한 농가')
        notes=' '.join(c.get('evidence',{}).get('location','') for c in p['conditions'])
        self.assertIn('농지',notes);self.assertIn('변경 신청',notes)
        self.assertFalse(any(c['kind']=='residence' for c in p['conditions']))
    def test_branch_does_not_become_city_restriction(self):
        self.assertEqual(explicit_locations('포항시에 거주하면서 실제 영농에 종사(경북내 타시군 거주자는 해당 시군에 신청)'),[])
    def test_publisher_region_never_fills_unnamed_target(self):
        self.assertEqual(explicit_locations('관내 농업인'),[])
        self.assertEqual(explicit_locations('도내 사업장 소재 업체'),[])
    def test_existing_conditions_preserved(self):
        base={'conditions':[{'condition_id':'old','kind':'applicant','presence':'specified','value':{'one_of':['agricultural_business']},'evidence':{}}], 'logic':{'condition_id':'old'}}
        p=payload_for({'target_description':{'value':'관내 농업인','evidence':{}}},base)
        self.assertEqual(p['conditions'][0],base['conditions'][0])
        self.assertEqual(len(base['conditions']),1)
    def test_reexecution_not_duplicate(self):
        p=payload('화성시에 거주하는 짝수년도 출생한 51~80세 여성농업인')
        q=payload_for({'target_description':{'value':'화성시에 거주하는 짝수년도 출생한 51~80세 여성농업인','evidence':{}}},p)
        self.assertEqual(len(q['conditions']),len(p['conditions']))
    def test_candidate_schema_valid(self):
        p=payload('화성시에 거주하는 짝수년도 출생한 51~80세 여성농업인')
        for c in p['conditions']:c.pop('status',None)
        eligibility.check_payload(p,{'original_url':'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127716'})

if __name__=='__main__':unittest.main()
