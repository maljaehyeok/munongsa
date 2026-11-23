const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
global.document={addEventListener:()=>{},getElementById:()=>null};
for(const f of ['support-public','support-review','notice-review','personalization','amount-display','farm-profile','support-details','application-journey'])vm.runInThisContext(fs.readFileSync('assets/'+f+'.js','utf8'));
const dir=process.argv[2];assert.ok(dir,'private public snapshot directory required');
const feed=JSON.parse(fs.readFileSync(dir+'/feed.json')),details=JSON.parse(fs.readFileSync(dir+'/details.json'));MunongsaSupportDetails.install(details);
const rows=MunongsaPersonalization.support(feed,{}),metrics={public:rows.length,comparison:0,details:0,blocked:0,method:0,documents:0,contact:0,shortcuts:0,nonElapsedShortcuts:0};const selected=[];
for(const row of rows){
 const p=MunongsaJourney.plan(row.item,row),html=MunongsaJourney.detail(row.item,row),render=MunongsaSupportDetails.detail(row.sourceItem,x=>String(x),x=>String(x));
 if(row.comparisonItem.eligibility.conditions.some(c=>c.status==='verified'))metrics.comparison++;
 if(p.detailAvailable)metrics.details++;
 if(MunongsaSupportDetails.availability(row.sourceItem).state==='scope_review')metrics.blocked++;
 for(const [key,field] of [['method','method'],['documents','documents_listed'],['contact','contact']])if(p.destinations.some(d=>d.section===field))metrics[key]++;
 if(p.destinations.length){metrics.shortcuts++;if(!p.past)metrics.nonElapsedShortcuts++;selected.push({id:row.item.id,title:row.item.title,state:row.display.state,links:p.destinations.map(d=>d.section)});}
 for(const d of p.destinations){assert.ok(render.includes('data-preparation-section="'+d.section+'"'));assert.ok(html.includes('data-preparation-jump="'+d.section+'"'));}
 if(p.past){assert.ok(html.includes('지난 공고의 승인된 준비 안내')||!p.destinations.length);assert.ok(p.actions.every(a=>a.kind==='past'));}
 assert.ok(html.includes('신청 가능 확정'));
}
assert.equal(metrics.public,126);assert.equal(metrics.comparison,26);assert.equal(metrics.details,12);assert.equal(metrics.blocked,7);assert.ok(metrics.shortcuts>0);
fs.writeFileSync(dir+'/impact.json',JSON.stringify({metrics,selected},null,2));console.log(JSON.stringify(metrics));
const baseline=JSON.stringify(feed);MunongsaJourney.plan(rows[0].item,rows[0]);assert.equal(JSON.stringify(feed),baseline);
const pending=JSON.parse(JSON.stringify(details));pending.records.forEach(r=>r.approval.state='pending');MunongsaSupportDetails.install(pending);
assert.ok(rows.every(r=>MunongsaJourney.plan(r.item,r).destinations.length===0));
// Verify production gates are byte-for-byte identical before/after the markup-only SDK change.
const pre=JSON.parse(fs.readFileSync(dir+'/preflight.json'));for(const f of pre.candidates.filter(f=>f.relative==='assets/support-details.js')){
 const load=name=>{const c=vm.createContext({URL,location:{hostname:'munongsa.duckdns.org',search:''}});vm.runInContext(fs.readFileSync(dir+'/'+name,'utf8'),c);return c.MunongsaSupportDetails};
 const a=load(f.original),b=load(f.candidate);for(const k of ['install','get','basis','availability','application','linkReview','linkHistory'])assert.equal(a[k].toString(),b[k].toString(),k);
}
console.log('승인된 준비 안내 이동·과거 공고 구분·미승인/차단 상세 보호·원본 및 승인 게이트 보존 검사 통과');
