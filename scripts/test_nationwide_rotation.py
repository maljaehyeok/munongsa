import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import support_official_apis as api,rag_profile,rag_dialogue
from support_runtime import rda

class Nationwide(unittest.TestCase):
    def test_rotation_covers_all_official_tags(self):
        start=datetime(2026,11,22,tzinfo=timezone.utc);seen=set()
        for day in range(6):
            tags=api.rotating_regions(start+timedelta(days=day));self.assertEqual(len(set(tags)),3);seen.update(tags)
        self.assertEqual(seen,set(api.REGION_TAGS))
        self.assertIn('전남광주',seen)

    def test_portal_pages_rotate_without_losing_latest(self):
        source={'api_pages':2,'portal_rotating_page_limit':30};start=datetime(2026,11,22,tzinfo=timezone.utc)
        pages=[api.discovery_pages('data_go_kr_bizinfo',source,start+timedelta(days=d)) for d in range(29)]
        self.assertTrue(all(p[0]==1 and len(p)==2 for p in pages))
        self.assertEqual({p[1] for p in pages},set(range(2,31)))
        self.assertEqual(api.discovery_pages('bizinfo',source,start),[1,2])

    def test_enterprise_target_is_not_individual_eligibility(self):
        from support_runtime.api_core import overview
        facts=overview('안내 ☞ 식품 제조 중소기업 ☞ 수출 컨설팅 지원','https://www.bizinfo.go.kr/example')
        self.assertEqual(facts['target_description']['value'],'식품 제조 중소기업')
        self.assertNotIn('applicant_types',facts)
        self.assertNotIn('farm_registration_required',facts)

    def test_official_bizinfo_id_survives_template_change(self):
        from support_runtime.ingestion import identity
        a='https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_123'
        b='https://bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=PBLN_123'
        self.assertEqual(identity(a),identity(b))
        self.assertNotEqual(identity(a),identity(b.replace('123','124')))

    def test_regional_daily_merge_and_private_only(self):
        row={'original_id':'PBLN_1','title':'농업인 지원사업 모집','original_url':'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_1','description':'','api_fields':{}}
        row['api_fields']={'target':'','application_method':'','application_period':''}
        calls=[]
        def fetch(provider,limit,page,environ=None,region=None):
            calls.append((provider,page,region));return [row],{'requests':1,'http_status':200}
        with patch.object(api.time,'sleep'):
            value=api.collect({'kind':'bizinfo','api_providers':['bizinfo'],'regional_queries_per_run':3},environ={'BIZINFO_API_KEY':'TEST'},fetcher=fetch)
        self.assertEqual(len(calls),4);self.assertEqual(value['candidate_count'],1)
        self.assertEqual(value['duplicate_count'],3);self.assertFalse(value['analyses'][0]['automatic_approval'])
        self.assertNotIn('location_requirement',value['analyses'][0]['facts'])

    def test_regional_failure_does_not_erase_national_candidates(self):
        row={'original_id':'PBLN_1','title':'농업인 지원사업 모집','original_url':'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_1','description':'','api_fields':{}}
        row['api_fields']={'target':'','application_method':'','application_period':''}
        def fetch(provider,limit,page,environ=None,region=None):
            if region:raise api.ApiError('quota_exceeded')
            return [row],{'requests':1}
        with patch.object(api.time,'sleep'):
            value=api.collect({'kind':'bizinfo','api_providers':['bizinfo'],'regional_queries_per_run':3},environ={'BIZINFO_API_KEY':'TEST'},fetcher=fetch)
        self.assertEqual(value['candidate_count'],1);self.assertEqual(len(value['regional_queries']),1)

    def test_explicit_province_survives_unknown_municipality(self):
        check=lambda actual,scope:rag_profile.region_state(actual,[scope],rag_dialogue.AREAS)
        self.assertEqual(check('제주','경남 합천군'),'mismatch')
        self.assertEqual(check('경남','경남 합천군'),'check')
        self.assertEqual(check('경남 합천군','경남 합천군'),'match')
        self.assertEqual(check('제주','합천군'),'check')
        self.assertEqual(check('전주','경남 전주시'),'check')

    def test_all_17_provinces_and_upcoming_query(self):
        for region in ('서울','부산','대구','인천','광주','대전','울산','세종','경기','강원','충북','충남','전북','전남','경북','경남','제주'):
            self.assertEqual(rag_profile.region_state(region,[region],rag_dialogue.AREAS),'match')
        from urllib.parse import urlsplit,parse_qs
        self.assertEqual(parse_qs(urlsplit(rda.list_url(state='예정',unfiltered=True)).query)['search_ingState'],['예정'])

if __name__=='__main__':unittest.main()
