"""Related discovery must never grant eligibility or use unpublished evidence."""
import copy,json,sys,unittest,types,subprocess
from pathlib import Path
from datetime import datetime,timedelta,timezone
import rag_catalogue as current
from unittest.mock import patch

class RelatedDiscoveryTests(unittest.TestCase):
    def test_topic_relevance_is_not_eligibility(self):
        score,hit=current.discovery_score('김제에서 토마토 농사를 시작하려고 해','청년농업인 창업 지원','청년농업인 창업 지원')
        self.assertTrue(hit);self.assertGreater(score,0)
        self.assertTrue(current.discovery_score('김제에서 토마토 재배하려고 해.','청년농업인 창업 지원','청년농업인 창업 지원')[1])
        self.assertFalse(current.discovery_score('시설 설치 관련 사업','농업인 건강검진','농업인 건강검진')[1])

    def test_context_does_not_force_crop_and_region_into_topic(self):
        now=datetime.now(timezone.utc)
        item={'id':'NOTICE-discovery','title':'온실 시설현대화 지원','institution':'공식 기관','url':'https://www.rda.go.kr/young/custom/policy/view.do?sId=1','publication':'official_guidance','verification_status':'basics_only','recommendation_eligible':False,'eligibility_complete':False,'freshness':'current','last_checked_at':now.isoformat(),'guidance_expires_at':(now+timedelta(days=1)).isoformat(),'rights':{'public_display':'allowed'}}
        feed={'schema_version':'munongsa-support-public-v1','notices':[item]}
        context={'farm_region':'전북 김제시','crop':'토마토','farm_registered':'no'}
        before=copy.deepcopy(feed)
        found=current.matches('시설 설치 관련 사업도 있어?',feed,context,now)
        self.assertEqual([r['id'] for r in found],[item['id']])
        decision=current.comparison(item,feed,context,now)['decision']
        self.assertEqual(decision['region_state'],'check')
        self.assertFalse(decision['final_application_eligibility_confirmed'])
        item['rights']['public_display']='pending'
        self.assertEqual(current.matches('시설',feed,context,now),[])
        self.assertEqual(before['notices'][0]['title'],item['title'])

    def test_beginner_question_returns_discovery_not_only_help(self):
        import rag_api,rag_nlu
        now=datetime.now(timezone.utc)
        item={'id':'NOTICE-beginner','title':'청년농업인 창업 지원','institution':'공식 기관','url':'https://www.rda.go.kr/young/custom/policy/view.do?sId=1','publication':'official_guidance','verification_status':'basics_only','recommendation_eligible':False,'eligibility_complete':False,'freshness':'current','last_checked_at':now.isoformat(),'guidance_expires_at':(now+timedelta(days=1)).isoformat(),'rights':{'public_display':'allowed'}}
        corpus={'guidance_feed':{'schema_version':'munongsa-support-public-v1','notices':[item]},'documents':{},'sync_generation':'isolated','sync_verified':True}
        with patch.object(rag_api,'load_api_corpus',return_value=corpus),patch.object(rag_nlu,'interpret',side_effect=AssertionError('unnecessary model call')):
            result=rag_api.local_pipeline('전북에서 농사 처음 시작하는데 받을 수 있는 지원이 뭐야?')
        self.assertEqual(result['kind'],'catalogue')
        self.assertEqual(result['programs'][0]['id'],item['id'])
        self.assertFalse(result['programs'][0]['comparison']['decision']['final_application_eligibility_confirmed'])

def operational_comparison(folder):
    feed=json.loads((Path(folder)/'feed.json').read_text('utf8'))
    old=types.ModuleType('previous_catalogue')
    exec(subprocess.check_output(['git','-c','safe.directory=*','show','371437c:scripts/rag_catalogue.py']).decode('utf8'),old.__dict__)
    profiles=[('전북에서 농사 처음 시작하는데 받을 수 있는 지원이 뭐야?','전북 김제시','토마토'),('김제에서 토마토 농사를 시작하려고 해','전북 김제시','토마토'),('시설 설치 관련 사업도 있어?','전북 김제시','토마토'),('교육 받을 사업','제주 제주시','감귤'),('비료 지원사업','경기 하남시','상추'),('유기질비료','전남 화순군','벼'),('농업인 건강검진','경기 화성시','포도'),('청년 창업','경북 안동시','사과'),('시설 현대화','경남 산청군','딸기'),('보험 지원','전북 전주시','벼'),('수출 지원','전남 구례군','오이'),('지난 공고','제주 제주시','감귤')]
    rows=[]
    for q,area,crop in profiles:
        context={'farm_region':area,'crop':crop,'farm_registered':'no','planned':True}
        before=old.matches(q,feed,context);after=current.matches(q,feed,context)
        for n in after:
            verdict=current.comparison(n,feed,context,datetime.now(timezone.utc))['decision']
            assert verdict['final_application_eligibility_confirmed'] is False
        rows.append({'query':q,'before':len(before),'after':len(after),'before_top3':[n['title'] for n in before[:3]],'after_top3':[n['title'] for n in after[:3]]})
    (Path(folder)/'search-comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'scenarios':len(rows),'improved':sum(r['after']>r['before'] for r in rows),'no_false_eligibility':True}))

if __name__=='__main__':
    if len(sys.argv)>1:operational_comparison(sys.argv[1])
    else:unittest.main()
