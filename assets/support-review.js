/* Reference browsing is explicit user policy; no eligibility or approval changes. */
(function(root){
  'use strict';
  const schema='munongsa-support-review-v1';
  function label(item,now=new Date()){
    const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
    if(item.known_closed)return {key:'elapsed',text:'마감으로 기록된 자료 · 연장·재공고는 원문 확인'};
    if(item.end_date&&item.end_date<today)return {key:'elapsed',text:'기재 신청기간 경과 · 연장 여부 미확인'};
    if(item.start_date&&item.start_date>today)return {key:'unknown',text:'기재 신청 시작일 전 · 최신 모집 여부 확인 필요'};
    if(item.start_date&&item.end_date&&item.start_date<=today&&today<=item.end_date)return {key:'unknown',text:'기재 신청기간 내 · 현재 접수 가능 여부 미확인'};
    return {key:'unknown',text:'신청 상태 미확인 · 현재 신청 가능한 사업이라는 뜻이 아님'};
  }
  function browse(data,query='',filter='all',now=new Date()){
    if(data?.schema_version!==schema||!Array.isArray(data.records))throw new Error('invalid_review_feed');
    const seen=new Set(),terms=String(query).trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return data.records.filter(r=>{
      if(!r||typeof r.id!=='string'||typeof r.title!=='string'||r.recommendation_eligible!==false||r.publication!=='review'||seen.has(r.id))return false;
      seen.add(r.id);const haystack=[r.title,r.institution,r.region,r.target,r.record_type,r.origin,r.summary].join(' ').toLocaleLowerCase();
      return terms.every(t=>haystack.includes(t))&&(filter==='all'||label(r,now).key===filter);
    });
  }
  root.MunongsaSupportReview={schema,browse,label};
})(globalThis);
