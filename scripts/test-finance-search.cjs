/* Approved public data only; search never changes facts or eligibility. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const finance=require('../assets/finance-mvp.js');
const data=require('../data/finance-mvp.json');
const before=JSON.stringify(data);
assert.ok(finance.filter(data.products,'귀농 주택').some(p=>p.id==='return-farmer'));
assert.deepEqual(finance.filter(data.products,'농신보').map(p=>p.id),['guarantee']);
assert.equal(finance.filter(data.products,'농신보 주택').length,0);
assert.equal(finance.filter(data.products,'농지','대출 보증').length,0);
assert.equal(finance.filter(data.products,'   ','all').length,data.products.length);
assert.ok(finance.filter(data.products,'귀농','주택 마련').some(p=>p.id==='return-farmer'));
assert.equal(JSON.stringify(data),before);
const engine={evaluate:()=>({conditions:[{status:'match',reason:'approved field'}]})};
global.MunongsaSupport=engine;
assert.match(finance.card(data.products.find(p=>p.id==='return-farmer'),{}),/notice-chip match/);
global.MunongsaSupport={evaluate:()=>({conditions:[{status:'mismatch',reason:'approved field'}]})};
assert.match(finance.card(data.products.find(p=>p.id==='return-farmer'),{}),/notice-chip mismatch/);
assert.deepEqual(finance.simpleInterest(50000000,150),{principal:50000000,annual:750000,monthlyAverage:62500});
assert.equal(finance.simpleInterest(-1,150),null);
const html=fs.readFileSync(require.resolve('../index.html'),'utf8');
assert.ok(!html.includes('id="profileAvatar"'));
assert.ok(html.includes('id="financeSearchReset"'));
assert.ok(!html.includes("fetch('./data/finance-products.json')"));
assert.equal(data.products.length,16);
assert.equal(data.products.slice(4).filter(p=>p.approvalId==='operator-finance-12-20261124').length,12);
for(const p of data.products.slice(4)){
 assert.ok(p.source.url.startsWith('https://'));
 assert.ok(p.unknowns.length&&p.comparisonNote);
 assert.equal(finance.interestAssumption(p,p.checkedAt),null);
 assert.ok(finance.discoveryQuery(data.products,p.title));
 assert.ok(finance.filter(data.products,finance.discoveryQuery(data.products,p.title)).some(v=>v.id===p.id));
 assert.ok(finance.applicationGuide(p).includes('https://'));
}
console.log('approved finance search, semantic states, interest and private boundary: passed');
