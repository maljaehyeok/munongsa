/* Local browser regression: node scripts/test-ui-navigation.cjs
   Requires Playwright in the test environment; does not modify source/data files. */
const fs=require('node:fs/promises');
const path=require('node:path');
const http=require('node:http');
const assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const names={support:'지원사업',bank:'농업금융',equipment:'농업장비',cultivation:'재배기술'};
const results=[];
let browser,server,url;
const errors=[];
async function check(group,name,fn){
  try{await fn();results.push({group,name,passed:true})}
  catch(error){results.push({group,name,passed:false,error:error.message.split('\n').slice(0,5).join('\n')})}
}
async function ready(page){
  await page.waitForFunction(()=>equipmentData&&financeData&&supportData&&cropData&&catalogData);
}
async function go(page,category){
  await page.locator('[data-nav-category="'+category+'"]').click();
  assert.equal(await page.locator('#resultTitle').textContent(),names[category]);
}
async function closed(page){
  await page.waitForFunction(()=>!document.getElementById('modal').classList.contains('show')&&!location.hash.includes('kind='));
}
async function close(page){await page.keyboard.press('Escape');await closed(page)}
async function openFirst(page){
  await page.locator('#cards .compact-open').first().click();
  await page.locator('#modal.show').waitFor();
}
async function fresh(fn){
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  page.setDefaultTimeout(5000);
  page.on('pageerror',e=>errors.push(e.message));
  try{await page.goto(url);await ready(page);await fn(page)}
  finally{await page.close()}
}
async function backTitle(page,title){
  await page.goBack();
  await page.waitForFunction(t=>document.getElementById('resultTitle').textContent===t,title);
}
async function home(page){
  await page.waitForFunction(()=>document.getElementById('results').hidden);
}
async function main(){
  const regression=spawnSync(process.execPath,['--test','scripts/test-support-matching.cjs'],{cwd:root,encoding:'utf8'});
  const text=regression.stdout||'';
  const n=Number(text.match(/(?:#|ℹ) tests (\d+)/)?.[1]);
  assert.equal(regression.status,0,regression.stderr||text);
  assert.equal(n,34,'Expected the preserved 34 support tests');
  server=http.createServer(async(req,res)=>{
    try{
      const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
      const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
      if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return}
      res.setHeader('Content-Type',file.endsWith('.json')?'application/json':file.endsWith('.js')?'text/javascript':'text/html; charset=utf-8');
      res.end(await fs.readFile(file));
    }catch{res.writeHead(404).end()}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  url='http://127.0.0.1:'+server.address().port;
  const edge=process.env['ProgramFiles(x86)']&&path.join(process.env['ProgramFiles(x86)'],'Microsoft/Edge/Application/msedge.exe');
  let executablePath=process.env.MUNONGSA_BROWSER_PATH;
  if(!executablePath&&edge){try{await fs.access(edge);executablePath=edge}catch{}}
  browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  page.setDefaultTimeout(5000);page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await ready(page);
  for(const [key,title] of Object.entries(names)){
    await check('B','menu '+key,async()=>assert.equal(await page.locator('[data-nav-category="'+key+'"]').textContent(),title));
    await check('B','home card '+key,async()=>{assert.equal(await page.locator('[data-category="'+key+'"] strong').textContent(),title);if(key==='equipment'){const description=await page.locator('[data-category="equipment"] small').textContent();assert.ok(description.includes('농기자재')&&description.includes('스마트농업 솔루션'))}});
    await go(page,key);
    await check('B','screen title '+key,async()=>assert.equal(await page.locator('#resultTitle').textContent(),title));
    await check('B','interest '+key,async()=>assert.equal(await page.locator('#interest option[value="'+key+'"]').textContent(),title));
  }
  await page.locator('[data-nav-home]').click();
  await check('C','home entry',()=>home(page));
  await page.locator('[data-category="support"]').click();
  await check('C','home card opens results',async()=>assert.ok(await page.locator('#results').isVisible()));
  await page.selectOption('#applicant','individual');await page.fill('#age','32');
  await page.selectOption('#experience','planned');await page.selectOption('#region','전북');
  await page.selectOption('#district','김제시');await page.selectOption('#crop','garlic');
  await page.selectOption('#cultivation','openfield');
  const profile=await page.evaluate(()=>JSON.stringify(readProfile()));
  await go(page,'bank');
  await check('C','profile retained bank',async()=>assert.equal(await page.evaluate(()=>JSON.stringify(readProfile())),profile));
  await check('C','finance detail opens',()=>openFirst(page));
  await check('C','Escape closes',()=>close(page));
  await go(page,'cultivation');
  await check('C','profile retained crop',async()=>assert.equal(await page.evaluate(()=>JSON.stringify(readProfile())),profile));
  await check('C','crop opens',async()=>{await page.locator('[data-crop-open="마늘"]').click();assert.equal(await page.locator('[data-crop-back]').count(),1)});
  await openFirst(page);
  await check('C','close button',async()=>{await page.locator('#closeModal').click();await closed(page)});
  await check('C','crop back button',async()=>{await page.locator('[data-crop-back]').click();assert.equal(await page.locator('[data-crop-open="마늘"]').count(),1)});
  await check('C','home menu',async()=>{await page.locator('[data-nav-home]').click();await home(page)});
  await page.locator('[data-category="equipment"]').click();
  await check('C','logo home',async()=>{await page.locator('.brand').click();await home(page)});
  await check('C','profile retained home',async()=>assert.equal(await page.evaluate(()=>JSON.stringify(readProfile())),profile));
  await check('C','browser Back previous category',()=>fresh(async p=>{await go(p,'support');await go(p,'bank');await backTitle(p,names.support)}));
  await page.locator('[data-category="support"]').click();
  const youth=page.locator('[data-info-key="youth"]');
  await check('A-ui','personal32 no audience conflict',async()=>assert.ok(!(await youth.innerText()).includes('신청 주체 기록과 불일치')));
  await page.fill('#age','');
  await check('A-ui','missing age check',async()=>assert.ok((await youth.innerText()).includes('연령 미입력')));
  await page.fill('#age','40');
  await check('A-ui','age40 separated',async()=>assert.equal(await page.locator('.support-mismatches [data-info-key="youth"]').count(),1));
  await page.locator('.support-mismatches').evaluate(e=>e.open=true);await youth.click();await page.locator('#modal.show').waitFor();
  await check('A-ui','mismatch explanation',async()=>assert.ok((await page.locator('#modalEligibility').innerText()).includes('연령 18~39세 기록과 불일치')));
  await check('A-ui','not official qualification',async()=>assert.ok((await page.locator('#modalEligibility').innerText()).includes('신청 자격 확정이 아닙니다')));
  await close(page);await page.selectOption('#experience','over3');
  await check('A-ui','general career unknown',async()=>assert.ok((await page.locator('[data-info-key="direct"]').innerText()).includes('영농 단계 조건 미기록')));
  await page.locator('#resetFilters').click();await page.selectOption('#applicant','individual');
  await check('A-ui','recorded match displayed',async()=>assert.ok((await page.locator('[data-info-key="direct"]').innerText()).includes('조건 부합')));
  await page.fill('#age','32');
  await check('A-ui','age then immediate detail',()=>openFirst(page));await close(page);
  const data={};
  for(const name of ['smart-agriculture-catalog','support-programs','crop-cultivation-records','finance-products','equipment-catalog']){
    await check('E','JSON '+name,async()=>{const response=await page.request.get(url+'/data/'+name+'.json');assert.equal(response.status(),200);data[name]=await response.json()});
  }
  await check('E','support 4 + references 6',async()=>{assert.equal(data['smart-agriculture-catalog'].supportPrograms.length,4);assert.equal(data['support-programs'].referenceDocuments.length,6)});
  await check('E','crop 169 + held 7',async()=>{assert.equal(data['crop-cultivation-records'].records.length,169);assert.equal(data['crop-cultivation-records'].reviewRecords.length,7)});
  await check('E','finance 28',async()=>assert.equal(data['finance-products'].masterProducts.length,28));
  await check('E','equipment 5/6/8/13',async()=>assert.equal(['officialGuidelineCategories','teamIdeas','productCandidates','facilityCandidates'].map(k=>data['equipment-catalog'][k].length).join('/'),'5/6/8/13'));
  for(const width of [320,375,390,430,768,1280]){
    const touch=width<768,context=await browser.newContext({viewport:{width,height:900},hasTouch:touch,isMobile:touch});
    const p=await context.newPage();p.setDefaultTimeout(5000);p.on('pageerror',e=>errors.push(e.message));
    await p.goto(url);await ready(p);
    for(const key of Object.keys(names))await check('D',width+' '+key,async()=>{
      const nav=p.locator('[data-nav-category="'+key+'"]');
      if(touch)await nav.tap();else await nav.click();
      await p.locator('#cards details').evaluateAll(els=>els.forEach(e=>e.open=true));
      const layout=await p.evaluate(()=>{
        const links=[...document.querySelectorAll('.nav a')].map(e=>e.getBoundingClientRect());
        let overlap=false;
        for(let i=0;i<links.length;i++)for(let j=i+1;j<links.length;j++){
          const a=links[i],b=links[j];
          if(a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top)overlap=true;
        }
        return {overflow:document.documentElement.scrollWidth>innerWidth+1,overlap,
          menuOutside:links.some(r=>r.left<0||r.right>innerWidth),
          cardOverflow:[...document.querySelectorAll('#cards .compact-open')].filter(e=>e.getClientRects().length).some(e=>e.scrollWidth>e.clientWidth+1)};
      });
      assert.ok(!Object.values(layout).some(Boolean),JSON.stringify(layout));
      if(key==='cultivation'){const tile=p.locator('[data-crop-open="파"]');if(touch)await tile.tap();else await tile.click()}
      const button=p.locator('#cards .compact-open').first();if(touch)await button.tap();else await button.click();
      await p.locator('#modal.show').waitFor();
      assert.ok(await p.locator('.modal-box').evaluate(e=>{const r=e.getBoundingClientRect();return e.scrollWidth<=e.clientWidth+1&&r.left>=0&&r.right<=innerWidth&&r.top>=-1&&r.bottom<=innerHeight+1}));
      const closeButton=p.locator('#closeModal');if(touch)await closeButton.tap();else await closeButton.click();await closed(p);
    });
    await context.close();
  }
  const extra=(name,fn)=>check('history-extra',name,()=>fresh(fn));
  await extra('Forward restores category',async p=>{await go(p,'support');await go(p,'bank');await backTitle(p,names.support);await p.goForward();await p.waitForFunction(()=>document.getElementById('resultTitle').textContent==='농업금융')});
  await extra('category Back returns home',async p=>{await go(p,'support');await p.goBack();await home(p)});
  await extra('successive category Back sequence',async p=>{for(const k of ['support','bank','equipment','cultivation'])await go(p,k);for(const k of ['equipment','bank','support'])await backTitle(p,names[k])});
  await extra('logo home Back restores category',async p=>{await go(p,'bank');await p.locator('.brand').click();await home(p);await backTitle(p,names.bank)});
  await extra('home menu Back and Forward',async p=>{await go(p,'support');await p.locator('[data-nav-home]').click();await home(p);await backTitle(p,names.support);await p.goForward();await home(p)});
  await extra('duplicate category no extra entry',async p=>{await go(p,'support');const n=await p.evaluate(()=>history.length);await go(p,'support');assert.equal(await p.evaluate(()=>history.length),n)});
  await extra('duplicate home no extra entry',async p=>{const n=await p.evaluate(()=>history.length);await p.locator('[data-nav-home]').click();await p.locator('.brand').click();assert.equal(await p.evaluate(()=>history.length),n)});
  await extra('Back closes modal before category',async p=>{await go(p,'support');await openFirst(p);await p.goBack();await closed(p);assert.equal(await p.locator('#resultTitle').textContent(),names.support);await p.goBack();await home(p)});
  await extra('Forward reopens same modal',async p=>{await go(p,'support');await openFirst(p);const title=await p.locator('#modalTitle').textContent();await p.goBack();await closed(p);await p.goForward();await p.locator('#modal.show').waitFor();assert.equal(await p.locator('#modalTitle').textContent(),title)});
  await extra('close button consumes modal entry',async p=>{await go(p,'support');await openFirst(p);const n=await p.evaluate(()=>history.length);await p.locator('#closeModal').click();await closed(p);assert.equal(await p.evaluate(()=>history.length),n);await p.goBack();await home(p)});
  await extra('Escape closes modal entry',async p=>{await go(p,'support');await openFirst(p);await close(p);assert.equal(await p.locator('#resultTitle').textContent(),names.support)});
  await extra('backdrop closes modal entry',async p=>{await go(p,'support');await openFirst(p);await p.locator('#modal').click({position:{x:2,y:2}});await closed(p)});
  await extra('crop Back restores crop list',async p=>{await go(p,'cultivation');await p.locator('[data-crop-open="파"]').click();await p.goBack();await p.locator('[data-crop-open="파"]').waitFor()});
  await extra('crop internal back button',async p=>{await go(p,'cultivation');await p.locator('[data-crop-open="파"]').click();await p.locator('[data-crop-back]').click();await p.locator('[data-crop-open="파"]').waitFor()});
  await extra('profile persists Back and Forward',async p=>{await go(p,'support');await p.fill('#age','32');await p.selectOption('#region','전북');await p.selectOption('#district','김제시');const value=await p.evaluate(()=>JSON.stringify(readProfile()));await go(p,'bank');await backTitle(p,names.support);await p.goForward();await p.waitForFunction(()=>document.getElementById('resultTitle').textContent==='농업금융');assert.equal(await p.evaluate(()=>JSON.stringify(readProfile())),value)});
  await extra('reload category and profile',async p=>{await go(p,'support');await p.fill('#age','32');await p.selectOption('#region','전북');await p.selectOption('#district','김제시');const value=await p.evaluate(()=>JSON.stringify(readProfile()));await p.reload();await ready(p);assert.equal(await p.locator('#resultTitle').textContent(),names.support);assert.equal(await p.evaluate(()=>JSON.stringify(readProfile())),value)});
  await extra('reload crop detail',async p=>{await go(p,'cultivation');await p.locator('[data-crop-open="파"]').click();await p.reload();await ready(p);assert.ok((await p.locator('#count').textContent()).startsWith('파 ·'))});
  await extra('reload open modal',async p=>{await go(p,'support');await openFirst(p);const title=await p.locator('#modalTitle').textContent();await p.reload();await ready(p);await p.locator('#modal.show').waitFor();assert.equal(await p.locator('#modalTitle').textContent(),title)});
  await extra('direct category URL',async p=>{await p.goto(url+'/#categories?category=bank');await ready(p);assert.equal(await p.locator('#resultTitle').textContent(),names.bank)});
  await extra('direct crop URL',async p=>{await p.goto(url+'/#categories?category=cultivation&crop='+encodeURIComponent('파'));await ready(p);assert.ok((await p.locator('#count').textContent()).startsWith('파 ·'))});
  await extra('direct modal URL closes inside site',async p=>{await p.goto(url+'/#categories?category=support&kind=program&key=youth');await ready(p);await p.locator('#modal.show').waitFor();await p.locator('#closeModal').click();await closed(p);assert.equal(await p.locator('#resultTitle').textContent(),names.support);assert.ok(p.url().startsWith(url))});
  await extra('unknown category falls back home',async p=>{await p.goto(url+'/#categories?category=invalid');await ready(p);await home(p)});
  const summary=Object.fromEntries(['A-ui','B','C','D','E','history-extra'].map(group=>[group,{passed:results.filter(r=>r.group===group&&r.passed).length,failed:results.filter(r=>r.group===group&&!r.passed).length}]));
  const base=results.filter(r=>r.group!=='history-extra');
  console.log(JSON.stringify({browser:await browser.version(),supportRegression:{tests:n,passed:n,failed:0},baseline104:{total:n+base.length,passed:n+base.filter(r=>r.passed).length,failed:base.filter(r=>!r.passed).length},summary,failures:results.filter(r=>!r.passed),pageErrors:errors,artifacts:'stdout only'},null,2));
  if(results.some(r=>!r.passed)||errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r))});
