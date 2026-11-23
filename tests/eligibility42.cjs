const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
global.document={addEventListener:()=>{},getElementById:()=>null};
for(const f of ['support-public','support-review','notice-review','personalization','selection-view','user-display','amount-display','support-details','application-journey'])vm.runInThisContext(fs.readFileSync('assets/'+f+'.js','utf8'));
const proof={url:'https://www.rda.go.kr/young/custom/policy/view.do?sId=47142',location:'가상 회귀검사용 근거',fact_confirmed:true};
const c={condition_id:'registration',kind:'farm_registration',presence:'specified',status:'verified',value:{registered:true},evidence:proof};
const item={id:'synthetic42',title:'가상 검증',url:proof.url,eligibility:{conditions:[c],logic:{condition_id:c.condition_id}}};
const row=(profile,category,notice=item)=>({item:notice,comparisonItem:notice,match:MunongsaSupport.evaluate(notice,profile),decision:{category}});
const mismatch=row({farmRegistered:'no'},'C');
assert.equal(mismatch.match.conditionStatus,'mismatch');
assert.match(MunongsaDisplay.comparisonSummary(mismatch),/필수조건 불일치/);
assert.match(MunongsaDisplay.comparisonSummary(mismatch),/농업경영체 등록 불일치/);
assert.match(MunongsaDisplay.comparisonSummary(row({farmRegistered:'yes'},'B')),/일치 1개/);
assert.match(MunongsaDisplay.comparisonSummary(row({},'B')),/추가 확인 1개/);
const none={...item,eligibility:{conditions:[],logic:{op:'UNKNOWN',children:[]}}};
assert.match(MunongsaDisplay.comparisonSummary(row({},'D',none)),/자격정보 부족/);
const bad={...item,eligibility:{conditions:[{...c,status:'pending'}],logic:{condition_id:c.condition_id}}};
assert.doesNotMatch(MunongsaDisplay.comparisonSummary(row({farmRegistered:'no'},'B',bad)),/등록 불일치/);
const or={...item,eligibility:{conditions:[c,{...c,condition_id:'optional',value:{registered:false}}],logic:{op:'OR',children:[{condition_id:c.condition_id},{condition_id:'optional'}]}}};
assert.equal(row({farmRegistered:'no'},'B',or).match.conditionStatus,'match');
assert.doesNotMatch(MunongsaDisplay.comparisonSummary(row({farmRegistered:'no'},'B',or)),/필수조건 불일치/);
assert.match(MunongsaDisplay.recruitment(item,{state:'standing'}),/상시·예산/);
assert.match(MunongsaDisplay.recruitment(item,{state:'unknown'}),/확인 필요/);
const before=JSON.stringify(mismatch);MunongsaDisplay.comparisonSummary(mismatch);assert.equal(JSON.stringify(mismatch),before);
if(process.argv[2]){
 const feed=JSON.parse(fs.readFileSync(process.argv[2]+'/feed.json','utf8')),details=JSON.parse(fs.readFileSync(process.argv[2]+'/details.json','utf8'));MunongsaSupportDetails.install(details);
 const rows=MunongsaPersonalization.support(feed,{});assert.equal(rows.length,126);
 for(const r of rows){const summary=MunongsaDisplay.comparisonSummary(r);assert.ok(summary.includes('신청 자격 확정은 아닙니다'));assert.ok(!summary.includes('undefined'));}
 assert.equal(rows.filter(r=>MunongsaSupportDetails.get(r.sourceItem)).length,12);
 assert.equal(rows.filter(r=>MunongsaSupportDetails.availability(r.sourceItem).state==='scope_review').length,7);
 console.log(JSON.stringify({public:rows.length,details_visible:12,details_blocked:7}));
}
console.log('자격 비교 요약·부분 일치·미승인 차단·OR 조건·상시 표시 검사 통과');
