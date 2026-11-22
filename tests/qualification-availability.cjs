const fs=require('fs'),vm=require('vm'),assert=require('assert');
global.document={addEventListener:()=>{},getElementById:()=>null};
for(const f of ['support-public','support-review','notice-review','personalization','support-details','application-journey'])vm.runInThisContext(fs.readFileSync('assets/'+f+'.js','utf8'));
const dir=process.argv[2];assert(dir,'private operational snapshot directory required');
const feed=JSON.parse(fs.readFileSync(dir+'/feed.json')),details=JSON.parse(fs.readFileSync(dir+'/details.json'));
MunongsaSupportDetails.install(details);
const rows=MunongsaPersonalization.support(feed,{}),blocked=rows.filter(r=>MunongsaSupportDetails.availability(r.sourceItem).state==='scope_review');
assert.equal(blocked.length,7);assert.equal(rows.filter(r=>MunongsaSupportDetails.get(r.sourceItem)).length,12);
const esc=x=>String(x).replace(/[<>&]/g,'');
for(const r of blocked){const html=MunongsaSupportDetails.detail(r.sourceItem,esc,String);assert(html.includes('상세정보 확인이 필요해요'));assert(!html.includes('신청 준비에 필요한 정보'));for(const f of Object.values(details.records.find(x=>x.basis.id===r.item.id).fields))for(const text of Array.isArray(f.value)?f.value:[f.value])assert(!html.includes(text));}
for(const p of [{residenceRegion:'제주',residenceDistrict:'제주시',region:'제주',district:'제주시',farmRegistered:'yes',applicant:'individual'},{residenceRegion:'경기',residenceDistrict:'화성시',farmRegistered:'no',applicant:'agricultural_business'},{}]){
 const result=MunongsaPersonalization.support(feed,p);assert(result.every(r=>!r.decision.final_application_eligibility_confirmed));
 for(const r of result.filter(r=>r.decision.excluded))assert(!r.recommendationAllowed);
 const unknown=result.find(r=>r.decision.region_state==='check'&&r.display.state!=='elapsed'&&!r.match.conditions.some(c=>['residence','business_location'].includes(c.field)&&c.status!=='check'));
 if(unknown)assert(MunongsaJourney.plan(unknown.item,unknown).actions.some(a=>a.kind==='region_unknown'));
}
assert.equal(MunongsaSupportDetails.availability(null).state,'unavailable');
const changed={...rows.find(r=>MunongsaSupportDetails.get(r.sourceItem)).sourceItem,title:'unmatched revised notice'};assert.equal(MunongsaSupportDetails.get(changed),null);
const pending=JSON.parse(JSON.stringify(details));pending.records.forEach(r=>r.approval.state='pending');MunongsaSupportDetails.install(pending);assert(feed.notices.every(n=>!MunongsaSupportDetails.get(n)&&MunongsaSupportDetails.availability(n).state==='unavailable'));
console.log(JSON.stringify({preserved_details:19,visible:12,blocked:7,unapproved_fields_exposed:0,profiles:3}));
