const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),ctx={Intl,Date,URL};
vm.runInNewContext(fs.readFileSync(path.join(root,'assets/support-review.js'),'utf8'),ctx);
const api=ctx.MunongsaSupportReview,now=new Date('2026-10-26T00:00:00Z');
const row={id:'MOCK-ONLY',title:'모의 마늘 사업',institution:'모의 기관',summary:'격리 시험',region:'전북 김제시',origin:'test',record_type:'모의',publication:'review',recommendation_eligible:false};
const feed=records=>({schema_version:api.schema,records});
test('date presentation converts UTC without inventing a time for date-only facts',()=>{
 assert.equal(api.displayDate('2026-10-29T02:45:34+00:00'),'2026.10.29 11:45');assert.equal(api.displayDate('2026-10-29'),'2026년 10월 29일');assert.equal(api.displayDate('2026-10-29T02:45:34'),'확인 필요');assert.equal(api.displayDate('2026-02-30'),'확인 필요');
});
test('friendly condition labels retain exclusion meaning and leave the engine payload untouched',()=>{
 const n={eligibility:{conditions:[{condition_id:'text_applicant',kind:'applicant',status:'verified',presence:'specified',value:{one_of:['individual_farmer']}},{condition_id:'text_residence',kind:'residence',presence:'unknown'}],logic:{op:'NOT',children:[{condition_id:'text_applicant'}]}}};
 const m={conditions:[{id:'text_applicant',field:'applicant',status:'match'},{id:'text_residence',field:'residence',status:'check'}]},before=JSON.stringify({n,m}),views=api.conditionViews(n,m);
 assert.equal(views[0].label,'제외 조건 · 신청 대상');assert.equal(views[0].status,'제외 조건에 해당');assert.equal(views[1].label,'거주 지역');assert.equal(views[1].fact,'확인 필요');assert.equal(JSON.stringify({n,m}),before);assert.ok(!JSON.stringify(views).includes('text_applicant'));
});
test('display dates are readable and use KST rather than raw ISO timestamps',()=>{
 const html=fs.readFileSync(path.join(root,'index.html'),'utf8'),start=html.indexOf('    function supportDisplayDate('),end=html.indexOf('    function supportBadges(',start),context={Intl,Date,MunongsaSupportReview:api};vm.runInNewContext(html.slice(start,end),context);
 assert.equal(context.supportDisplayDate('2026-10-28T18:00:00+00:00'),'2026.10.29 03:00');assert.equal(context.supportDisplayDate(null),'확인 필요');assert.equal(context.supportDisplayDate('2026-10-25T08:08:17+00:00 (수집일 · 원문 검증일 아님)'),'2026.10.25 17:08');
});
test('safe reference view contains only existing official RSS metadata',()=>{
 const source=JSON.parse(fs.readFileSync(path.join(root,'data/support-review.json'),'utf8')),rows=api.publicRecords(source);
 assert.ok(rows.length>0);for(const r of rows){assert.ok(r.id.startsWith('collected-'));assert.ok(r.url.startsWith('https://www.mafra.go.kr/bbs/home/'));assert.equal(r.recommendation_eligible,false);for(const k of ['summary','target','conditions','body_text','region'])assert.ok(!(k in r));}
 assert.equal(api.publicRecords(feed([{...row,id:'private',url:rows[0].url}])).length,0);
 assert.equal(api.publicRecords(feed([{...rows[0],url:'https://evil.example/x'}])).length,0);
 assert.equal(api.publicRecords(feed([rows[0],{...rows[0],id:'collected-copy'}])).length,1);
});
test('KST deadline rules distinguish unknown time, exact time and expiry',()=>{
 const n={reference_application_dates:{start:{date:'2026-10-01'},end:{date:'2026-10-30'}}};
 assert.equal(api.presentation(n,Date.parse('2026-10-29T12:00:00+09:00')).headline,'D-1 · 내일 마감');
 assert.equal(api.presentation(n,Date.parse('2026-10-30T12:00:00+09:00')).state,'unknown');
 assert.equal(api.presentation(n,Date.parse('2026-10-31T00:00:00+09:00')).state,'elapsed');
 n.reference_application_dates.end={date:'2026-10-30',time:'18:00',timezone:'Asia/Seoul'};
 assert.equal(api.presentation(n,Date.parse('2026-10-30T17:59:00+09:00')).headline,'오늘 18시 마감');
 assert.equal(api.presentation(n,Date.parse('2026-10-30T18:00:00+09:00')).state,'elapsed');
});
test('common cautions never claim eligibility or confirmed reception',()=>{
 const d=api.presentation({target:'5인 이상 법인·모임',end_date:'2026-10-30'},Date.parse('2026-10-29T00:00:00+09:00'),true);
 for(const text of ['검토중 · 참고자료','마감 임박','마감 시각 미확인','세부 자격 일부 미확인','개인 신청 전 확인 필요'])assert.ok(d.chips.some(c=>c.text===text));
 assert.equal(d.eligibility_confirmed,false);assert.equal(d.reception_confirmed,false);
 const future=api.presentation({start_date:'2026-10-30',end_date:'2026-10-31'},Date.parse('2026-10-29T12:00:00+09:00'));
 assert.equal(future.headline,'모집 예정');assert.equal(future.urgent,false);
});
test('card ordering prioritizes in-period urgency and leaves expired last',()=>{
 const now=Date.parse('2026-10-29T12:00:00+09:00'),rows=['2026-10-01','2026-10-30',null].map(end_date=>({item:{end_date},display:api.presentation({end_date},now)}));
 assert.equal(api.sortRows(rows)[0].item.end_date,'2026-10-30');assert.equal(rows.at(-1).display.state,'elapsed');
});
test('homepage reuses approved engine and safe reference view without localhost-only hiding',()=>{
 const html=fs.readFileSync(path.join(root,'index.html'),'utf8'),code=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];new vm.Script(code);
 assert.ok(code.includes('data-support-section="official"'));assert.ok(code.includes('data-support-section="review"'));assert.ok(code.includes('MunongsaSupportReview.publicRecords'));
 const fragment=code.slice(code.indexOf('    function appendSupportReviews'),code.indexOf('    function drawApprovedSupport('));assert.ok(!fragment.includes('location.hostname'));assert.ok(!fragment.includes('item.summary'));
});
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
