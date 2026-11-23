const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
global.document={addEventListener(){}};
for(const file of ['crop-directory','cultivation-mvp'])vm.runInThisContext(fs.readFileSync('assets/'+file+'.js','utf8'));
const guide=MunongsaCultivation;
assert.equal(guide.crops.length,67);assert.equal(guide.topics.length,6);
for(const crop of guide.crops)for(let topic=0;topic<6;topic++){
 const rows=guide.select(crop,topic,'open');assert.ok(rows.length,`${crop}/${topic}`);
 for(const r of rows){assert.equal(new URL(r.url).protocol,'https:');assert.ok(r.connection&&r.button);assert.ok(!r.crop||r.crop===crop);}
}
const pest=guide.select('오이',3,'open').find(s=>s.id==='pest');
assert.equal(new URL(pest.url).searchParams.get('kncrCode'),'VC010901');assert.ok(pest.url.includes('VegitablesPhotoListR'));
for(const crop of guide.crops){const s=guide.select(crop,3,'open').find(s=>s.id==='pesticide');assert.equal(new URL(s.url).searchParams.get('sAgCropsNm1'),crop);assert.ok(s.searchCrop);}
for(const [crop,topic,hash] of [['고추',1,'#sectionCrop02'],['오이',3,'#sectionCrop06'],['벼',2,'#sectionCrop05'],['딸기',4,'#sectionCrop05']]){
 const s=guide.select(crop,topic,'open').find(s=>s.overview);assert.equal(new URL(s.url).hash,hash);assert.ok(s.url.includes('stdPrdlstCode='));
}
assert.equal(guide.select('난류',3,'open').find(s=>s.id==='pest').crop,undefined,'unmapped official crop name must require selection');
assert.ok(guide.select('고추',1,'open').some(s=>s.id==='pepper'&&s.url.includes('cntntsNo=30600')),'existing precise link preserved');
assert.ok(!guide.select('오이',2,'facility').some(s=>s.id==='water'),'open-field prescription must not apply to facilities');
for(const topic of [0,1,4])assert.ok(guide.select('난류',topic,'open').some(s=>s.id==='guide'),'unmapped crop keeps official fallback');
const direct=guide.crops.filter(c=>guide.select(c,3,'open').find(s=>s.id==='pest')?.crop).length;
guide.choose(3);const html=guide.render('방울토마토');assert.ok(html.includes('토마토 등록농약 검색')&&html.includes('병해충 도감 보기'));assert.ok(!html.includes('방울토마토 등록농약 검색'));
console.log(JSON.stringify({crops:67,topics:6,crop_topic_combinations:402,pest_direct_crops:direct,pesticide_crop_queries:67,existing_exact_materials_preserved:true}));
