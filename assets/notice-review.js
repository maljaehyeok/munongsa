/* Observed dates and reception are separate from eligibility and approval. */
(function(root){'use strict';
 const basis=i=>Object.fromEntries(['id','title','url','source_id'].map(k=>[k,i[k]??null]));
 function project(item,value,now=Date.now()){
  if(!value||value.review_required||value.schema!=='munongsa-notice-observation-v1'||JSON.stringify(value.basis)!==JSON.stringify(basis(item))||value.official_url!==item.url||!/^[a-f0-9]{64}$/.test(value.article_sha||''))return item;
  const a=Date.parse(value.checked_at),b=Date.parse(value.expires_at);
  if(!Number.isFinite(a)||!Number.isFinite(b)||a>now||b-a>26*3600000||b<=a)return item;
  const dates=value.reference_application_dates||{},valid=v=>!v||Object.keys(v).length===0||/^\d{4}-\d{2}-\d{2}$/.test(v.date)&&Number.isFinite(Date.parse(v.date+'T00:00:00Z'))&&new Date(v.date+'T00:00:00Z').toISOString().slice(0,10)===v.date;
  if(!valid(dates.start)||!valid(dates.end)||dates.start?.date&&dates.end?.date&&dates.start.date>dates.end.date)return item;
  const newerPeriod=Date.parse(item.verified_period_at)>Date.parse(value.facts_checked_at||value.checked_at);
  const fresh=now<b&&!value.source_recheck_pending,age=now-Date.parse(value.reception_checked_at),reception=!newerPeriod&&fresh&&age>=0&&age<86400000?value.actual_reception:'unconfirmed';
  return {...item,reference_application_dates:newerPeriod?item.reference_application_dates:Object.keys(dates).length?dates:item.reference_application_dates,
   actual_reception_state:['operator_notice','login_unverified','confirmed','unavailable'].includes(reception)?reception:'unconfirmed',
   official_observation_at:value.facts_checked_at||value.checked_at,official_observation_current:fresh,official_observation_expires_at:value.expires_at,recorded_standing_application:value.standing===true,standing_application:fresh&&value.standing===true,
   official_reception_checked_at:reception!=='unconfirmed'&&['operator_notice','login_unverified','confirmed','unavailable'].includes(reception)?value.reception_checked_at:null,
   application_preparation:value.preparation||{},application_method:value.preparation?.method||value.method||item.application_method,published_at:value.published_at||item.published_at};
 }
 root.MunongsaNoticeReview={project};
})(globalThis);
