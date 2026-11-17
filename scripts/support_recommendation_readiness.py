"""Classify existing comparison output; does not approve conditions or notices."""
import rag_profile


def classify(document,context,valid_url,areas):
    item=document['public'];clauses=(item.get('eligibility') or {}).get('conditions',[])
    if (item.get('publication') not in ('approved','approved_reference')
            or not any(c.get('status')=='verified' and c.get('presence')=='specified' for c in clauses)):
        return {'category':'D','label':'맞춤 비교 근거 부족','reason':'공개·조건 승인 전이거나 검증된 조건이 없습니다.'}
    if item.get('application_status') in ('closed','period_elapsed','closed_verified'):
        return {'category':'D','label':'지난 공고 참고','reason':'기간이 경과한 공고는 현재 신청 추천으로 표시하지 않습니다.'}
    result=rag_profile.compare(document,context,valid_url,areas)
    if result['label']=='조건 불일치':category='C'
    elif (item.get('eligibility_complete') is True and not result['checks']
          and all(c.get('status')=='verified' and c.get('presence')!='unknown' for c in clauses)
          and result['label']=='관련 가능성 있음'):category='A'
    else:category='B'
    return {'category':category,'comparison':result,'final_application_eligibility_confirmed':False}
