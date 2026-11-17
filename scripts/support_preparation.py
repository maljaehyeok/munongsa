"""Conservative local review of already fetched official HTML. No approval or network."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
import review_support_details as review

ALIASES = {
    'target': ('사업대상','지원대상','신청대상','신청자격','지원자격'),
    'summary': ('사업내용','지원내용','사업개요'),
    'funding': ('지원한도',), 'subsidy': ('지원비율',),
    'method': ('신청방법',), 'office': ('신청장소','접수처'),
    'documents_listed': ('제출서류','신청서류','첨부서류'),
    'documents_required': ('필수제출서류',),
}
LABELS = '|'.join(sorted(set(sum((list(v) for v in ALIASES.values()),[])) |
    {'사업명','신청기간','신청기한','접수기간','지원조건','지원기간','지원기준','문의사항','유의사항','주의사항'},key=len,reverse=True))
BOUNDARY = re.compile(r'\s*(?:[▪□○※]|[가-힣]\.\s*(?='+LABELS+r')|(?<![가-힣])(?='+LABELS+r'\s*[:：]))')

def clean(value): return re.sub(r'\s+',' ',value).strip()

def preview_feed(records):
    """Rendering fixtures, not operational approval or a publishable RAG feed."""
    now=datetime.now(timezone.utc);items=[]
    for record in records:
        b=record['basis'];item={k:copy.deepcopy(b[k]) for k in ('id','title','url','target','region')}
        item.update(reference_application_dates=copy.deepcopy(b['dates']),application_period=copy.deepcopy(b['period']),eligibility=copy.deepcopy(b['eligibility']),
            source_id='local-official-review',institution='공식 원문 확인 · 로컬 검토용',publication='official_guidance',verification_status='basics_only',
            recommendation_eligible=False,eligibility_complete=False,freshness='current',last_checked_at=now.isoformat(),guidance_expires_at=(now+timedelta(hours=24)).isoformat(),
            local_review_only=True,rights={'public_display':'allowed','evidence_url':b['url'],'checked_at':now.date().isoformat()},
            attribution='로컬 검토용 · 실제 공개 승인이 아님',license='공개 이용 범위 최종확인 전')
        items.append(item)
    return {'schema_version':'munongsa-support-public-v1','local_review_only':True,'generated_at':now.isoformat(),'notices':items}

def extract(basis, html, checked_at):
    """Only labelled values become facts; attachment names are not required papers."""
    soup=BeautifulSoup(html,'html.parser');host=urlsplit(basis['url']).hostname
    if host not in ('www.rda.go.kr','global.at.or.kr'):raise ValueError('explicit review scope only')
    node=soup.select_one('.viewArea') if host=='www.rda.go.kr' else soup.select_one('.contentGroup')
    if node is None:raise ValueError('official detail unavailable')
    body=clean(node.get_text(' ',strip=True))
    title=clean(basis['title']).replace('농업기술센터 ','').replace(' 첨부파일 있음','')
    if title.replace(' ','') not in body.replace(' ',''):raise ValueError('official title mismatch')
    tables={};summary=''
    for tr in node.select('tr'):
        th,td=tr.find('th'),tr.find('td')
        if th is None or td is None:continue
        label=clean(th.get_text(' ',strip=True)).replace(' 필수','');value=clean(td.get_text(' ',strip=True))
        if value and label not in tables:tables[label]=value
    summary=tables.get('요약내용') or tables.get('사업요약내용') or tables.get('내용') or ''
    segments=[s.strip(' -') for s in BOUNDARY.split(summary) if s.strip(' -')]
    fields={}
    def add(name,value,location,quote):
        if not value or not quote:return
        fields[name]={'value':value,'evidence':{'url':basis['url'],'location':location,
            'checked_at':checked_at,'quote':quote}}
    for name,aliases in ALIASES.items():
        candidate=None
        for alias in aliases:
            if tables.get(alias):candidate=(tables[alias],alias);break
            for segment in segments:
                match=re.match(re.escape(alias)+r'(?:\s*[:：]\s*|\s+)(.+)',segment)
                if match:candidate=(match[1],alias);break
            if candidate:break
        if candidate:
            value,label=candidate
            if name.startswith('documents_') and re.fullmatch(r'.{0,35}(?:참고|참조).{0,10}',value):continue
            add(name,value,'본문 '+label,value)
    period=tables.get('신청기간') or tables.get('접수기간')
    if period and re.search(r'20\d{2}-\d{2}-\d{2}',period):add('period',period,'공식 신청·접수기간 표',period)
    department=tables.get('담당부서') or tables.get('주관기관') or ''
    phone=re.search(r'(?<!\d)0\d{1,2}-\d{3,4}-\d{4}(?:,\d{4})?',department+' '+body)
    if phone:add('contact',phone[0],'공식 담당부서·문의 전화',phone[0])
    method=fields.get('method',{}).get('value','')
    office=re.search(r'방문\s*신청\s*[(（]([^）)]+)[)）]',method)
    if office and not fields.get('office'):add('office',office[1],'본문 신청방법의 접수처',office[0])
    visit=re.search(r'방문\s*신청',summary)
    if visit and not method:add('method','방문 신청','본문 방문 신청 명시 문구',visit[0])
    if host=='global.at.or.kr' and re.search(r'사업\s*신청',body) and '로그인' in soup.get_text():
        add('method','공식 페이지의 사업 신청 버튼 · 로그인 이후 절차 미검증','공식 신청 버튼과 로그인 안내','사업 신청')
    target=fields.get('target',{}).get('value','')
    age=re.search(r'만\s*\d+\s*세?\s*(?:이상|~)\s*만?\s*\d+\s*세?\s*(?:미만|이하)?',target)
    if age:add('age',age[0],'본문 신청자격의 연령 문구',age[0])
    geographic=[s for s in segments if re.search(r'농지소재지|농지 소재지|관내|거주|주소지',s) and re.match(r'(?:지원자격|신청대상|지원대상|지원조건)',s)]
    if geographic:add('region',geographic[:2],'본문 거주지·농지·접수처 구분',geographic[0])
    share=re.search(r'자부담\s*\d+(?:\.\d+)?\s*%',summary)
    if share:add('self_payment',share[0],'본문 자부담 명시 비율',share[0])
    cautions=[s for s in segments if re.search(r'지원\s*제한|신청불가|지원\s*불가|예산|사업을 포기|초과 지원',s)]
    if cautions:add('warnings',cautions[:4],'본문 지원 제한·예산 유의사항',cautions[0])
    unresolved=['실제 접수 완료 여부와 첨부 지침 전체는 검증하지 않았습니다.','현재 운영 승인 DB와의 일치 및 공개 이용 범위는 최종 검토가 필요합니다.']
    if fields.get('documents_listed') and not fields.get('documents_required'):unresolved.append('본문 기재 서류의 필수·해당자·가점 구분은 첨부 지침에서 확인해야 합니다.')
    if '지원비율' not in tables and not fields.get('subsidy'):unresolved.append('보조율과 자부담의 전체 조건은 확인되지 않았습니다.')
    if '포항' in body:unresolved.append('연령 표현과 출생연도 범위의 일치 여부는 운영기관 확인이 필요합니다.')
    add('unconfirmed',unresolved,'이번 로컬 검토 범위',title)
    return {'basis':copy.deepcopy(basis),'source_sha256':hashlib.sha256(html).hexdigest(),'rights':{'facts_only':True,'policy_url':basis['url'],
        'note':'로컬 검토 초안. 원문·첨부 재배포 또는 공개 승인 아님.'},'fields':fields}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--audit',type=Path,required=True);p.add_argument('--basis',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    root=Path(__file__).resolve().parents[1];out=args.output.resolve()
    if not out.is_relative_to(root/'work') or out.exists():raise ValueError('new private work output required')
    audit=json.loads(args.audit.read_text(encoding='utf-8'));basis={r['basis']['id']:r['basis'] for r in json.loads(args.basis.read_text(encoding='utf-8-sig'))['records']};records=[];excluded=[]
    for row in audit['records']:
        if len(records)>=11:break
        if row['status']!='fetched' or urlsplit(row['url']).hostname not in ('www.rda.go.kr','global.at.or.kr'):continue
        try:
            html=(args.audit.parent/(row['id']+'.html')).read_bytes()
            records.append(extract(basis[row['id']],html,row['checked_at']))
        except ValueError as e:excluded.append({'id':row['id'],'reason':str(e)})
    if not records:raise ValueError('no verified detail candidates')
    plan={'schema':'munongsa-support-details-plan-v1','records':records};review.validate(plan)
    out.mkdir(parents=True);raw=(json.dumps(plan,ensure_ascii=False,indent=2)+'\n').encode();(out/'plan.json').write_bytes(raw)
    preview=review.build(plan,'local-preview',hashlib.sha256(raw).hexdigest())
    (out/'preview-details.json').write_text(json.dumps(preview,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'preview-feed.json').write_text(json.dumps(preview_feed(records),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reviewed_candidates':len(records),'excluded':excluded,'approved':False,'plan_sha256':hashlib.sha256(raw).hexdigest()}))

if __name__=='__main__':main()
