/* Local UI v2 regression. Playwright + headless Edge, no remote calls or source/data writes. */
const fs=require('node:fs/promises'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'outputs','ui-v2');
let browser,server,base;const results=[],errors=[];
async function check(name,fn){try{await fn();results.push({name,passed:true})}catch(e){results.push({name,passed:false,error:e.message.split('\n').slice(0,5).join('\n')});console.log('FAIL: '+name)}}
async function ready(page){await page.waitForFunction(()=>catalogData&&supportReview&&publicSupport&&financeData&&cropData&&equipmentData)}
async function wire(page){await page.route('**/*',async route=>{try{const u=new URL(route.request().url());if(u.origin!==new URL(base).origin){await route.abort();return}const file=path.resolve(root,'.'+(u.pathname==='/'?'/index.html':decodeURIComponent(u.pathname)));if(!file.startsWith(root+path.sep)){await route.fulfill({status:403,body:''});return}await route.fulfill({status:200,contentType:file.endsWith('.json')?'application/json':file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html; charset=utf-8',body:await fs.readFile(file)})}catch{await route.fulfill({status:404,body:''})}})}
async function noOverflow(page){const sizes=await page.evaluate(()=>({viewport:innerWidth,body:document.body.scrollWidth,doc:document.documentElement.scrollWidth}));assert.ok(sizes.body<=sizes.viewport+1&&sizes.doc<=sizes.viewport+1,JSON.stringify(sizes))}
async function go(page,category){await page.evaluate(c=>navigateTo(c),category)}
async function main(){
 await fs.mkdir(out,{recursive:true});
 server=http.createServer(async(req,res)=>{
  try{const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname),file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return}res.setHeader('Content-Type',file.endsWith('.json')?'application/json':file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html; charset=utf-8');res.end(await fs.readFile(file))}catch{res.writeHead(404).end()}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));base='http://127.0.0.1:'+server.address().port;
 browser=await chromium.launch({headless:true,executablePath:process.env.MUNONGSA_BROWSER_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1280,height:900}});page.setDefaultTimeout(6000);page.on('pageerror',e=>errors.push(e.message));
 await wire(page);await page.goto(base);await ready(page);
 await check('initial brand home',async()=>{assert.equal(await page.locator('body').getAttribute('data-view'),'brand');assert.ok(await page.locator('#brandHeading').isVisible());assert.equal(await page.locator('#results').isVisible(),false);assert.equal(await page.locator('#serviceHome').isVisible(),false)});
 await check('brand secondary support CTA removed',async()=>{assert.equal(await page.locator('[data-open-support]').count(),0);assert.equal(await page.locator('.brand-actions a').count(),1)});
 await page.screenshot({path:path.join(out,'brand-desktop.png')});
 await page.locator('.primary-action').click();
 await check('start opens distinct service home',async()=>{assert.equal(new URL(page.url()).hash,'#service');assert.ok(await page.locator('#serviceHome').isVisible());assert.equal(await page.locator('#top').isVisible(),false)});
 await check('three service categories, equipment absent',async()=>{assert.deepEqual(await page.locator('#categories [data-category]').evaluateAll(rows=>rows.map(r=>r.dataset.category)),['support','bank','cultivation']);assert.equal(await page.locator('.nav [data-nav-category="equipment"]').count(),0);assert.equal(await page.locator('#interest option[value="equipment"]').count(),0)});
 await check('support has visual priority',async()=>{const support=await page.locator('[data-category="support"]').boundingBox(),bank=await page.locator('[data-category="bank"]').boundingBox();assert.ok(support.width>bank.width*1.5);assert.ok(await page.locator('[data-category="support"]').evaluate(el=>getComputedStyle(el).backgroundColor!=='rgb(255, 255, 255)'))});
 await page.screenshot({path:path.join(out,'service-desktop.png'),fullPage:true});
 await page.locator('[data-category="support"]').click();
 await check('support references preserved',async()=>{assert.equal(await page.locator('#resultTitle').textContent(),'지원사업');assert.equal(await page.locator('[data-info-kind="supportReview"]').count(),await page.evaluate(()=>MunongsaSupportReview.publicRecords(supportReview).length));assert.ok((await page.locator('#cards').textContent()).includes('검토 중 참고 공고'))});
 await check('profile heading has accessible high contrast',async()=>{const values=await page.locator('.filter-heading').evaluate(el=>{const s=getComputedStyle(el);return {fg:s.color,bg:s.backgroundColor}});const luminance=rgb=>{const c=rgb.match(/\d+/g).slice(0,3).map(v=>{const n=Number(v)/255;return n<=0.04045?n/12.92:Math.pow((n+0.055)/1.055,2.4)});return .2126*c[0]+.7152*c[1]+.0722*c[2]};const a=luminance(values.fg),b=luminance(values.bg);assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5)});
 await page.screenshot({path:path.join(out,'support-desktop.png')});
 await page.locator('#supportSearch').fill('농식품');
 await check('reference keyword search',async()=>{assert.ok(await page.locator('[data-info-kind="supportReview"]').count()>0);assert.ok(await page.locator('[data-info-kind="supportReview"]').count()<67)});
 await page.locator('#supportSearch').fill('');
 await page.locator('[data-info-kind="supportReview"]').first().click();
 await check('reference modal and official link',async()=>{await page.locator('#modal.show').waitFor();assert.ok((await page.locator('#modalTag').textContent()).includes('신청 추천 아님'));assert.ok((await page.locator('#modalSource a').first().getAttribute('href')).startsWith('https://'))});
 await page.goBack();
 await check('browser back closes modal',async()=>{await page.waitForFunction(()=>!document.getElementById('modal').classList.contains('show'));assert.ok(await page.locator('#results').isVisible())});
 await page.fill('#age','32');await page.locator('#additionalProfileFields>summary').click();await page.selectOption('#applicant','individual');
 await page.locator('[data-nav-category="bank"]').click();
 await check('finance data and detail preserved',async()=>{await page.locator('#cards .compact-open').first().click();await page.locator('#modal.show').waitFor();await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.getElementById('modal').classList.contains('show'));assert.equal(await page.locator('#age').inputValue(),'32')});
 await page.goBack();
 await check('category back restores support',async()=>{await page.waitForFunction(()=>document.getElementById('resultTitle').textContent==='지원사업')});
 await page.goForward();
 await check('category forward restores finance',async()=>{await page.waitForFunction(()=>document.getElementById('resultTitle').textContent==='농업금융')});
 await page.locator('[data-nav-category="cultivation"]').click();
 await check('crop data and official source detail preserved',async()=>{await page.locator('[data-crop-open="마늘"]').click();await page.locator('#cards .compact-open').first().click();await page.locator('#modal.show').waitFor();assert.ok(await page.locator('#modalSource a').count());await page.locator('#closeModal').click();await page.waitForFunction(()=>!document.getElementById('modal').classList.contains('show'));await page.locator('[data-crop-back]').click();assert.ok(await page.locator('[data-crop-open="마늘"]').isVisible())});
 await page.locator('[data-service-home]').last().click();
 await check('return service home retains profile',async()=>{assert.ok(await page.locator('#serviceHome').isVisible());assert.equal(await page.locator('#age').inputValue(),'32')});
 await page.reload();await ready(page);
 await check('service URL and profile restored after reload',async()=>{assert.ok(await page.locator('#serviceHome').isVisible());assert.equal(await page.locator('#age').inputValue(),'32')});
 await page.locator('.brand').click();
 await check('logo returns brand home',async()=>assert.ok(await page.locator('#top').isVisible()));
 await page.goBack();
 await check('back from brand returns service home',async()=>{await page.waitForFunction(()=>document.body.dataset.view==='service')});
 await page.close();
 for(const width of [320,375,390,430,768,1280]){
  const p=await browser.newPage({viewport:{width,height:900}});p.setDefaultTimeout(6000);p.on('pageerror',e=>errors.push(e.message));
  await wire(p);await p.goto(base);await ready(p);
  await check(width+' brand no horizontal overflow',()=>noOverflow(p));
  await check(width+' brand CTA is usable',async()=>{const box=await p.locator('.primary-action').boundingBox();assert.ok(box.height>=44&&box.width<=width)});
  if(width===390)await p.screenshot({path:path.join(out,'brand-mobile-390.png'),fullPage:true});
  await p.locator('.primary-action').click();
  await check(width+' service no horizontal overflow',()=>noOverflow(p));
  await check(width+' category cards stay within viewport',async()=>{for(const box of await p.locator('#categories button').evaluateAll(rows=>rows.map(r=>{const b=r.getBoundingClientRect();return {x:b.x,right:b.right}})))assert.ok(box.x>=0&&box.right<=width)});
  if(width===390)await p.screenshot({path:path.join(out,'service-mobile-390.png'),fullPage:true});
  await p.locator('[data-category="support"]').click();
  await check(width+' support no horizontal overflow',()=>noOverflow(p));
  await check(width+' references visible',async()=>assert.ok(await p.locator('[data-info-kind="supportReview"]').first().isVisible()));
  if(width<=760){
   await check(width+' mobile profile panel opens and closes',async()=>{assert.equal(await p.locator('#applicant').isVisible(),false);await p.locator('#profileToggle').click();assert.ok(await p.locator('#age').isVisible());assert.equal(await p.locator('#applicant').isVisible(),false);await p.locator('#additionalProfileFields>summary').click();assert.ok(await p.locator('#applicant').isVisible());await p.selectOption('#applicant','individual');await p.locator('#profileToggle').click();assert.equal(await p.locator('#applicant').inputValue(),'individual')});
   await check(width+' mobile menu opens and navigates',async()=>{await p.locator('#menuToggle').click();assert.equal(await p.locator('#menuToggle').getAttribute('aria-expanded'),'true');await p.locator('[data-nav-category="bank"]').click();assert.equal(await p.locator('#menuToggle').getAttribute('aria-expanded'),'false');await go(p,'support')});
  }
  if(width===390)await p.screenshot({path:path.join(out,'support-mobile-390.png')});
  await p.locator('[data-info-kind="supportReview"]').first().click();
  await check(width+' modal fits and closes',async()=>{await p.locator('#modal.show').waitFor();const box=await p.locator('.modal-box').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=width+1);await p.locator('#closeModal').click();await p.waitForFunction(()=>!document.getElementById('modal').classList.contains('show'))});
  await check(width+' very long card title wraps',async()=>{const title=p.locator('[data-info-kind="supportReview"] strong').first();await title.evaluate(el=>el.textContent='긴 사업명과 신청 조건을 확인하는 레이아웃 시험입니다 '.repeat(12));await noOverflow(p)});
  await p.close();
 }
 const direct=await browser.newPage();
 await wire(direct);await direct.goto(base);await ready(direct);const detailKey=await direct.evaluate(()=>MunongsaSupportReview.publicRecords(supportReview)[0].id);await direct.goto(base+'/#categories?category=support&kind=supportReview&key='+encodeURIComponent(detailKey));
 await check('direct category/detail URL restored',async()=>{await direct.locator('#modal.show').waitFor();assert.ok((await direct.locator('#modalTag').textContent()).includes('검토'))});
 await direct.close();
 await check('no browser JavaScript errors',async()=>assert.deepEqual(errors,[]));
 await fs.writeFile(path.join(out,'test-results.json'),JSON.stringify({results,errors},null,2));
 console.log(JSON.stringify({passed:results.filter(r=>r.passed).length,failed:results.filter(r=>!r.passed).length,errors,failures:results.filter(r=>!r.passed),screenshots:out},null,2));
 if(results.some(r=>!r.passed))process.exitCode=1;
}
main().catch(async e=>{await fs.writeFile(path.join(out,'test-results.json'),JSON.stringify({results,errors,fatal:e.message},null,2));console.error(e.message);process.exitCode=1}).finally(async()=>{if(browser)await browser.close();if(server)await new Promise(resolve=>server.close(resolve))});
