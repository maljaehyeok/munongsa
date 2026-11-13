const assert=require('assert/strict'),fs=require('fs'),vm=require('vm'),path=require('path');
const S=path.join(__dirname,'..');const sandbox={URL,Date,Intl,console};sandbox.globalThis=sandbox;
vm.createContext(sandbox);for(const f of ['support-public.js','selection-view.js'])vm.runInContext(fs.readFileSync(path.join(S,'assets',f),'utf8'),sandbox);
const support=sandbox.MunongsaSupport,filter=sandbox.MunongsaSelection.regionFilter;
const proof={url:'https://www.rda.go.kr/young/custom/policy/view.do?sId=999999',location:'가상 근거',quote:'가상 지역 조건'};
function item(kind='residence',regions=['경기 안산시'],basis){return {publication:'approved_reference',verification_status:'verified',region:'경기 안산시',eligibility:{conditions:[{condition_id:'geo',kind,presence:'specified',status:'verified',value:{regions,location_basis:basis},evidence:proof}],logic:{condition_id:'geo'}}};}
const profile={residenceRegion:'경기',residenceDistrict:'안산시',region:'전북',district:'김제시'};
assert.equal(support.evaluate(item(),profile).conditionStatus,'match');
assert.equal(filter(item('residence',['전북 전주시']),profile).keep,false);
assert.equal(support.evaluate(item('business_location',['전북 김제시'],'farm_land'),profile).conditionStatus,'match');
assert.equal(support.evaluate(item('business_location',['전북 김제시'],'business_site'),profile).conditionStatus,'check');
assert.equal(filter(item('residence',['전국']),{}).keep,true);
let unknown=item();unknown.eligibility.conditions[0].status='candidate';assert.equal(filter(unknown,profile).state,'check');
assert.equal(filter({publication:'approved_reference',verification_status:'verified',region:'안산시농업기술센터 접수 공고. 지역 요건 확인 필요'},profile).state,'check');
assert.equal(filter(item('residence',['전북 김제시']),{residenceRegion:'전북'}).state,'check');
let either=item('residence',['전북 전주시']);either.eligibility.conditions.push({...either.eligibility.conditions[0],condition_id:'any',value:{regions:['전국']}});either.eligibility.logic={op:'OR',children:[{condition_id:'geo'},{condition_id:'any'}]};assert.equal(filter(either,profile).keep,true);
console.log(JSON.stringify({passed:true,cases:9}));
