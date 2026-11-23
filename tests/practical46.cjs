const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
global.document={addEventListener(){},getElementById(){return null}};
for(const f of ['support-public','support-review','notice-review','personalization','amount-display','support-details','application-journey'])vm.runInThisContext(fs.readFileSync('assets/'+f+'.js','utf8'));
const dir=process.argv[2],feed=JSON.parse(fs.readFileSync(dir+'/feed.json')),details=JSON.parse(fs.readFileSync(dir+'/details.json'));MunongsaSupportDetails.install(details);
const rows=MunongsaPersonalization.support(feed,{}),now=Date.parse('2026-11-23T04:00:00Z');
let d=MunongsaSupportReview.presentation({recorded_period_elapsed:true},now);assert.equal(d.state,'unknown');assert.equal(d.historical_elapsed,true);assert.match(d.headline,/과거/);assert.equal(d.reception_confirmed,false);
assert.equal(MunongsaSupportReview.presentation({},now).historical_elapsed,false);
for(const [dates,state] of [[{start:{date:'2026-11-24'},end:{date:'2026-12-01'}},'upcoming'],[{start:{date:'2026-11-01'},end:{date:'2026-12-01'}},'window']]){d=MunongsaSupportReview.presentation({recorded_period_elapsed:true,reference_application_dates:dates},now);assert.equal(d.state,state);assert.equal(d.historical_elapsed,false);}
const receipt=MunongsaJourney.receptionSummary({last_checked_at:'2026-11-23T03:00:00Z'},null);assert.ok(receipt.includes('목록 정보 확인일')&&receipt.includes('접수를 확인한 시점은 아닙니다'));
const oldSource=JSON.stringify(feed);
const cases=[{name:'김제 마늘 준비 청년',p:{region:'전북',district:'김제시',applicant:'prospective',farmingSituation:'preparing',crop:'garlic',cultivation:'openfield',farmRegistered:'no',supportSearch:'마늘'}},{name:'전주 거주 예비 농업인',p:{residenceRegion:'전북',residenceDistrict:'전주시',applicant:'prospective',farmingSituation:'preparing',farmRegistered:'unknown',supportSearch:'유기농업자재'}},{name:'김제 기존 농업인 추가 지원',p:{region:'전북',district:'김제시',applicant:'individual',farmingSituation:'independent',farmRegistered:'yes',supportSearch:'유기농업자재'}}];
const scenarios=cases.map(c=>({profile:c.name,top:MunongsaPersonalization.support(feed,c.p).filter(r=>r.discovery.matches&&!r.decision.excluded).slice(0,3).map(r=>({id:r.item.id,title:r.item.title,decision:r.decision.label,period:r.display.state,next:MunongsaJourney.plan(r.item,r).actions[0]?.text}))}));
const pre=JSON.parse(fs.readFileSync(dir+'/preflight.json'));let unchanged=0;
for(const f of pre.candidates.filter(f=>f.relative==='assets/support-review.js')){
 const load=name=>{const c=vm.createContext({URL});vm.runInContext(fs.readFileSync(dir+'/'+name,'utf8'),c);return c.MunongsaSupportReview;};const a=load(f.original),b=load(f.candidate);
 assert.equal(a.conditionViews.toString(),b.conditionViews.toString());
 for(const r of rows){const x=a.presentation(r.item),y=b.presentation(r.item);for(const k of ['state','start','end','urgent','reception_confirmed','operator_notice'])assert.equal(x[k],y[k],r.item.id+' '+k);unchanged++;}
}
const counts={public:rows.length,comparison:rows.filter(r=>r.comparisonItem.eligibility.conditions.some(c=>c.status==='verified')).length,visibleDetails:rows.filter(r=>MunongsaSupportDetails.get(r.sourceItem)).length,blockedDetails:rows.filter(r=>MunongsaSupportDetails.availability(r.sourceItem).state==='scope_review').length,historicalUnknown:rows.filter(r=>r.display.historical_elapsed).length,preparationDestinations:rows.filter(r=>MunongsaJourney.plan(r.item,r).destinations.length).length};
assert.equal(counts.public,126);assert.equal(counts.comparison,26);assert.equal(counts.visibleDetails,12);assert.equal(counts.blockedDetails,7);assert.equal(JSON.stringify(feed),oldSource);
fs.writeFileSync(dir+'/impact.json',JSON.stringify({counts,state_and_filter_checks_unchanged:unchanged,scenarios,historical:rows.filter(r=>r.display.historical_elapsed).map(r=>({id:r.item.id,title:r.item.title}))},null,2));console.log(JSON.stringify({...counts,state_and_filter_checks_unchanged:unchanged,virtual_profiles:3,unapproved_applied:0}));
