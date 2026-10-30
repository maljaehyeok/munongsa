/* Reviewed explanatory facts only. Never changes eligibility, ranking or dates. */
(function(root){
 'use strict';
 let records=[];
 const fields=['summary','funding','conditions','method','office','documents_required','documents_conditional','documents_bonus','contact','warnings','unconfirmed'];
 const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
 function basis(n){
  const date=v=>v?.date?{date:v.date,time:v.time||null,timezone:v.timezone||null}:null;
  return {id:n.id,url:n.url,title:n.title,target:n.target,region:n.region,
   dates:{start:date(n.reference_application_dates?.start),end:date(n.reference_application_dates?.end)},period:n.application_period||{},
   eligibility:{conditions:(n.eligibility?.conditions||[]).map(c=>({condition_id:c.condition_id,kind:c.kind,presence:c.presence,status:c.status,value:c.value})),logic:n.eligibility?.logic||null}};
 }
 function install(data){
  records=[];
  const preview=data?.preview===true&&['localhost','127.0.0.1'].includes(root.location?.hostname)&&new URLSearchParams(root.location.search).get('support-details-preview')==='1';
  if(data?.schema!=='munongsa-support-details-v1'||!Array.isArray(data.records)||data.preview&&!preview)return;
  records=data.records.filter(r=>r.approval?.state===(preview?'preview':'approved')&&r.approval?.reviewer&&r.approval?.reference&&r.approval?.checked_at&&r.rights?.facts_only===true&&r.basis&&r.fields&&Object.keys(r.fields).every(k=>fields.includes(k)&&validField(r.fields[k])));
 }
 function validField(f){return f?.evidence?.url?.startsWith('https://')&&f.evidence.location&&f.evidence.checked_at&&(typeof f.value==='string'||Array.isArray(f.value)&&f.value.every(x=>typeof x==='string'))}
 function get(item){
  if(!['approved','approved_reference'].includes(item.publication)||item.verification_status!=='verified'||item.rights?.public_display!=='allowed')return null;
  const r=records.find(r=>r.basis.id===item.id&&canonical(r.basis)===canonical(basis(item)));
  return r||null;
 }
 function card(item,escape){const r=get(item);if(!r)return '';return ['summary','funding'].filter(k=>r.fields[k]).map(k=>`<span class="notice-target">${k==='summary'?'지원 내용':'지원 금액·비율'} · ${escape(r.fields[k].value)}</span>`).join('')}
 function detail(item,escape,date){
  const r=get(item);if(!r)return '';
  const labels={summary:'지원 내용',funding:'지원 금액·비율',conditions:'지원 조건',method:'신청 방법',office:'접수처',documents_required:'필수 제출서류',documents_conditional:'해당자만 필요한 서류',documents_bonus:'가점자료',contact:'문의처',warnings:'중요한 제한사항',unconfirmed:'아직 확인되지 않은 사항'};
  const list=f=>Array.isArray(f.value)?`<ul>${f.value.map(v=>`<li>${escape(v)}</li>`).join('')}</ul>`:escape(f.value);
  const documentFields=['documents_required','documents_conditional','documents_bonus'];
  const row=k=>`<div><dt>${labels[k]}</dt><dd>${list(r.fields[k])}</dd></div>`;
  const rows=fields.filter(k=>r.fields[k]&&!documentFields.includes(k)).map(row).join('');
  const documents=documentFields.filter(k=>r.fields[k]);
  const paperwork=documents.length?`<details class="more-conditions support-paperwork"><summary>필요 서류 확인 · 필수 ${r.fields.documents_required?.value.length||0}개 항목${r.fields.documents_conditional?' · 해당자 추가 서류 있음':''}</summary><dl class="support-detail-list user-facts">${documents.map(row).join('')}</dl></details>`:'';
  const proofs=fields.filter(k=>r.fields[k]).map(k=>{const e=r.fields[k].evidence;return `<li><b>${labels[k]}</b> · ${escape(e.location)} · 확인일 ${escape(date(e.checked_at))} <a href="${escape(e.url)}" target="_blank" rel="noopener">공식 근거 보기 ↗</a></li>`}).join('');
  return `<section class="support-reviewed-details"><h3>지원 내용과 신청 안내</h3><dl class="support-detail-list user-facts">${rows}</dl>${paperwork}<details class="more-conditions"><summary>항목별 공식 근거와 확인일</summary><ul>${proofs}</ul></details></section>`;
 }
 root.MunongsaSupportDetails={basis,install,get,card,detail};
})(globalThis);
