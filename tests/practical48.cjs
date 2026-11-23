const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
global.document={addEventListener(){},getElementById(){return null}};
for(const f of ['support-public','support-review','notice-review','personalization','amount-display','support-details','application-journey','user-display'])vm.runInThisContext(fs.readFileSync('assets/'+f+'.js','utf8'));
const dir=process.argv[2],feed=JSON.parse(fs.readFileSync(dir+'/feed.json')),details=JSON.parse(fs.readFileSync(dir+'/details.json'));MunongsaSupportDetails.install(details);
const raw=JSON.stringify(feed),rows=MunongsaPersonalization.support(feed,{}),trusted=v=>v.evidenceUrl&&v.fact!=='확인 필요';
const recovered=rows.map(r=>({id:r.item.id,before:MunongsaSupportReview.conditionViews(r.item,r.match).filter(trusted).length,after:MunongsaSupportReview.conditionViews(r.comparisonItem,r.match).filter(trusted).length})).filter(r=>r.after>r.before);
const detailReady=rows.filter(r=>{const p=MunongsaJourney.plan(r.item,r);return p.method||p.office||p.documents.length||p.contact});
const connected=rows.filter(r=>MunongsaJourney.plan(r.item,r).destinations.length);
const added=rows.filter(r=>{const p=MunongsaJourney.plan(r.item,r);return p.observed&&!p.method&&!p.office});
for(const r of recovered){const row=rows.find(x=>x.item.id===r.id),html=MunongsaDisplay.supportDetail(row.item,row,row.display,row.display.periodText);for(const v of MunongsaSupportReview.conditionViews(row.comparisonItem,row.match).filter(trusted))assert.ok(html.includes(v.fact.replace(/&/g,'&amp;')),r.id);}
for(const r of added){const p=MunongsaJourney.plan(r.item,r),html=MunongsaJourney.detail(r.item,r);assert.ok(html.includes(p.observed.method.replace(/&/g,'&amp;')));assert.ok(html.includes('observed_method'));assert.equal(p.documents.length,0);}
const actual=rows.find(r=>r.item.id==='NOTICE-2593a32e903d2f3e3ac46fea');
const no=MunongsaPersonalization.support(feed,{region:'전북',district:'김제시',crop:'garlic',applicant:'prospective',farmRegistered:'no',farmingSituation:'preparing'}).find(r=>r.item.id===actual.item.id);
assert.equal(no.decision.category,'C');assert.ok(MunongsaJourney.plan(no.item,no).actions.some(a=>a.kind==='mismatch'&&a.text.includes('농업경영체 등록 필요')&&a.field==='farmRegistered'));
const now=Date.now(),source={id:'NOTICE-test',title:'상시 모집',url:'https://www.rda.go.kr/test',source_id:'rda',rights:{public_display:'allowed'}};
const o={schema:'munongsa-notice-observation-v1',basis:{id:source.id,title:source.title,url:source.url,source_id:source.source_id},official_url:source.url,article_sha:'a'.repeat(64),checked_at:new Date(now-1000).toISOString(),expires_at:new Date(now+10000).toISOString(),standing:true,actual_reception:'operator_notice',reception_checked_at:new Date(now-1000).toISOString(),preparation:{method:'방문 신청'}};
let projected=MunongsaNoticeReview.project(source,o,now),d=MunongsaSupportReview.presentation(projected,now);
assert.equal(d.state,'standing');assert.ok(d.periodText.includes('상시'));assert.equal(d.reception_confirmed,false);assert.ok(MunongsaJourney.observedPreparation(projected,now));
projected=MunongsaNoticeReview.project(source,o,now+20000);d=MunongsaSupportReview.presentation(projected,now+20000);assert.equal(d.state,'unknown');assert.ok(d.headline.includes('과거 상시'));assert.equal(projected.official_reception_checked_at,null);assert.equal(MunongsaJourney.observedPreparation(projected,now+20000),null);
assert.equal(MunongsaJourney.observedPreparation({...source,application_preparation:{method:'unapproved'}}),null);
assert.equal(MunongsaNoticeReview.project(source,{...o,basis:{...o.basis,id:'NOTICE-wrong'}},now),source);
assert.equal(MunongsaJourney.observedPreparation({...projected,official_observation_current:true,official_observation_expires_at:new Date(now-1).toISOString()},now),null);
const counts={public:rows.length,comparison:rows.filter(r=>r.comparisonItem.eligibility.conditions.some(c=>c.status==='verified')).length,visibleDetails:rows.filter(r=>MunongsaSupportDetails.get(r.sourceItem)).length,blockedDetails:rows.filter(r=>MunongsaSupportDetails.availability(r.sourceItem).state==='scope_review').length,existingPreparation:detailReady.length,connectedPreparation:connected.length,observedMethodAdded:added.length,conditionEvidenceRestoredNotices:recovered.length,conditionEvidenceRestoredFields:recovered.reduce((n,r)=>n+r.after-r.before,0)};
const pre=JSON.parse(fs.readFileSync(dir+'/preflight.json'));
for(const f of pre.candidates.filter(f=>f.relative==='assets/support-review.js')){
 const load=n=>{const c=vm.createContext({URL});vm.runInContext(fs.readFileSync(dir+'/'+n,'utf8'),c);return c.MunongsaSupportReview;};const a=load(f.original),b=load(f.candidate);assert.equal(a.conditionViews.toString(),b.conditionViews.toString());
 for(const r of rows){const x=a.presentation(r.item),y=b.presentation(r.item);for(const k of ['state','start','end','reception_confirmed','operator_notice'])assert.equal(x[k],y[k],r.item.id+' '+k);}
}
assert.equal(counts.public,126);assert.equal(counts.comparison,26);assert.equal(counts.visibleDetails,12);assert.equal(counts.blockedDetails,7);assert.equal(counts.existingPreparation,7);assert.ok(counts.observedMethodAdded>0);assert.ok(counts.conditionEvidenceRestoredNotices>0);assert.equal(JSON.stringify(feed),raw);
fs.writeFileSync(dir+'/impact.json',JSON.stringify({counts,recovered,added:added.map(r=>({id:r.item.id,title:r.item.title,method:MunongsaJourney.plan(r.item,r).observed.method}))},null,2));console.log(JSON.stringify(counts));
