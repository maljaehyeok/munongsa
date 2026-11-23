/* Discovery restoration must never write the farming profile or alter official links. */
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),cp=require('child_process');
const code=fs.readFileSync('assets/cultivation-mvp.js','utf8'),directory=fs.readFileSync('assets/crop-directory.js','utf8');
const storage=new Map(),context=()=>{const c={sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},readProfile:()=>({crop:'마늘'})};vm.createContext(c);vm.runInContext(directory,c);vm.runInContext(code,c);return c.MunongsaCultivation};
let m=context();m.explore('키위',3);const original=m.render('마늘',{crop:'마늘'});assert.match(original,/선택 작물 · 참다래/);
m=context();assert.match(m.render('마늘',{crop:'마늘'}),/선택 작물 · 참다래/);assert.match(m.render('마늘',{crop:'마늘'}),/data-cultivation-topic="3" aria-pressed="true"/);
m.explore('',0);m=context();assert.doesNotMatch(m.render('마늘',{crop:'마늘'}),/선택 작물 · 마늘/);
m.explore('오이',2);m.render('벼',{crop:'벼'});m=context();assert.doesNotMatch(m.render('벼',{crop:'벼'}),/선택 작물 · 오이/);
m.explore('배추',1);m.resetSelection();m=context();assert.doesNotMatch(m.render('',{}),/선택 작물 · 배추/);
storage.set('munongsa.cultivation-discovery.v1','{"explorationCrop":"<script>","explorationProfileCrop":"마늘"}');m=context();assert.doesNotMatch(m.render('',{}),/<script>/);
const base=cp.execFileSync('git',['show','c3645e7:assets/cultivation-mvp.js'],{encoding:'utf8'}),old={};vm.createContext(old);vm.runInContext(directory,old);vm.runInContext(base,old);
assert.equal(JSON.stringify(m.sources),JSON.stringify(old.MunongsaCultivation.sources));
for(const crop of ['고추','오이','배추','벼','참다래'])for(const topic of [0,2,3])assert.equal(JSON.stringify(m.select(crop,topic,'all')),JSON.stringify(old.MunongsaCultivation.select(crop,topic,'all')));
assert.doesNotMatch(code,/자주 찾는 작물/);assert.match(original,/검색 조건 지우기/);
console.log('PASS: restoration, topic, explicit clear, profile change, reset, untrusted state, unchanged official mappings, neutral copy');
