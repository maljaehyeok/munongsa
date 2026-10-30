/* Presentation only: original titles, conditions, approvals and profile history stay intact. */
(function(root){
 'use strict';
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function title(value){const raw=String(value||'');return raw.replace(/^(?:\s*[\[(]\s*첨부파일\s*있음\s*[\])]\s*)+/,'').replace(/(?:\s*[\[(]?\s*첨부파일\s*있음\s*[\])]?\s*)+$/,'').trim()||raw}
 function period(item){const display=root.MunongsaSupportReview.displayDate,p=item.application_period||{},r=item.reference_application_dates||{};const fact=v=>v?.date?display(v.date)+(/^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(v.time||'')?' '+v.time+(v.timezone==='Asia/Seoul'?'':' (원문 시각 · 시간대 확인 필요)'):''):null;return (p.start?display(p.start):fact(r.start)||'시작일 미확인')+' ~ '+(p.end?display(p.end):fact(r.end)||'마감일 미확인')}
 function recruitment(item,display){return {window:'기재 모집기간 내 · 접수 여부는 원문 확인',upcoming:'모집 예정 · 확인된 시작일 기준',elapsed:item.known_closed===true?'공식 마감 안내':'기재 신청기한 경과',unknown:'기간·접수 상태 확인 필요'}[display.state]||'기간·접수 상태 확인 필요'}
 const situationApplicant={preparing:'prospective',family:'all',independent:'individual',organization:'organization',unknown:'all'};
 function applicantForSituation(value){return situationApplicant[value]||'all'}
 function situationForApplicant(value,current){return ['organization','agricultural_corporation','group','business','municipality'].includes(value)?'organization':applicantForSituation(current)===value?current:'unknown'}
 function sourceButton(url,label='공식 공고 보기'){return root.MunongsaSupport.safeUrl(url)?`<a class="source-link source-action" href="${esc(url)}" target="_blank" rel="noopener">${esc(label)} <span aria-hidden="true">↗</span></a>`:''}
 function supportDetail(item,row,display,period){
  const known=v=>typeof v==='string'&&v.trim()&&!['unknown','확인 필요'].includes(v),review=root.MunongsaSupportReview;
  const views=row?review.conditionViews(item,row.match):[],facts=views.filter(v=>v.fact!=='확인 필요'),missing=views.filter(v=>v.fact==='확인 필요');
  const status={match:'입력 조건 일치',mismatch:'입력 조건 불일치',check:'내 정보 또는 세부 조건 확인'};
  const documents=known(item.required_documents)?item.required_documents:Array.isArray(item.required_documents)&&item.required_documents.length&&item.required_documents.every(known)?item.required_documents.join(' · '):'필요 서류는 공식 공고에서 확인해 주세요.';
  const fields=[...(known(item.support)?[['지원 내용',item.support]]:[]),['신청기간',period],['모집 상태',recruitment(item,display)],['신청 대상',known(item.target)?item.target:'공식 공고의 신청 대상을 확인해 주세요.'],['대상 지역',known(item.region)?item.region:'공식 공고의 지역 요건을 확인해 주세요.'],...(!known(item.support)?[['지원 내용','지원 규모와 세부 내용은 공식 공고에서 확인해 주세요.']]:[]),['신청 방법',known(item.application_method)?item.application_method:'신청처와 접수 방법은 공식 공고에서 확인해 주세요.'],['필요 서류',documents]];
  const reviewed=root.MunongsaSupportDetails?.get(row?.item||item);
  const shownFields=reviewed?fields.filter(([k])=>!['지원 내용','신청 방법','필요 서류'].includes(k)):fields;
  const details=reviewed?root.MunongsaSupportDetails.detail(row?.item||item,esc,review.displayDate):'';
  const comparisons=facts.map(v=>`<li><b>${esc(v.label)}</b><p class="condition-result ${esc(v.comparison)}">${esc(v.comparison==='check'?'입력 후 비교 가능':v.status)}</p><p>${esc(v.fact)}</p></li>`).join('');
  const application=item.application_url_verified===true?sourceButton(item.application_url,'공식 신청 페이지 보기'):'';
  return `<h3>내 조건과 비교</h3><p>${row?esc(status[row.match.conditionStatus]||status.check):'검토 중 참고 공고 · 자격 비교 전'}</p><dl class="support-detail-list user-facts">${shownFields.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${details}<div class="detail-actions">${sourceButton(item.url)}${application}</div>${facts.length?`<h3>비교한 조건과 근거</h3><ul>${comparisons}</ul>`:''}${missing.length?`<details class="more-conditions"><summary>더 확인할 조건 ${missing.length}개</summary><p>${esc([...new Set(missing.map(v=>v.label))].join(' · '))}</p></details>`:''}<div class="detail-caution"><h3>신청 전 확인하세요</h3><p>${esc(display.chips.filter(c=>!['세부 자격 일부 미확인','마감 임박','기재 기간 경과','검토중 · 참고자료'].includes(c.text)).map(c=>c.text).join(' · '))}</p><p>조건 비교는 신청 자격·접수 가능 확정이 아닙니다. 정정·연장·예산 소진·조기 종료와 세부 요건은 공식 원문에서 확인하세요.</p></div><p class="notice-meta">게시일 ${esc(review.displayDate(item.published_at))}<br>정보 확인일 ${row?esc(review.displayDate(item.last_checked_at)):'검토 전'}<br>마지막 수집일 ${esc(review.displayDate(item.last_collected_at||item.collected_at||item.checked_at))}</p><p>${esc(item.institution)}</p>`;
 }
 function profileFields(category,published,products=[],profile={}){
  const support=category==='support',bank=category==='bank',cultivation=category==='cultivation';
  const kinds=new Set();
  if(support)for(const n of published?.notices||[]){const item=root.MunongsaPersonalization.project(n);for(const c of item.eligibility?.conditions||[])if(c.status==='verified'&&c.presence==='specified')kinds.add(c.kind)}
  const precise=['organization','agricultural_corporation','group','business','municipality'].includes(profile.applicant)||profile.farmingSituation==='organization';
  return {region:!bank,district:!bank,age:false,experience:false,budget:false,
   applicant:precise&&(support&&kinds.has('applicant')||bank&&products.some(p=>p.applicants?.length)),
   exporterStatus:support&&kinds.has('export_activity'),groupMemberCount:support&&precise&&kinds.has('group_size'),
   crop:cultivation||support&&kinds.has('crop'),cultivation:cultivation||support&&kinds.has('facility'),area:support&&kinds.has('scale'),
   residenceRegion:support&&kinds.has('residence'),residenceDistrict:support&&kinds.has('residence'),
   birthDate:support&&kinds.has('age')||bank&&products.some(p=>p.birthYears?.length&&!root.MunongsaFinance.compare(p,profile).rows.some(c=>c.label==='신청 대상'&&c.state==='mismatch')),
   farmRegistered:support&&kinds.has('farm_registration'),farmingYears:support&&kinds.has('farming_experience'),independentYears:support&&kinds.has('independent_management'),
   experienceBasisDate:support&&(kinds.has('farming_experience')||kinds.has('independent_management'))};
 }
 function applyProfileFields(category,published,products,profile){const fields=profileFields(category,published,products,profile);for(const [id,show]of Object.entries(fields)){const el=document.getElementById(id);if(el)el.closest('.field').hidden=!show}
  const additional=document.getElementById('additionalProfileFields');additional.hidden=!Object.entries(fields).some(([id,show])=>show&&!['region','district'].includes(id));
  if(category==='bank'){const comparable=products.some(p=>p.applicants?.length);document.getElementById('farmingSituationField').hidden=!comparable;document.querySelector('.filters-intro').textContent=comparable?'현재 농업 상황만 알려주세요. 생년월일은 연령 조건이 있는 상품을 비교할 때만 입력해요.':'보증제도는 별도 상담과 심사가 필요합니다. 현재 입력값으로 보증 승인 여부를 판단하지 않아요.'}
  return fields}
 root.MunongsaDisplay={title,period,recruitment,applicantForSituation,situationForApplicant,sourceButton,supportDetail,profileFields,applyProfileFields};
})(globalThis);
