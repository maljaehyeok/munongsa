/* Next actions from existing approved comparisons and detail fields only. */
(function(root){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const editFields={farm_registration:'farmRegistered',residence:'residenceRegionEntry',business_location:'regionEntry',crop:'cropEntry',applicant:'applicant',age:'birthDateEntry',farming_experience:'farmingYears',independent_management:'independentYears',scale:'area',group_size:'groupMemberCount',export_activity:'exporterStatus'};
 function plan(item,row){
  const source=row?.sourceItem||row?.item||item,detail=root.MunongsaSupportDetails?.get(source),display=row?.display||root.MunongsaSupportReview.presentation(source);
  const views=row?root.MunongsaSupportReview.conditionViews(row.comparisonItem||source,row.match):[];
  const decision=row?.decision,actions=[];
  if(display.state==='elapsed')actions.push({text:'기재된 신청기간이 지났어요. 연장·재공고가 있는지 공식 기관에 확인하세요.',kind:'past'});
  else{
   if(display.historical_elapsed)actions.push({text:'과거 모집기간이 지난 기록이 있어요. 현재 추가 모집·연장이 있는지 공식 기관에 먼저 확인하세요.',kind:'history'});
   if(decision?.excluded)actions.push({text:'확인된 조건이 맞지 않아요. 아래 불일치 이유를 확인하고, 입력이 잘못됐다면 수정하세요.',kind:'mismatch'});
   if(decision?.region_state==='check'&&!views.some(v=>/거주 지역|영농지|사업장 소재지/.test(v.label)&&v.fact!=='확인 필요'))actions.push({text:'신청 가능한 거주지·영농지 범위가 확인되지 않았어요. 게시 기관의 지역만으로 신청할 수 있다고 판단하지 말고 원문의 지역 요건을 확인하세요.',kind:'region_unknown'});
   for(const view of views.filter(v=>v.comparison==='check').slice(0,3)){
    const key=view.kind;
    const field=key==='business_location'&&view.locationBasis!=='farm_land'?null:editFields[key];
    actions.push({text:view.label+'을 확인해 주세요. '+(view.fact==='확인 필요'?'공식 조건이 부족해 입력만으로 판단할 수 없어요.':view.fact),field:view.fact==='확인 필요'?null:field,kind:'check'});
   }
   if(!views.length)actions.push({text:'공식 자격조건이 부족해 적합 여부를 판단할 수 없어요. 원문의 신청 대상과 지역 요건을 먼저 확인하세요.',kind:'unknown'});
   const periodAction={unknown:'현재 접수 일정이 확인되지 않았어요. 공식 원문·접수처에서 최신 모집 여부를 확인하세요.',standing:'상시 안내라도 예산 소진·조기 종료될 수 있어요. 접수처에 현재 접수와 잔여 예산을 확인하세요.',upcoming:'기재된 신청 시작일 전입니다. 공식 서식과 제출 방법을 미리 확인하고 접수 시작 안내를 확인하세요.',window:'기재된 모집기간 안이지만 실제 접수는 미확인일 수 있어요. 제출 전 조기 마감·연장·예산 상태를 확인하세요.'};
   actions.push({text:periodAction[display.state]||'제출 전 공식 접수처에서 최신 모집 여부를 확인하세요.',kind:'period'});
  }
  const f=detail?.fields||{},documents=['documents_required','documents_listed','documents_conditional','documents_bonus'].filter(k=>f[k]);
  const destinations=[];
  if(f.method||f.office)destinations.push({section:'method',label:f.method&&f.office?'신청 방법·접수처':f.method?'신청 방법':'접수처'});
  if(documents.length)destinations.push({section:'documents_listed',label:'준비 서류',note:documents.map(k=>({documents_required:'필수로 명시된 서류',documents_listed:'본문 기재 서류 · 필수 여부 별도 확인',documents_conditional:'해당자용 서류',documents_bonus:'가점자료 · 필수 서류와 별개'}[k])).join(' · ')});
  if(f.contact)destinations.push({section:'contact',label:'문의처·주의사항'});
  return {actions,views,method:f.method||null,office:f.office||null,contact:f.contact||null,documents:documents.map(k=>({field:k,...f[k]})),destinations,past:display.state==='elapsed',detailAvailable:!!detail};
 }
 function receptionSummary(item,row){
  const shown=row?.item||item,d=row?.display||root.MunongsaSupportReview.presentation(shown),date=root.MunongsaSupportReview.displayDate;
  const checked=shown.official_observation_at||shown.verified_facts_at;
  const current=d.state==='elapsed'?(shown.known_closed||shown.actual_reception_state==='unavailable'||['closed_verified','cancelled_verified'].includes(shown.application_status)?d.headline:'기재 기간 경과 · 연장·재공고는 별도 확인'):d.historical_elapsed?'과거 기간 경과 기록 있음 · 최신 접수 미확인':d.operator_notice||d.reception_confirmed?'운영기관 모집 안내 확인 · 실제 제출·접수 완료는 미검증':'실제 접수 가능 여부 미확인';
  return `<dl class="preparation-status"><div><dt>기재된 신청기간</dt><dd>${esc(d.periodText)}</dd></div><div><dt>현재 접수 확인</dt><dd>${esc(current)}</dd></div><div><dt>${checked?'공식 사실 확인일':'목록 정보 확인일'}</dt><dd>${esc(date(checked||shown.last_checked_at))}${checked?' · 현재 접수 확인 시점과 다를 수 있어요.':' · 현재 접수를 확인한 시점은 아닙니다.'}</dd></div></dl>`;
 }
 function shortcuts(p){return p.destinations.length?`<div class="preparation-shortcuts"><p><b>${p.past?'지난 공고의 승인된 준비 안내':'승인된 신청 준비 안내'}</b> · 현재 접수 가능 여부는 별도 확인하세요.</p><div class="preparation-actions">${p.destinations.map(d=>`<button type="button" data-preparation-jump="${esc(d.section)}">${esc(d.label)} 확인 ↓</button>`).join('')}</div>${p.destinations.filter(d=>d.note).map(d=>`<p class="notice-meta">${esc(d.note)}</p>`).join('')}</div>`:'';}
 function detail(item,row){const p=plan(item,row);return `<section class="application-next" aria-label="신청 전 다음 행동"><h3>${p.past?'지난 공고를 확인하는 방법':'지금 확인할 일'}</h3>${receptionSummary(item,row)}${shortcuts(p)}<p>공식 요건과 현재 입력을 비교한 안내예요. 신청 가능 확정이나 접수 완료가 아닙니다.</p><ol>${p.actions.map(a=>`<li>${esc(a.text)}${a.field?` <button type="button" class="journey-edit" data-edit-condition="${esc(a.field)}">입력·수정</button>`:''}</li>`).join('')}</ol>${!p.past&&p.documents.length?'<p>아래 ‘준비 서류’는 승인된 공식 자료에 있는 항목만 표시합니다. 해당자용 서류와 필수 서류를 구분하세요.</p>':''}${!p.past&&!p.documents.length?'<p>확인된 공식 서류 목록이 없어요. 임의의 서류를 준비하기보다 원문·접수처에서 목록을 확인하세요.</p>':''}${!p.method&&!p.past?'<p>신청 방법·접수처가 확인되지 않았다면 공식 원문에서 먼저 확인하세요.</p>':''}</section>`;}
 function card(item,row,escape=esc){const p=plan(item,row);return `<span class="match-note journey-next">다음 행동 · ${escape(p.actions[0]?.text||'공식 원문에서 미확인 조건을 확인하세요.')}</span>`;}
 function fundingPlan(money){const project=money.project,own=money.own;const valid=v=>Number.isSafeInteger(v)&&v>=0;return {project:valid(project)?project:null,own:valid(own)?own:null,gap:valid(project)&&valid(own)?Math.max(0,project-own):null};}
 document.addEventListener('click',event=>{const b=event.target.closest?.('[data-edit-condition]');if(!b||!Object.values(editFields).includes(b.dataset.editCondition))return;document.getElementById('closeModal')?.click();if(typeof navigateTo==='function')navigateTo('support');const toggle=document.getElementById('profileToggle');if(toggle?.getAttribute('aria-expanded')==='false')toggle.click();const input=document.getElementById(b.dataset.editCondition);if(!input)return;input.dataset.conditionRequested='true';input.closest('.field')?.removeAttribute('hidden');let parent=input.parentElement;while(parent){if(parent.tagName==='DETAILS')parent.open=true;if(parent.id==='additionalProfileFields')parent.hidden=false;parent=parent.parentElement;}input.focus();input.scrollIntoView({block:'center',behavior:'auto'});});
 document.addEventListener('click',event=>{const button=event.target.closest?.('[data-preparation-jump]'),section=button?.dataset.preparationJump;if(!['method','documents_listed','contact'].includes(section))return;const target=document.querySelector('#modalSource [data-preparation-section="'+section+'"]');if(!target)return;target.focus({preventScroll:true});target.scrollIntoView({block:'start',behavior:'auto'});});
 let fundingDraft=false;
 function syncFunding(){
  if(typeof activeCategory==='undefined'||!root.MunongsaFarmProfile)return;
  let box=document.getElementById('fundingPlanFields');const field=document.getElementById('requiredFundsField');if(!field)return;
  if(!box){box=document.createElement('details');box.id='fundingPlanFields';box.className='funding-plan';box.innerHTML='<summary>사업비와 보유 자금을 나눠서 계산 · 선택</summary><p>입력값의 단순 차액이며 지원금·대출금 확보 예상액이 아닙니다. 숫자만 입력하면 만원 단위예요.</p><label for="projectCostInput">필요 사업비</label><input id="projectCostInput" type="text" maxlength="24" placeholder="예: 5,000만원"><label for="ownFundsInput">보유 자금</label><input id="ownFundsInput" type="text" maxlength="24" placeholder="예: 2,000만원"><div class="chat-followups"><button type="button" id="applyFundingPlan">계산하기</button><button type="button" id="clearFundingPlan">비우기</button></div><p id="fundingPlanStatus" role="status"></p><button type="button" id="useFundingGap" hidden>차액을 필요 자금으로 비교</button>';field.after(box);
   box.querySelector('#applyFundingPlan').addEventListener('click',()=>{const cost=MunongsaAmounts.parseInput(document.getElementById('projectCostInput').value),ownText=document.getElementById('ownFundsInput').value.trim(),own=MunongsaAmounts.parseInput(ownText,'man',true);if(Number.isNaN(cost)||Number.isNaN(own)){document.getElementById('fundingPlanStatus').textContent='음수·잘못된 단위는 사용할 수 없어요. 입력 금액을 확인해 주세요.';return;}fundingDraft=false;const m=MunongsaFarmProfile.money;for(const [k,v]of [['project',cost],['own',own]]){if(v===null)delete m[k];else m[k]=v;}syncFunding();});
   box.querySelector('#clearFundingPlan').addEventListener('click',()=>{fundingDraft=false;delete MunongsaFarmProfile.money.project;delete MunongsaFarmProfile.money.own;box.querySelectorAll('input').forEach(i=>i.value='');syncFunding();});
   box.querySelectorAll('input').forEach(input=>{input.addEventListener('input',()=>{fundingDraft=true;document.getElementById('fundingPlanStatus').textContent='입력 중이에요. 계산하기를 눌러 반영하세요.';});input.addEventListener('change',event=>event.stopPropagation());input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();event.stopPropagation();document.getElementById('applyFundingPlan').click();}});});
   box.querySelector('#useFundingGap').addEventListener('click',()=>{const v=fundingPlan(MunongsaFarmProfile.money);if(v.gap>0&&v.gap%10000===0)MunongsaInputUX.setFunds(v.gap);});
  }
  box.hidden=activeCategory!=='bank';const p=fundingPlan(MunongsaFarmProfile.money),money=v=>MunongsaAmounts.wonText(v);const status=document.getElementById('fundingPlanStatus');
  for(const [id,key]of [['projectCostInput','project'],['ownFundsInput','own']])if(!fundingDraft&&document.activeElement?.id!==id)document.getElementById(id).value=p[key]===null?'':p[key]===0?'0':money(p[key]);
  status.textContent=p.gap!==null?'사업비 '+money(p.project)+' − 보유 자금 '+money(p.own)+' · 단순 차액 '+money(p.gap)+'입니다. 실제 조달 가능액은 별도 심사해요.':'사업비와 보유 자금을 각각 입력하면 단순 차액을 확인할 수 있어요.';
  document.getElementById('useFundingGap').hidden=!(p.gap>0&&p.gap%10000===0);
 }
 document.addEventListener('munongsa:profile-change',()=>setTimeout(syncFunding,0));document.addEventListener('munongsa:profile-reset',()=>{fundingDraft=false;document.querySelectorAll('[data-condition-requested]').forEach(input=>delete input.dataset.conditionRequested);setTimeout(syncFunding,0);});
 root.MunongsaJourney={plan,detail,card,fundingPlan,syncFunding,receptionSummary};
})(globalThis);
