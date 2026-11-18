"""Classify existing comparison output; does not approve conditions or notices."""
import rag_profile


def decision(result, *, national=False, complete=False, audience_check=False):
    """Presentation/rank over verified comparison only; never grants eligibility."""
    region='match' if national else result.get('region_state','check')
    if result.get('label')=='조건 불일치':category,label,tier='C','명확한 조건 불일치',4
    elif audience_check:category,label,tier='D','조건 정보 부족',3
    elif region=='match':
        if complete and result.get('structured_state')=='match' and not result.get('checks'):
            category,label,tier='A','확인된 조건 일치',0
        else:category,label,tier='B','추가 자격 확인 필요',1
    elif result.get('verified_condition_count',0):category,label,tier='B','지역 확인 필요',2
    else:category,label,tier='D','조건 정보 부족',3
    return {'category':category,'label':label,'tier':tier,'region_state':region,
            'audience_check':bool(audience_check),'excluded':category=='C',
            'final_application_eligibility_confirmed':False}


def apply(result, **kwargs):
    value={**result,'reasons':list(result.get('reasons',[])),'checks':list(result.get('checks',[])),
           'questions':list(result.get('questions',[]))}
    value['decision']=decision(value,**kwargs)
    if value['decision']['region_state']=='match' and not value['decision']['excluded']:
        value['reasons']=list(dict.fromkeys(['공식 자료의 지역 적용 범위 일치 · 전체 자격은 미확정입니다.']+value['reasons']))[:3]
    if value['decision']['region_state']!='match' and not value['decision']['excluded']:
        value['checks']=list(dict.fromkeys(['공식 지역 기준이 확인되지 않았거나 필요한 거주지·영농지·사업장 정보가 부족합니다.']+value['checks']))[:4]
    if value['decision']['audience_check']:
        value['checks']=list(dict.fromkeys(['수출업체·수출실적 요건은 영농 시작 예정 여부와 별도로 확인해야 합니다.']+value['checks']))[:4]
    return value


def classify(document,context,valid_url,areas):
    item=document['public'];clauses=(item.get('eligibility') or {}).get('conditions',[])
    if (item.get('publication') not in ('approved','approved_reference')
            or not any(c.get('status')=='verified' and c.get('presence')=='specified' for c in clauses)):
        return {'category':'D','label':'맞춤 비교 근거 부족','reason':'공개·조건 승인 전이거나 검증된 조건이 없습니다.'}
    if item.get('application_status') in ('closed','period_elapsed','closed_verified'):
        return {'category':'D','label':'지난 공고 참고','reason':'기간이 경과한 공고는 현재 신청 추천으로 표시하지 않습니다.'}
    result=rag_profile.compare(document,context,valid_url,areas)
    verdict=decision(result,complete=item.get('eligibility_complete') is True)
    return {**verdict,'comparison':result}
