const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const box={URL,URLSearchParams,Date,Intl,location:{hostname:'munongsa.duckdns.org',search:''}};box.globalThis=box;vm.createContext(box);
for(const f of ['support-public.js','support-review.js','notice-review.js','personalization.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets',f),'utf8'),box);
const evidence={url:'https://www.rda.go.kr/young/custom/policy/view.do?sId=1',location:'synthetic',fact_confirmed:true};
function item(id,region){return {id:'NOTICE-'+id,title:'Synthetic',url:evidence.url,eligibility:{conditions:[{condition_id:'r',kind:'residence',status:'verified',presence:'specified',value:{regions:[region]},evidence}],logic:{op:'AND',children:[{condition_id:'r'}]}}};}
for(const [short,long] of [['서울','서울특별시'],['부산','부산광역시'],['대구','대구광역시'],['인천','인천광역시'],['광주','광주광역시'],['대전','대전광역시'],['울산','울산광역시'],['세종','세종특별자치시']])assert.equal(box.MunongsaSupport.evaluate(item(short,long),{residenceRegion:short}).conditionStatus,'match');
assert.equal(box.MunongsaSupport.evaluate(item('regional','경남 합천군'),{residenceRegion:'제주'}).conditionStatus,'mismatch');
assert.equal(box.MunongsaSupport.evaluate(item('regional','경남 합천군'),{residenceRegion:'경남'}).conditionStatus,'check');
const now=Date.now(),today=new Date(now).toISOString().slice(0,10),future=new Date(now+86400000*10).toISOString().slice(0,10);
function browse(id,state){return {id:'NOTICE-'+id,title:'Synthetic '+id,url:evidence.url,institution:'Synthetic',publication:'official_guidance',verification_status:'basics_only',recommendation_eligible:false,eligibility_complete:false,freshness:'current',last_checked_at:new Date(now).toISOString(),guidance_expires_at:new Date(now+86400000).toISOString(),rights:{public_display:'allowed',evidence_url:evidence.url,checked_at:today},...(state==='upcoming'?{reference_application_dates:{start:{date:future,timezone:'Asia/Seoul'},end:{date:future,timezone:'Asia/Seoul'}}}:state==='standing'?{standing_application:true}:{})};}
const unknown=browse('unknown','unknown'),upcoming=browse('upcoming','upcoming'),standing=browse('standing','standing');
let feed={schema_version:'munongsa-support-public-v1',notices:[unknown,upcoming,standing]};
assert.deepEqual(Array.from(box.MunongsaPersonalization.support(feed,{},now),r=>r.item.id),['NOTICE-upcoming','NOTICE-standing','NOTICE-unknown']);
const privateOnly={...unknown,local_review_only:true};const groups=box.MunongsaSupport.explore({...feed,notices:[privateOnly]},{});
assert.equal(groups.references.length+groups.recommendations.length+groups.excluded.length,0);
console.log('전국 지역명·모집 정렬·미승인 차단 검사 통과');
