const assert=require('node:assert/strict');
const fs=require('node:fs');
async function main(){
 const code=fs.readFileSync('system-b/static/shot_text.js','utf8');
 const {selectedShots,selectedShotText}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
 const data={project:{title:'检查',activeShootingId:'new'},scenes:[{id:'one',order:0,title:'开盒',shootingScriptId:'old',presentationFreshness:'broken'},{id:'two',order:1,title:'预演',shootingScriptId:'new'},{id:'gone',order:2,status:'archived'}],
  shots:[{id:'first',sceneId:'one',order:0,actionLine:'阿青开盒',dialogueIds:['line'],presentationId:'main',status:'locked'},{id:'preview',sceneId:'two',order:2,actionLine:'小林拿到玉牌',presentationId:'preview'},{id:'deleted',sceneId:'one',status:'archived'},{id:'archived-scene',sceneId:'gone'}],
  shooting_scripts:[{id:'old',payload:{continuity:{entities:{a:{name:'阿青'}}},dialogueLines:[{id:'line',speakerId:'a',text:'旧拍摄版的准确台词'}]}},{id:'new',payload:{presentationPlan:[{id:'preview',kind:'preview',reason:'先预演再回切'},{id:'main'}],continuity:{entities:{a:{name:'另一个名字'}}},dialogueLines:[{id:'line',speakerId:'a',text:'不能混入的其他版本'}]}}]};
 const ids=['deleted','missing','first','preview','first','archived-scene'];
 assert.deepEqual(selectedShots(data,ids).map(s=>s.id),['preview','first']);
 const text=selectedShotText(data,ids);
 assert.ok(text.indexOf('小林拿到玉牌')<text.indexOf('阿青开盒'));
 assert.ok(text.includes('预演 · 先预演再回切')&&text.includes('阿青：旧拍摄版的准确台词')&&text.includes('待复核'));
 assert.ok(!text.includes('另一个名字')&&!text.includes('不能混入的其他版本'));
 assert.equal(selectedShotText(data,[]),'');
 console.log('storyboard text: playback order, versioned dialogue, archived filtering and deduplication passed');
}
main().catch(e=>{console.error(e);process.exitCode=1});
