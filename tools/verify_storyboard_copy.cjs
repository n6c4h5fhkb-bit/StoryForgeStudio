// Use only the offline fixture prepared by seed_storyboard_copy_check.py.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
async function main(){
 const dir='.validation/storyboard-copy', fixture=JSON.parse(fs.readFileSync(dir+'/fixture.json','utf8'));
 const url='http://127.0.0.1:18852',browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],mutations=[];
 const checks=[];
 try{
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))mutations.push(r.url());});
  await page.addInitScript(project=>{
   localStorage.setItem('system-b-project',project);
   Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{if(window.failCopy)throw new Error('denied');window.copiedText=value;}}});
  },fixture.projectId);
  await page.goto(url);await page.locator('.rw-shot').first().waitFor();
  const boxes=fixture.shots.map(s=>page.locator(`[data-shot-select="${s.id}"]`));
  await boxes[1].check();await boxes[3].check();
  assert.equal(await page.locator('[data-reader="refine"]').isDisabled(),true,'locked shot must remain protected');
  await page.locator('[data-reader="copy-shots"]').click();
  let copied=await page.evaluate(()=>window.copiedText);
  assert.ok(copied.includes(fixture.shots[1].actionLine)&&copied.includes(fixture.shots[3].actionLine));
  assert.ok(!copied.includes(fixture.shots[0].actionLine)&&!copied.includes(fixture.shots[2].actionLine));
  assert.ok(copied.indexOf('镜头 02')<copied.indexOf('镜头 04'));
  checks.push('noncontiguous_and_locked_selection_copy');
  await page.locator(`[data-reader="scene"][data-id="${fixture.shots[4].sceneId}"]`).click();
  await boxes[4].check();await page.locator('[data-reader="copy-shots"]').click();
  copied=await page.evaluate(()=>window.copiedText);assert.ok(copied.includes('交接完成。')&&copied.includes('老林'));
  assert.equal(await page.locator('.rw-selection strong').textContent(),'3');
  checks.push('cross_scene_selection_and_versioned_dialogue');
  await page.locator('[data-reader="continuous"]').click();
  assert.equal(await page.locator('.rw-selection').count(),1);
  await page.screenshot({path:dir+'/desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'mobile overflow');
  await page.screenshot({path:dir+'/mobile.png',fullPage:true});
  await page.evaluate(()=>window.failCopy=true);await page.locator('[data-reader="copy-shots"]').click();
  assert.equal(await page.locator('#rw-copy-text').inputValue(),copied);
  assert.ok(await page.locator('#rw-copy-text').evaluate(el=>el.selectionEnd===el.value.length));
  await page.locator('[data-close]').click();
  checks.push('mobile_and_clipboard_denial_fallback');
  await page.locator('[data-reader="clear-shots"]').click();
  assert.equal(await page.locator('[data-reader="copy-shots"]').isDisabled(),true);
  await page.locator(`[data-reader="select-scene"][data-id="${fixture.shots[0].sceneId}"]`).click();
  assert.equal(await page.locator('.rw-selection strong').textContent(),'4');
  await page.locator('#rw-project').selectOption(fixture.otherProjectId);
  await page.waitForFunction(()=>document.querySelector('.rw-next h1')?.textContent==='空项目用于检查选择隔离');
  assert.equal(await page.locator('[data-shot-select]:checked').count(),0);
  await page.locator('#rw-project').selectOption(fixture.projectId);
  await page.waitForFunction(()=>document.querySelector('.rw-selection strong')?.textContent==='4');
  checks.push('select_scene_clear_and_project_isolation');
  assert.deepEqual(errors,[]);assert.deepEqual(mutations,[]);
  checks.push('no_api_mutations_or_model_calls');
  fs.writeFileSync(dir+'/verification.json',JSON.stringify({passed:true,checks},null,2));
  console.log(JSON.stringify({passed:true,checks}));
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
