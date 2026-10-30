/* Three-notice presentation + field approval boundaries. No collection or DB writes. */
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert/strict'),vm=require('vm'),cp=require('child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'work/support-details'),results=[],errors=[];
const production=!!process.env.MUNONGSA_FINANCE_BASE,started=Date.now();let server,browser;
const read=f=>JSON.parse(fs.readFileSync(path.join(root,f),'utf8'));
const pass=name=>results.push({name,passed:true});
const clone=x=>JSON.parse(JSON.stringify(x));
const source=fs.readFileSync(path.join(root,'assets/support-details.js'),'utf8');
const preview=read('work/support-details/preview.json'),snapshot=read('work/support-details/public-snapshot.json');
const stateFiles=['data/support-public.json','data/support-review.json','assets/personalization.js','assets/profile-matching.js','assets/support-public.js','assets/support-review.js','assets/finance-mvp.js','data/finance-mvp.json'];
(async()=>{try{
 for(const f of stateFiles){const old=cp.execFileSync('git',['-c','safe.directory='+root.replace(/\\/g,'/'),'show','4109ea6:'+f],{cwd:root}).toString('utf8');assert.equal(fs.readFileSync(path.join(root,f),'utf8').replace(/\r\n/g,'\n'),old.replace(/\r\n/g,'\n'),f)}
 pass('existing public data, qualification, ranking and date modules unchanged');
 const context=(hostname,search)=>{const c=vm.createContext({URLSearchParams,location:{hostname,search}});vm.runInContext(source,c);return c.MunongsaSupportDetails};
 const item=snapshot.notices.find(n=>n.id===preview.records[0].basis.id),local=context('127.0.0.1','?support-details-preview=1'),external=context('43.201.72.109','?support-details-preview=1');
 local.install(preview);assert.ok(local.get(item));external.install(preview);assert.equal(external.get(item),null);
 const neutral=context('localhost','');neutral.install(preview);assert.equal(neutral.get(item),null);
 pass('draft preview requires explicit localhost query; cannot appear on AWS');
 for(const key of ['publication','verification_status']){const n=clone(item);n[key]='review';assert.equal(local.get(n),null)}
 const metadata={...item,last_checked_at:'2026-10-31T00:00:00Z',last_collected_at:'2026-10-31T00:01:00Z'};assert.ok(local.get(metadata));
 for(const key of ['target','url','title','region']){const n=clone(item);n[key]+=' changed';assert.equal(local.get(n),null)}
 const changed=clone(item);changed.reference_application_dates.end.date='2026-11-05';assert.equal(local.get(changed),null);
 const eligibility=clone(item);eligibility.eligibility={conditions:[{kind:'age',status:'verified',presence:'specified',value:{min:25}}]};assert.equal(local.get(eligibility),null);
 pass('fact/date/eligibility changes hide stale descriptions; collection metadata preserves them');
 const approved=clone(preview);approved.preview=false;for(const r of approved.records)r.approval.state='approved';external.install(approved);assert.ok(external.get(item));
 const draft=clone(approved);draft.records[0].approval.state='review';external.install(draft);assert.equal(external.get(item),null);external.install({schema:'wrong',records:approved.records});assert.equal(external.get(item),null);
 pass('field-level approval and supported schema required independently of notice approval');
 const originalAsset=fs.readFileSync(path.join(root,'assets/support-details.json'),'utf8');
 const denied=cp.spawnSync('python',['-B','scripts/review_support_details.py','--plan','work/support-details/review-plan.json','--output','assets/support-details.json','--approve'],{cwd:root});assert.notEqual(denied.status,0);assert.equal(fs.readFileSync(path.join(root,'assets/support-details.json'),'utf8'),originalAsset);
 pass('approval CLI refuses missing human approval reference/hash without changing public asset');
 let base=process.env.MUNONGSA_FINANCE_BASE;
 if(!base){server=http.createServer((req,res)=>{const u=new URL(req.url,'http://localhost');let f=path.resolve(root,'.'+(u.pathname==='/'?'/index.html':u.pathname));if(!f.startsWith(root+path.sep)||u.pathname.startsWith('/work'))return res.writeHead(404).end();if(u.pathname==='/data/support-public.json')f=path.join(out,'public-snapshot.json');if(u.pathname==='/assets/support-details.json'&&!read('assets/support-details.json').records.length)f=path.join(out,'preview.json');try{res.writeHead(200,{'Content-Type':f.endsWith('.js')?'text/javascript':f.endsWith('.json')?'application/json':f.endsWith('.css')?'text/css':f.endsWith('.png')?'image/png':'text/html; charset=utf-8'}).end(fs.readFileSync(f))}catch{res.writeHead(404).end()}});await new Promise(ok=>server.listen(0,'127.0.0.1',ok));base='http://127.0.0.1:'+server.address().port}
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 for(const width of [1440,390]){
  const c=await browser.newContext({viewport:{width,height:1000},isMobile:width<760,hasTouch:width<760});
  await c.route('**/*',async r=>{const u=new URL(r.request().url());if(u.origin!==new URL(base).origin)return r.abort();if(u.pathname==='/favicon.ico')return r.fulfill({status:204});try{const response=await c.request.get(u.href,{timeout:20000});if(response.status()>=400)errors.push({path:u.pathname,status:response.status()});return r.fulfill({response})}catch(e){errors.push({path:u.pathname,error:e.name});return r.abort()}});
  const p=await c.newPage();p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));
  await p.goto(base+'/'+(production||read('assets/support-details.json').records.length?'':'?support-details-preview=1'),{waitUntil:'domcontentloaded'});
  await p.waitForFunction(()=>publicSupport&&publicSupport.notices.length===11&&publicSupport.notices.filter(n=>MunongsaSupportDetails.get(n)).length===3);
  await p.locator('[data-open-support]').click();assert.equal(await p.locator('[data-official-id]').count(),11);
  const before=await p.evaluate(()=>approvedRows().map(r=>({id:r.item.id,match:r.match,days:r.display.days,state:r.display.state,relevance:r.relevance})));
  const samples=[['47069','국비 20%','가점자료'],['836510','연 최대 300만원','해당자만 필요한 서류'],['8113','연간 최대 8천만원','최초 신청업체']];
  for(const [token,amount,detailText] of samples){
   const n=await p.evaluate(token=>publicSupport.notices.find(n=>n.url.includes(token)),token),card=p.locator('[data-official-id="'+n.id+'"]');
   assert.ok((await card.textContent()).includes(amount));assert.equal(await card.locator('.source-action').getAttribute('href'),n.url);
   await card.locator('.compact-open').click();const detail=p.locator('#modalSource');const text=await detail.textContent();
   for(const term of ['지원 내용과 신청 안내','신청 방법','접수처','필수 제출서류','문의처',detailText])assert.ok(text.includes(term),token+': '+term);
   assert.ok(!text.includes('신청처와 접수 방법은 공식 공고에서 확인'));assert.ok(!text.includes('필요 서류는 공식 공고에서 확인'));
   if(token==='8113'){assert.ok(text.includes('조기 종료'));assert.ok(text.includes('23:59:59'));assert.ok(text.includes('중복'))}
   if(token==='836510')assert.ok(text.includes('예상 지원액을 계산하지'));
   if(token==='47069')assert.ok(text.includes('마감 시각이 없습니다'));
   await detail.locator('.support-paperwork > summary').click();assert.ok(await detail.locator('.support-paperwork').getAttribute('open')!==null);
   await detail.locator('.support-paperwork dt').first().scrollIntoViewIfNeeded();
   await p.screenshot({path:path.join(out,(production?'aws':'local')+'-documents-'+token+'-'+width+'.png')});
   await detail.locator('.support-paperwork > summary').click();
   await detail.locator('.more-conditions').filter({hasText:'항목별 공식 근거와 확인일'}).locator('summary').click();assert.ok((await detail.textContent()).includes('2026.10.30'));
   assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
   assert.equal(await detail.evaluate(e=>e.scrollWidth>e.clientWidth+1),false,'detail horizontal overflow');
   await p.screenshot({path:path.join(out,(production?'aws':'local')+'-'+token+'-'+width+'.png')});
   await p.locator('#modal .modal-box').evaluate(e=>{e.scrollTop=0});
   await p.screenshot({path:path.join(out,(production?'aws':'local')+'-top-'+token+'-'+width+'.png')});
   const links=await detail.locator('.source-action').evaluateAll(es=>es.map(e=>e.href));assert.ok(links.includes(n.url));
   await p.locator('#closeModal').click();
  }
  pass(width+' three cards and detailed methods/documents/contact/proofs readable; official URLs correct');
  const unaffected=await p.evaluate(()=>approvedRows().filter(r=>!MunongsaSupportDetails.get(r.item)).map(r=>({id:r.item.id,html:approvedCard(r)})));
  assert.equal(unaffected.length,8);const unchanged=await p.evaluate(()=>{MunongsaSupportDetails.install(null);return approvedRows().map(r=>({id:r.item.id,html:approvedCard(r)}))});
  for(const n of unaffected)assert.equal(n.html,unchanged.find(x=>x.id===n.id).html);
  assert.deepEqual(await p.evaluate(()=>approvedRows().map(r=>({id:r.item.id,match:r.match,days:r.display.days,state:r.display.state,relevance:r.relevance}))),before);
  pass(width+' other eight cards byte-identical; comparisons, rank and D-day unchanged');
  await c.close();
 }
 assert.deepEqual(errors,[]);pass('no browser exceptions or failed first-party requests');
}catch(e){results.push({name:'execution',passed:false,error:e.stack})}finally{
 await browser?.close();if(server)await new Promise(ok=>server.close(ok));
 const report={production,checkedAt:new Date().toISOString(),elapsedSeconds:(Date.now()-started)/1000,passed:results.filter(r=>r.passed).length,failed:results.filter(r=>!r.passed).length,results,errors};
 fs.writeFileSync(path.join(out,production?'aws-result.json':'local-result.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));process.exitCode=report.failed?1:0;
}})();
