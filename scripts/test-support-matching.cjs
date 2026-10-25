// Run: node --test scripts/test-support-matching.cjs (no external packages).
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const context={};
vm.runInNewContext(fs.readFileSync(path.join(root,'assets/profile-matching.js'),'utf8'),context);
const matching=context.MunongsaMatching;
const catalog=JSON.parse(fs.readFileSync(path.join(root,'data/smart-agriculture-catalog.json'),'utf8'));
const programs=catalog.supportPrograms;
vm.runInNewContext(fs.readFileSync(path.join(root,'index.html'),'utf8').match(/function matches\(p,x\)\{[\s\S]*?\n    \}/)[0],context);
const base={applicant:'individual',age:'32',experience:'planned',region:'전북',district:'김제시',crop:'garlic',cultivation:'openfield'};
const evaluate=(id,changes={})=>matching.evaluate('program',programs.find(p=>p.id===id),{...base,...changes});
const profiles=[
  ['blank',{applicant:'all',age:'',experience:'unknown',region:'all',district:'all',crop:'all',cultivation:'all'}],
  ['base',{}],['other-region',{region:'전남',district:'나주시'}],
  ...['17','18','39','40',''].map(age=>['age-'+(age||'missing'),{age}]),
  ...['planned','under1','1to3','over3'].map(experience=>['stage-'+experience,{experience}]),
  ['green-onion',{crop:'greenonion'}],['rice',{crop:'rice'}],['apple',{crop:'apple'}],
  ['young',{applicant:'young'}],['young-age-missing',{applicant:'young',age:''}],
  ['organization',{applicant:'organization',age:'60',experience:'over3',district:'고창군',crop:'cabbage'}],
  ['municipality',{applicant:'municipality',district:'고창군',crop:'cabbage'}],
  ['facility',{cultivation:'facility'}],['invalid-age',{age:'-10'}],
  ['conflicting',{applicant:'prospective',experience:'over3'}],
  ['area',{area:'1000'}],['budget',{budget:'1'}]
];
for(const [name,changes] of profiles)test('shared filter/rank: '+name,()=>{
  const profile={...base,...changes};
  for(const row of matching.rank('program',programs,profile)) {
    assert.equal(context.matches(row.item,profile),row.match.conditionStatus!=='mismatch');
    assert.equal(row.match.score,row.match.conditions.reduce((sum,c)=>sum+(c.status==='match'?c.weight:0),0));
    assert.ok(row.match.conditions.filter(c=>c.status!=='match').every(c=>c.weight===0));
  }
});
test('personal and young applicants use identical age/career rules',()=>{
  for(const age of ['17','18','32','39','40','']) {
    const a=evaluate('youth',{age,applicant:'individual'}),b=evaluate('youth',{age,applicant:'young'});
    assert.deepEqual(JSON.parse(JSON.stringify(a)),JSON.parse(JSON.stringify(b)));
  }
});
test('recorded youth age boundaries; missing/invalid age is unknown',()=>{
  for(const age of ['17','40'])assert.equal(evaluate('youth',{age}).conditionStatus,'mismatch');
  for(const age of ['18','39'])assert.equal(evaluate('youth',{age}).different.length,0);
  for(const age of ['','-10','abc','18.5'])assert.ok(evaluate('youth',{age}).unknown.some(s=>s.includes('연령')));
});
test('general programs do not infer planned-only from audience',()=>{
  for(const id of ['direct','insurance']) {
    const scores=['planned','under1','1to3','over3'].map(experience=>{
      const result=evaluate(id,{experience});
      assert.equal(result.different.length,0);
      assert.ok(result.unknown.some(s=>s.includes('영농 단계 조건 미기록')));
      return result.score;
    });
    assert.equal(new Set(scores).size,1);
  }
});
test('career limit is used only where explicitly flagged',()=>{
  assert.equal(evaluate('youth',{experience:'over3'}).conditionStatus,'mismatch');
  for(const experience of ['planned','under1','1to3'])assert.equal(evaluate('youth',{experience}).different.length,0);
});
test('conflicting personal profile requires review on general programs',()=>{
  assert.ok(evaluate('direct',{applicant:'prospective',experience:'over3'}).unknown.some(s=>s.includes('상충')));
});
test('missing age range is never invented',()=>{
  const youth=programs.find(p=>p.id==='youth');
  const result=matching.evaluate('program',{...youth,eligibility:''},base);
  assert.ok(result.unknown.includes('연령 범위 미기록'));
});
test('missing audiences does not throw or award audience points',()=>{
  const result=matching.evaluate('program',{id:'missing'},base);
  assert.equal(result.conditionStatus,'check');assert.equal(result.score,0);
});
test('three states distinguish recorded match, missing input, explicit conflict',()=>{
  const row={id:'fixture',audiences:['individual'],regions:['all'],cultivationModes:['both']};
  const input={...base,experience:'unknown',crop:'all'};
  assert.equal(matching.evaluate('program',row,input).conditionStatus,'match');
  assert.equal(matching.evaluate('program',row,{...input,applicant:'all'}).conditionStatus,'check');
  assert.equal(matching.evaluate('program',row,{...input,applicant:'municipality'}).conditionStatus,'mismatch');
});
test('verification and application state are not eligibility or relevance bonuses',()=>{
  const row=programs[0];
  const a=matching.evaluate('program',row,base),b=matching.evaluate('program',{...row,applicationStatus:'open',factVerificationStatus:'source_checked'},base);
  assert.equal(a.score,b.score);assert.equal(a.conditionStatus,b.conditionStatus);
});
test('entity types, regions and crops use explicit recorded conflicts',()=>{
  assert.equal(evaluate('youth',{applicant:'organization'}).conditionStatus,'mismatch');
  assert.equal(evaluate('youth',{applicant:'municipality'}).conditionStatus,'mismatch');
  const district={applicant:'municipality',region:'전북',district:'고창군',crop:'cabbage'};
  assert.equal(evaluate('district',district).different.length,0);
  assert.ok(evaluate('district',{...district,region:'전남'}).different.some(s=>s.includes('시·도')));
  assert.ok(evaluate('district',{...district,district:'완주군'}).different.some(s=>s.includes('시·군·구')));
  assert.ok(evaluate('insurance',{crop:'greenonion'}).different.some(s=>s.includes('작물')));
  assert.ok(evaluate('direct',{crop:'greenonion'}).unknown.some(s=>s.includes('작물')));
});
