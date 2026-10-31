/* View filtering and profile labels only; never changes eligibility or stored values. */
(function(root){
 'use strict';
 const selected=v=>v!==undefined&&v!==null&&String(v).trim()!==''&&!['all','unknown'].includes(String(v));
 function money(won){if(!Number.isSafeInteger(won)||won<=0||won%10000)return '';const man=won/10000,uk=Math.floor(man/10000),rest=man%10000;return (uk?uk.toLocaleString('ko-KR')+'억':'')+(uk&&rest?' ':'')+(rest?rest.toLocaleString('ko-KR')+'만원':uk?'원':'');}
 function regionFilter(item,p){
  const scope=String(item.region||'').trim();
  if(item.verification_status!=='verified'||!['approved','approved_reference'].includes(item.publication))return {state:'check',keep:true,text:'지역 적용 확인 필요'};
  if(/전국|국가 지원사업/.test(scope))return {state:'match',keep:true,text:'전국 대상 · 세부 자격 별도 확인'};
  // Do not turn an office location, an unclear scope or an institution name into a restriction.
  if(/미확인|확인 필요|안내|지역본부|unknown/i.test(scope))return {state:'check',keep:true,text:'지역 적용 확인 필요'};
  const token=scope.split(/[\s;,./]+/)[0],place=root.MunongsaInputUX?.region(token);
  if(!place)return {state:'check',keep:true,text:'지역 적용 확인 필요'};
  if(!selected(p.region)||p.customFarmRegion)return {state:'unselected',keep:true,text:'탐색 지역 미선택'};
  const same=place.region===p.region&&(!place.district||!selected(p.district)||place.district===p.district);
  return {state:same?'match':'mismatch',keep:same,text:same?'선택 지역의 공고 · 세부 자격 별도 확인':'선택한 탐색 지역과 공고 지역이 다름'};
 }
 function chips(p,category,fields,optionText){
  const rows=[];
  const effect=id=>id==='crop'&&p.customCrop||id==='region'&&p.customFarmRegion||id==='residenceRegion'&&p.customResidence?'참고':category==='support'&&id==='region'?'지역 필터':category==='bank'&&id==='requiredFundsWon'?'한도 비교':category==='cultivation'&&['crop','cultivation'].includes(id)?'자료 탐색':['support','bank'].includes(category)&&['applicant','farmingSituation'].includes(id)?'기본 조건 비교':category!=='cultivation'&&fields[id]?'기본 조건 비교':'참고';
  const add=(id,label,value)=>{if(selected(value))rows.push({id,text:label+': '+value+' · '+effect(id)})};
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
