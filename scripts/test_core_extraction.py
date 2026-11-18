"""Synthetic core extraction and existing comparison integration tests."""
import copy
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from support_runtime import core_facts,conditions,periods,enrichment
from support_recommendation_readiness import classify
from reprocess_core_candidates import reprocess

URL='https://www.rda.go.kr/young/custom/policy/view.do?sId=999999&cp=1'


def document(complete=False,unknown=True,publication='approved'):
    proof={'url':URL,'location':'가상 자격 항목','quote':'가상 경영체 등록 필수'}
    clauses=[{'condition_id':'registration','kind':'farm_registration','presence':'specified',
              'value':{'registered':True},'evidence':proof,'status':'verified'}]
    logic={'condition_id':'registration'}
    if unknown:
        clauses.append({'condition_id':'other','kind':'other_required','presence':'unknown','value':None,'evidence':{},'status':'candidate'})
        logic={'op':'AND','children':[logic,{'condition_id':'other'}]}
    return {'public':{'publication':publication,'eligibility_complete':complete,'eligibility':{'conditions':clauses,'logic':logic}},'record':{'fields':{}}}


class CoreTests(unittest.TestCase):
    def test_numbered_heading_and_multiline_children(self):
        f=core_facts.extract(['1. 지원대상','- 농업인 및 농업법인','2. 지원내용 : 종자 구입비 지원','3. 신청방법: 방문 신청'],URL)
        self.assertIn('농업법인',f['target_description']['value'])
        self.assertEqual(f['support_description']['value'],'종자 구입비 지원')
        self.assertEqual(f['application_method']['value'],'방문 신청')

    def test_inline_sections_do_not_mix_budget_with_target(self):
        f=core_facts.extract(['가. 지원내용 : 자재 구입비 일부 지원 나. 지원단가 : 100만원 다. 사업대상 : 등록 농지 라. 제외대상 : 중복 지원 농지'],URL)
        self.assertEqual(f['support_description']['value'],'자재 구입비 일부 지원')
        self.assertNotIn('100만원',f['target_description']['value'])

    def test_total_budget_not_personal_support_summary(self):
        f=core_facts.extract(['지원내용: 종자 지원 총사업비: 200억원'],URL)
        self.assertEqual(f['support_summary']['value'],'종자 지원')

    def test_farmer_group_not_individual_or_corporate_employee(self):
        f=core_facts.extract(['지원대상: 농업인 단체'],URL)
        self.assertEqual(f['applicant_types']['value'],['institution_group'])
        self.assertNotIn('applicant_types',core_facts.extract(['지원대상: 농업법인 소속 농업인'],URL))

    def test_split_day_preserved_without_project_year_fallback(self):
        lines=['신청기간 : 2026-11-01 ~ 2026-12-31','신청기간: 2026.11.1.~12.','31. 나. 사업명 : 2027년 가상 사업']
        parsed=periods.extract(core_facts.period_input(lines),URL)
        self.assertEqual(parsed['period']['end']['date'],'2026-12-31')
        self.assertIsNone(periods.extract(core_facts.period_input(['사업명: 2027년 가상 사업','신청기간: 11.1.~12.31.']),URL)['period'])

    def test_closed_signal_outside_date_heading_not_lost(self):
        lines=['신청기간: 2026-11-01 ~ 2026-12-31','접수가 조기 마감되었습니다']
        parsed=periods.extract(core_facts.period_input(lines),URL)
        self.assertEqual(periods.assess({},parsed,now='2026-11-18')['status'],'closed')

    def test_explicit_extension_outside_label_retained(self):
        lines=['신청기간: 2026-11-01 ~ 2026-11-15','접수기간 연장: 2026-11-01 ~ 2026-12-31']
        parsed=periods.extract(core_facts.period_input(lines),URL)
        self.assertEqual(parsed['period']['end']['date'],'2026-12-31')

    def test_no_region_from_publisher_or_local_word(self):
        f=core_facts.extract(['주관기관: 홍천군청','신청대상: 관내 농업인'],URL)
        self.assertNotIn('geographic_scope',f);self.assertNotIn('location_requirement',f)

    def test_national_scope_requires_explicit_support_region_label(self):
        self.assertNotIn('geographic_scope',core_facts.extract(['전국 사업을 소개하는 게시판'],URL))
        f=core_facts.extract(['지원지역: 전국'],URL)
        self.assertEqual(f['geographic_scope']['value']['scope'],'national')
        self.assertNotIn('location_requirement',f)

    def test_metropolitan_and_municipal_scope_are_distinct(self):
        self.assertEqual(core_facts.extract(['지원지역: 부산광역시'],URL)['geographic_scope']['value']['scope'],'province')
        self.assertEqual(core_facts.extract(['지원지역: 김제시'],URL)['geographic_scope']['value']['scope'],'municipality')

    def test_residence_farm_and_office_remain_distinct(self):
        for text,kind,basis in [('김제시에 거주하는 농업인','residence','residence'),
            ('김제시에 농지를 둔 농업인','business_location','farm_land'),
            ('김제시에 사업장을 둔 농업법인','business_location','business_office')]:
            f=core_facts.extract(['신청대상: '+text],URL);loc=f['location_requirement']['value']
            self.assertEqual((loc['kind'],loc['location_basis']),(kind,basis))
            p=conditions.payload_for(f,{})
            self.assertTrue(any(c['kind']==kind and c['value'].get('location_basis')==basis for c in p['conditions'] if c['presence']=='specified'))

    def test_alternative_and_exclusion_are_not_flattened(self):
        f=core_facts.extract(['지원대상: 농업인 또는 예비농업인, 다만 미등록자는 제외'],URL)
        self.assertNotIn('applicant_types',f)
        self.assertNotIn('location_requirement',f)

    def test_shared_applicant_types_and_incomplete_institution(self):
        f=core_facts.extract(['주관기관: 가상시농업기술센','신청대상: 농업인 및 농업법인'],URL)
        self.assertNotIn('implementing_institution',f)
        self.assertEqual(f['applicant_types']['value'],['individual_farmer','agricultural_business'])

    def test_bullets_separate_target_and_support(self):
        f=core_facts.extract(['☞ 농업경영정보를 등록한 농업경영체 ☞ 종자, 자재 구입비 지원'],URL)
        self.assertEqual(f['target_description']['value'],'농업경영정보를 등록한 농업경영체')
        self.assertEqual(f['support_summary']['value'],'종자, 자재 구입비 지원')

    def test_abcd_existing_engine_and_approval_gate(self):
        self.assertEqual(classify(document(True,False),{'farm_registered':'yes'},lambda _:True,{})['category'],'B')
        d=document(True,False);payload=d['public']['eligibility']
        payload['conditions'].append({**payload['conditions'][0],'condition_id':'national','kind':'residence','value':{'regions':['전국']}})
        payload['logic']={'op':'AND','children':[{'condition_id':c['condition_id']} for c in payload['conditions']]}
        self.assertEqual(classify(d,{'farm_registered':'yes'},lambda _:True,{})['category'],'A')
        self.assertEqual(classify(document(),{'farm_registered':'yes'},lambda _:True,{})['category'],'B')
        self.assertEqual(classify(document(),{'farm_registered':'no'},lambda _:True,{})['category'],'C')
        self.assertEqual(classify(document(publication='private'),{'farm_registered':'yes'},lambda _:True,{})['category'],'D')
        d=document();d['public']['eligibility']['conditions'][0]['status']='candidate'
        self.assertEqual(classify(d,{'farm_registered':'yes'},lambda _:True,{})['category'],'D')

    def test_expired_notice_is_not_current_recommendation(self):
        d=document(True,False);d['public']['application_status']='closed'
        self.assertEqual(classify(d,{'farm_registered':'yes'},lambda _:True,{})['category'],'D')

    def test_reprocessor_does_not_mutate_or_approve_input(self):
        n={'official_url':URL,'original_id':'synthetic','publication':'private','recommendation_eligible':False,
           'facts':{},'eligibility_candidate':{'conditions':[]},'condition_schema_valid':True}
        baseline={'candidates':[n]};saved=copy.deepcopy(baseline)
        with tempfile.TemporaryDirectory() as p:r=reprocess(baseline,Path(p))
        self.assertEqual(baseline,saved);self.assertEqual(r['core_extraction_summary']['actual_categories'],{'D':1})
        self.assertFalse(r['candidates'][0]['recommendation_eligible'])

    def test_cache_other_notice_is_rejected(self):
        n={'official_url':URL,'original_id':'synthetic','publication':'private','recommendation_eligible':False,'facts':{},'eligibility_candidate':{'conditions':[]}}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/(hashlib.sha256(URL.encode()).hexdigest()[:16]+'-lines.json')
            p.write_text(json.dumps({'official_url':URL+'1','lines':[]}),encoding='utf8')
            with self.assertRaises(ValueError):reprocess({'candidates':[n]},Path(d))

    def test_changed_date_without_extension_retains_history_and_holds(self):
        old={'value':{'date':'2026-12-01'},'evidence':{'url':URL,'location':'가상 원문','quote':'신청기한 2026-12-01'}}
        n={'official_url':URL,'original_id':'synthetic','publication':'private','recommendation_eligible':False,
           'facts':{'application_deadline':old},'eligibility_candidate':{'conditions':[]}}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/(hashlib.sha256(URL.encode()).hexdigest()[:16]+'-lines.json')
            p.write_text(json.dumps({'official_url':URL,'lines':['신청기간: 2026-11-01 ~ 2026-12-31'],
                'checked_at':'2026-11-18T00:00:00+09:00'},ensure_ascii=False),encoding='utf8')
            r=reprocess({'candidates':[n]},Path(d))['candidates'][0]
        self.assertEqual(r['facts']['application_deadline'],old)
        self.assertEqual(r['recruitment']['status'],'unknown')
        self.assertEqual(r['new_application_period_candidate']['end']['date'],'2026-12-31')


if __name__=='__main__':unittest.main()
