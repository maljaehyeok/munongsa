"""Focused synthetic collection/region safety checks; no network or approvals."""
import copy,unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
import support_official_apis as api
import support_eligibility as eligibility
from support_runtime import api_core,source_quality,conditions,bizinfo_detail
from collect_national_candidates import identity
from prepare_core_collection import build,portal_release_review

URL='https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_123'


def row(ident='123',target='산청군에 주소 및 농지를 둔 농업경영체 등록 1년 이상인 농가'):
    return {'original_id':'PBLN_'+ident,'title':'농업인 지원사업 신청 공고',
        'original_url':URL.replace('123',ident),'description':'사업 안내 ☞ '+target+' ☞ 종자 구입비 지원',
        'api_fields':{'target':'중소기업','application_period':'20261101 ~ 20261130','application_method':'방문 접수'}}


def body(title='농업인 지원사업 신청 공고',target='산청군에 주소 및 농지를 둔 농업경영체 등록 1년 이상인 농가'):
    return ('<div class="support_project_detail"><h2 class="title">'+title+'</h2><div class="view_cont"><ul>'
        '<li><span class="s_title">사업개요</span><div class="txt">사업 안내 ☞ '+target+' ☞ 종자 구입비 지원</div></li>'
        '<li><span class="s_title">신청기간</span><div class="txt">2026.11.01 ~ 2026.11.30</div></li>'
        '<li><span class="s_title">사업신청 방법</span><div class="txt">방문 접수</div></li>'
        '</ul></div></div><div>관련 사업 ☞ 전국 농업인 ☞ 지원</div>').encode()


