/* Synthetic evidence only; no API calls or production data. */
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const root={Date,Intl,URL,URLSearchParams,location:{hostname:'example.test'},MunongsaSupport:{safeUrl:u=>u.startsWith('https://')}};root.globalThis=root;
for(const name of ['notice-review','support-review','support-details','personalization'])vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../assets/'+name+'.js'),'utf8'),root);
const now=Date.parse('2026-11-14T09:00:00Z'),item={id:'synthetic',title:'Synthetic',url:'https://agency.go.kr/notice/1',source_id:'test'},dates={start:{date:'2026-11-01'},end:{date:'2026-11-15'}};
const observation={schema:'munongsa-notice-observation-v1',basis:{...item},official_url:item.url,article_sha:'a'.repeat(64),checked_at:new Date(now).toISOString(),expires_at:new Date(now+26*3600000).toISOString(),reference_application_dates:dates,reception_checked_at:new Date(now).toISOString(),actual_reception:'operator_notice'};
const review={schema:'munongsa-official-link-review-v1',basis:{...item},state:'official_detail',checked_at:new Date(now).toISOString(),expires_at:new Date(now+48*3600000).toISOString()};
root.MunongsaSupportDetails.install({schema:'munongsa-support-details-v1',records:[],link_reviews:[review]});
for(const hours of [0,26,48,72]){
 const at=now+hours*3600000,shown=root.MunongsaNoticeReview.project(item,observation,at);
 assert.equal(JSON.stringify(shown.reference_application_dates),JSON.stringify(dates));
 if(hours)assert.equal(shown.actual_reception_state,'unconfirmed');
 if(hours>=48)assert.equal(root.MunongsaSupportReview.presentation(shown,at).state,'elapsed');
 assert(root.MunongsaSupportDetails.linkHistory(item,at));
 assert.equal(Boolean(root.MunongsaSupportDetails.linkReview(item,at)),hours<48);
}
assert.equal(root.MunongsaNoticeReview.project(item,{...observation,review_required:true},now),item);
assert.equal(root.MunongsaSupportDetails.linkHistory({...item,title:'Changed'},now),null);
const basis=Object.fromEntries(['id','title','url','target','region','reference_application_dates','application_period','eligibility'].map(k=>[k,item[k]??null]));
const facts={basis,complete:false,checked_at:observation.checked_at,expires_at:observation.expires_at,evidence:{url:item.url,fact_confirmed:true},fields:{reference_application_dates:dates}};
assert(root.MunongsaPersonalization.sourceFacts(item,facts,now+72*3600000).reference_application_dates);
assert.equal(root.MunongsaPersonalization.sourceConditions(item,facts,now+72*3600000),null);
assert.equal(root.MunongsaPersonalization.sourceFacts(item,{...facts,review_required:true},now),item);
console.log(JSON.stringify({passed:true,hours:[0,26,48,72],dates_preserved:true,stale_reception_blocked:true,link_history_preserved:true}));
