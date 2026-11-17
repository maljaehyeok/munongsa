/* Synthetic UI and approval gates only; no operating feed or network. */
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const code=fs.readFileSync(path.join(__dirname,'../assets/support-details.js'),'utf8');
function api(hostname,search){const c={URLSearchParams,location:{hostname,search}};vm.runInNewContext(code,c);return c.MunongsaSupportDetails;}
const item={id:'test',title:'Synthetic',url:'https://www.rda.go.kr/young/custom/policy/view.do?sId=1',target:'test',region:'unknown',publication:'official_guidance',verification_status:'basics_only',rights:{public_display:'allowed'}};
const local=api('127.0.0.1','?support-details-preview=1');
const evidence={url:item.url,location:'synthetic',checked_at:'2026-11-17T10:00:00Z'};
const record={basis:local.basis(item),rights:{facts_only:true},approval:{state:'preview',reviewer:'local-test',reference:'synthetic',checked_at:evidence.checked_at},fields:{target:{value:'<script>unsafe</script>',evidence}}};
const data={schema:'munongsa-support-details-v1',preview:true,records:[record]};
for(const [host,query] of [['munongsa.duckdns.org','?support-details-preview=1'],['127.0.0.1','']]){const a=api(host,query);a.install(data);assert.equal(a.get(item),null);}
local.install(data);assert(local.get(item));assert.equal(local.get({...item,title:'Other round'}),null);
const escape=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const html=local.detail(item,escape,x=>x);assert(html.includes('확인되지 않음'));assert(html.includes('&lt;script&gt;'));assert(!html.includes('<script>'));assert(html.includes('공개 승인이나 운영 반영 결과가 아닙니다'));
assert(html.indexOf('신청기간')<html.indexOf('누가 신청'));assert(html.indexOf('신청 방법과 접수처')<html.indexOf('준비 서류'));
const publicCode=fs.readFileSync(path.join(__dirname,'../assets/support-public.js'),'utf8');
const notice={...item,id:'NOTICE-local-test',local_review_only:true,recommendation_eligible:false,eligibility_complete:false,freshness:'current',last_checked_at:evidence.checked_at,guidance_expires_at:'2099-01-01T00:00:00Z',rights:{public_display:'allowed',evidence_url:item.url,checked_at:'2026-11-17'}};
for(const [hostname,search,expected] of [['munongsa.duckdns.org','?support-details-preview=1',0],['127.0.0.1','',0],['127.0.0.1','?support-details-preview=1',1]]){
 const c={URL,URLSearchParams,location:{hostname,search}};vm.runInNewContext(publicCode,c);const r=c.MunongsaSupport.explore({schema_version:'munongsa-support-public-v1',notices:[notice]},{});assert.equal(r.references.length,expected);
}
const prod=api('munongsa.duckdns.org','');
const guidance={...item,recommendation_eligible:false,eligibility_complete:false};
const approved={...record,approval:{...record.approval,state:'approved'},fields:{summary:{value:'Approved synthetic support',evidence},funding:{value:'UNAPPROVED-AMOUNT',evidence}},rights:{facts_only:true,display_scope:'reviewed_facts_v1',public_fields:['summary','funding'],audience:'detail_display_only',eligibility_approval:false,body_redistribution:false,attachment_redistribution:false,use_basis:{kind:'independent_facts',urls:['https://www.law.go.kr/']}}};
approved.field_approvals={summary:{...approved.approval},funding:{...approved.approval,state:'pending'}};
prod.install({schema:data.schema,preview:false,records:[approved]});
assert(prod.get(guidance));assert.deepEqual(Object.keys(prod.get(guidance).fields),['summary']);
assert(!prod.detail(guidance,escape,x=>x).includes('UNAPPROVED-AMOUNT'));
assert.equal(prod.get({...guidance,title:'Changed notice'}),null);assert.equal(prod.get({...guidance,rights:{public_display:'blocked'}}),null);
const noFields=structuredClone(approved);delete noFields.field_approvals;prod.install({schema:data.schema,preview:false,records:[noFields]});assert.equal(prod.get(guidance),null);
prod.install({schema:data.schema,preview:true,records:[approved]});assert.equal(prod.get(guidance),null);
const legacy={...record,approval:{...record.approval,state:'approved'}};
prod.install({schema:data.schema,preview:false,records:[legacy]});assert(prod.get({...item,publication:'approved',verification_status:'verified'}));assert.equal(prod.get(guidance),null);
const existing=JSON.parse(fs.readFileSync(path.join(__dirname,'../assets/support-details.json'),'utf8'));
prod.install(existing);assert.equal(existing.records.length,11);
for(const r of existing.records){const b=r.basis;const n={id:b.id,title:b.title,url:b.url,target:b.target,region:b.region,reference_application_dates:b.dates,application_period:b.period,eligibility:b.eligibility,publication:'approved_reference',verification_status:'verified',rights:{public_display:'allowed'}};assert(prod.get(n),b.id);}
console.log(JSON.stringify({passed:true,cases:20,preview_blocked_on_production:true,unknowns_visible:true,text_escaped:true,mixed_feed_blocked:true,field_approval_enforced:true,legacy_records:11}));
