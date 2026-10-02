const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');

async function main(){
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const folder='.validation/codex-ui-20260928';fs.mkdirSync(folder,{recursive:true});
 const results=[];const errors=[];
 try{
  for(const [system,port] of [['A',18851],['B',18852]]){
   const page=await browser.newPage({viewport:{width:1440,height:1000}});
   page.on('pageerror',e=>errors.push(e.message));
   // UI-only fixture; live host authentication is verified separately.
   await page.route('**/api/codex/status*',r=>r.fulfill({json:{ready:true,version:'codex-cli 0.157.1',model:'本机默认模型',reasoning:'medium'}}));
   await page.goto(`http://127.0.0.1:${port}`);await page.locator('#reader-workspace').waitFor();
   await page.evaluate(async system=>{const c=await import('/static/common.js');await c.settingsDialog(system)},system);
   await page.locator('[name="provider"]').selectOption('codex_cli');
   assert.equal(await page.locator('[name="apiKey"]').count(),0);
   assert.equal(await page.locator('[name="inputPerMillion"]').count(),0);
   assert.equal(await page.locator('[name="maxTokens"]').count(),0);
   assert.equal(await page.locator('[name="timeout"]').inputValue(),'600');
   assert.equal(await page.locator('[name="codexPreset"]').count(),1);
   await page.locator('[name="codexPreset"]').selectOption('gpt-5.6-sol-high');
   assert.equal(await page.locator('[name="model"]').inputValue(),'gpt-5.6-sol');
   assert.equal(await page.locator('[name="codexReasoning"]').inputValue(),'high');
   assert.equal(await page.locator('[name="contextCharacters"]').inputValue(),'96000');
   await page.locator('[data-codex-status]').click();
   await page.locator('[data-codex-result]').filter({hasText:'已登录'}).waitFor();
   await page.screenshot({path:`${folder}/${system}-settings-desktop.png`,fullPage:true});
   await page.setViewportSize({width:390,height:844});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:`${folder}/${system}-settings-mobile.png`,fullPage:true});
   await page.locator('[form="settings-form"]').click();
   await page.locator('#settings-form').waitFor({state:'hidden'});
   const cfg=await (await page.request.get(`http://127.0.0.1:${port}/api/settings`)).json();
   assert.equal(cfg.llm.provider,'codex_cli');assert.equal(cfg.llm.timeout,600);
   assert.equal(cfg.llm.model,'gpt-5.6-sol');assert.equal(cfg.llm.codexReasoning,'high');
   assert.equal(cfg.llm.contextCharacters,96000);
   assert.equal(Object.hasOwn(cfg.llm,'codexPreset'),false);
   await page.evaluate(async()=>{const c=await import('/static/common.js');await c.costDialog('ui-fixture')});
   await page.locator('[data-codex-sessions]').click();
   await page.getByText('首次真实创作后，会话会自动保存在这里。').waitFor();
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:`${folder}/${system}-sessions-mobile.png`,fullPage:true});
   await page.locator('[data-close]').click();
   await page.evaluate(async system=>{const c=await import('/static/common.js');void c.modelRoutingDialog(system)},system);
   await page.locator('[name="role"]').selectOption('reviewer');
   await page.locator('[form="modal-form"]').click();
   await page.locator('#role-model-form').waitFor();
   assert.equal(await page.locator('[name="provider"]').inputValue(),'codex_cli');
   await page.locator('[name="codexPreset"]').selectOption('gpt-5.6-sol-high');
   assert.equal(await page.locator('[name="model"]').inputValue(),'gpt-5.6-sol');
   assert.equal(await page.locator('[name="codexReasoning"]').inputValue(),'high');
   assert.equal(await page.locator('[name="contextCharacters"]').inputValue(),'96000');
   await page.locator('[form="role-model-form"]').click();
   await page.locator('#role-model-form').waitFor({state:'hidden'});
   await page.waitForTimeout(250);
   const routed=await (await page.request.get(`http://127.0.0.1:${port}/api/settings`)).json();
   assert.equal(routed.models.reviewer.model,'gpt-5.6-sol');assert.equal(routed.models.reviewer.codexReasoning,'high');assert.equal(routed.models.reviewer.contextCharacters,96000);
   // Return only these isolated server settings to demo, preserving user data.
   const response=await page.request.put(`http://127.0.0.1:${port}/api/settings`,{headers:{'x-studio-client':'local-ui'},data:{llm:{provider:'demo'},models:{reviewer:{provider:'demo'}}}});
   assert.ok(response.ok());results.push({system,desktop:true,mobile:true,gpt56HighPreset:true,roleRouting:true,sessionView:true});await page.close();
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(`${folder}/browser-verification.json`,JSON.stringify({passed:true,results,errors},null,2));
  console.log(JSON.stringify({passed:true,results,errors}));
 }finally{await browser.close()}
}
main().catch(e=>{console.error(e);process.exitCode=1});
