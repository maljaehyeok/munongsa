const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'..'),box={URL,Date,Intl,console};box.globalThis=box;vm.createContext(box);
for(const file of ['support-public.js','support-review.js','notice-review.js','personalization.js'])vm.runInContext(fs.readFileSync(path.join(root,'assets',file),'utf8'),box);
const proof={url:'https://www.rda.go.kr/young/custom/policy/view.do?sId=1',location:'가상 근거',fact_confirmed:true};
const condition=(id,kind,value)=>({condition_id:id,kind,value,status:'verified',presence:'specified',evidence:proof});
function item(cs,logic){return {url:proof.url,eligibility:{conditions:cs,logic:logic||{op:'AND',children:cs.map(c=>({condition_id:c.condition_id}))}}};}
function decide(n,p,shown=n){return box.MunongsaPersonalization.decision(n,shown,box.MunongsaSupport.evaluate(n,p),p);}
test('registration alone cannot establish regional suitability',()=>{
 const n=item([condition('f','farm_registration',{registered:true})]);assert.equal(decide(n,{farmRegistered:'yes'}).label,'지역 확인 필요');
});
test('confirmed mismatch dominates other matches',()=>{
 const n=item([condition('r','residence',{regions:['경기 파주시']}),condition('f','farm_registration',{registered:true})]);
 const d=decide(n,{residenceRegion:'제주',farmRegistered:'yes'});assert.equal(d.category,'C');assert.equal(d.excluded,true);
});
test('residence and farm are compared independently',()=>{
 const n=item([condition('r','business_location',{regions:['경기 파주시'],location_basis:'farm_land'})]);
 assert.equal(decide(n,{region:'경기',district:'파주시',residenceRegion:'전북'}).region_state,'match');
 assert.equal(decide(n,{region:'전북',district:'전주시',residenceRegion:'경기',residenceDistrict:'파주시'}).category,'C');
});
test('province alone cannot prove a required city',()=>{
 const n=item([condition('r','residence',{regions:['경기 파주시']})]);assert.equal(decide(n,{residenceRegion:'경기'}).region_state,'check');
});
test('OR alternative cannot become a mandatory regional exclusion',()=>{
 const n=item([condition('r','residence',{regions:['경기']}),condition('a','applicant',{one_of:['individual_farmer']})],{op:'OR',children:[{condition_id:'r'},{condition_id:'a'}]});
 assert.equal(decide(n,{residenceRegion:'제주',applicant:'individual'}).region_state,'check');assert.notEqual(decide(n,{residenceRegion:'제주',applicant:'individual'}).category,'C');
});
test('national scope needs verified fact projection',()=>{
 const n=item([]);assert.equal(decide(n,{}, {...n,geographic_scope:'nationwide_verified'}).category,'D');
 assert.equal(decide(n,{}, {...n,geographic_scope:'nationwide_verified',verified_facts_at:new Date().toISOString()}).label,'추가 자격 확인 필요');
});
