const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const ctx={URL,URLSearchParams};ctx.globalThis=ctx;
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../assets/support-public.js'),'utf8'),ctx);
const url='https://www.rda.go.kr/young/custom/policy/view.do?sId=47120&cp=1';let checks=0;
function result(actual,one_of,status='verified'){
 const item={eligibility:{conditions:[{condition_id:'applicant',kind:'applicant',presence:'specified',value:{one_of},status,evidence:{url,location:'공식 신청대상',quote:'농업인 및 농업법인'}}],logic:{op:'AND',children:[{condition_id:'applicant'},{op:'UNKNOWN',children:[]}]}}};
 return ctx.MunongsaSupport.evaluate(item,{applicant:actual});
}
for(const [actual,allowed,expected] of [
 ['agricultural_corporation',['individual_farmer','agricultural_business'],'match'],
 ['agricultural_corporation',['individual_farmer'],'mismatch'],
 ['business',['individual_farmer','agricultural_business'],'check'],
 ['business',['business'],'match'],['group',['institution_group'],'match'],
 ['group',['individual_farmer','agricultural_business'],'mismatch'],
 ['individual',['individual_farmer'],'match'],['organization',['agricultural_business'],'check']]){
 const r=result(actual,allowed);assert.equal(r.conditions[0].status,expected);if(expected==='match')assert.equal(r.conditionStatus,'check');checks++;
}
assert.equal(result('agricultural_corporation',['individual_farmer'],'candidate').conditionStatus,'check');checks++;
assert.equal(result('agricultural_corporation',[{bad:'value'}]).conditions[0].status,'check');checks++;
console.log(JSON.stringify({passed:checks,failed:0}));
