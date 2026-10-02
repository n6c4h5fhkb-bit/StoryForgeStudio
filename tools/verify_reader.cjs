// Optional UI regression. Requires Playwright and locally installed Edge.
// Start A and B uvicorn on 127.0.0.1:18741 / :18742 with separate STUDIO_DATA
// directories inside .validation and demo model settings. Never use real data.
// From repository root: node tools/verify_reader.cjs
// Playwright may be resolved with NODE_PATH; this is not a runtime dependency.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
async function run(){
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const results=[];
 for(const system of ['A','B']){
  const page=await browser.newPage({viewport:{width:1440,height:1080}}),errors=[];
  page.on('pageerror',e=>{errors.push(e.message);console.log('PAGEERROR',e.message)});page.on('console',m=>m.type()==='error'&&console.log('CONSOLE',m.text()));
  const port=Number(process.env[system==='A'?'SYSTEM_A_PORT':'SYSTEM_B_PORT']||(system==='A'?18741:18742));
  await page.goto('http://127.0.0.1:'+port);await page.locator('#reader-workspace').waitFor();
  await page.locator('.rw-header [data-action="new"]').click();
  if(system==='A')await page.locator('[data-idea-action="manual"]').click();
  const expectedTitle='阅读联调 · '+system+' · '+Date.now();await page.locator('#f-title').fill(expectedTitle);
  await page.locator(system==='A'?'#f-seed':'#f-source').fill('雨夜便利店。店员发现母亲留下的一封信，却迟迟不敢打开。顾客敲了敲玻璃。');
  if(system==='A')await page.locator('#f-targetDuration').fill('48');
  else await page.locator('#f-aspectRatio').selectOption('16:9');
  await page.locator('button[form="modal-form"]').click();await page.waitForTimeout(500);if(await page.locator('.modal-backdrop').count())console.log('MODAL',await page.locator('.modal-backdrop').innerText());await page.locator('.modal-backdrop').waitFor({state:'hidden',timeout:3000});await page.locator('.rw-next').waitFor().catch(async e=>{console.log(await page.locator('body').innerText());throw e});
  const createdId=await page.locator('#rw-project').inputValue();const created=await(await page.request.get('http://127.0.0.1:'+port+'/api/projects/'+createdId)).json();assert.equal(created.project.title,expectedTitle);assert.equal(created.project.targetDuration,system==='A'?48:null);
  await page.locator('.rw-next [data-reader="advance"]').click();
  await page.locator(system==='A'?'[data-reader="adopt"]':'[data-studio="draft-adopt"]').waitFor({timeout:15000});
  assert.ok(await page.locator('.rw-proposal-part').count());
  await page.screenshot({path:'.validation/reader-'+system.toLowerCase()+'-choices.png',fullPage:true});
  const nextSelector=system==='A'?'[data-reader="adopt-next"]':'[data-studio="draft-adopt-next"]';
  const firstId=await page.locator(nextSelector).getAttribute('data-id');await page.locator(nextSelector).click();await page.locator(nextSelector+'[data-id="'+firstId+'"]').waitFor({state:'detached'});
  if(system==='A'){
   await page.locator('[data-reader="adopt"]').waitFor({timeout:15000});
   await page.locator('[data-reader="adopt"]').click();
   await page.locator('#rw-instruction').waitFor();
   await page.locator('#rw-instruction').fill('保留雨夜背景，让人物选择更果断。');
   await page.locator('[data-reader="refine"]').click();await page.locator('[data-reader="adopt"]').waitFor({timeout:15000});
   assert.equal(await page.locator('.rw-choice-tabs button').count(),1);
   await page.locator('[data-reader="adopt"]').click();
  }else{
   await page.locator('[data-reader="adopt"]').waitFor({timeout:15000});
   for(let i=0;i<15;i++){
    const id=await page.locator('#rw-project').inputValue();
    const data=await (await page.request.get('http://127.0.0.1:'+port+'/api/projects/'+id)).json();
    if(data.workflow.state==='complete')break;
    if(data.workflow.state==='awaiting_choice'){
     if(!await page.locator('[data-reader="adopt"]').isVisible())await page.locator('.rw-next [data-reader="decisions"]').click();
     const previous=await page.locator('[data-reader="adopt-next"]').getAttribute('data-id');await page.locator('[data-reader="adopt-next"]').click();await page.locator('[data-reader="adopt-next"][data-id="'+previous+'"]').waitFor({state:'detached'});
    }else if(data.workflow.action==='finalize_assets'){
     await page.locator('[data-reader="assets"]').click();
     while(await page.locator('[data-reader="finalize-master"]').count()){
      const button=page.locator('[data-reader="finalize-master"]').first();const assetId=await button.getAttribute('data-id');await button.click();await page.locator('[data-reader="finalize-master"][data-id="'+assetId+'"]').waitFor({state:'detached'});
     }
     await page.locator('.rw-next [data-reader="advance"]').click();
    }else if(data.workflow.state==='ready')await page.locator('.rw-next [data-reader="advance"]').click();
    else throw Error('Unexpected workflow '+JSON.stringify(data.workflow));
    await page.waitForTimeout(800);
   }
   if(await page.getByRole('dialog').count()){assert.notEqual(await page.getByRole('dialog').getAttribute('aria-label'),'操作未完成');await page.locator('[data-close]').click();}await page.locator('[data-reader="reading"]').first().click();
   assert.ok(await page.locator('.rw-shot').count());
   await page.locator('[data-reader="shot-refine"]').first().click();
   await page.locator('#rw-instruction').fill('保持镜头数量，只强化这个镜头的细节。');
   await page.locator('[data-reader="refine"]').click();
   await page.locator('[data-reader="adopt"]').waitFor({timeout:15000});
   assert.equal(await page.locator('.rw-proposal-part').count(),1);
   await page.locator('[data-reader="adopt"]').click();
  }
  await page.locator('#rw-font').selectOption('20');
  await page.locator('[data-reader="theme"]').click();
  await page.locator('[data-reader="focus"]').click();
  await page.reload();await page.locator('#reader-workspace.rw-night.rw-focus').waitFor();
  assert.equal(await page.locator('#rw-font').inputValue(),'20');
  await page.locator('[data-reader="theme"]').click();
  await page.screenshot({path:'.validation/reader-'+system.toLowerCase()+'-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
  await page.screenshot({path:'.validation/reader-'+system.toLowerCase()+'-mobile.png',fullPage:true});
  await page.locator('[data-reader="cost"]').click();await page.getByRole('dialog').waitFor();await page.locator('[data-close]').click();
  if(system==='B'){
   const base='http://127.0.0.1:'+port;
   async function post(path,data={}){const r=await page.request.post(base+path,{data,headers:{'x-studio-client':'local-ui'}});assert.equal(r.status(),200,await r.text());return r.json()}
   async function result(job){for(let i=0;i<150;i++){const r=await(await page.request.get(base+'/api/jobs/'+job.id)).json();if(!['running','queued'].includes(r.state)){assert.equal(r.state,'succeeded');return r.result;}await page.waitForTimeout(100)}throw Error('Demo task timeout')}
   const made=await post('/api/projects',{title:'32秒节奏检查',source:'单场雨夜。',targetDuration:32,preset:'vertical'}),id=made.project.id,url='/api/projects/'+id;
   for(const stage of ['B0','B1']){const proposal=await result(await post(url+'/propose/'+stage,{}));await post(url+'/proposals/'+proposal.id+'/adopt');if(stage==='B0'){const d=await(await page.request.get(base+url)).json();await post(url+'/objects/style/'+d.style.id+'/finalize',{expectedVersion:d.style._version})}}
   const d=await(await page.request.get(base+url)).json();assert.equal(d.workflow.action,'review_timing');assert.equal(d.scenes[0].targetDuration,32);
   await page.evaluate(id=>localStorage.setItem('system-b-project',id),id);await page.reload();await page.locator('.rw-next [data-reader="advance"]').click();await page.locator('.nav-button.active[data-stage="B1"]').waitFor({state:'attached'});await page.locator('#page-content').waitFor();
  }
  assert.deepEqual(errors,[]);results.push({system,errors,passed:true});await page.close();
 }
 await browser.close();fs.writeFileSync('.validation/reader-smoke-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}
run().catch(e=>{console.error(e);process.exit(1)});
