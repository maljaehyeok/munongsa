const fs=require('fs'),vm=require('vm'),assert=require('assert');
global.document={addEventListener:()=>{},getElementById:()=>null};
for(const f of ['support-public','support-review','notice-review','personalization','amount-display','farm-profile','support-details','application-journey'])vm.runInThisContext(fs.readFileSync('assets/'+f+'.js','utf8'));
assert.equal(MunongsaJourney.fundingPlan({project:50000000,own:20000000}).gap,30000000);
assert.equal(MunongsaJourney.fundingPlan({project:10000000,own:20000000}).gap,0);
assert.equal(MunongsaJourney.fundingPlan({project:50000000}).gap,null);
const facts=MunongsaFarmProfile.fundingFacts('사업비는 5천만원이고 보유 자금은 2천만원이에요');assert.equal(facts.length,2);assert.equal(facts[0].won,50000000);assert.equal(facts[1].kind,'own');
assert.equal(MunongsaFarmProfile.fundingFacts('만약 사업비는 5천만원이고 보유 자금은 2천만원이면').length,0);
assert.equal(MunongsaFarmProfile.fundingFacts('사업비 3천만원, 사업비 5천만원').length,0);
if(process.argv[2]){
 const dir=process.argv[2],feed=JSON.parse(fs.readFileSync(dir+'/feed.json')),details=JSON.parse(fs.readFileSync(dir+'/details.json'));MunongsaSupportDetails.install(details);
 let available=0,methods=0,docs=0;
 for(const item of feed.notices){const row=MunongsaPersonalization.support(feed,{}).find(r=>r.item.id===item.id),p=MunongsaJourney.plan(item,row);assert(MunongsaJourney.detail(item,row).includes('신청 가능 확정'));if(p.detailAvailable)available++;if(p.method)methods++;if(p.documents.length)docs++;if(p.past)assert(p.actions.every(a=>a.kind==='past'));}
 assert(available>0);console.log(JSON.stringify({public:feed.notices.length,approvedDetailAvailable:available,methods,documents:docs}));
 const record=JSON.parse(JSON.stringify(details));record.records.forEach(r=>r.approval.state='pending');MunongsaSupportDetails.install(record);assert(feed.notices.every(n=>!MunongsaJourney.plan(n).detailAvailable));
}
console.log('신청 준비·자금 구분·미승인 차단 검사 통과');
