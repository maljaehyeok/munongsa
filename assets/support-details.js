/* Reviewed explanatory facts only. Never changes eligibility, ranking or dates. */
(function(root){
 'use strict';
 let records=[],linkReviews=[],localPreview=false;
 const fields=['summary','funding','conditions','method','office','documents_required','documents_conditional','documents_bonus','contact','warnings','unconfirmed','target','region','age','experience','period','subsidy','self_payment','documents_listed'];
 const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
 function basis(n){
  const date=v=>v?.date?{date:v.date,time:v.time||null,timezone:v.timezone||null}:null;
  return {id:n.id,url:n.url,title:n.title,target:n.target,region:n.region,
   dates:{start:date(n.reference_application_dates?.start),end:date(n.reference_application_dates?.end)},period:n.application_period||{},
   eligibility:{conditions:(n.eligibility?.conditions||[]).map(c=>({condition_id:c.condition_id,kind:c.kind,presence:c.presence,status:c.status,value:c.value})),logic:n.eligibility?.logic||null}};
 }
 function install(data){
  records=[];linkReviews=[];localPreview=false;
  const preview=data?.preview===true&&['localhost','127.0.0.1'].includes(root.location?.hostname)&&new URLSearchParams(root.location.search).get('support-details-preview')==='1';
  if(data?.schema!=='munongsa-support-details-v1'||!Array.isArray(data.records)||data.preview&&!preview)return;
  localPreview=preview;
  records=data.records.filter(r=>(r.approval?.state==='approved'||preview&&r.approval?.state==='preview')&&r.approval?.reviewer&&r.approval?.reference&&r.approval?.checked_at&&r.rights?.facts_only===true&&r.basis&&r.fields&&Object.keys(r.fields).every(k=>fields.includes(k)&&validField(r.fields[k])));
  records=records.map(r=>{
   if(!r.rights.display_scope)return r;
   if(!factScope(r))return null;
   const approvedFields=Object.fromEntries(Object.entries(r.fields).filter(([k])=>r.rights.public_fields.includes(k)&&fieldApproved(r,k,preview)));
   return Object.keys(approvedFields).length?{...r,fields:approvedFields}:null;
  }).filter(Boolean);
  if(Array.isArray(data.detail_supplements))for(const s of data.detail_supplements){
   const index=records.findIndex(r=>r.basis.id===s?.basis?.id);if(index<0)continue;
   const base=records[index];
   if(data.detail_supplements.filter(x=>x?.basis?.id===s.basis.id).length!==1||canonical(base)!==canonical(s.base_record)||canonical(base.basis)!==canonical(s.basis))continue;
   if(!s.approval?.reviewer||!s.approval.reference||!s.approval.checked_at||!(s.approval.state==='approved'||preview&&s.approval.state==='preview')||!factScope(s)||!s.fields)continue;
   const names=Object.keys(s.fields);if(names.some(k=>k in base.fields||!fields.includes(k)||!validField(s.fields[k])))continue;
   const approvedFields=Object.fromEntries(Object.entries(s.fields).filter(([k])=>s.rights.public_fields.includes(k)&&fieldApproved(s,k,preview)));
   records[index]={...base,fields:{...base.fields,...approvedFields}};
  }
  if(Array.isArray(data.link_reviews))linkReviews=data.link_reviews.filter(r=>r.schema==='munongsa-official-link-review-v1'&&r.basis&&['official_detail','title_or_detail_unconfirmed','access_restricted','access_policy_unconfirmed','not_found','request_error','login_only'].includes(r.state));
 }
 function validField(f){return f?.evidence?.url?.startsWith('https://')&&f.evidence.location&&f.evidence.checked_at&&(typeof f.value==='string'||Array.isArray(f.value)&&f.value.every(x=>typeof x==='string'))}
 function factScope(r){const x=r.rights;return x.display_scope==='reviewed_facts_v1'&&x.audience==='detail_display_only'&&x.eligibility_approval===false&&x.body_redistribution===false&&x.attachment_redistribution===false&&x.use_basis?.kind==='independent_facts'&&Array.isArray(x.use_basis.urls)&&x.use_basis.urls.length>0&&x.use_basis.urls.every(v=>typeof v==='string'&&v.startsWith('https://'))&&Array.isArray(x.public_fields)&&x.public_fields.length>0&&new Set(x.public_fields).size===x.public_fields.length&&x.public_fields.every(k=>['summary','funding','target','period','subsidy','self_payment','method','office','documents_listed','contact','unconfirmed'].includes(k))}
 function fieldApproved(r,k,preview){const a=r.field_approvals?.[k],b=r.approval;return a&&(a.state==='approved'||preview&&a.state==='preview')&&a.state===b.state&&a.reviewer===b.reviewer&&a.reference===b.reference&&a.checked_at===b.checked_at}
 function get(item){
  if(item?.local_review_only===true&&!localPreview)return null;
  const r=records.find(r=>r.basis.id===item.id&&canonical(r.basis)===canonical(basis(item)));
  const fieldGuidance=item.publication==='official_guidance'&&item.verification_status==='basics_only'&&item.recommendation_eligible===false&&item.eligibility_complete===false&&r?.approval?.state==='approved'&&factScope(r);
  if(!(localPreview&&r?.approval?.state==='preview')&&(!fieldGuidance&&(!['approved','approved_reference'].includes(item.publication)||item.verification_status!=='verified')||item.rights?.public_display!=='allowed'))return null;
  return r||null;
 }
 function availability(item){
  if(!item||typeof item.id!=='string')return {state:'unavailable',message:''};
  if(get(item))return {state:'available',message:''};
  if(item?.local_review_only===true||!records.some(r=>r.basis.id===item?.id))return {state:'unavailable',message:''};
  if(item.publication==='official_guidance'&&item.verification_status==='basics_only')return {state:'scope_review',message:'이 공고는 현재 제목·기관·공식 링크 중심의 기본 안내입니다. 상세정보는 현재 공고와 공개 범위를 다시 확인해야 하므로 표시하지 않습니다. 원문에서 신청 대상·기간·서류를 확인해 주세요.'};
  return {state:'basis_review',message:'현재 공고와 기존 상세정보의 확인 기준이 달라 상세 안내를 보류했습니다. 원문의 변경·정정 여부와 신청 조건을 확인해 주세요.'};
 }
 function linkReview(item,now=Date.now()){
    const r=linkHistory(item,now);return r&&now<Date.parse(r.expires_at)?r:null;
  }
  function linkHistory(item,now=Date.now()){
  const binding={id:item.id,title:item.title,url:item.url,source_id:item.source_id};
    return linkReviews.find(r=>canonical(r.basis)===canonical(binding)&&Number.isFinite(Date.parse(r.checked_at))&&Date.parse(r.checked_at)<=now&&Date.parse(r.expires_at)>Date.parse(r.checked_at)&&Date.parse(r.expires_at)-Date.parse(r.checked_at)<=172800000)||null;
 }
 function application(item,now=Date.now()){
  const review=linkReview(item,now),a=review?.application;if(review?.state!=='official_detail'||!a||a.source_url!==item.url||a.url===item.url||a.actual_submission_verified!==false||!['entry_accessible','login_unverified'].includes(a.kind))return null;
  if(!Array.isArray(a.evidence_chain)||a.evidence_chain.length<2||a.evidence_chain[0]?.url!==item.url||a.evidence_chain.at(-1)?.url!==a.url||!a.evidence_chain.every(e=>typeof e.location==='string'&&e.location.trim()))return null;
  try{const u=new URL(a.url),host=new URL(item.url).hostname;const allowed=u.hostname===host||u.hostname.endsWith('.go.kr')||u.hostname==='www.xn--289a74g35ad77bgsep7dntbbx5b.com';if(u.protocol!=='https:'||u.username||u.password||u.port&&u.port!=='443'||!allowed||[...u.searchParams.keys()].some(k=>/key|token|auth|secret|password|session/i.test(k)))return null;}catch{return null;}
  return a;
 }
 function links(item,escape){
    const r=linkHistory(item);if(!r)return '';
  const labels={official_detail:'공식 상세 공고와 제목 확인',title_or_detail_unconfirmed:'원문 제목·상세 내용 재확인 필요',access_restricted:'공식 사이트 접근 제한 · 원문 확인 필요',access_policy_unconfirmed:'공식 사이트 접근 정책 확인 필요',not_found:'원문을 찾지 못함 · 기관 확인 필요',request_error:'원문 연결 재확인 필요',login_only:'로그인 안내로 연결 · 원문 확인 필요'};
  const date=new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(r.checked_at))+' (한국시간)';
  const a=application(item),source=root.MunongsaSupport.safeUrl(item.url)?`<a class="source-link source-action" href="${escape(item.url)}" target="_blank" rel="noopener noreferrer">공식 공고 원문 ↗</a>`:'';
  const entry=a?`<a class="source-link source-action" href="${escape(a.url)}" target="_blank" rel="noopener noreferrer">별도 신청 안내 · ${a.kind==='login_unverified'?'로그인 이후 미검증':'접수 완료 미검증'} ↗</a>`:'';
  const names={target:'신청 대상',conditions:'필수 자격조건',period:'신청기간',support:'지원 내용',funding:'지원 규모·금액',method:'신청 방법',office:'접수처',documents:'제출서류',exclusions:'제외 조건',contact:'문의처'};
  const locations=Object.entries(r.field_locations||{}).filter(([k,v])=>names[k]&&typeof v==='string'&&v.length<=120).map(([k,v])=>`<li><b>${names[k]}</b> · ${escape(v)}</li>`).join('');
  return `<section class="support-reviewed-details"><h3>공식 원문과 신청 창구</h3><p><b>${linkReview(item)?labels[r.state]:'과거 링크 확인 기록 · 현재 접근 재확인 필요'}</b><br>링크 확인: ${escape(date)}</p><div class="detail-actions">${source}${entry}</div><p>${a?'별도 신청 안내를 확인했으며 로그인·서류 제출·접수 완료는 검증하지 않았어요.':'별도 신청 페이지는 확인되지 않았어요. 원문의 신청 방법과 접수처를 확인해 주세요.'}</p><p>원문 연결 확인은 전체 자격·금액·현재 접수 가능 여부 검증과 다릅니다.</p>${locations?`<details class="more-conditions"><summary>원문에서 확인할 정보 위치</summary><ul>${locations}</ul><p>정보가 기재된 위치 안내입니다. 세부 조건과 첨부 전체를 검증한 결과는 아닙니다.</p></details>`:''}</section>`;
 }
 function card(item,escape){const r=get(item);if(!r)return '';return ['summary','funding'].filter(k=>r.fields[k]).map(k=>`<span class="notice-fact${k==='funding'?' notice-funding':''}"><b class="notice-fact-label">${k==='summary'?'지원 내용':'지원 금액·비율'}</b><span class="notice-fact-value">${escape(r.fields[k].value)}</span></span>`).join('')}
 function detail(item,escape,date){
  const r=get(item);if(!r){const state=availability(item);return state.message?`<section class="support-reviewed-details"><h3>상세정보 확인이 필요해요</h3><p>${escape(state.message)}</p></section>`:'';}
  const labels={documents_listed:'\uBCF8\uBB38\uC5D0 \uAE30\uC7AC\uB41C \uC11C\uB958',summary:'지원 내용',funding:'지원 금액·한도',conditions:'필수 자격조건',method:'신청 방법',office:'접수처',documents_required:'필수 제출서류',documents_conditional:'해당자만 필요한 서류',documents_bonus:'가점자료',contact:'문의처',warnings:'중요한 제한사항',unconfirmed:'추가 확인 사항',target:'신청 대상',region:'거주지·영농지 기준',age:'연령 기준',experience:'영농 경력',period:'공식 신청기간',subsidy:'지원 비율',self_payment:'자부담'};
  const list=f=>Array.isArray(f.value)?`<ul>${f.value.map(v=>`<li>${escape(v)}</li>`).join('')}</ul>`:escape(f.value);
  const row=k=>`<div><dt>${labels[k]}</dt><dd>${r.fields[k]?list(r.fields[k]):'<span class="support-fact-unknown">확인되지 않음</span>'}</dd></div>`;
  const groups=[['신청기간',['period']],['누가 신청할 수 있나요?',['target','region','age','experience','conditions']],['어떤 지원을 받나요?',['summary']],['지원 금액과 자부담',['funding','subsidy','self_payment']],['신청 방법과 접수처',['method','office']],['준비 서류',['documents_listed','documents_required','documents_conditional','documents_bonus']],['문의처와 주의사항',['contact','warnings','unconfirmed']]];
  const optional=new Set(['age','experience','documents_listed','documents_conditional','documents_bonus','warnings']);
  const sections=groups.filter(([,keys])=>keys.some(k=>r.fields[k])).map(([label,keys])=>`<section class="support-preparation-section" data-preparation-section="${keys[0]}" tabindex="-1"><h4>${label}</h4><dl class="support-detail-list user-facts">${keys.filter(k=>r.fields[k]).map(row).join('')}</dl>${['method','documents_listed','contact'].includes(keys[0])?`<p class="preparation-evidence">${[...new Set(keys.filter(k=>r.fields[k]).map(k=>r.fields[k].evidence.url))].map(url=>`<a href="${escape(url)}" target="_blank" rel="noopener">이 안내의 공식 근거 ↗</a>`).join(' · ')}</p>`:''}</section>`).join('')+`<p class="support-fact-unknown">확인되지 않음: ${escape(groups.filter(([,keys])=>!keys.some(k=>r.fields[k])).map(([label])=>label).join(' · ')||'표시한 항목 외의 전체 필수조건·현재 접수 여부는 별도 확인')}</p>`;
  const proofs=fields.filter(k=>r.fields[k]).map(k=>{const e=r.fields[k].evidence;return `<li><b>${labels[k]}</b> · ${escape(e.location)} · 확인일 ${escape(date(e.checked_at))} <a href="${escape(e.url)}" target="_blank" rel="noopener">공식 근거 보기 ↗</a></li>`}).join('');
  return `<section class="support-reviewed-details"><h3>신청 준비에 필요한 정보</h3>${localPreview?'<p class="support-local-review" role="status">로컬 검토 미리보기 · 공개 승인이나 운영 반영 결과가 아닙니다.</p>':''}<p>확인된 항목만 안내합니다. 일부 조건이 맞아도 신청 자격이나 현재 접수 가능 여부가 확정되는 것은 아닙니다.</p>${sections}<details class="more-conditions"><summary>공식 근거와 항목별 확인일</summary><ul>${proofs}</ul></details></section>`;
 }
 root.MunongsaSupportDetails={basis,install,get,availability,card,detail,linkReview,linkHistory,application,links};
})(globalThis);
