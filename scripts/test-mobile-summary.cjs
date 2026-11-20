/* Isolated summary regression: no API, data, approval or profile mutation. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../assets/ui-v2.js'),'utf8')
  .replace("window.addEventListener('resize'","root.testFoldSummary=foldSummary;window.addEventListener('resize'");
let checks=0;
for(const width of [320,390,1440]){
 const chip=id=>({dataset:{conditionId:id},hidden:false});
 const profile=['farmingSituation','applicant','region','crop','residenceRegion','age','farmRegistered'].map(chip);
 const button={hidden:false,setAttribute(k,v){this[k]=v;}};
 const nodes={selectionSummary:{},profileSummary:{children:profile},browseFilterSummary:{children:[chip('search')]},selectionMore:button};
 const ctx={innerWidth:width,window:{addEventListener(){}},document:{getElementById:id=>nodes[id]}};
 ctx.globalThis=ctx;vm.runInNewContext(source,ctx);ctx.testFoldSummary();
 assert.equal(profile.find(n=>n.dataset.conditionId==='region').hidden,false);checks++;
 assert.equal(profile.find(n=>n.dataset.conditionId==='residenceRegion').hidden,false);checks++;
 const hidden=profile.filter(n=>n.hidden).length+nodes.browseFilterSummary.children.filter(n=>n.hidden).length;
 assert.equal(button.textContent,`조건 ${hidden}개 더 보기`);checks++;
 assert.equal(profile.filter(n=>n.hidden).every(n=>!['region','residenceRegion'].includes(n.dataset.conditionId)),true);checks++;
 // Removed selections must not create stale summary entries.
 profile.splice(0);nodes.browseFilterSummary.children=[];ctx.testFoldSummary();assert.equal(button.hidden,true);checks++;
}
console.log(JSON.stringify({passed:checks,failed:0}));
