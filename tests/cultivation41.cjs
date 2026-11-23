require('./cultivation39.cjs');
const assert=require('node:assert/strict');const api=MunongsaCultivation;
assert.equal(MunongsaCropDirectory.find('논벼').name,'벼');
const rice=api.select('논벼',3,'open').find(s=>s.id==='pest');
assert.equal(new URL(rice.url).searchParams.get('kncrCode'),'FC010101');assert.ok(api.inputGuide(rice,'벼').includes('공식 도감명 논벼'));
const standard=api.select('배추',2,'open').find(s=>s.id==='soil-standard'),field=api.select('배추',2,'open').find(s=>s.id==='soil');
assert.equal(standard.url,'https://soil.rda.go.kr/sibi/cropSibiPrescript.do');assert.equal(new URL(standard.url).search,'');assert.ok(!api.inputGuide(standard,'배추').includes('선택됨'));assert.ok(standard.conditions.includes('개별 필지 처방과 다르며'));
assert.equal(field.url,'https://soil.rda.go.kr/sibi/sibiPrescript.do');assert.ok(field.connection.includes('필지·토양검정'));
assert.ok(api.select('배추',2,'open').find(s=>s.overview).url.endsWith('#sectionCrop05'));
assert.ok(api.select('배추',1,'open').find(s=>s.id==='cabbage').url.includes('cntntsNo=224491'));
for(const crop of api.crops)for(let topic=0;topic<6;topic++)for(const s of api.select(crop,topic,'open')){
 assert.ok(s.nextSteps,'every destination has concise next steps');
 if(['soil','soil-standard','water','consult','guide'].includes(s.id))assert.ok(!api.inputGuide(s,crop).includes('선택됨'));
 if(s.id==='pesticide')assert.ok(api.inputGuide(s,crop).includes('검색어 전달'));
}
console.log('흙토람 표준·필지 처방 구분, 벼 공식 별칭, 추가 선택 안내 검사 통과');
