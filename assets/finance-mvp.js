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
  function filter(items,query='',purpose='all'){
    const normalize=value=>String(value??'').normalize('NFKC').toLocaleLowerCase('ko-KR');
    const terms=normalize(query).trim().split(/\s+/u).filter(Boolean);
    return items.filter(p=>{
      if(purpose!=='all'&&!p.purposes.includes(purpose))return false;
      // Search approved public fields only. All entered words must be present;
      // searching is independent of eligibility and never expands to review data.
      const hay=normalize([p.title,p.institution,p.type,p.target,p.uses,...p.purposes,p.id==='guarantee'?'농신보':''].join(' '));
      return terms.every(term=>hay.includes(term));
    });
  }
  function rank(items,profile){return items.map((item,index)=>({item,index,comparison:compare(item,profile)})).sort((a,b)=>({match:0,check:1,mismatch:2}[a.comparison.state]-{match:0,check:1,mismatch:2}[b.comparison.state])||a.index-b.index).map(r=>r.item)}
  // Funding guidance is separate from eligibility and ranking. Never sum distinct caps.
  function fundingView(p,profile){
    const need=profile.requiredFundsWon;if(need==null||need==='')return null;
    const note='제도상 최대 한도와의 비교예요. 개인별 대출 가능 금액·선정·승인을 뜻하지 않습니다.';
    if(!Number.isSafeInteger(need)||need<=0)return {state:'check',rows:[],notice:'입력 금액 확인 필요',note};
    const f=p.fundingLimits,purpose=profile.financePurpose||'all',valid=f?.currency==='KRW'&&f.scope==='scheme_maximum_not_personal_approval'&&f.source?.url?.startsWith('https://')&&f.checkedAt;
    if(!valid)return {state:'check',rows:[],notice:p.type==='신용보증'?'보증한도 추가 확인 필요 · 직접 대출상품 아님':'개인별 총한도 추가 확인 필요 · 면적당 지원단가와 비교하지 않아요.',note};
    if(purpose!=='all'&&!p.purposes.includes(purpose))return {state:'check',rows:[],notice:'자금 용도 확인 필요',note};
    const kind=purpose==='all'?null:purpose==='주택 마련'?'housing':'startup';
    const caps=(f.caps||[]).filter(c=>(c.kind==='all'||!kind||c.kind===kind)&&Number.isSafeInteger(c.won)&&c.won>0);
    if(!caps.length)return {state:'check',rows:[],notice:'해당 용도의 한도 추가 확인 필요',note};
    const money=n=>root.MunongsaSelection.money(n);
    const rows=caps.map(c=>({state:need>c.won?'over':'within',text:(c.kind==='housing'?'주택자금':c.kind==='startup'?'농업창업자금':'육성자금')+' · '+money(need)+' / 제도상 최대 '+money(c.won)+' · '+(need>c.won?'최대 한도 초과':'최대 한도 이내')}));
    return {state:rows.length>1?'check':rows[0].state,rows,notice:rows.length>1?'자금 용도별 한도 참고 · 두 한도를 합산하지 않아요.':'필요 자금 한도 참고',note,source:f.source,checkedAt:f.checkedAt};
  }
  function fundingHtml(p,profile){const v=fundingView(p,profile);if(!v)return '';return `<section class="finance-funding-guide" data-funding-state="${esc(v.state)}"><b>${esc(v.notice)}</b>${v.rows.map(r=>`<p data-funding-row="${esc(r.state)}">${esc(r.text)}</p>`).join('')}<p class="finance-funding-caution">${esc(v.note)}</p>${v.source?`<a class="source-link" href="${esc(v.source.url)}" target="_blank" rel="noopener">공식 한도 근거 ↗</a><p class="notice-meta">한도 확인일 <b>${esc(date(v.checkedAt))}</b></p>`:''}</section>`}
  const action=p=>`<a class="source-link source-action" href="${esc(p.source.url)}" target="_blank" rel="noopener">공식 금융 안내 보기 ↗</a>`;
  // Presentation only: explain the exact rows already produced by compare().
  function comparisonView(p,m){
    if(p.type==='신용보증')return {label:'금융기관·농신보 상담 필요',rows:[],scope:'현재 입력정보로 보증 자격을 자동 비교하지 않습니다. 직접 대출상품이 아닌 신용보증제도이며 금융기관·농신보 상담과 별도 심사가 필요합니다.'};
    const states={match:'일치',mismatch:'불일치',check:'확인 필요'};
    const rows=m.rows.map((r,i)=>({state:r.state,text:(i===0&&p.applicants?'개인 신청자 유형':'일반 후계농 2026년 출생연도 범위')+' '+(states[r.state]||states.check),detail:r.detail}));
    return {label:rows.map(r=>r.text).join(' · ')||'비교할 입력 항목 확인 필요',rows,scope:'귀농 여부·교육·영농경력·선정 여부 등은 이 비교로 확인하지 않았습니다. 전체 신청 자격과 실제 대출 승인은 별도 확인이 필요합니다.'};
  }
  function amountLabel(p){return p.id==='farmland'?'지원단가':p.type==='신용보증'?'보증한도':'대출한도'}
  function amountScope(p){return p.id==='farmland'?'면적당 지원 기준이며 실제 토지 매입가격이나 개인별 확정 대출금액이 아닙니다.':p.type==='신용보증'?'보증금액·보증료와 대출금리는 다릅니다. 보증 승인과 은행 대출 승인은 별도 심사합니다.':'제도상 최대 한도입니다. 개인별 실제 대출금액은 자금 배정·담보·신용심사에 따라 달라집니다.'}
  function terms(p){return [['자금 용도',p.purposes.join(' · ')],[amountLabel(p),p.limit],['금리·비용',p.interest],[p.type==='신용보증'?'이용 대출':'거치·상환',p.type==='신용보증'?p.repayment:(p.grace==='확인 필요'?'거치기간 확인 필요':p.grace+' 거치')+' / '+p.repayment]]}
  function card(p,profile){const m=compare(p,profile),view=comparisonView(p,m),chips=view.rows.length?view.rows:[{text:view.label,state:'check'}];return `<article class="card notice-card finance-card" data-finance-id="${esc(p.id)}"><div class="notice-status"><span class="notice-chip">${esc(p.type)}</span>${chips.map(r=>`<span class="notice-chip ${r.state==='mismatch'?'mismatch':r.state==='match'?'match':'check'}">${esc(r.text)}</span>`).join('')}</div><button class="compact-open" type="button" data-info-kind="financeMvp" data-info-key="${esc(p.id)}"><strong>${esc(p.title)}</strong><span class="notice-institution">${esc(p.institution)}</span><dl class="finance-card-terms"><div><dt>지원 대상</dt><dd>${esc(p.target)}</dd></div>${terms(p).map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl><span class="finance-amount-scope notice-meta">${esc(amountScope(p))}</span><span class="notice-meta">${esc(p.type==='\uC2E0\uC6A9\uBCF4\uC99D'?view.scope:'\uAE30\uBCF8 \uC785\uB825\uB9CC \uBE44\uAD50\uD574\uC694. \uC804\uCCB4 \uC790\uACA9\uACFC \uB300\uCD9C \uC2B9\uC778\uC740 \uBCC4\uB3C4 \uD655\uC778\uC774 \uD544\uC694\uD574\uC694.')}</span><span class="compact-hint">신청 방법·세부 조건 보기 ↗</span></button>${fundingHtml(p,profile)}<div class="notice-footer">${action(p)}</div></article>`}
  // Descriptive guidance only; never used by comparison or ranking.
  function applicationGuide(p){
    const g=p.applicationGuide;if(!g)return '';
    const list=items=>items.map(v=>`<li>${esc(v)}</li>`).join('');
    return `<section class="finance-application-guide"><h3>신청 방법·접수처</h3><p>${esc(g.scope)}</p><ol>${list(g.steps)}</ol><dl class="support-detail-list"><div><dt>접수처</dt><dd>${esc(g.reception)}</dd></div></dl><details class="more-conditions finance-documents"><summary>준비서류 확인하기</summary>${g.documents.length?`<h4>공식 안내의 주요 서류</h4><ul>${list(g.documents)}</ul>`:''}${g.conditionalDocuments.length?`<h4>해당자만 확인할 서류</h4><ul>${list(g.conditionalDocuments)}</ul>`:''}<p>${esc(g.documentNote)}</p></details><p class="notice-meta">신청·서류 정보 확인일: ${esc(date(g.checkedAt))}</p><div class="cite"><a href="${esc(g.source.url)}" target="_blank" rel="noopener">${esc(g.source.publisher)} · 신청·서류 근거 보기 ↗</a><p>${esc(g.source.location)}</p></div></section>`;
  }
  // Calculation only, separate from funding needs, eligibility and approval.
  // Enable only the existing reviewed 2026 fixed-rate product, never guarantees
  // or variable rates inferred from a general percentage in free text.
  function interestAssumption(p,checkedAt){
    if(p?.id!=='successor'||p.type!=='정책융자'||!String(p.year).includes('2026'))return null;
    if(p.source?.url!=='https://agro.seoul.go.kr/archives/55168?listPage=4'||!p.source.location)return null;
    if(!/^2026-\d{2}-\d{2}$/.test(checkedAt||'')||date(checkedAt)==='확인 필요'||new Date(checkedAt+'T00:00:00Z').toISOString().slice(0,10)!==checkedAt)return null;
    const m=p.interest?.match(/연\s*(\d+(?:\.\d+)?)%\s*고정금리/);
    if(!m||Number(m[1])!==1.5)return null;
    return {percent:1.5,basisPoints:150,source:p.source,checkedAt,terms:p.interest};
  }
  function simpleInterest(principal,basisPoints){
    if(!Number.isSafeInteger(principal)||principal<=0||!Number.isInteger(basisPoints)||basisPoints<0||basisPoints>10000)return null;
    const numerator=BigInt(principal)*BigInt(basisPoints),round=d=>Number((numerator+d/2n)/d);
    return {principal,annual:round(10000n),monthlyAverage:round(120000n)};
  }
  const interestConfigs=new Map();
  function interestHtml(p,checkedAt){
    const assumption=interestAssumption(p,checkedAt);if(!assumption)return '';
    interestConfigs.set(p.id,assumption);
    return `<details class="more-conditions finance-interest" data-interest-product="${esc(p.id)}"><summary>고정금리 선택 시 단순 예상 이자 계산</summary><p>2026년 안내의 연 ${assumption.percent}% 고정금리를 선택한다고 가정합니다. 변동금리에는 적용하지 않습니다.</p><label for="interestPrincipal-${esc(p.id)}">계산할 가정 대출금액 · 원 또는 만원</label><input id="interestPrincipal-${esc(p.id)}" data-interest-principal type="text" inputmode="text" maxlength="24" autocomplete="off" placeholder="예: 5,000만원 또는 50,000,000원" aria-describedby="interestCaution-${esc(p.id)}"><button type="button" data-calculate-interest>가정 이자 계산</button><output data-interest-result role="status" aria-live="polite"></output><p id="interestCaution-${esc(p.id)}">대출 원금이 1년 동안 줄지 않는 단순 가정입니다. 월평균은 연간 이자를 12로 나눈 참고값이며 실제 월 상환액이 아닙니다. 표시 금액은 원 단위로 반올림합니다. 원금 상환·보증료·수수료는 제외하며, 실제 승인액·적용 금리·거치기간 이자 납부는 취급기관에 확인하세요.</p><a href="${esc(assumption.source.url)}" target="_blank" rel="noopener">금리 공식 근거 ↗</a><p class="notice-meta">안내 정보 확인일 ${esc(date(checkedAt))} · 계산값은 영농 조건이나 필요 자금에 자동 저장하지 않습니다.</p></details>`;
  }
  if(typeof document!=='undefined'){
    document.addEventListener('click',event=>{
      const button=event.target.closest?.('[data-calculate-interest]');if(!button)return;
      const box=button.closest('[data-interest-product]'),config=interestConfigs.get(box?.dataset.interestProduct);if(!config)return;
      const input=box.querySelector('[data-interest-principal]'),output=box.querySelector('[data-interest-result]');
      const amount=root.MunongsaAmounts?.parseInput(input.value),result=simpleInterest(amount,config.basisPoints);
      input.setAttribute('aria-invalid',String(!result));
      output.textContent=result?'가정 대출금 '+root.MunongsaAmounts.wonText(result.principal)+' · 연 '+config.percent+'% 가정\n연간 단순 이자 '+root.MunongsaAmounts.wonText(result.annual)+'\n월평균 단순 환산 약 '+root.MunongsaAmounts.wonText(result.monthlyAverage)+' · 실제 월 상환액 아님':'계산할 대출금액을 양수로 입력해 주세요. 예: 5,000만원 또는 50,000,000원';
    });
    document.addEventListener('input',event=>{if(!event.target.matches?.('[data-interest-principal]'))return;const box=event.target.closest('[data-interest-product]');box.querySelector('[data-interest-result]').textContent='';event.target.removeAttribute('aria-invalid');});
  }
  function detail(p,profile,checkedAt){const m=compare(p,profile),view=comparisonView(p,m);const fields=[['지원 대상',p.target],['적용 지역',p.region],['자금 용도',p.uses],[p.id==='farmland'?'지원단가·개인별 총한도':amountLabel(p),p.limit],['금리·보증료',p.interest],[p.type==='신용보증'?'이용 대출 거치기간':'거치기간',p.grace],[p.type==='신용보증'?'이용 대출 상환조건':'상환기간·방식',p.repayment],['신청 방법·취급기관',p.application]];
    const glossary=p.type==='신용보증'?'':`<details class="more-conditions finance-glossary"><summary>거치·상환 용어 알아보기</summary><dl><dt>거치기간</dt><dd>원금 상환을 미루는 기간입니다. 이자 납부 여부는 해당 제도 조건에 따릅니다.</dd><dt>원금균등분할상환</dt><dd>매번 갚는 원금은 같고, 이자는 남은 대출 잔액에 따라 달라지는 방식입니다.</dd></dl></details>`;
    const comparison=interestHtml(p,checkedAt)+(p.type==='신용보증'?`<h3>보증 상담 안내</h3><p>${esc(view.scope)}</p>`:`<h3>실제로 비교한 입력 항목</h3><ul>${view.rows.map(r=>`<li><b>${esc(r.text)}</b><br>${esc(r.detail)}</li>`).join('')}</ul><p class="finance-caution">${esc(view.scope)}</p>`);
    return {match:m,label:view.label,html:`<h3>주요 조건</h3><dl class="support-detail-list finance-facts">${fields.map(([a,b])=>`<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join('')}</dl><p class="finance-amount-scope notice-meta">${esc(amountScope(p))}</p>${fundingHtml(p,profile)}${glossary}${applicationGuide(p)}<h3>현재 신청 안내</h3><p>${esc(p.status)}</p><div class="detail-actions">${action(p)}</div>${comparison}<h3>신청 시 확인할 조건</h3><ul>${p.conditions.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><details class="more-conditions"><summary>추가로 확인할 항목</summary><ul>${p.unknowns.map(u=>`<li>${esc(u)}</li>`).join('')}</ul></details><p class="finance-caution">자금 배정·보증·대출 승인은 별도 심사합니다. 최신 금융조건과 접수 일정은 취급기관에서 확인하세요.</p><p>정보 확인일: <b>${esc(date(checkedAt))}</b> (한국시간)<br>자료 기준: ${esc(p.year)}</p><div class="cite"><b>${esc(p.source.publisher)}</b><p>${esc(p.source.location)}</p></div>`};
  }
  const api={compare,filter,rank,card,detail,date,labels,comparisonView,fundingView,applicationGuide,interestAssumption,simpleInterest};root.MunongsaFinance=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
