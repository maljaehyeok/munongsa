/* View filtering and profile labels only; never changes eligibility or stored values. */
(function(root){
 'use strict';
 const selected=v=>v!==undefined&&v!==null&&String(v).trim()!==''&&!['all','unknown'].includes(String(v));
 function money(won){if(!Number.isSafeInteger(won)||won<=0||won%10000)return '';const man=won/10000,uk=Math.floor(man/10000),rest=man%10000;return (uk?uk.toLocaleString('ko-KR')+'억':'')+(uk&&rest?' ':'')+(rest?rest.toLocaleString('ko-KR')+'만원':uk?'원':'');}
 function regionFilter(item,p){
  const scope=String(item.region||'').trim();
  if(item.verification_status!=='verified'||!['approved','approved_reference'].includes(item.publication))return {state:'check',keep:true,text:'지역 적용 확인 필요'};
  const comparison=root.MunongsaSupport?.regional(item,p);
  if(comparison?.conditionStatus==='mismatch')return {state:'mismatch',keep:false,text:'입력한 거주지·영농지와 확인된 지역 요건 불일치'};
  if(comparison?.conditionStatus==='match')return {state:'match',keep:true,text:'확인된 지역 요건 비교 · 전체 자격 별도 확인'};
  if((item.eligibility?.conditions||[]).some(c=>['residence','business_location'].includes(c.kind)))return {state:'check',keep:true,text:'공식 지역 기준 또는 입력 정보 추가 확인 필요'};
  if(/^전국(?:\s*대상)?$/.test(scope))return {state:'match',keep:true,text:'전국 대상 · 세부 자격 별도 확인'};
  // Do not turn an office location, an unclear scope or an institution name into a restriction.
  if(/미확인|확인 필요|확인되지|안내|지역본부|unknown/i.test(scope))return {state:'check',keep:true,text:'지역 적용 확인 필요'};
  // A bare city or reception-office label establishes relevance, not whether
  // the applicant must live there or farm there. Never guess that basis.
  if(!/농지|영농지|재배지|거주/.test(scope))return {state:'check',keep:true,text:'거주지·영농지 중 적용 기준 확인 필요'};
  if(/거주/.test(scope)&&/농지|영농지|재배지/.test(scope))return {state:'check',keep:true,text:'거주지·영농지의 결합 기준 추가 확인 필요'};
  const token=scope.split(/[\s;,./]+/)[0],place=root.MunongsaInputUX?.region(token);
  if(!place)return {state:'check',keep:true,text:'지역 적용 확인 필요'};
  const residence=/거주/.test(scope),province=residence?p.residenceRegion:p.region,district=residence?p.residenceDistrict:p.district;
  if(!selected(province)||(residence?p.customResidence:p.customFarmRegion))return {state:'unselected',keep:true,text:'비교할 지역 미입력'};
  if(place.district&&!selected(district)&&place.region===province)return {state:'check',keep:true,text:'비교할 시·군 추가 확인 필요'};
  const same=place.region===province&&(!place.district||place.district===district);
  return {state:same?'match':'mismatch',keep:same,text:same?'선택 지역의 공고 · 세부 자격 별도 확인':'선택한 탐색 지역과 공고 지역이 다름'};
 }
 function chips(p,category,fields,optionText){
  const rows=[];
  const add=(id,label,value)=>{if(selected(value))rows.push({id,label,value:String(value),text:label+': '+value})};
  const text=id=>optionText(id,p[id])||p[id];
  add('farmingSituation','영농 형태',selected(p.farmingSituation)?text('farmingSituation'):'');
  add('applicant','신청자 유형',selected(p.applicant)?text('applicant'):'');
  add('region','영농지역',p.customFarmRegion||[selected(p.region)?text('region'):'',selected(p.district)?p.district:''].filter(Boolean).join(' '));
  add('crop','작물',p.customCrop||(selected(p.crop)?text('crop'):''));
  add('cultivation','재배방식',selected(p.cultivation)?text('cultivation'):'');
  add('residenceRegion','거주지',p.customResidence||[selected(p.residenceRegion)?p.residenceRegion:'',selected(p.residenceDistrict)?p.residenceDistrict:''].filter(Boolean).join(' '));
  for(const [id,label]of [['birthDate','생년월일'],['experienceBasisDate','경력 기준일']])if(root.MunongsaInputUX.validBirth(p[id]||''))add(id,label,p[id]);
  for(const [id,label]of [['farmRegistered','경영체 등록'],['experience','영농경력 구분'],['exporterStatus','수출 관련']])add(id,label,selected(p[id])?text(id):'');
  for(const [id,label,unit]of [['age','나이','세'],['farmingYears','영농경력','년'],['independentYears','독립경영','년'],['groupMemberCount','공동 신청','명'],['area','면적','ha'],['budget','예산','만원']])if(selected(p[id])&&Number.isFinite(Number(p[id]))&&Number(p[id])>=0&&(id!=='age'||Number(p[id])>=15&&Number(p[id])<=100))add(id,label,Number(p[id]).toLocaleString('ko-KR')+unit);
  add('requiredFundsWon','필요 자금',money(p.requiredFundsWon));
  return rows;
 }
 root.MunongsaSelection={money,regionFilter,chips};
})(globalThis);
