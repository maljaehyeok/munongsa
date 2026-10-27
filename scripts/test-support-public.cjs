// Offline: node --test scripts/test-support-public.cjs. All records below are fictional.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),context={URL};
vm.runInNewContext(fs.readFileSync(path.join(root,'assets/support-public.js'),'utf8'),context);
const api=context.MunongsaSupport,now=Date.parse('2026-10-26T12:00:00+09:00');
const clone=v=>JSON.parse(JSON.stringify(v));
function condition(id,kind,value,presence='specified'){
  return {condition_id:id,kind,value,presence,status:'verified',evidence:{url:'https://www.mafra.go.kr/test',location:'모의 p.1',quote:'실제 공고가 아닌 격리 테스트 조건'}};
}
function record(){
  const conditions=[condition('person','applicant',{one_of:['individual_farmer']}),
    condition('home','residence',{regions:['전북특별자치도 김제시']}),
    condition('age','age',{min:18,max:39,min_inclusive:true,max_inclusive:true,basis_date:'2026-01-01',age_basis:'international'}),
    condition('registration','farm_registration',{registered:true})];
  return {id:'MOCK-ONLY-01',title:'모의 개인농 지원 · 실제 사업 아님',institution:'모의 기관',
    publication:'approved',verification_status:'verified',freshness:'current',url:'https://www.mafra.go.kr/test',
    rights:{public_display:'allowed',evidence_url:'https://www.mafra.go.kr/rights',checked_at:'2026-10-25'},
    last_checked_at:'2026-10-25T12:00:00+09:00',recommendation_eligible:true,application_status:'open_verified',
    application_period:{start:'2026-10-01T00:00:00+09:00',end:'2026-10-31T18:00:00+09:00'},
    eligibility:{conditions,logic:{op:'AND',children:conditions.map(c=>({condition_id:c.condition_id}))}}};
}
const base={applicant:'individual',birthDate:'1994-01-01',age:'32',experience:'planned',
  region:'전북',district:'김제시',residenceRegion:'전북',residenceDistrict:'김제시',farmRegistered:'yes',crop:'garlic',area:'1'};
const profiles=[['기준',{},'match'],['거주지 변경',{residenceRegion:'전남',residenceDistrict:'나주시'},'mismatch'],
  ['영농지만 변경',{region:'전남',district:'나주시'},'match'],['생년월일 누락',{birthDate:''},'check'],
  ['현재 나이만 변경',{age:'70'},'match'],['공고 기준 17세',{birthDate:'2009-01-01'},'mismatch'],
  ['공고 기준 18세',{birthDate:'2008-01-01'},'match'],['공고 기준 39세',{birthDate:'1987-01-01'},'match'],
  ['공고 기준 40세',{birthDate:'1986-01-01'},'mismatch'],['등록 미확인',{farmRegistered:'unknown'},'check'],
  ['미등록',{farmRegistered:'no'},'mismatch'],['거주지 누락',{residenceRegion:'',residenceDistrict:''},'check'],
  ['작물 변경',{crop:'rice'},'match'],['면적 변경',{area:'100'},'match'],['예산 변경',{budget:'1'},'match'],
  ['법인·단체 선택',{applicant:'organization'},'check'],['청년농 선택',{applicant:'young'},'match'],
  ['예비농 상충 입력',{applicant:'prospective',experience:'over3'},'check']];
