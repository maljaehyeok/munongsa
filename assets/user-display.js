/* Presentation only: original titles, conditions, approvals and profile history stay intact. */
(function(root){
 'use strict';
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function title(value){const raw=String(value||'');return raw.replace(/^(?:\s*[\[(]\s*첨부파일\s*있음\s*[\])]\s*)+/,'').replace(/(?:\s*[\[(]?\s*첨부파일\s*있음\s*[\])]?\s*)+$/,'').trim()||raw}
 function period(item){const display=root.MunongsaSupportReview.displayDate,p=item.application_period||{},r=item.reference_application_dates||{};const fact=v=>v?.date?display(v.date)+(v.timezone==='Asia/Seoul'&&/^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(v.time||'')?' '+v.time+' (한국시간)':''):null;return (p.start?display(p.start):fact(r.start)||'시작일 미확인')+' ~ '+(p.end?display(p.end):fact(r.end)||'마감일 미확인')}
 const situationApplicant={preparing:'prospective',family:'all',independent:'individual',organization:'organization',unknown:'all'};
 function applicantForSituation(value){return situationApplicant[value]||'all'}
 function sourceButton(url,label='공식 공고 보기'){return root.MunongsaSupport.safeUrl(url)?`<a class="source-link source-action" href="${esc(url)}" target="_blank" rel="noopener">${esc(label)} <span aria-hidden="true">↗</span></a>`:''}
 function supportDetail(item,row,display,period){
  const known=v=>typeof v==='string'&&v.trim()&&!['unknown','확인 필요'].includes(v),review=root.MunongsaSupportReview;
  const views=row?review.conditionViews(item,row.match):[],facts=views.filter(v=>v.fact!=='확인 필요'),missing=views.filter(v=>v.fact==='확인 필요');
  const status={match:'입력 조건 일치',mismatch:'입력 조건 불일치',check:'내 정보 또는 세부 조건 확인'};
  const fields=[['신청기간',period],['신청 대상',known(item.target)?item.target:'공식 공고의 신청 대상을 확인해 주세요.'],['대상 지역',known(item.region)?item.region:'공식 공고의 지역 요건을 확인해 주세요.'],['지원 내용',known(item.support)?item.support:'지원 규모와 세부 내용은 공식 공고에서 확인해 주세요.']];
  const comparisons=facts.map(v=>`<li><b>${esc(v.label)}</b><span class="condition-result ${esc(v.comparison)}">${esc(v.comparison==='check'?'입력 후 비교 가능':v.status)}</span><p>${esc(v.fact)}</p></li>`).join('');
  const application=item.application_url_verified===true?sourceButton(item.application_url,'별도 신청 페이지'):'';
  return `<div class="detail-actions">${sourceButton(item.url)}${application}</div><dl class="support-detail-list user-facts">${fields.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl><h3>내 조건과 비교</h3><p>${row?esc(status[row.match.conditionStatus]||status.check):'참고 공고입니다. 신청 대상과 자격은 원문에서 확인해 주세요.'}</p><ul>${comparisons}</ul>${missing.length?`<details class="more-conditions"><summary>더 확인할 조건 ${missing.length}개</summary><p>${esc([...new Set(missing.map(v=>v.label))].join(' · '))}</p></details>`:''}<div class="detail-caution"><h3>신청 전 확인하세요</h3><p>${esc(display.chips.filter(c=>!['세부 자격 일부 미확인','마감 임박','기재 기간 경과','검토중 · 참고자료'].includes(c.text)).map(c=>c.text).join(' · '))}</p><p>기재 모집기간과 내 조건 비교는 신청 자격·접수 가능 확정이 아닙니다. 정정·연장·예산 소진·조기 종료 여부와 세부 자격은 공식 원문에서 확인하세요.</p></div><p class="notice-meta">게시일 ${esc(review.displayDate(item.published_at))}<br>정보 확인일 ${row?esc(review.displayDate(item.last_checked_at)):'검토 전'}<br>마지막 수집일 ${esc(review.displayDate(item.last_collected_at||item.collected_at||item.checked_at))}</p><p>${esc(item.institution)}</p>${sourceButton(item.url)}`;
 }
 root.MunongsaDisplay={title,period,applicantForSituation,sourceButton,supportDetail};
})(globalThis);
