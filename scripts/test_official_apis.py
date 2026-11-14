"""Synthetic contracts only. No credentials, external requests or production DB."""
import json,unittest,urllib.parse
import support_official_apis as api

class Contracts(unittest.TestCase):
    def setUp(self):
        self.row={'pblancId':'PBLN_TEST_1','pblancNm':'농업법인 판로 지원 모집','pblancUrl':'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_TEST_1','bsnsSumryCn':'농업법인 신청','trgetNm':'중소기업'}
    def test_separate_keys_and_single_encoding(self):
        env={'BIZINFO_API_KEY':'SYNTHETIC_BIZ_123','DATA_GO_KR_BIZINFO_API_KEY':urllib.parse.quote('SYNTHETIC+PORTAL/KEY==',safe='')}
        for provider in api.KEYS:
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(api.prepare_request(provider,environ=env).full_url).query)
            self.assertEqual(q['crtfcKey'][0],'SYNTHETIC_BIZ_123') if provider=='bizinfo' else self.assertEqual(q['serviceKey'][0],'SYNTHETIC+PORTAL/KEY==')
        self.assertEqual(api.key_for('bizinfo',{'BIZINFO_API_KEY':'TEST06'}),'TEST06')
    def test_same_records(self):
        b=api.parse_response(json.dumps({'jsonArray':[self.row]}).encode(),'bizinfo')
        p=api.parse_response(json.dumps({'response':{'header':{'resultCode':'00'},'body':{'items':{'item':[self.row]}}}}).encode(),'data_go_kr_bizinfo')
        merged,duplicates,conflicts=api.merge(b+p)
        self.assertEqual(len(merged),1);self.assertEqual(len(duplicates),1);self.assertFalse(conflicts)
    def test_empty_not_authentication_failure(self):
        self.assertEqual(api.parse_response(b'{"response":{"header":{"resultCode":"00"},"body":{"items":[]}}}','data_go_kr_bizinfo'),[])
    def test_authentication_error(self):
        with self.assertRaisesRegex(api.ApiError,'authentication_failed'):api.parse_response(b'<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>','data_go_kr_bizinfo')
    def test_no_redirect_and_redaction(self):
        rows,metrics=api.fetch('bizinfo',environ={'BIZINFO_API_KEY':'SYNTHETIC_KEY_12345'},transport=lambda req,timeout:(json.dumps({'jsonArray':[dict(self.row,bsnsSumryCn='SYNTHETIC_KEY_12345')]}).encode(),200,'application/json'))
        self.assertNotIn('SYNTHETIC_KEY_12345',json.dumps(rows));self.assertEqual(metrics['requests'],1)
        self.assertIsNone(api.biz.NoProbeRedirects().redirect_request(None,None,302,'',{},'https://example.org'))
    def test_candidate_not_individual_eligibility(self):
        row=api.parse_response(json.dumps({'jsonArray':[self.row]}).encode(),'bizinfo')[0]
        self.assertTrue(api.agricultural(row));self.assertEqual(api.biz.extract_hints(row)['individual_farmer_eligibility'],'unknown')
    def test_conflict_detected(self):
        a={'original_id':'PBLN_TEST_1','title':'old'};b={**a,'title':'new'}
        self.assertEqual(api.merge([a,b])[2],['PBLN_TEST_1'])
    def test_provider_failure_does_not_stop_other(self):
        row=api.parse_response(json.dumps({'jsonArray':[self.row]}).encode(),'bizinfo')[0]
        def fetch(provider,limit,page,environ):
            if provider=='bizinfo':raise api.ApiError('authentication_failed')
            return [row],{'requests':1}
        group=api.collect({'kind':'bizinfo','api_providers':list(api.KEYS)},environ={k:'SYNTHETIC' for k in api.KEYS.values()},fetcher=fetch)
        self.assertEqual(group['candidate_count'],1);self.assertEqual(len(group['errors']),1)
    def test_both_providers_one_candidate(self):
        row=api.parse_response(json.dumps({'jsonArray':[self.row]}).encode(),'bizinfo')[0]
        group=api.collect({'kind':'bizinfo','api_providers':list(api.KEYS)},environ={k:'SYNTHETIC' for k in api.KEYS.values()},fetcher=lambda *args:([row],{'requests':1}))
        self.assertEqual(group['candidate_count'],1);self.assertEqual(group['duplicate_count'],1)
        self.assertFalse(group['analyses'][0]['automatic_approval'])

if __name__=='__main__':unittest.main()