class CollectionQualityTests(unittest.TestCase):
    def test_joint_residence_farmland_and_registration(self):
        e=api.entry(row());f=e['facts'];self.assertEqual(len(f['location_requirements']['value']),2)
        p=conditions.payload_for(f,{})
        for c in p['conditions']:c.pop('status',None)
        eligibility.check_payload(p,{'original_url':URL})
        specified={c['kind'] for c in p['conditions'] if c['presence']=='specified'}
        self.assertTrue({'residence','business_location','farm_registration'}<=specified)
        self.assertNotIn('farming_experience',specified)  # registration duration is NOT farming history
        self.assertTrue(any(c['presence']=='unknown' for c in p['conditions']))

    def test_publisher_region_and_api_category_not_eligibility(self):
        r=row(target='농업경영정보를 등록한 농업인 및 농업법인')
        r.update(list_region='제주');r['api_fields'].update(agency='제주특별자치도',target='중소기업')
        f=api.entry(r)['facts'];self.assertNotIn('geographic_scope',f)
        self.assertEqual(f['applicant_types']['value'],['individual_farmer','agricultural_business'])

    def test_unknown_and_disjunctive_regions_stay_unknown(self):
        for target in ('관내 농업경영체 등록 농가','산청군에 거주하는 농업인 또는 전국 예비농업인'):
            f=api.entry(row(target=target))['facts'];self.assertNotIn('geographic_scope',f)

    def test_registration_unknown_negative_or_planned_not_required(self):
        for target in ('농업경영체 등록 여부와 무관한 농업인','농업경영체 등록 예정 농가',
                '농업경영체 등록이 필요하지 않은 농업인','농업경영체 등록한 농업인도 등록 여부와 무관'):
            facts=api.entry(row(target=target))['facts']
            self.assertNotIn('farm_registration_required',facts)
            self.assertFalse(any(c['kind']=='farm_registration' and c['presence']=='specified'
                for c in conditions.payload_for(facts,{})['conditions']))

    def test_no_unmarked_or_multiple_bullets_invented(self):
        for text in ('농업인 지원사업','☞ 농업인 ☞ 지원 ☞ 별도 조건', '☞ 전국 농업인 ☞ 신청 안내'):
            self.assertFalse(api_core.overview(text,URL))

    def test_distinct_source_and_title_are_required(self):
        e=api.entry(row());out=bizinfo_detail.enrich(e,body(title='다른 공고'))
        self.assertEqual(out['status'],'failed');self.assertNotIn('publisher_original_link',out)

    def test_api_detail_conflict_is_held(self):
        e=api.entry(row());out=bizinfo_detail.enrich(e,body(target='함안군 관내 주소를 둔 농업인'))
        self.assertTrue(out['fact_conflicts']);self.assertEqual(out['recruitment']['status'],'unknown')
        for key in ('location_requirements','geographic_scope','target_description'):
            self.assertNotIn(key,out['facts'])

    def test_detail_related_notices_are_not_facts(self):
        out=bizinfo_detail.enrich(api.entry(row()),body())
        self.assertEqual(out['facts']['geographic_scope']['value']['regions'],['산청군'])
        self.assertNotIn('fact_conflicts',out)

    def test_quality_requires_proof_for_same_notice(self):
        e=api.entry(row());self.assertTrue(source_quality.quality(e)['core_complete'])
        e['facts']['geographic_scope']['evidence']['url']=URL.replace('123','456')
        self.assertFalse(source_quality.quality(e)['core_complete'])
        self.assertFalse(source_quality.quality(e)['recommendation_eligible'])

    def test_known_ids_excluded_before_detail_budget(self):
        entries=[api.entry(row('1')),api.entry(row('2')),api.entry(row('3'))]
        entries[0]['metadata']['list_region']='강원';entries[1]['metadata']['list_region']='강원'
        entries[2]['metadata']['list_region']='제주'
        plan=source_quality.detail_plan(entries,[entries[0]['metadata']['original_url']],limit=2)
        self.assertEqual([e['metadata']['original_id'] for e in plan['entries']],['PBLN_2','PBLN_3'])
        self.assertEqual(plan['counts']['operating_duplicates'],1)

    def test_previous_reviews_not_requested_again(self):
        e=api.entry(row());p=source_quality.detail_plan([e],excluded_urls=[URL])
        self.assertFalse(p['entries']);self.assertEqual(p['counts']['previous_review_excluded'],1)

    def test_legacy_current_paths_same_identity_years_distinct(self):
        old=URL.replace('/sii/siia/selectSIIA200Detail.do','/web/lay1/bbs/S1T122C128/AS/74/view.do')
        self.assertEqual(identity(URL),identity(old))
        self.assertNotEqual(identity(URL),identity(URL.replace('123','456')))
        self.assertNotEqual(identity(URL),identity(URL.replace('www.bizinfo.go.kr','example.org')))

    def test_official_region_query_bounds_and_no_auth_bypass(self):
        env={'BIZINFO_API_KEY':'SYNTHETIC_KEY'}
        q=parse_qs(urlsplit(api.prepare_request('bizinfo',environ=env,region='제주').full_url).query)
        self.assertEqual(q['hashtags'],['제주'])
        for region in ('농업','제주,강원','unknown'):
            with self.assertRaises(api.ApiError):api.prepare_request('bizinfo',environ=env,region=region)
        with self.assertRaises(api.ApiError):api.prepare_request('data_go_kr_bizinfo',environ=env,region='제주')
        with self.assertRaises(api.ApiError):api.prepare_request('bizinfo',environ={},region='제주')

    def test_regional_collection_cap_and_candidates_only(self):
        calls=[]
        def fetch(*args,**kwargs):calls.append(kwargs['region']);return [row()],{'requests':1}
        with patch.object(api.time,'sleep'):
            group=api.collect_regions({'kind':'bizinfo'},['제주','강원'],
                environ={'BIZINFO_API_KEY':'SYNTHETIC'},fetcher=fetch)
        self.assertEqual(calls,['제주','강원']);self.assertEqual(group['duplicate_count'],1)
        self.assertFalse(group['automatic_approval'])
        with self.assertRaises(api.ApiError):api.collect_regions({},list(api.REGION_TAGS))

    def test_pipeline_preserves_input_and_never_approves(self):
        inv={'notices':[],'public_feed':{'notices':[]}};doc={'rows':[row()]};before=copy.deepcopy(doc)
        result,_=build([doc],inv,detail_fetcher=lambda _:body())
        self.assertEqual(doc,before);self.assertEqual(result['summary']['new_candidate_count'],1)
        c=result['candidates'][0];self.assertFalse(c['recommendation_eligible'])
        self.assertEqual(c['publication'],'private');self.assertFalse(c['basic_release_review']['approved'])

    def test_authentication_failure_never_retried_as_region_probe(self):
        calls=[]
        def fetch(*args,**kwargs):calls.append(kwargs['region']);raise api.ApiError('authentication_failed')
        group=api.collect_regions({'kind':'bizinfo'},['제주','충북','강원'],
            environ={'BIZINFO_API_KEY':'SYNTHETIC'},fetcher=fetch)
        self.assertEqual(len(calls),1);self.assertEqual(group['state'],'부분 실패')

    def test_portal_metadata_candidate_cannot_release_details(self):
        inv={'notices':[],'public_feed':{'notices':[]}}
        result,group=build([{'rows':[row()]}],inv,detail_fetcher=lambda _:body())
        portal_release_review(result,[row()],group['analyses'])
        item=result['candidates'][0];release=item['basic_release_review']
        self.assertEqual(release['status'],'candidate');self.assertFalse(release['approved'])
        self.assertEqual(release['allowed_fields'],['title','institution','url'])
        self.assertIn('eligibility',release['excludes']);self.assertFalse(item['recommendation_eligible'])

    def test_changed_or_duplicate_not_counted_as_ready(self):
        inv={'notices':[],'public_feed':{'notices':[]}}
        changed=dict(row(),title='농업인 지원사업 변경 신청 공고')
        result,group=build([{'rows':[changed]}],inv,detail_fetcher=lambda _:body(title=changed['title']))
        portal_release_review(result,[changed],group['analyses'])
        self.assertEqual(result['summary']['basic_approval_candidates'],0)

    def test_generic_overview_does_not_inflate_source_quality(self):
        e=api.entry(row());e['facts']['support_description']['evidence']['location']='공식 API 사업개요; 세부 자격 검토 전'
        self.assertNotIn('support_description',source_quality.quality(e)['core_fields'])


if __name__=='__main__':unittest.main()
