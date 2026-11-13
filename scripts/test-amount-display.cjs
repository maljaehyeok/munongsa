const assert=require('assert/strict'),fs=require('fs'),vm=require('vm'),path=require('path');
const root={};vm.createContext(root);vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/amount-display.js'),'utf8'),root);const a=root.MunongsaAmounts;
for(const [raw,display] of [['200백만원','2억 원'],['25천원','2만 5천 원'],['10백만원','1,000만 원'],['2.5백만원','250만 원'],['총사업비 200백만원 · 농가당 최대 10백만원','총사업비 2억 원 · 농가당 최대 1,000만 원'],['기준단가 25천원/㎡','기준단가 2만 5천 원/㎡'],['100~200백만원','100~200백만원'],['25~30천원/㎡','25~30천원/㎡'],['0.0001천원','0.0001천원'],['200백만 달러','200백만 달러'],['지원금 확인 필요','지원금 확인 필요'],['한도 200백만원, 자부담 50%','한도 2억 원, 자부담 50%']])assert.equal(a.format(raw),display);
assert.equal(a.analyse('총사업비 200백만원').segments[0].role,'project_budget');assert.equal(a.analyse('기준단가 25천원/㎡').segments[0].role,'unit_price');assert.equal(a.analyse('최대 10백만원').original,'최대 10백만원');
console.log(JSON.stringify({passed:true,cases:15}));
