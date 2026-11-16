/* Reviewed explanatory facts only. Never changes eligibility, ranking or dates. */
(function(root){
 'use strict';
 let records=[],linkReviews=[];
 const fields=['summary','funding','conditions','method','office','documents_required','documents_conditional','documents_bonus','contact','warnings','unconfirmed'];
 const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
 function basis(n){
  const date=v=>v?.date?{date:v.date,time:v.time||null,timezone:v.timezone||null}:null;
  return {id:n.id,url:n.url,title:n.title,target:n.target,region:n.region,
   dates:{start:date(n.reference_application_dates?.start),end:date(n.reference_application_dates?.end)},period:n.application_period||{},
   eligibility:{conditions:(n.eligibility?.conditions||[]).map(c=>({condition_id:c.condition_id,kind:c.kind,presence:c.presence,status:c.status,value:c.value})),logic:n.eligibility?.logic||null}};
 }
 function install(data){
  records=[];linkReviews=[];
  const preview=data?.preview===true&&['localhost','127.0.0.1'].includes(root.location?.hostname)&&new URLSearchParams(root.location.search).get('support-details-preview')==='1';
  if(data?.schema!=='munongsa-support-details-v1'||!Array.isArray(data.records)||data.preview&&!preview)return;
  records=data.records.filter(r=>(r.approval?.state==='approved'||preview&&r.approval?.state==='preview')&&r.approval?.reviewer&&r.approval?.reference&&r.approval?.checked_at&&r.rights?.facts_only===true&&r.basis&&r.fields&&Object.keys(r.fields).every(k=>fields.includes(k)&&validField(r.fields[k])));
  if(Array.isArray(data.link_reviews))linkReviews=data.link_reviews.filter(r=>r.schema==='munongsa-official-link-review-v1'&&r.basis&&['official_detail','title_or_detail_unconfirmed','access_restricted','access_policy_unconfirmed','not_found','request_error','login_only'].includes(r.state));
 }
 function validField(f){return f?.evidence?.url?.startsWith('https://')&&f.evidence.location&&f.evidence.checked_at&&(typeof f.value==='string'||Array.isArray(f.value)&&f.value.every(x=>typeof x==='string'))}
 function get(item){
  if(!['approved','approved_reference'].includes(item.publication)||item.verification_status!=='verified'||item.rights?.public_display!=='allowed')return null;
  const r=records.find(r=>r.basis.id===item.id&&canonical(r.basis)===canonical(basis(item)));
  return r||null;
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
 root.MunongsaSupportDetails={basis,install,get,card,detail,linkReview,linkHistory,application,links};
})(globalThis);
