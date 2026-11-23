/* Public scheme alias only; no review workbook or added financial facts. */
const assert=require('node:assert/strict');
const finance=require('../assets/finance-mvp.js');
const data=require('../data/finance-mvp.json');
assert.deepEqual(finance.filter(data.products,'농신보').map(p=>p.id),['guarantee']);
assert.ok(finance.filter(data.products,'귀농').some(p=>p.id==='return-farmer'));
assert.equal(finance.filter(data.products,'없는가상상품').length,0);
assert.deepEqual(finance.simpleInterest(50000000,150),{principal:50000000,annual:750000,monthlyAverage:62500});
console.log('public finance alias and calculation: passed');
