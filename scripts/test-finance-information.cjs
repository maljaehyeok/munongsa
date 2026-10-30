/* Application guidance only; comparison and prior financial facts stay intact. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),http=require('http'),vm=require('vm'),cp=require('child_process');
const {chromium}=require('playwright'),root=path.resolve(__dirname,'..'),out=path.join(root,'work/finance-information'),results=[],errors=[],started=Date.now();let browser,server;
fs.mkdirSync(out,{recursive:true});const production=!!process.env.MUNONGSA_FINANCE_BASE,pass=name=>results.push({name,passed:true}),clean=s=>s.replace(/\r\n/g,'\n');
const git=f=>cp.execFileSync('git',['-c','safe.directory='+root.replace(/\\/g,'/'),'show','a79c08d:'+f],{cwd:root}).toString('utf8');
const data=JSON.parse(fs.readFileSync(path.join(root,'data/finance-mvp.json'),'utf8'));
(async()=>{try{
 for(const f of ['assets/support-public.js','assets/support-review.js','assets/support-details.js','assets/support-details.json','assets/user-display.js','assets/personalization.js','assets/profile-matching.js','assets/cultivation-mvp.js','data/support-public.json','data/support-review.json','assets/black-minimal.css'])assert.equal(clean(fs.readFileSync(path.join(root,f),'utf8')),clean(git(f)),f+' changed');
 const old=vm.createContext({URL}),now=vm.createContext({URL});for(const c of [old,now])vm.runInContext(fs.readFileSync(path.join(root,'assets/support-public.js'),'utf8'),c);vm.runInContext(git('assets/finance-mvp.js'),old);vm.runInContext(fs.readFileSync(path.join(root,'assets/finance-mvp.js'),'utf8'),now);
 for(const f of ['compare','filter','rank','date'])assert.equal(clean(now.MunongsaFinance[f].toString()),clean(old.MunongsaFinance[f].toString()),f+' modified');
 const prior=JSON.parse(git('data/finance-mvp.json')),stripped=structuredClone(data);
 for(const p of stripped.products)delete p.applicationGuide;assert.deepEqual(stripped,prior);
 for(const p of data.products){const g=p.applicationGuide;assert.equal(g.checkedAt,'2026-10-30');assert.ok(g.source.url.startsWith('https://'));assert.ok(g.source.location);assert.ok(g.documentNote);assert.ok(!/[\u4e00-\u9fff]/.test(JSON.stringify(g)))}
 assert.deepEqual(data.products.find(p=>p.id==='farmland').applicationGuide.documents,[]);
 pass('finance facts and comparison/filter/ranking/date functions unchanged; support/cultivation preserved');
 let base=process.env.MUNONGSA_FINANCE_BASE;
 if(!base){server=http.createServer((req,res)=>{const u=new URL(req.url,'http://localhost'),f=path.resolve(root,'.'+(u.pathname==='/'?'/index.html':u.pathname));if(!f.startsWith(root+path.sep)||u.pathname.startsWith('/work'))return res.writeHead(404).end();try{res.writeHead(200,{'Content-Type':f.endsWith('.js')?'text/javascript':f.endsWith('.json')?'application/json':f.endsWith('.css')?'text/css':f.endsWith('.png')?'image/png':'text/html; charset=utf-8'}).end(fs.readFileSync(f))}catch{res.writeHead(404).end()}});await new Promise(ok=>server.listen(0,'127.0.0.1',ok));base='http://127.0.0.1:'+server.address().port}
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 for(const width of [1440,390]){
  const c=await browser.newContext({viewport:{width,height:1000},isMobile:width<760,hasTouch:width<760});
  await c.route('**/*',async r=>{const u=new URL(r.request().url());if(u.origin!==new URL(base).origin)return r.abort();if(u.pathname==='/favicon.ico')return r.fulfill({status:204});try{const response=await c.request.get(u.href,{timeout:20000});if(response.status()>=400)errors.push({path:u.pathname,status:response.status()});return r.fulfill({response})}catch(e){errors.push({path:u.pathname,error:e.name});return r.abort()}});
  const p=await c.newPage();p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));await p.goto(base+'/#categories?category=bank',{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>financeMvp&&activeCategory==='bank');assert.equal(await p.locator('[data-finance-id]').count(),4);assert.ok(!(await p.locator('#cards').textContent()).includes('기본 조건 일치'));
  pass(width+' four products available without requiring profile input');
  for(const item of data.products){
   const card=p.locator('[data-finance-id="'+item.id+'"]');assert.equal(await card.locator('.source-action').getAttribute('href'),item.source.url);const terms=await card.locator('.finance-card-terms dt').allTextContents();assert.ok(terms.includes(item.id==='farmland'?'지원단가':item.id==='guarantee'?'보증한도':'대출한도'));assert.ok((await card.textContent()).includes(item.limit));assert.ok((await card.textContent()).includes(item.interest));
   await card.locator('.compact-open').click();const detail=p.locator('#modalSource'),text=await detail.textContent();for(const k of ['limit','grace','repayment'])assert.ok(text.includes(item[k]));assert.equal(await detail.locator('.source-action').getAttribute('href'),item.source.url);
   const g=item.applicationGuide,guide=detail.locator('.finance-application-guide');assert.equal(await guide.count(),1);assert.ok(text.includes(g.scope));assert.ok(text.includes(g.reception));
   assert.equal(await guide.locator('ol li').count(),g.steps.length);const docs=guide.locator('.finance-documents');assert.equal(await docs.getAttribute('open'),null);await docs.locator('summary').click();assert.ok(await docs.locator('p').isVisible());
   for(const v of [...g.documents,...g.conditionalDocuments,g.documentNote])assert.ok((await docs.textContent()).includes(v));
   assert.equal(await guide.locator('a').getAttribute('href'),g.source.url);assert.ok((await guide.textContent()).includes('2026. 10. 30.'));
   await docs.locator('summary').scrollIntoViewIfNeeded();
   assert.equal(await detail.evaluate(e=>e.scrollWidth>e.clientWidth+1),false,'detail overflow');assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'page overflow');await p.screenshot({path:path.join(out,(production?'aws':'local')+'-'+item.id+'-'+width+'.png')});await p.locator('#closeModal').click();
  }
  pass(width+' four application guides, documents, references and original financial terms verified');await c.close();
 }
 assert.deepEqual(errors,[]);pass('no browser exceptions or failed first-party requests');
}catch(e){results.push({name:'execution',passed:false,error:e.stack})}finally{
 await browser?.close();if(server)await new Promise(ok=>server.close(ok));const r={production,checkedAt:new Date().toISOString(),elapsedSeconds:(Date.now()-started)/1000,passed:results.filter(x=>x.passed).length,failed:results.filter(x=>!x.passed).length,results,errors};fs.writeFileSync(path.join(out,production?'aws-result.json':'local-result.json'),JSON.stringify(r,null,2));console.log(JSON.stringify(r));process.exitCode=r.failed?1:0;
}})();
