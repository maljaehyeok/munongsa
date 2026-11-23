const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const finance=require('../assets/finance-mvp.js'),data=require('../data/finance-mvp.json');
const original=JSON.stringify(data);
for(const p of data.products){
  const rows=finance.factRows(p,'금리와 한도, 거치·상환, 대상은?');
  assert.equal(rows.length,5);
  assert.deepEqual(rows.map(r=>r[1]),['interest','limit','grace','repayment','target'].map(k=>p[k]));
  if(p.id!=='successor')assert.equal(finance.interestAssumption(p,p.checkedAt||data.checkedAt),null);
}
assert.deepEqual(finance.simpleInterest(50000000,150),{principal:50000000,annual:750000,monthlyAverage:62500});
assert.equal(JSON.stringify(data),original);
const scope={document:{getElementById(){return null},addEventListener(){}},setTimeout(){}};
vm.createContext(scope);vm.runInContext(fs.readFileSync(require.resolve('../assets/farm-profile.js'),'utf8'),scope);
const adapter=scope.MunongsaFarmProfile;
let c=adapter.toConversation({area:'0.1',exporterStatus:'no'});
assert.equal(c.farm_area_ha,0.1);assert.equal(c.export_activity,'no');
c=adapter.toConversation({area:'',exporterStatus:'unknown'},c);
assert.equal(c.farm_area_ha,undefined);assert.equal(c.export_activity,undefined);
assert.equal(adapter.toConversation({area:'-1'}).farm_area_ha,undefined);
assert.equal(adapter.toConversation({area:'0'}).farm_area_ha,0);
console.log('16 approved finance facts; unchanged interest; area/export adapter and clear: passed');
