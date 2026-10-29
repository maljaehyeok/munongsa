/* Approved support records only. Three-valued evidence comparison, not eligibility approval. */
(function(root){
  'use strict';
  const schema='munongsa-support-public-v1';
  const names={applicant:'신청 주체',residence:'거주지',business_location:'사업장 소재지',age:'연령',farming_experience:'영농경력',independent_management:'독립경영 기간',farm_registration:'농업경영체 등록',crop:'작물',livestock:'축종',scale:'영농 규모',facility:'시설 조건',other_required:'기타 필수 조건',exclusion:'제외 조건'};
  const crops={rice:'벼',garlic:'마늘',onion:'양파',apple:'사과',cabbage:'배추',radish:'무',potato:'감자',sweetpotato:'고구마',soybean:'콩',wheat:'밀',pepper:'고추',greenonion:'파',scallion:'쪽파',strawberry:'딸기'};
  const selected=v=>v!==undefined&&v!==null&&v!==''&&!['all','unknown'].includes(v);
  const number=v=>selected(v)&&Number.isFinite(Number(v))&&Number(v)>=0?Number(v):null;
  const normalize=v=>String(v||'').trim().replace(/전북특별자치도|전라북도/g,'전북').replace(/전라남도/g,'전남').replace(/강원특별자치도|강원도/g,'강원').replace(/경상북도/g,'경북').replace(/경상남도/g,'경남').replace(/충청북도/g,'충북').replace(/충청남도/g,'충남').replace(/경기도/g,'경기').replace(/제주특별자치도|제주도/g,'제주');
  function date(v){if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(v))return null;const d=new Date(v+'T00:00:00Z');return Number.isFinite(+d)&&d.toISOString().slice(0,10)===v?d:null}
  function period(item){const p=item.application_period||{};const aware=v=>typeof v==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(v);const a=aware(p.start)?Date.parse(p.start):NaN,b=aware(p.end)?Date.parse(p.end):NaN;return Number.isFinite(a)&&Number.isFinite(b)&&a<=b?{start:a,end:b}:null}
  function safeUrl(v){try{const u=new URL(v);return u.protocol==='https:'&&!u.username&&!u.password&&(!u.port||u.port==='443')&&!u.hash&&![...u.searchParams.keys()].some(k=>/key|token|auth|secret|password|session/i.test(k))}catch{return false}}
  function publishable(i){return i&&['approved','approved_reference'].includes(i.publication)&&i.verification_status==='verified'&&i.freshness==='current'&&i.last_checked_at&&safeUrl(i.url)&&i.rights?.public_display==='allowed'&&safeUrl(i.rights.evidence_url)&&date(i.rights.checked_at)}
  function eligible(item,now=Date.now()){
    const p=period(item);
    return !!(publishable(item)&&item.publication==='approved'&&item.recommendation_eligible===true&&item.application_status==='open_verified'&&p&&p.start<=now&&now<=p.end);
  }
  function status(item,now=Date.now()){
    const p=period(item);
    if(p&&now>p.end)return item.application_status==='closed_verified'?'모집 마감 · 연장·재공고는 원문 확인':'기재 신청기간 경과 · 연장 여부 확인 필요';
    if(p&&now<p.start&&item.application_status==='upcoming_verified')return '모집 예정 · 확인된 시작일 기준';
    if(p&&p.start<=now&&now<=p.end&&item.application_status==='open_verified')return '기재 신청기간 내 · 예산·접수 가능 여부 원문 확인';
    const facts=item.reference_application_dates||{},valid=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v+'T00:00:00+09:00'))&&new Date(Date.parse(v+'T00:00:00+09:00')+9*3600000).toISOString().slice(0,10)===v;
    const start=facts.start?.date,end=facts.end?.date,today=new Date(now+9*3600000).toISOString().slice(0,10);
    const endTime=facts.end?.time;
    const timed=facts.end?.timezone==='Asia/Seoul'&&typeof endTime==='string'&&/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(endTime);
    if(valid(end)&&timed&&now>=Date.parse(end+'T'+endTime+':00+09:00'))return '기재 신청기한 경과 · 연장·재공고 확인 필요';
    if(valid(end)&&today>end)return '기재 신청기한 경과 · 연장·재공고 확인 필요';
    if(valid(end)&&today===end&&!timed)return '마감일 당일 · 종료 시각 확인 필요';
    if(valid(start)&&today<start)return '기재 신청 시작일 전 · 접수 여부 확인 필요';
    if(valid(start)&&valid(end)&&start<=end&&start<=today&&today<=end)return '기재 신청기간 내 · 접수 시각·가능 여부 확인 필요';
    return '신청 상태 확인 필요';
  }
  function evaluate(item,p){
    const payload=item.eligibility||{},conditions=[],ids=new Set();
    const inRange=(n,v)=>n!==null&&typeof v.min_inclusive==='boolean'&&typeof v.max_inclusive==='boolean'&&
      (v.min==null||(v.min_inclusive?n>=v.min:n>v.min))&&(v.max==null||(v.max_inclusive?n<=v.max:n<v.max));
    for(const c of payload.conditions||[]){
      let state='check',detail='정보 또는 공식 검증 부족';const v=c.value||{},label=names[c.kind]||'조건';
      if(c.status==='verified'&&(c.evidence?.quote||c.evidence?.fact_confirmed===true)&&c.evidence?.location&&safeUrl(c.evidence.url)){
        if(c.presence==='no_restriction'){state='match';detail='원문에서 제한 없음 확인'}
        else if(c.presence==='specified'){
          let actual=null,known=false,ok=false;
          if(c.kind==='applicant'){
            actual={individual:'individual_farmer',young:'individual_farmer',municipality:'institution_group'}[p.applicant];
            // The existing UI groups corporations with producer associations.
            // That combined selection does not establish a specific legal form.
            // Prospective status does not establish that the user is already a farmer.
            known=!!actual&&Array.isArray(v.one_of);ok=known&&v.one_of.includes(actual);
          }else if(c.kind==='residence'){
            const province=normalize(p.residenceRegion),district=normalize(p.residenceDistrict);
            const scopes=Array.isArray(v.regions)?v.regions.map(normalize):[];
            const values=scopes.map(scope=>{
              const parts=scope.split(/\s+/);if(scope==='전국')return 'match';
              if(!selected(province))return 'check';
              if(province!==parts[0])return 'mismatch';
              if(parts.length===1)return 'match';
              if(!selected(district))return 'check';
              return parts.length===2?(district===parts[1]?'match':'mismatch'):'check';
            });
            state=values.includes('match')?'match':!values.length||values.includes('check')?'check':'mismatch';
            detail=state==='check'?'거주지 또는 지역 범위 추가 확인':'입력한 거주지와 원문 지역 비교';
          }else if(c.kind==='age'){
            const born=date(p.birthDate),basis=date(v.basis_date);
            if(born&&basis&&born<=basis&&['international','calendar'].includes(v.age_basis)){
              actual=basis.getUTCFullYear()-born.getUTCFullYear();
              if(v.age_basis==='international'&&(basis.getUTCMonth()<born.getUTCMonth()||(basis.getUTCMonth()===born.getUTCMonth()&&basis.getUTCDate()<born.getUTCDate())))actual--;
              known=true;ok=inRange(actual,v);detail=`공고 기준일 ${v.basis_date} · 계산 연령 ${actual}세`;
            }else detail='생년월일·공고 연령 기준일 확인 필요 (현재 나이로 과거 기준일을 추정하지 않음)';
          }else if(c.kind==='farming_experience'||c.kind==='independent_management'){
            actual=number(c.kind==='farming_experience'?p.farmingYears:p.independentYears);
            known=actual!==null&&v.unit==='years'&&!!date(v.basis_date)&&p.experienceBasisDate===v.basis_date;
            ok=known&&inRange(actual,v);detail=known?`공고 기준일 ${v.basis_date}의 입력 경력 비교`:'정확한 경력·단위·공고 기준일 확인 필요 (영농 단계만으로 추정하지 않음)';
          }else if(c.kind==='farm_registration'){
            known=['yes','no'].includes(p.farmRegistered);ok=known&&((p.farmRegistered==='yes')===v.registered);
          }else if(c.kind==='crop'){
            actual=crops[p.crop];known=!!actual&&Array.isArray(v.any_of);ok=known&&v.any_of.includes(actual);
          }else if(c.kind==='scale'){
            actual=number(p.area);known=actual!==null&&v.unit==='ha'&&v.metric==='cultivated_area';ok=known&&inRange(actual,v);
          }else detail='현재 프로필로 확인할 수 없는 조건 · 원문과 담당 기관 확인';
          if(known){state=ok?'match':'mismatch';if(detail==='정보 또는 공식 검증 부족')detail='입력값과 검증된 조건 비교'}
        }
      }
      if(ids.has(c.condition_id))state='check';ids.add(c.condition_id);
      conditions.push({id:c.condition_id,field:c.kind,status:state,reason:`${label}: ${state==='match'?'일치':state==='mismatch'?'불일치':'추가 확인 필요'} · ${detail}`,evidence:c.evidence||{}});
    }
    const byId=new Map(conditions.map(c=>[c.id,c]));let nodes=0;
    function walk(node,depth=0){
      if(!node||++nodes>200||depth>12)return 'check';
      if(node.condition_id)return byId.get(node.condition_id)?.status||'check';
      if(!Array.isArray(node.children)||!node.children.length)return 'check';
      const values=node.children.map(n=>walk(n,depth+1));
      if(node.op==='AND')return values.includes('mismatch')?'mismatch':values.includes('check')?'check':'match';
      if(node.op==='OR')return values.includes('match')?'match':values.includes('check')?'check':'mismatch';
      if(node.op==='NOT'&&values.length===1)return {match:'mismatch',mismatch:'match',check:'check'}[values[0]];
      return 'check';
    }
    let conditionStatus=walk(payload.logic);
    // A malformed graph must never silently omit a required condition.
    const used=new Set();function refs(n,d=0){if(!n||d>12)return;if(n.condition_id)used.add(n.condition_id);else if(Array.isArray(n.children))n.children.forEach(x=>refs(x,d+1))}refs(payload.logic);
    if(!conditions.length||used.size!==byId.size||[...used].some(id=>!byId.has(id))||ids.size!==conditions.length)conditionStatus='check';
    if(p.applicant==='prospective'&&selected(p.experience)&&p.experience!=='planned')conditionStatus='check';
    return {conditionStatus,conditions,matched:conditions.filter(c=>c.status==='match').map(c=>c.reason),
      unknown:conditions.filter(c=>c.status==='check').map(c=>c.reason),different:conditions.filter(c=>c.status==='mismatch').map(c=>c.reason),
      explanation:conditionStatus==='match'?'기록된 논리식 충족 · 공식 신청 자격 확정 아님':conditionStatus==='mismatch'?'전체 조건 논리식과 불일치 · 공식 탈락 판정 아님':'미확인 조건 또는 입력 정보 부족 · 신청 자격 판단 보류'};
  }
  function recruitment(item,now=Date.now()){
    const p=period(item),facts=item.reference_application_dates||{};
    const kday=ms=>new Date(ms+9*3600000).toISOString().slice(0,10),today=kday(now);
    const start=p?kday(p.start):facts.start?.date,end=p?kday(p.end):facts.end?.date;
    let state='unknown';const text=status(item,now);
    if(/경과|모집 마감/.test(text))state='elapsed';
    else if(/시작일 전|모집 예정/.test(text))state='upcoming';
    else if(/신청기간 내/.test(text))state='window';
    let badge='';
    if(date(end)&&end>=today){
      const days=Math.round((Date.parse(end+'T00:00:00Z')-Date.parse(today+'T00:00:00Z'))/86400000);
      badge=days===0?'오늘 마감(기재 기한) · 접수 시각·여부 확인':`D-${days} · 기재 마감일 기준`;
    }
    return {state,badge,start:start||null,end:end||null,as_of:new Date(now).toISOString(),eligibility_separate:true};
  }
  function explore(data,profile,now=Date.now()){
    if(!data||data.schema_version!==schema||!Array.isArray(data.notices))throw new Error('invalid_support_public_schema');
    const seen=new Set(),rows=[];
    for(const item of data.notices){if(!item||typeof item.id!=='string'||seen.has(item.id)||!publishable(item))continue;seen.add(item.id);rows.push({item,match:evaluate(item,profile),available:eligible(item,now),status:status(item,now),recruitment:recruitment(item,now)})}
    const rank=r=>/경과|모집 마감/.test(r.status)?3:/시작일 전|모집 예정/.test(r.status)?1:/신청기간 내/.test(r.status)?0:2;
    rows.sort((a,b)=>rank(a)-rank(b)||((a.recruitment.end||'9999-12-31').localeCompare(b.recruitment.end||'9999-12-31'))||({match:0,check:1,mismatch:2}[a.match.conditionStatus]-{match:0,check:1,mismatch:2}[b.match.conditionStatus]));
    return {recommendations:rows.filter(r=>r.available&&r.match.conditionStatus!=='mismatch'),excluded:rows.filter(r=>r.available&&r.match.conditionStatus==='mismatch'),references:rows.filter(r=>!r.available)};
  }
  root.MunongsaSupport={evaluate,explore,eligible,status,recruitment,safeUrl,schema};
})(globalThis);
