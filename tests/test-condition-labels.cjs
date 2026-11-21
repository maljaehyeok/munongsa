const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const c={};vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'../assets/support-review.js'),'utf8'),c);
function view(field,value,status='verified'){
 return c.MunongsaSupportReview.conditionViews({eligibility:{conditions:[{condition_id:'c',kind:field,status,presence:'specified',value}]}},{conditions:[{id:'c',field,status:'check'}]})[0];
}
assert.equal(view('applicant',{one_of:['individual_farmer','agricultural_business']}).fact,'개인 농업인 또는 농업법인');
assert.equal(view('applicant',{one_of:['business']}).fact,'사업자');
assert.equal(view('business_location',{location_basis:'farm_land',regions:['제주특별자치도']}).label,'영농지');
assert.equal(view('business_location',{location_basis:'business_office',regions:['제주특별자치도']}).label,'사업장 소재지');
assert.equal(view('business_location',{regions:['제주특별자치도']}).label,'소재지 기준 확인 필요');
assert.equal(view('applicant',{one_of:['agricultural_business']},'candidate').fact,'확인 필요');
console.log('조건 표시 회귀 검사 6개 통과');
