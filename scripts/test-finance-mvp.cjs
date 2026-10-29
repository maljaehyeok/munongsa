/* Targeted finance data, three-valued comparison and actual Chrome user flows. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),http=require('node:http'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..'),data=require('../data/finance-mvp.json');
require('../assets/support-public.js');
const finance=require('../assets/finance-mvp.js'),{chromium}=require('playwright');
const out=path.join(root,'work/finance-mvp'),production=process.env.MUNONGSA_FINANCE_BASE;
fs.mkdirSync(out,{recursive:true});const results=[],errors=[],failedRequests=[];
function check(name,fn){fn();results.push({name,passed:true})}
const preserved=['data/support-public.json','data/support-review.json','data/finance-products.json','assets/support-public.js','assets/support-review.js'];
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex'),before=Object.fromEntries(preserved.map(f=>[f,hash(f)]));
let server,browser;
(async()=>{try{
check('four distinct products',()=>assert.equal(new Set(data.products.map(p=>p.id)).size,4));
for(const p of data.products){check(p.id+' source and fact fields',()=>{assert.ok(/^https:\/\//.test(p.source.url));for(const k of ['institution','target','region','limit','interest','grace','repayment','application','status','year'])assert.ok(p[k]);assert.ok(p.source.useNote);assert.ok(p.unknowns.length)})}
const successor=data.products[0];
check('individual with official birth year matches checked subset',()=>assert.equal(finance.compare(successor,{applicant:'individual',birthDate:'1994-01-01'}).state,'match'));
check('older applicant fails ordinary successor birth range',()=>assert.equal(finance.compare(successor,{applicant:'individual',birthDate:'1960-01-01'}).state,'mismatch'));
check('current age and farming stage never substitute for evidence',()=>assert.equal(finance.compare(successor,{age:32,experience:'planned'}).state,'check'));
check('national product not excluded by farming location',()=>assert.equal(finance.filter(data.products,'','all').length,4));
check('housing purpose is one program, not duplicate cards',()=>assert.equal(finance.filter(data.products,'','주택 마련').length,1));
check('guarantee distinct and unverified ratios not promised',()=>{const p=data.products.find(p=>p.id==='guarantee');assert.equal(p.type,'신용보증');assert.equal(finance.compare(p,{}).state,'check');assert.match(p.limit,/확인 필요/)});
check('KST date conversion',()=>assert.match(finance.date('2026-10-28T18:30:00Z'),/2026.*10.*29/));
let base=production;
if(!base){server=http.createServer((req,res)=>{const u=new URL(req.url,'http://localhost');let f=path.resolve(root,'.'+decodeURIComponent(u.pathname));if(f===root)f=path.join(root,'index.html');if(!f.startsWith(root+path.sep)||!['/','/index.html','/favicon.ico'].includes(u.pathname)&&!/^\/(assets|data)\//.test(u.pathname)){res.writeHead(404).end();return}try{const body=fs.readFileSync(f);res.writeHead(200,{'Content-Type':f.endsWith('.js')?'text/javascript':f.endsWith('.css')?'text/css':f.endsWith('.json')?'application/json':'text/html; charset=utf-8'}).end(body)}catch{res.writeHead(404).end()}});await new Promise(ok=>server.listen(0,'127.0.0.1',ok));base='http://127.0.0.1:'+server.address().port}
browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
let publicBefore;
for(const width of [1280,390]){
 const context=await browser.newContext({viewport:{width,height:900}});
 // Reuse verify-approved-batch.cjs transport: render actual HTTP response bytes
 // from AWS in Chrome, without substituting local data for production responses.
 if(production)await context.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.origin===new URL(base).origin){
   if(u.pathname==='/favicon.ico')return route.fulfill({status:204});
   try{const response=await context.request.get(u.href,{timeout:20000});if(response.status()>=400)failedRequests.push({path:u.pathname,status:response.status()});return route.fulfill({response})}
   catch(e){failedRequests.push({path:u.pathname,error:e.name});return route.abort()}
  }
  if(route.request().isNavigationRequest())return route.fulfill({status:200,contentType:'text/plain',body:'Official destination URL check only; external contents not tested'});
  return route.abort('blockedbyclient');
 });
 const page=await context.newPage();page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(30000);page.on('pageerror',e=>errors.push(e.message));page.on('requestfailed',r=>{if(new URL(r.url()).origin===new URL(base).origin)failedRequests.push({url:r.url(),error:r.failure()?.errorText})});
 await page.goto(base+'/#categories?category=bank',{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>typeof financeMvp!=='undefined'&&financeMvp&&publicSupport&&supportReview);
 const current=await page.evaluate(()=>({public:publicSupport,review:supportReview}));if(!publicBefore)publicBefore=current;else assert.deepEqual(current,publicBefore);
 if(production){const response=await context.request.get(base+'/data/finance-mvp.json');assert.equal(response.status(),200);assert.deepEqual(await response.json(),data)}
 check(width+' four finance cards visible',()=>assert.equal(true,true));assert.equal(await page.locator('[data-finance-id]').count(),4);assert.ok(await page.locator('[data-finance-id]').first().isVisible());
 assert.ok(!/unverified|approved_reference|AND\(|팀 엑셀|농기계/.test(await page.locator('#cards').innerText()));
 await page.locator('#financeSearch').fill('보증');assert.equal(await page.locator('[data-finance-id]').count(),1);assert.ok(await page.locator('#financeSearch').evaluate(e=>e===document.activeElement));
 await page.locator('#financeSearch').fill('');await page.locator('#financePurpose').selectOption({label:'주택 마련'});assert.equal(await page.locator('[data-finance-id]').count(),1);await page.locator('#financePurpose').selectOption('all');
 results.push({name:width+' search and purpose filter',passed:true});
 for(const p of data.products){await page.locator(`[data-info-key="${p.id}"]`).click();await page.locator('#modal.show').waitFor();assert.equal(await page.locator('#modalTitle').innerText(),p.title);const text=await page.locator('#modal').innerText();assert.ok(text.includes('2026. 10. 29.'));assert.ok(text.includes('별도 심사'));assert.ok(!/undefined|unverified|AND\(|approved_reference|T\d\d:/.test(text));assert.equal(await page.locator('#modalSource a').getAttribute('href'),p.source.url);const popup=page.waitForEvent('popup');await page.locator('#modalSource a').click();const opened=await popup;assert.ok(opened.url()===p.source.url||opened.url()==='about:blank'||opened.url().startsWith('https://'));await opened.close();await page.locator('#closeModal').click()}
 results.push({name:width+' four details and official links',passed:true});
 if(width<=760&&await page.locator('#profileToggle').getAttribute('aria-expanded')==='false')await page.locator('#profileToggle').click();
 if(!await page.locator('#additionalProfileFields').getAttribute('open')&&await page.locator('#additionalProfileFields').getAttribute('open')===null)await page.locator('#additionalProfileFields>summary').click();
 await page.locator('#applicant').selectOption('individual');await page.locator('#birthDate').fill('1994-01-01');await page.locator('[data-info-key="successor"]').click();assert.equal(await page.locator('#modalStatus').innerText(),'기본 조건 일치');await page.locator('#closeModal').click();
 await page.locator('#birthDate').fill('1960-01-01');await page.locator('[data-info-key="successor"]').click();assert.equal(await page.locator('#modalStatus').innerText(),'불일치');await page.locator('#closeModal').click();
 await page.locator('#birthDate').fill('');await page.locator('[data-info-key="successor"]').click();assert.equal(await page.locator('#modalStatus').innerText(),'추가 확인 필요');await page.locator('#closeModal').click();results.push({name:width+' three actual profile results',passed:true});
 await page.locator('[data-info-key="farmland"]').click();await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>financeMvp&&document.getElementById('modal').classList.contains('show'));assert.equal(await page.locator('#modalTitle').innerText(),data.products[2].title);await page.locator('#closeModal').click();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await page.screenshot({path:path.join(out,`finance-${width}.png`),fullPage:true});
 await page.locator('[data-nav-category="support"]').evaluate(e=>e.click());await page.waitForFunction(()=>activeCategory==='support');assert.deepEqual(await page.evaluate(()=>({public:publicSupport,review:supportReview})),publicBefore);await page.locator('[data-nav-category="bank"]').evaluate(e=>e.click());await page.waitForFunction(()=>activeCategory==='bank');assert.equal(await page.locator('[data-finance-id]').count(),4);results.push({name:width+' navigation restoration no overflow support preserved',passed:true});await page.close();
}
check('no console exceptions',()=>assert.deepEqual(errors,[]));check('no failed same-origin requests',()=>assert.deepEqual(failedRequests,[]));check('original support and finance data unchanged by tests',()=>{for(const f of preserved)assert.equal(hash(f),before[f])});
}catch(e){results.push({name:'execution',passed:false,error:e.stack})}finally{if(browser)await browser.close();if(server)await new Promise(ok=>server.close(ok));const report={production:!!production,base:production||'local',results,errors,failedRequests,passed:results.filter(r=>r.passed).length,failed:results.filter(r=>!r.passed).length};fs.writeFileSync(path.join(out,production?'aws-browser-result.json':'local-result.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));process.exitCode=report.failed?1:0}})();
