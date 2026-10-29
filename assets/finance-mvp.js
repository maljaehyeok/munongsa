/* Fact-only finance guidance. Reuses the existing three-valued condition engine. */
(function(root){
  'use strict';
  const labels={match:'기본 조건 일치',mismatch:'불일치',check:'추가 확인 필요'};
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function compare(item,profile,engine=root.MunongsaSupport){
    const evidence={url:item.source.url,location:item.source.location,fact_confirmed:true};
    const conditions=item.applicants?[{condition_id:'applicant',kind:'applicant',presence:'specified',status:'verified',value:{one_of:item.applicants},evidence}]:[];
    const result=engine.evaluate({eligibility:{conditions,logic:{op:'AND',children:conditions.map(c=>({condition_id:c.condition_id}))}}},profile);
    const rows=result.conditions.map(c=>({label:'신청 대상',state:c.status,detail:c.reason}));
    // Official annual birth-year selection range; never infer this from current age.
    if(item.birthYears){
      const b=profile.birthDate||'',d=new Date(b+'T00:00:00Z'),valid=/^\d{4}-\d{2}-\d{2}$/.test(b)&&Number.isFinite(+d)&&d.toISOString().slice(0,10)===b;
      const state=valid?(Number(b.slice(0,4))>=item.birthYears[0]&&Number(b.slice(0,4))<=item.birthYears[1]?'match':'mismatch'):'check';
      rows.push({label:'일반 후계농 2026년 연령 기준',state,detail:valid?item.birthRuleLabel:'생년월일을 입력하면 공고의 출생연도 범위와 비교합니다. 현재 만 나이만으로는 확정하지 않습니다.'});
    }
    const state=rows.some(r=>r.state==='mismatch')?'mismatch':!rows.length||rows.some(r=>r.state!=='match')?'check':'match';
    return {state,label:labels[state],rows,unknowns:item.unknowns,notice:'입력값과 확인된 기본 조건만 비교한 결과입니다. 전체 신청 자격·선정·보증·대출 승인을 의미하지 않습니다.'};
  }
  function date(value){if(!value)return '확인 필요';const d=new Date(value.length===10?value+'T00:00:00+09:00':value);if(!Number.isFinite(+d))return '확인 필요';return new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(d)}
  function filter(items,query='',purpose='all'){const q=query.trim().toLocaleLowerCase('ko-KR');return items.filter(p=>(purpose==='all'||p.purposes.includes(purpose))&&(!q||[p.title,p.institution,p.type,p.target,p.uses,...p.purposes].join(' ').toLocaleLowerCase('ko-KR').includes(q)))}
  function rank(items,profile){return items.map((item,index)=>({item,index,comparison:compare(item,profile)})).sort((a,b)=>({match:0,check:1,mismatch:2}[a.comparison.state]-{match:0,check:1,mismatch:2}[b.comparison.state])||a.index-b.index).map(r=>r.item)}
  const action=p=>`<a class="source-link source-action" href="${esc(p.source.url)}" target="_blank" rel="noopener">공식 금융 안내 보기 ↗</a>`;
  function terms(p){return [['자금 용도',p.purposes.join(' · ')],[p.type==='신용보증'?'보증한도':'대출한도',p.limit],['금리·비용',p.interest],[p.type==='신용보증'?'이용 대출':'거치·상환',p.type==='신용보증'?p.repayment:p.grace+' 거치 / '+p.repayment]]}
  function card(p,profile){const m=compare(p,profile);return `<article class="card notice-card finance-card" data-finance-id="${esc(p.id)}"><div class="notice-status"><span class="notice-chip">${esc(p.type)}</span><span class="notice-chip ${m.state==='mismatch'?'elapsed':'check'}">${esc(m.label)}</span></div><button class="compact-open" type="button" data-info-kind="financeMvp" data-info-key="${esc(p.id)}"><strong>${esc(p.title)}</strong><span class="notice-institution">${esc(p.institution)}</span><dl class="finance-card-terms">${terms(p).map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl><span class="compact-hint">대상·내 조건·신청 방법 보기 ↗</span></button><div class="notice-footer">${action(p)}</div></article>`}
  function detail(p,profile,checkedAt){const m=compare(p,profile);const fields=[['지원 대상',p.target],['적용 지역',p.region],['자금 용도',p.uses],['한도',p.limit],['금리·보증료',p.interest],['거치기간',p.grace],['상환기간·방식',p.repayment],['신청 방법·취급기관',p.application]];return {match:m,html:`<div class="detail-actions">${action(p)}</div><h3>주요 조건</h3><dl class="support-detail-list finance-facts">${fields.map(([a,b])=>`<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join('')}</dl><h3>신청 시 확인할 조건</h3><ul>${p.conditions.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><h3>내 조건 비교 · ${esc(m.label)}</h3><ul>${m.rows.map(r=>`<li><b>${esc(r.label)} · ${esc(labels[r.state]||labels.check)}</b><br>${esc(r.detail)}</li>`).join('')}</ul><h3>현재 신청 안내</h3><p>${esc(p.status)}</p><details class="more-conditions"><summary>추가로 확인할 항목</summary><ul>${p.unknowns.map(u=>`<li>${esc(u)}</li>`).join('')}</ul></details><p class="finance-caution">제도 대상에 해당하거나 기본 조건이 일치해도 실제 자금 배정·보증·대출 승인은 별도 심사합니다. 금융조건과 접수 일정은 최신 공식 안내 및 취급기관에서 확인하세요.</p><p>정보 확인일: ${esc(date(checkedAt))} (한국시간)<br>자료 기준: ${esc(p.year)}</p><div class="cite"><b>${esc(p.source.publisher)}</b><p>${esc(p.source.location)}</p>${action(p)}</div>`}}
  const api={compare,filter,rank,card,detail,date,labels};root.MunongsaFinance=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