for(const [name,change,status] of profiles)test('verified comparison: '+name,()=>{
  const r=api.evaluate(record(),{...base,...change});assert.equal(r.conditionStatus,status);assert.ok(r.explanation.includes('확정 아님')||r.explanation.includes('판정 아님')||r.explanation.includes('판단 보류'));
});
function one(c,logic){const r=record();r.eligibility={conditions:[c],logic:logic||{condition_id:c.condition_id}};return r}
test('AND/OR/NOT/UNKNOWN preserve three-valued meaning',()=>{
  const r=record(),person=r.eligibility.conditions[0],home=r.eligibility.conditions[1];
  r.eligibility={conditions:[person,home],logic:{op:'OR',children:[{condition_id:'person'},{condition_id:'home'}]}};
  assert.equal(api.evaluate(r,{...base,residenceRegion:'전남'}).conditionStatus,'match');
  r.eligibility.logic={op:'AND',children:r.eligibility.logic.children};
  assert.equal(api.evaluate(r,{...base,residenceRegion:'전남'}).conditionStatus,'mismatch');
  r.eligibility={conditions:[person],logic:{op:'NOT',children:[{condition_id:'person'}]}};
  assert.equal(api.evaluate(r,base).conditionStatus,'mismatch');
  assert.equal(api.evaluate(r,{}).conditionStatus,'check');
  r.eligibility.logic.op='UNKNOWN';assert.equal(api.evaluate(r,base).conditionStatus,'check');
});
test('unverified assertions cannot cause eligibility mismatch',()=>{
  const c=condition('crop','crop',{any_of:['벼']});c.status='candidate';assert.equal(api.evaluate(one(c),base).conditionStatus,'check');
});
test('unknown and verified no restriction differ',()=>{
  const c=condition('crop','crop',null,'unknown');assert.equal(api.evaluate(one(c),base).conditionStatus,'check');
  c.presence='no_restriction';assert.equal(api.evaluate(one(c),{}).conditionStatus,'match');
});
test('age birthday boundary uses documented date not present age',()=>{
  assert.equal(api.evaluate(record(),{...base,birthDate:'2008-01-02'}).conditionStatus,'mismatch');
  for(const birthDate of ['invalid','2026-02-30','2030-01-01'])assert.equal(api.evaluate(record(),{...base,birthDate}).conditionStatus,'check');
});
test('broad farming stage is not exact years at reference date',()=>{
  const r=one(condition('career','farming_experience',{min:0,max:3,min_inclusive:true,max_inclusive:true,unit:'years',basis_date:'2026-01-01'}));
  assert.equal(api.evaluate(r,base).conditionStatus,'check');
  assert.equal(api.evaluate(r,{...base,farmingYears:'2',experienceBasisDate:'2026-01-01'}).conditionStatus,'match');
  assert.equal(api.evaluate(r,{...base,farmingYears:'4',experienceBasisDate:'2026-01-01'}).conditionStatus,'mismatch');
  assert.equal(api.evaluate(r,{...base,farmingYears:'2',experienceBasisDate:'2026-10-26'}).conditionStatus,'check');
});
test('crop and explicitly measured scale comparisons reject invalid values',()=>{
  const crop=one(condition('crop','crop',{any_of:['마늘']}));
  assert.equal(api.evaluate(crop,base).conditionStatus,'match');
  assert.equal(api.evaluate(crop,{...base,crop:'rice'}).conditionStatus,'mismatch');
  assert.equal(api.evaluate(crop,{...base,crop:'nonsense'}).conditionStatus,'check');
  const area=one(condition('area','scale',{metric:'cultivated_area',unit:'ha',min:0.1,max:2,min_inclusive:true,max_inclusive:false}));
  assert.equal(api.evaluate(area,base).conditionStatus,'match');
  assert.equal(api.evaluate(area,{...base,area:'2'}).conditionStatus,'mismatch');
  for(const invalid of ['','-1','NaN','Infinity'])assert.equal(api.evaluate(area,{...base,area:invalid}).conditionStatus,'check');
});
test('free-text exclusion, facility, unknown IDs do not become inferred rules',()=>{
  for(const kind of ['exclusion','facility','business_location'])assert.equal(api.evaluate(one(condition('x',kind,{text:'원문 검토 필요'})),base).conditionStatus,'check');
  const r=record();r.eligibility.logic={condition_id:'missing'};assert.equal(api.evaluate(r,base).conditionStatus,'check');
});
test('reference approvals never become recommendations even within application period',()=>{
  const r=record();r.publication='approved_reference';assert.equal(api.eligible(r,now),false);
  const g=api.explore({schema_version:api.schema,notices:[r]},base,now);assert.equal(g.references.length,1);assert.equal(g.recommendations.length,0);
});
test('expired or upcoming records never current recommendation',()=>{
  const r=record();assert.equal(api.eligible(r,now),true);
  assert.equal(api.eligible(r,Date.parse('2026-11-02T00:00:00+09:00')),false);
  assert.ok(api.status(r,Date.parse('2026-11-02T00:00:00+09:00')).includes('연장 여부 확인 필요'));
  r.application_status='upcoming_verified';assert.equal(api.eligible(r,now),false);
});
test('missing or timezone-free period cannot advertise open recruitment',()=>{
  const r=record();r.application_period={};assert.equal(api.eligible(r,now),false);assert.equal(api.status(r,now),'신청 상태 확인 필요');
  r.application_period={start:'2026-10-01T00:00:00',end:'2026-10-31T18:00:00'};assert.equal(api.eligible(r,now),false);
});
test('no unapproved, rights-unknown, unsafe links, duplicate or schema fallback',()=>{
  const original=record();
  for(const patch of [{publication:'review'},{freshness:'due'},{verification_status:'unverified'},{rights:{}},{url:'javascript:alert(1)'}]){
    assert.equal(api.explore({schema_version:api.schema,notices:[{...original,...patch}]},base,now).recommendations.length,0);
  }
  assert.equal(api.explore({schema_version:api.schema,notices:[original,clone(original)]},base,now).recommendations.length,1);
  for(const data of [null,[],{}, {schema_version:api.schema,notices:{}}])assert.throws(()=>api.explore(data,base));
});
test('empty real feed never falls back to mock or legacy programs',()=>{
  const data=JSON.parse(fs.readFileSync(path.join(root,'data/support-public.json'),'utf8'));
  assert.equal(data.notices.length,0);const g=api.explore(data,base,now);assert.equal(g.recommendations.length+g.references.length,0);
});
test('inline UI wiring, safe empty/error text and additional profile history',()=>{
  const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
  const code=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];assert.doesNotThrow(()=>new vm.Script(code));
  assert.ok(html.includes('drawApprovedSupport(x);'));
  assert.ok(html.includes("fetch('./data/support-public.json')"));
  assert.ok(html.includes('승인 자료 연결 실패'));
  assert.ok(html.includes("'supportReference','supportPublic'"));
  assert.ok(html.includes('공식 신청 자격·접수 가능 확정이 아닙니다'));
  assert.ok(!html.includes('????'));
});
