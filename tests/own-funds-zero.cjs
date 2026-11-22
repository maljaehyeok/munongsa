const assert=require('node:assert/strict');
require('../assets/amount-display.js');
const parse=globalThis.MunongsaAmounts.parseInput;
for(const text of ['0','0원','0만원','0 만원','0.0만원']){
 assert.equal(parse(text,'man',true),0,text);
 assert.ok(Number.isNaN(parse(text)),`positive-only field: ${text}`);
}
for(const text of ['-0원','-1만원','0원원','0abc','1,00만원','Infinity','1e3원'])assert.ok(Number.isNaN(parse(text,'man',true)),text);
assert.equal(parse('','man',true),null);
assert.equal(parse('3,000만원','man',true),30000000);
assert.equal(parse('30,000,000원','man',true),30000000);
assert.equal(parse('1.5억','man',true),150000000);
console.log('보유 자금 0 입력·단위 환산·비정상 입력 검사 통과');
