const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),ctx={Intl,Date};
vm.runInNewContext(fs.readFileSync(path.join(root,'assets/support-review.js'),'utf8'),ctx);
const api=ctx.MunongsaSupportReview,now=new Date('2026-10-26T00:00:00Z');
const row={id:'MOCK-ONLY',title:'모의 마늘 사업',institution:'모의 기관',summary:'격리 시험',region:'전북 김제시',origin:'test',record_type:'모의',publication:'review',recommendation_eligible:false};
const feed=records=>({schema_version:api.schema,records});
test('pending reference display never requires or grants approval',()=>{
 const source=feed([row]);assert.equal(api.browse(source).length,1);assert.equal(source.records[0].publication,'review');assert.equal(source.records[0].recommendation_eligible,false);
});
test('elapsed and unknown are separate; old open label never becomes currently open',()=>{
 assert.equal(api.label({...row,end_date:'2026-07-10'},now).key,'elapsed');
 assert.ok(api.label({...row,start_date:'2026-10-01',end_date:'2026-10-31',recorded_status:'open_verified'},now).text.includes('현재 접수 가능 여부 미확인'));
 assert.equal(api.label({...row,known_closed:true},now).key,'elapsed');
 assert.equal(api.label(row,now).key,'unknown');
});
test('status filters and all-word keyword search work',()=>{
 const source=feed([row,{...row,id:'second',title:'지난 모의 공고',known_closed:true}]);
 assert.equal(api.browse(source,'마늘 김제').length,1);
 assert.equal(api.browse(source,'해당없는검색어').length,0);
 assert.equal(api.browse(source,'','elapsed',now).length,1);
 assert.equal(api.browse(source,'','unknown',now).length,1);
});
test('bad schema and duplicate IDs are safely handled',()=>{
 for(const source of [null,[],{},feed({})])assert.throws(()=>api.browse(source));
 assert.equal(api.browse(feed([row,row])).length,1);
 assert.equal(api.browse(feed([{...row,recommendation_eligible:true}])).length,0);
});
test('actual feed exposes no internal DB/reviewer/raw-body fields',()=>{
 const source=JSON.parse(fs.readFileSync(path.join(root,'data/support-review.json'),'utf8'));
 assert.ok(api.browse(source).length>=4);
 for(const r of source.records){assert.equal(r.recommendation_eligible,false);assert.equal(r.publication,'review');for(const key of ['reviewer','approved_by','hints_json','conditions','raw_response','body_text'])assert.ok(!(key in r));}
});
test('actual UI renders references even when approved feed is empty or unavailable',()=>{
 const html=fs.readFileSync(path.join(root,'index.html'),'utf8'),code=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];new vm.Script(code);
 const start=code.indexOf('    function reviewCard('),end=code.indexOf('    function openSupportReview(');
 const nodes={supportSearch:{value:''},supportStateFilter:{value:'all'}};
 const local={MunongsaSupportReview:api,document:{getElementById:id=>nodes[id]},supportReview:feed([row]),supportReviewError:false,message:{},count:{textContent:''},cards:{html:'',insertAdjacentHTML(_,v){this.html+=v}},esc:v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
 vm.runInNewContext(code.slice(start,end),local);
 local.drawApprovedSupportOnly=()=>{local.cards.html='approved feed unavailable';};
 local.drawApprovedSupport({});
 assert.ok(local.cards.html.includes('모의 마늘 사업'));assert.ok(local.cards.html.includes('정식 승인 미완료'));assert.ok(local.cards.html.includes('신청 추천 아님'));
 local.supportReview=feed([{...row,title:'<script>unsafe</script>'}]);local.drawApprovedSupport({});assert.ok(local.cards.html.includes('&lt;script&gt;'));assert.ok(!local.cards.html.includes('<script>unsafe'));
});
