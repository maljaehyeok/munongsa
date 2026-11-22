const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const root={URL};vm.createContext(root);vm.runInContext(fs.readFileSync('assets/support-public.js','utf8'),root);
let checks=0;
for(const [city,province] of [['화성시','경기'],['산청군','경남'],['함안군','경남']]){
 const c={condition_id:'r',kind:'residence',presence:'specified',status:'verified',value:{regions:[city]},evidence:{url:'https://www.rda.go.kr/young/custom/policy/view.do?sId=1',location:'공식 문장',fact_confirmed:true}};
 const item={eligibility:{conditions:[c],logic:{condition_id:'r'}}};
 for(const [profile,expected] of [[{residenceRegion:'제주'},'mismatch'],[{residenceRegion:province},'check'],[{residenceRegion:province,residenceDistrict:city},'match']]){
  assert.equal(root.MunongsaSupport.evaluate(item,profile).conditionStatus,expected);checks++;
 }
 c.kind='business_location';c.value.location_basis='farm_land';
 assert.equal(root.MunongsaSupport.evaluate(item,{residenceRegion:province,residenceDistrict:city,region:'제주'}).conditionStatus,'mismatch');checks++;
}
console.log(JSON.stringify({officialMunicipalityChecks:checks,passed:true}));
