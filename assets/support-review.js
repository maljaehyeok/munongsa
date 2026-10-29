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
  function validDay(value){return typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value+'T00:00:00Z'))&&new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value}
  function publicRecords(data,query='',now=new Date()){
    if(!data)return [];
    const seen=new Set();
    return browse(data,query,'all',now).filter(r=>{
      // Existing public RSS metadata only. Private DB rows, old trial bundles,
      // document downloads and unverified creative summaries are not published.
      if(!r.id.startsWith('collected-'))return false;
      let u;try{u=new URL(r.url)}catch{return false}
      if(u.protocol!=='https:'||u.hostname!=='www.mafra.go.kr'||u.username||u.password||u.port||u.hash||!/\/bbs\/home\/\d+\/\d+\/artclView\.do$/.test(u.pathname)||u.search)return false;
      if(/농기계|농업기계|장비|채용|입찰|포상|자문단|체험단|감사|환경영향|조사\s*주관|선정\s*결과/.test(r.title))return false;
      if(!/지원|보조사업|공모|모집|선정계획/.test(r.title))return false;
      if(seen.has(u.href))return false;seen.add(u.href);return true;
    }).map(r=>({id:r.id,title:r.title,institution:r.institution,url:r.url,
      published_at:r.published_at,checked_at:r.checked_at,
      start_date:validDay(r.start_date)?r.start_date:null,end_date:validDay(r.end_date)?r.end_date:null,
      known_closed:r.known_closed===true,publication:'review',recommendation_eligible:false,
      verification_status:r.verification_status,record_type:'자동수집 참고공고' }));
  }
  function presentation(item,now=Date.now(),reference=false){
    const ms=now instanceof Date?+now:Number(now),today=new Date(ms+9*3600000).toISOString().slice(0,10);
    const dates=item.reference_application_dates||{},aware=item.application_period||{};
    const awareDay=v=>typeof v==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v))?new Date(Date.parse(v)+9*3600000).toISOString().slice(0,10):null;
    const start=validDay(dates.start?.date)?dates.start.date:validDay(item.start_date)?item.start_date:awareDay(aware.start);
    const end=validDay(dates.end?.date)?dates.end.date:validDay(item.end_date)?item.end_date:awareDay(aware.end);
    let cutoff=dates.end?.timezone==='Asia/Seoul'&&/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(dates.end?.time||'')?dates.end.time:null;
    if(!cutoff&&awareDay(aware.end)){const d=new Date(Date.parse(aware.end)+9*3600000);cutoff=d.toISOString().slice(11,16)}
    const closed=item.known_closed===true||(end&&(end<today||(end===today&&cutoff&&ms>=Date.parse(end+'T'+cutoff+':00+09:00'))));
    const state=closed?'elapsed':start&&start>today?'upcoming':start&&end&&start<=today&&today<=end&&(today!==end||cutoff)?'window':'unknown';
    const days=end?Math.round((Date.parse(end+'T00:00:00Z')-Date.parse(today+'T00:00:00Z'))/86400000):null;
    const urgent=!closed&&state!=='upcoming'&&days!==null&&days>=0&&days<=10;
    let headline=closed?'마감':state==='upcoming'?'모집 예정':days===0?'오늘 기재 기한':days===1?'D-1 · 내일 마감':urgent?'D-'+days+' · '+days+'일 후 마감':state==='window'?'기재 모집기간 내':'기간 확인 필요';
    if(!closed&&days===0&&cutoff)headline='오늘 '+Number(cutoff.slice(0,2))+'시'+(cutoff.slice(3)==='00'?'':cutoff.slice(3)+'분')+' 마감';
    const chips=[];
    if(reference)chips.push({text:'검토중 · 참고자료',tone:'review'});
    if(urgent)chips.push({text:'마감 임박',tone:'urgent'});
    if(end&&!cutoff)chips.push({text:'마감 시각 미확인',tone:'check'});
    const conditions=item.eligibility?.conditions||[];
    if(!conditions.length||conditions.some(c=>c.presence==='unknown'||c.status!=='verified'||JSON.stringify(c.value||{}).includes('unknown')))chips.push({text:'세부 자격 일부 미확인',tone:'check'});
    const org=conditions.some(c=>c.kind==='applicant'&&c.presence==='specified'&&Array.isArray(c.value?.one_of)&&!c.value.one_of.includes('individual_farmer')&&c.value.one_of.some(v=>/corporation|institution|group|business/.test(v)));
    if(org||/법인|모임|단체|기관/.test(item.target||''))chips.push({text:'개인 신청 전 확인 필요',tone:'check'});
    if(closed)chips.push({text:'기재 기간 경과',tone:'muted'});
    return {state,days,start,end,cutoff,urgent,headline,chips,reference,
      tone:closed?'muted':urgent?'urgent':state==='window'?'window':state==='upcoming'?'upcoming':'check',
      periodText:start&&end?start+' ~ '+end+(cutoff?' '+cutoff+'(KST)':''):end?'기재 기한 '+end:'신청기간 확인 필요',
      // A calendar window is never a claim of verified reception or eligibility.
      eligibility_confirmed:false,reception_confirmed:false};
  }
  function sortRows(rows){
    const rank=r=>r.display.state==='elapsed'?4:r.display.urgent?0:r.display.state==='window'?1:r.display.state==='upcoming'?2:3;
    return rows.sort((a,b)=>rank(a)-rank(b)||(a.display.end||'9999-12-31').localeCompare(b.display.end||'9999-12-31')||String(b.item.published_at||'').localeCompare(String(a.item.published_at||'')));
  }
  root.MunongsaSupportReview={schema,browse,label,publicRecords,presentation,sortRows};
})(globalThis);
