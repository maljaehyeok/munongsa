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
  // Presentation only: explain the exact rows already produced by compare().
  function comparisonView(p,m){
    if(p.type==='신용보증')return {label:'금융기관·농신보 상담 필요',rows:[],scope:'현재 입력정보로 보증 자격을 자동 비교하지 않습니다. 직접 대출상품이 아닌 신용보증제도이며 금융기관·농신보 상담과 별도 심사가 필요합니다.'};
    const states={match:'일치',mismatch:'불일치',check:'확인 필요'};
    const rows=m.rows.map((r,i)=>({state:r.state,text:(i===0&&p.applicants?'개인 신청자 유형':'일반 후계농 2026년 출생연도 범위')+' '+(states[r.state]||states.check),detail:r.detail}));
    return {label:rows.map(r=>r.text).join(' · ')||'비교할 입력 항목 확인 필요',rows,scope:'귀농 여부·교육·영농경력·선정 여부 등은 이 비교로 확인하지 않았습니다. 전체 신청 자격과 실제 대출 승인은 별도 확인이 필요합니다.'};
  }
  function amountLabel(p){return p.id==='farmland'?'지원단가':p.type==='신용보증'?'보증한도':'대출한도'}
  function terms(p){return [['자금 용도',p.purposes.join(' · ')],[amountLabel(p),p.limit],['금리·비용',p.interest],[p.type==='신용보증'?'이용 대출':'거치·상환',p.type==='신용보증'?p.repayment:p.grace+' 거치 / '+p.repayment]]}
  function card(p,profile){const m=compare(p,profile),view=comparisonView(p,m),chips=view.rows.length?view.rows:[{text:view.label,state:'check'}];return `<article class="card notice-card finance-card" data-finance-id="${esc(p.id)}"><div class="notice-status"><span class="notice-chip">${esc(p.type)}</span>${chips.map(r=>`<span class="notice-chip ${r.state==='mismatch'?'elapsed':'check'}">${esc(r.text)}</span>`).join('')}</div><button class="compact-open" type="button" data-info-kind="financeMvp" data-info-key="${esc(p.id)}"><strong>${esc(p.title)}</strong><span class="notice-institution">${esc(p.institution)}</span><dl class="finance-card-terms"><div><dt>지원 대상</dt><dd>${esc(p.target)}</dd></div>${terms(p).map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl><span class="notice-meta">${esc(view.scope)}</span><span class="compact-hint">신청 방법·세부 조건 보기 ↗</span></button><div class="notice-footer">${action(p)}</div></article>`}
  // Descriptive guidance only; never used by comparison or ranking.
  function applicationGuide(p){
    const g=p.applicationGuide;if(!g)return '';
    const list=items=>items.map(v=>`<li>${esc(v)}</li>`).join('');
    return `<section class="finance-application-guide"><h3>신청 방법·접수처</h3><p>${esc(g.scope)}</p><ol>${list(g.steps)}</ol><dl class="support-detail-list"><div><dt>접수처</dt><dd>${esc(g.reception)}</dd></div></dl><details class="more-conditions finance-documents"><summary>준비서류 확인하기</summary>${g.documents.length?`<h4>공식 안내의 주요 서류</h4><ul>${list(g.documents)}</ul>`:''}${g.conditionalDocuments.length?`<h4>해당자만 확인할 서류</h4><ul>${list(g.conditionalDocuments)}</ul>`:''}<p>${esc(g.documentNote)}</p></details><p class="notice-meta">신청·서류 정보 확인일: ${esc(date(g.checkedAt))}</p><div class="cite"><a href="${esc(g.source.url)}" target="_blank" rel="noopener">${esc(g.source.publisher)} · 신청·서류 근거 보기 ↗</a><p>${esc(g.source.location)}</p></div></section>`;
  }
  function detail(p,profile,checkedAt){const m=compare(p,profile),view=comparisonView(p,m);const fields=[['지원 대상',p.target],['적용 지역',p.region],['자금 용도',p.uses],[p.id==='farmland'?'지원단가·개인별 총한도':'한도',p.limit],['금리·보증료',p.interest],['거치기간',p.grace],['상환기간·방식',p.repayment],['신청 방법·취급기관',p.application]];
    const glossary=p.type==='신용보증'?'':`<details class="more-conditions finance-glossary"><summary>거치·상환 용어 알아보기</summary><dl><dt>거치기간</dt><dd>원금 상환을 미루는 기간입니다. 이자 납부 여부는 해당 제도 조건에 따릅니다.</dd><dt>원금균등분할상환</dt><dd>매번 갚는 원금은 같고, 이자는 남은 대출 잔액에 따라 달라지는 방식입니다.</dd></dl></details>`;
    const comparison=p.type==='신용보증'?`<h3>보증 상담 안내</h3><p>${esc(view.scope)}</p>`:`<h3>실제로 비교한 입력 항목</h3><ul>${view.rows.map(r=>`<li><b>${esc(r.text)}</b><br>${esc(r.detail)}</li>`).join('')}</ul><p class="finance-caution">${esc(view.scope)}</p>`;
    return {match:m,label:view.label,html:`<h3>주요 조건</h3><dl class="support-detail-list finance-facts">${fields.map(([a,b])=>`<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join('')}</dl>${glossary}${applicationGuide(p)}<h3>현재 신청 안내</h3><p>${esc(p.status)}</p><div class="detail-actions">${action(p)}</div>${comparison}<h3>신청 시 확인할 조건</h3><ul>${p.conditions.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><details class="more-conditions"><summary>추가로 확인할 항목</summary><ul>${p.unknowns.map(u=>`<li>${esc(u)}</li>`).join('')}</ul></details><p class="finance-caution">자금 배정·보증·대출 승인은 별도 심사합니다. 최신 금융조건과 접수 일정은 취급기관에서 확인하세요.</p><p>정보 확인일: ${esc(date(checkedAt))} (한국시간)<br>자료 기준: ${esc(p.year)}</p><div class="cite"><b>${esc(p.source.publisher)}</b><p>${esc(p.source.location)}</p></div>`};
  }
  const api={compare,filter,rank,card,detail,date,labels,comparisonView};root.MunongsaFinance=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
