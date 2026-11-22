"""Intent regressions and bounded comparison against an existing private feed."""
import sys,json,types,subprocess,re,unittest
from pathlib import Path
import rag_catalogue as current

class IntentQualityTests(unittest.TestCase):
    def test_purposes_do_not_cross_expand(self):
        for query,title in [('교육 받고 싶어','수출 통관 컨설팅'),('수출 지원','국내 판로 개척'),('농기계 구입','온실 시설현대화'),('시설하우스 설치','청년 창업 정착'),('보험 지원','농식품 안전성 검사'),('시설 설치','기업지원시설 장비 활용'),('시설하우스 설치','시설농업 AI로봇 기술지도 수혜기업')]:
            self.assertFalse(current.discovery_quality(query,title,title)['matches'],(query,title))
    def test_synonyms_and_declared_purpose(self):
        for query,title in [('시설하우스 설치','온실 현대화'),('농업 교육','농업마이스터대학 신입생 모집'),('농기계 구입','농업기계 구입 지원'),('수출 지원','농산물 수출 장려금')]:
            self.assertTrue(current.discovery_quality(query,title,title)['matches'],(query,title))
    def test_crop_plan_is_not_startup(self):
        for context in ({},{'planned':False}):self.assertFalse(current.discovery_quality('토마토 재배하려고 해','청년 창업 지원','청년 창업 지원',context)['matches'])
        self.assertTrue(current.discovery_quality('토마토 시설하우스 설치','온실 현대화','온실 현대화',{'planned':False})['matches'])
    def test_target_education_is_not_an_education_offer(self):
        self.assertFalse(current.discovery_quality('교육 받고 싶어','유기질비료 지원','유기질비료 지원 교육 이수 농업인',purpose='유기질비료 지원')['matches'])

def compare(folder):
    feed=json.loads((Path(folder)/'feed.json').read_text('utf8'));old=types.ModuleType('baseline_catalogue')
    exec(subprocess.check_output(['git','-c','safe.directory=*','show','58c6b31:scripts/rag_catalogue.py']).decode('utf8'),old.__dict__)
    # Reuse the twelve 3.3 questions, then add only newly required distinctions.
    baseline=Path(folder).parents[0]/'practical33-20261122/search-comparison.json'
    questions=[r['query'] for r in json.loads(baseline.read_text('utf8'))]+['토마토 시설하우스를 설치하고 싶어.','농기계 구입 지원사업을 찾아줘.','김제에서 토마토 재배하려고 해.','신청기간이 남은 사업만 보여줘.']
    rows=[]
    for q in questions:
        context={'farm_region':'김제','crop':'토마토','farm_registered':'no','planned':False}
        before=old.matches(q,feed,context);after=current.matches(q,feed,context)
        assert len({(n['url'],n['title']) for n in after})==len(after)
        rows.append({'query':q,'before_total':len(before),'after_total':len(after),'before_top5':[{'id':n['id'],'title':n['title']} for n in before[:5]],'after_top5':[{'id':n['id'],'title':n['title']} for n in after[:5]]})
    (Path(folder)/'quality-comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(rows,ensure_ascii=False,indent=2))

if __name__=='__main__':
    if len(sys.argv)>1:compare(sys.argv[1])
    else:unittest.main()
