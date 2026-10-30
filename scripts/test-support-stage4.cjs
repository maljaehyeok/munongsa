/* Eight appended explanations only. Earlier three approvals must remain byte-equivalent. */
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert/strict'),vm=require('vm'),cp=require('child_process'),crypto=require('crypto');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'work/support-details'),results=[],errors=[],start=Date.now();let browser,server;
const read=f=>JSON.parse(fs.readFileSync(path.join(root,f),'utf8'));
const snapshot=read('work/support-details/stage4-public-snapshot.json'),plan=read('work/support-details/stage4-review-plan.json'),preview=read('work/support-details/stage4-preview.json');
const old=JSON.parse(cp.execFileSync('git',['-c','safe.directory='+root.replace(/\\/g,'/'),'show','9dc7e74:assets/support-details.json'],{cwd:root}).toString('utf8'));
const production=!!process.env.MUNONGSA_FINANCE_BASE,pass=name=>results.push({name,passed:true});
const localAsset=()=>read('assets/support-details.json'),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{try{
 const git=f=>cp.execFileSync('git',['-c','safe.directory='+root.replace(/\\/g,'/'),'show','9dc7e74:'+f],{cwd:root}).toString('utf8').replace(/\r\n/g,'\n');
 for(const f of ['index.html','assets/user-display.js','assets/support-public.js','assets/support-review.js','assets/personalization.js','assets/profile-matching.js','data/support-public.json','data/support-review.json','assets/finance-mvp.js','data/finance-mvp.json','assets/cultivation-mvp.js'])assert.equal(fs.readFileSync(path.join(root,f),'utf8').replace(/\r\n/g,'\n'),git(f),f);
 assert.deepEqual(preview.records.slice(0,3),old.records);assert.deepEqual(localAsset().records.slice(0,3),old.records);
 pass('original three descriptions/approval histories and all comparison/data/date modules preserved');
 const c=vm.createContext({URLSearchParams,location:{hostname:'127.0.0.1',search:'?support-details-preview=1'}});vm.runInContext(fs.readFileSync(path.join(root,'assets/support-details.js'),'utf8'),c);c.MunongsaSupportDetails.install(preview);
 assert.equal(snapshot.notices.filter(n=>c.MunongsaSupportDetails.get(n)).length,11);
 const ext=vm.createContext({URLSearchParams,location:{hostname:'43.201.72.109',search:''}});vm.runInContext(fs.readFileSync(path.join(root,'assets/support-details.js'),'utf8'),ext);ext.MunongsaSupportDetails.install(preview);assert.equal(snapshot.notices.filter(n=>ext.MunongsaSupportDetails.get(n)).length,0);
 pass('merged preview retains old approvals and eight drafts; draft bundle blocked outside localhost');
 const raw=fs.readFileSync(path.join(root,'assets/support-details.json')),hash=sha(raw),planHash=sha(fs.readFileSync(path.join(out,'stage4-review-plan.json')));
 const denied=cp.spawnSync('python',['-B','scripts/review_support_details.py','--plan','work/support-details/stage4-review-plan.json','--output','assets/support-details.json','--approve','--reviewer','test','--approval-reference','test','--approved-plan-sha256',planHash,'--preserve-sha256','incorrect'],{cwd:root});assert.notEqual(denied.status,0);assert.equal(sha(fs.readFileSync(path.join(root,'assets/support-details.json'))),hash);
 pass('append approval refuses incorrect preservation hash; existing public asset untouched');
 for(const r of plan.records){assert.ok(r.fields.summary);for(const f of Object.values(r.fields)){assert.ok(f.evidence.url.startsWith('https://'));assert.ok(f.evidence.location);assert.ok(f.evidence.checked_at)}}
 const vietnam=plan.records.find(r=>r.basis.url.includes('8210'));assert.equal(vietnam.basis.dates.end,null);assert.ok(vietnam.fields.unconfirmed.value.join(' ').includes('확정 건수에 포함하지'));
 pass('eight source-backed summaries; Vietnam has no invented deadline or definite-open classification');
 let base=process.env.MUNONGSA_FINANCE_BASE;
 if(!base){server=http.createServer((req,res)=>{const u=new URL(req.url,'http://localhost');let f=path.resolve(root,'.'+(u.pathname==='/'?'/index.html':u.pathname));if(!f.startsWith(root+path.sep)||u.pathname.startsWith('/work'))return res.writeHead(404).end();if(u.pathname==='/data/support-public.json')f=path.join(out,'stage4-public-snapshot.json');if(u.pathname==='/assets/support-details.json'&&localAsset().records.length===3)f=path.join(out,'stage4-preview.json');try{res.writeHead(200,{'Content-Type':f.endsWith('.js')?'text/javascript':f.endsWith('.json')?'application/json':f.endsWith('.css')?'text/css':f.endsWith('.png')?'image/png':'text/html; charset=utf-8'}).end(fs.readFileSync(f))}catch{res.writeHead(404).end()}});await new Promise(ok=>server.listen(0,'127.0.0.1',ok));base='http://127.0.0.1:'+server.address().port}
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 for(const width of [1440,390]){
  const ctx=await browser.newContext({viewport:{width,height:1000},isMobile:width<760,hasTouch:width<760});
  await ctx.route('**/*',async r=>{const u=new URL(r.request().url());if(u.origin!==new URL(base).origin)return r.abort();if(u.pathname==='/favicon.ico')return r.fulfill({status:204});try{const response=await ctx.request.get(u.href,{timeout:20000});if(response.status()>=400)errors.push({path:u.pathname,status:response.status()});return r.fulfill({response})}catch(e){errors.push({path:u.pathname,error:e.name});return r.abort()}});
  const p=await ctx.newPage();p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));
  await p.goto(base+'/'+(production||localAsset().records.length===11?'':'?support-details-preview=1'),{waitUntil:'domcontentloaded'});
  await p.waitForFunction(()=>publicSupport?.notices?.filter(n=>MunongsaSupportDetails.get(n)).length===11);
  await p.locator('[data-open-support]').click();assert.equal(await p.locator('[data-official-id]').count(),11);
  const before=await p.evaluate(()=>approvedRows().map(r=>({id:r.item.id,match:r.match,state:r.display.state,days:r.display.days,relevance:r.relevance})));
  for(const r of plan.records){
   const card=p.locator('[data-official-id="'+r.basis.id+'"]');assert.ok((await card.textContent()).includes(r.fields.summary.value));if(r.fields.funding)assert.ok((await card.textContent()).includes(r.fields.funding.value));
   assert.equal(await card.locator('.source-action').getAttribute('href'),r.basis.url);await card.locator('.compact-open').click();
   const box=p.locator('#modalSource'),text=await box.textContent();
   for(const k of ['method','office','contact'])if(r.fields[k])assert.ok(text.includes(r.fields[k].value),r.basis.title+': '+k);
   assert.ok(text.includes('아직 확인되지 않은 사항'));assert.ok(text.includes('항목별 공식 근거와 확인일'));
   if(r.fields.documents_required){await box.locator('.support-paperwork > summary').click();for(const d of r.fields.documents_required.value)assert.ok((await box.textContent()).includes(d));await box.locator('.support-paperwork dt').first().scrollIntoViewIfNeeded();}
   else{assert.equal(await box.locator('.support-paperwork').count(),0);assert.ok(r.fields.unconfirmed.value.join(' ').includes('서류'));}
   assert.equal(await box.evaluate(e=>e.scrollWidth>e.clientWidth+1),false);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
   if(['371110','8173','671793','8232'].some(token=>r.basis.url.includes(token)))await p.screenshot({path:path.join(out,'stage4-'+(production?'aws':'local')+'-'+new URL(r.basis.url).hostname+'-'+plan.records.indexOf(r)+'-'+width+'.png')});
   await p.locator('#closeModal').click();
  }
  pass(width+' eight cards/details, separate required/conditional documents, partial-information reasons and official links');
  await p.evaluate(old=>MunongsaSupportDetails.install(old),old);const oldCards=await p.evaluate(ids=>ids.map(id=>approvedCard(approvedRows().find(r=>r.item.id===id))),old.records.map(r=>r.basis.id));
  await p.evaluate(doc=>MunongsaSupportDetails.install(doc),production||localAsset().records.length===11?localAsset():preview);
  assert.deepEqual(await p.evaluate(ids=>ids.map(id=>approvedCard(approvedRows().find(r=>r.item.id===id))),old.records.map(r=>r.basis.id)),oldCards);
  assert.deepEqual(await p.evaluate(()=>approvedRows().map(r=>({id:r.item.id,match:r.match,state:r.display.state,days:r.display.days,relevance:r.relevance}))),before);
  pass(width+' old three cards unchanged and all eleven comparisons/ranking/D-day preserved');
  await ctx.close();
 }
 assert.deepEqual(errors,[]);pass('no browser exceptions or failed first-party requests');
}catch(e){results.push({name:'execution',passed:false,error:e.stack})}finally{
 await browser?.close();if(server)await new Promise(ok=>server.close(ok));
 const report={production,checkedAt:new Date().toISOString(),elapsedSeconds:(Date.now()-start)/1000,passed:results.filter(x=>x.passed).length,failed:results.filter(x=>!x.passed).length,results,errors};
 fs.writeFileSync(path.join(out,production?'stage4-aws-result.json':'stage4-local-result.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));process.exitCode=report.failed?1:0;
}})();
