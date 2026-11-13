import unittest,copy
from support_review_queue import classify,report,source_status

URL='https://www.rda.go.kr/young/custom/policy/view.do?sId=1&cp=1'
class QueueTest(unittest.TestCase):
    def row(self,title,identity='one',start='2026-11-01',end='2026-11-30'):
        proof={'url':URL,'quote':'신청기간 2026년','location':'공식 신청기간'}
        return {'notice_id':identity,'title':title,'original_url':URL,'institution':'공식기관','facts':{'application_start':{'value':{'date':start},'evidence':proof},'application_deadline':{'value':{'date':end},'evidence':proof}}}
    def test_guideline_not_open_notice(self):
        r=classify(self.row('2026 농업 지원사업 시행지침'),'2026-11-13');self.assertEqual(r['category'],'reference');self.assertFalse(r['actual_reception_confirmed'])
    def test_stale_open_recomputed_at_kst(self):
        row=self.row('농업인 모집',end='2026-11-10');row['period_assessment']={'status':'date_window_open'}
        self.assertEqual(classify(row,'2026-11-13')['category'],'elapsed')
    def test_duplicate_identity_not_title(self):
        a=self.row('청년농 신청 공고');b=self.row('청년농 신청 공고','two');b['original_url']=URL.replace('sId=1','sId=2')
        r=report([a,b],'2026-11-13');self.assertEqual(r['counts']['중복 자료'],0)
        b['original_url']=URL.replace('cp=1','cp=2');self.assertEqual(report([a,b],'2026-11-13')['counts']['중복 자료'],1)
    def test_missing_does_not_grant_approval(self):
        r=classify(self.row('농업 지원사업 모집'),'2026-11-13');self.assertFalse(r['available_information']['신청 대상']);self.assertIn('보류',r['approval']);self.assertFalse(r['verified_conditions'])
    def test_reference_in_application_letter(self):
        r=classify(self.row('농촌융복합사업 지침을 알려드리니 신청기간 내 신청하세요'),'2026-11-13');self.assertEqual(r['category'],'application')
    def test_unknown_conditions_not_counted_as_proof(self):
        row=self.row('농업 모집');row['facts']['official_condition_candidates']={'value':{'conditions':[{'presence':'unknown'}]},'evidence':{'url':URL,'location':'본문','quote':'응시 자격'}}
        self.assertFalse(classify(row,'2026-11-13')['available_information']['주요 자격조건'])
    def test_source_states_separate(self):
        sources=[{'source_id':str(i),'enabled':i!=2,'institution':'기관'} for i in range(4)]
        r=source_status(sources,{'sources':[{'source_id':'0','status':'completed'},{'source_id':'1','status':'failed','errors':['Blocked']}]},[])
        self.assertEqual(set(r['counts']),{'정상 수집','수집 실패','의도적 비활성','신규 등록 후 실행 결과 미확인'})
    def test_manual_duplicate_requires_both_versions(self):
        a=self.row('공식 신청 공고');a['content_hash']='a'
        b=self.row('동일 사업 안내','two');b.update(content_hash='b',original_url=URL.replace('sId=1','sId=2'))
        d={'two':{'content_hash':'b','url':b['original_url'],'duplicate_of':'one','primary_hash':'a','evidence_note':'같은 기관·기간·대상·지원 내용 원문 대조'}}
        self.assertEqual(report([b],'2026-11-13',[a],d)['counts']['중복 자료'],1)
        a['content_hash']='changed'
        self.assertEqual(report([b],'2026-11-13',[a],d)['counts']['중복 자료'],0)
if __name__=='__main__':unittest.main()
