import {api,esc,form,modal,closeModal,toast,showError,upload,submitJob,confirm} from './common.js';
import {readableBody} from './reader.js';
import {intentNotes,directorNotes} from './directing-notes.js';

const modes={cinema:'电影',series:'剧集',fast_drama:'快节奏短剧'};
const button=(action,label,id='',primary=false)=>`<button type="button" data-studio="${action}" data-id="${esc(id)}" class="${primary?'primary':''}">${esc(label)}</button>`;
const text=value=>esc(typeof value==='string'?value:JSON.stringify(value??'',null,2)).replace(/\n/g,'<br>');
const blockNames=doc=>Object.fromEntries(Object.entries(doc.continuity?.entities||{}).map(([id,value])=>[id,value.name||id]));
const prose=doc=>(doc.scenes||[]).map(scene=>`<section class="rw-proposal-part"><h3>${esc(scene.title||'场次')}</h3>${readableBody({blocks:scene.blocks},blockNames(doc))}${intentNotes(scene,doc.continuity?.entities)}</section>`).join('');
const endpoint=row=>row.mode?`/shooting/${row.id}`:`/novel/drafts/${row.id}`;

export function installStudioReader(reader){
 const link=document.createElement('link');link.rel='stylesheet';link.href='/static/studio-upgrade.css';document.head.append(link);
 const novel=()=>reader.state.data?.project.creationMode==='novel';
 const modern=()=>reader.system==='B'&&reader.state.data?.project.workflowVersion>=2;
 const drafts=()=>novel()?reader.state.data.novelDrafts||[]:[...(reader.state.data?.adopted_scripts||[]),...(reader.state.data?.shooting_scripts||[])];
 const path=suffix=>`/api/projects/${reader.project}${suffix}`;
 const activeId=()=>novel()?reader.state.data.project.activeNovelDraft:(reader.state.data?.project.activeScriptId||reader.state.data?.project.activeShootingId);
 const draftView=()=>novel()||modern()&&(reader.ui.tab==='shooting'||reader.state.data.workflow?.action==='choose_shooting');
 const previousMount=reader.mount.bind(reader),previousDecisions=reader.decisions.bind(reader),previousReading=reader.reading.bind(reader),previousAssets=reader.assets.bind(reader),previousAdvance=reader.advance.bind(reader),previousClick=reader.click.bind(reader),previousCandidates=reader.candidates.bind(reader);
 reader.candidates=()=>draftView()?drafts().filter(row=>row.status==='proposed'&&(row.baseShootingId??null)===((reader.state.data?.project.activeScriptId||reader.state.data?.project.activeShootingId)??null)&&(row.baseDraftId??null)===(reader.state.data?.project.activeNovelDraft??null)):previousCandidates();
 function draftPage(rows,history=false){
  if(!rows.length)return novel()?`<article class="rw-paper"><h2>准备小说改编</h2><p>AI 提出完整正文和改编理由，你阅读后采用。</p>${button('novel-range','选择章节并改编','',true)}</article>`:`<article class="rw-paper"><h2>等待 A 的采用剧本</h2><p>先在 A 比较并采用电影、剧集或短剧版本，再回到 B 完成导演与制作。</p>${button('story-origin','回 A 选择剧本','',true)}</article>`;
  const selected=rows.find(r=>r.id===reader.ui.studioDraft)||rows.find(r=>r.status==='proposed')||rows.find(r=>r.id===activeId())||rows.at(-1);reader.ui.studioDraft=selected.id;
  const doc=selected.payload||{},current=selected.id===activeId();
  return `<div class="rw-choice-tabs">${rows.map((r,i)=>button('draft-view',`${r.mode?modes[r.mode]:'改编剧本'} · ${i+1}${r.id===activeId()?' · 当前采用':''}`,r.id)).join('')}</div><article class="rw-paper" data-read-anchor="${esc(selected.id)}"><header class="rw-pagehead"><span>${selected.mode?modes[selected.mode]:'小说改编'} · ${current?'当前采用':selected.status==='adopted'?'历史版本':'待选择'}</span><span>${selected.demo?'离线模板，未验证创作质量':''}</span></header><h2>${esc(doc.title||reader.state.data.project.title)}</h2>${doc.summary?`<p>${text(doc.summary)}</p>`:''}${(selected.issues||[]).length?`<div class="rw-warning">${selected.issues.map(i=>`<p>${text(i.location||i.code)}：${text(i.message)}</p>`).join('')}</div>`:''}${doc.storyChanges?.length?`<div class="rw-warning"><strong>涉及故事事实的修改，需先确认故事新版本</strong>${doc.storyChanges.map(x=>`<p>${text(x)}</p>`).join('')}</div>`:''}<div class="rw-prose">${doc.presentationPlan?.some(x=>x.kind!=='main')?`<details open><summary>观看顺序（含明确的预演、倒叙或跳时）</summary><ol>${doc.presentationPlan.map(item=>`<li>${esc({main:'正篇',preview:'预演',flashback:'倒叙',time_jump:'跳时'}[item.kind]||item.kind)}：${text(doc.continuity.events.find(e=>e.id===item.eventId)?.action)}${item.reason?' · '+text(item.reason):''}</li>`).join('')}</ol></details>`:''}${prose(doc)}</div><details><summary>主要改动与来源</summary>${(doc.changeReasons||[]).map(x=>`<p>${text(x)}</p>`).join('')}<ul>${(doc.sourceMapping||[]).map(x=>`<li>${esc(x.sourceId)}：${text(x.reason)}</li>`).join('')}</ul><p>${selected.start?'实际阅读章节 '+selected.start+'–'+selected.end:'故事版本 '+(selected.sourceHash||'').slice(0,12)}</p></details><footer class="rw-decision-actions">${novel()&&selected.passed&&!doc.storyChanges?.length&&!current&&selected.status!=='rejected'?button('draft-adopt-next','采用并继续',selected.id,true)+button('draft-adopt','仅采用',selected.id):''}${novel()&&selected.status==='proposed'?button('draft-reject','这版不合适',selected.id):''}${button(novel()?'novel-range':'story-origin',novel()?'提出修改 / 换一版':'回 A 修改情节',selected.id)}</footer></article>`;
 }
 reader.decisions=()=>draftView()?draftPage(reader.candidates()):previousDecisions();
 reader.reading=()=>{
  if(modern()&&reader.ui.tab==='shooting')return draftPage(drafts(),true);
  if(modern()&&reader.ui.continuous){const d=reader.state.data,doc=drafts().find(r=>r.id===activeId())?.payload,order=new Map((doc?.presentationPlan||[]).map((item,i)=>[item.id,i])),scenes=new Map(reader.activeRows().map(s=>[s.id,s])),shots=d.shots.filter(s=>s.status!=='archived'&&scenes.has(s.sceneId)).sort((a,b)=>(order.get(a.presentationId)??1e9)-(order.get(b.presentationId)??1e9)||a.order-b.order),groups=[];for(const shot of shots){const group=groups.at(-1);if(group?.sceneId===shot.sceneId)group.shots.push(shot);else groups.push({sceneId:shot.sceneId,shots:[shot]});}if(groups.length)return reader.selectionBar()+groups.map(g=>reader.boardPage(scenes.get(g.sceneId),g.shots)).join('');}
  return previousReading();
 };
 const readingWithDirections=reader.reading;
 reader.reading=()=>{
  const d=reader.state.data,requests=(d?.change_requests||[]).filter(row=>row.status==='pending'&&row.sourceScriptVersionId===d.project.sourceScriptVersionId);
  const notice=requests.length?`<aside class="rw-warning"><p>有场次需要在 A 补充情节，其余内容已保留。</p>${requests.map(row=>`<details><summary>情节修改建议</summary><p>${text(row.instruction)}</p><p>${text(row.reason)}</p></details>${button('request-to-a','回 A 查看修改建议',row.id)}`).join('')}</aside>`:'';
  return notice+readingWithDirections();
 };
 const previousBProposal=reader.bProposal.bind(reader);
 function taskCard(task){
  const d=reader.state.data,clips=(task.renderIds||[]).map(id=>d.renders.find(row=>row.id===id)).filter(Boolean),adopted=clips.length===task.shotIds.length&&clips.every(row=>row.selected&&row.adoption),stale=task.freshness==='broken';
  return `<section class="rw-proposal-part"><p>${esc(task.focus)} · ${task.shotIds.length} 镜 · ${Number(task.duration).toFixed(1)} 秒</p><p class="rw-muted">${stale?'依据已变化，请重新准备':adopted?'整段已采用，区间与末态已记录':clips.length?'已标定区间，等待连续情节审片与采用':task.generationFileId?'已返回视频，等待标定区间':task.capabilitiesVerified?'按已配置的平台限制检查':'平台限制尚未完整配置，可先导出任务'}</p>${!stale?button('task-render','费用预览 → 生成',task.id)+button('task-import',task.generationFileId?'查看 / 调整镜头区间':'导入已有单元视频',task.id)+(clips.length===task.shotIds.length?button('task-sequence-review','AI 连续情节审片',task.id)+button('task-adopt',adopted?'复核整段采用':'查看并成组采用',task.id,true):''):''}</section>`;
 }
 reader.bProposal=c=>c.workflowVersion===2?(directorNotes(c.payload?.direction?.directingPlan)||`<p>${text(c.payload?.rationale||'')}</p>${c.payload?.direction?`<p>观看重点：${text(c.payload.direction.dramaticFunction)}</p><p>表演与调度：${text(c.payload.direction.blocking?.description)}</p>`:''}`)+`${(c.issues||[]).length?`<div class="rw-warning">${c.issues.map(x=>`<p>${text(x.location||x.code)}：${text(x.message)}</p>`).join('')}</div>`:''}`+previousBProposal(c):previousBProposal(c);
 reader.assets=()=>{
  if(!modern())return previousAssets();
  const d=reader.state.data,used=new Set(d.scenes.filter(s=>s.status!=='archived').flatMap(s=>s.requiredImageVariantIds||s.requiredVariantIds||[]));
  const masters=new Set(d.variants.filter(v=>used.has(v.id)).map(v=>v.masterId));
  for(const master of d.masters)if(masters.has(master.id)&&master.defaultVariantId)used.add(master.defaultVariantId);
  const variants=d.variants.filter(v=>used.has(v.id)&&(v.requiresImage||v.referenceFileId)).sort((a,b)=>Number(a.id!==d.masters.find(m=>m.id===a.masterId)?.defaultVariantId)-Number(b.id!==d.masters.find(m=>m.id===b.masterId)?.defaultVariantId));
  const stateOnly=new Set(d.scenes.filter(s=>s.status!=='archived').flatMap(s=>s.requiredVariantIds||[]));const optionalStates=d.variants.filter(v=>stateOnly.has(v.id)&&!v.requiresImage&&!v.referenceFileId&&d.masters.find(m=>m.id===v.masterId)?.kind==='prop'&&Object.keys(v.claims||{}).some(key=>['lid','open','closed','damage','damaged','@contents','contents','开合','损坏','内容物'].includes(key)));
  return `<article class="rw-paper"><h2>实际入画素材</h2><p>人物母图使用正常中性表情；道具独立，场景保留固定布局。笑怒、拿放和开合由分镜表达。缺图只影响相关任务。</p><p>${esc(d.style.name)} · ${esc(d.style.aspectRatio)} <button data-action="choose-aspect">画幅</button> <button data-action="edit-style">视觉风格</button></p>${d.style.status!=='locked'?`<button data-reader="finalize-style" data-id="${esc(d.style.id)}">采用当前视觉风格</button>`:''}${variants.map(v=>{const master=d.masters.find(m=>m.id===v.masterId),file=d.files.find(f=>f.id===v.referenceFileId);return `<section class="studio-asset"><div>${file?`<img src="${esc(file.url)}" alt="${esc(master?.name||'')} · ${esc(v.name)}">`:'<div class="rw-noimage">待准备实际参考图</div>'}</div><div><h3>${esc(master?.name||'')} · ${esc(v.name)}</h3><p>${text(master?.freezeString)}</p>${Object.keys(v.claims||{}).length?`<p>本镜状态：${text(v.claims)}</p>`:''}<p class="rw-muted">${v.visualReview?'已记录视觉核对依据':'尚未查看并确认实际图片'}</p>${button('reference-generate',file?'生成新候选':'费用预览 → AI 补图',v.id)}${button('reference',file?'核对 / 更换参考图':'上传并核对',v.id)}${file?button('reference-existing','复用项目图片',v.id):button('reference-existing','选择已有图片',v.id)}</div></section>`;}).join('')||'<p>先采用导演分镜，系统会筛出真正入画的状态；无需提前把全书素材都生成。</p>'}<h3>生成单元</h3>${(d.generation_tasks||[]).filter(task=>!reader.selectedRow()||task.shotIds.some(id=>d.shots.find(shot=>shot.id===id)?.sceneId===reader.selectedRow().id)).map(taskCard).join('')}${button('key-scenes','选择关键场次拍法')}${optionalStates.length?`<details><summary>关键道具状态按需补参考图（默认复用母图）</summary>${optionalStates.map(v=>`<p>${esc(d.masters.find(m=>m.id===v.masterId)?.name||'道具')} · ${text(v.claims)} ${button('reference-generate','费用预览 → 补状态图',v.id)}</p>`).join('')}</details>`:''}${button('make-tasks','将当前场分镜组成生成单元')}${button('sequence-review','连续情节审片')}${button('production','查看视频与采用区间')}</article>`;
 };
 reader.mount=()=>{
  previousMount();const root=document.querySelector('#reader-workspace');if(!root)return;
  if(reader.system==='A')root.querySelector('.rw-header-actions')?.insertAdjacentHTML('afterbegin',button('new-novel','小说改编'));
  if(reader.system==='B'&&!modern()&&reader.state.data)root.querySelector('.rw-header-actions')?.insertAdjacentHTML('afterbegin',button('story-origin','回 A 选择剧本'));
  if(modern()){
   root.querySelector('.rw-eyebrow').textContent='采用剧本 → 导演分镜 → 素材与制作';
   root.querySelector('.rw-tabs')?.insertAdjacentHTML('afterbegin',button('shooting','采用剧本与历史'));
   root.querySelector('.rw-tabs [data-reader="assets"]').textContent='素材';
   root.querySelector('.rw-tools')?.insertAdjacentHTML('beforebegin',`<div class="studio-bar"><span>呈现：${esc(modes[reader.state.data.project.presentationMode]||'未选择')}</span>${button('story-origin','回 A 比较')}${button('story-change','向 A 提出情节修改')}${button('key-scenes','选择关键拍法')}${button('import-story','导入采用剧本')}${button('production','生成与审片')}</div>`);
  }
  if(novel())root.querySelector('.rw-tools')?.insertAdjacentHTML('beforebegin',`<div class="studio-bar"><span>已记录 ${reader.state.data.novelSource?.readRanges?.length||0} 次阅读范围 · 共 ${reader.state.data.novelSource?.chapters?.length||0} 个章节单元</span>${button('novel-range','选择章节 / 局部改编')}</div>`);
  if(modern()){const selected=reader.candidates().find(c=>c.id===reader.ui.candidate)||reader.candidates()[0];if(selected?.workflowVersion===2&&!selected.passed)root.querySelectorAll('[data-reader=adopt],[data-reader=adopt-next]').forEach(el=>el.disabled=true);}
  root.querySelectorAll('[data-studio]').forEach(el=>{if(reader.busy.has(reader.project))el.disabled=true;});
 };
 async function run(suffix,data){
  const out=await reader.job(suffix,data);reader.ui.tab='decisions';reader.ui.reviewIds=out?.proposal?[out.proposal.id]:out?.id?[out.id]:[];reader.ui.studioDraft=out?.shootingScript?.id||out?.novelDraft?.id||out?.id;reader.mount();return out;
 }
 reader.advance=async()=>{
  const w=reader.state.data?.workflow;
  if(['choose_story_source','update_story_source'].includes(w?.action)){const source=reader.state.data.project.sourceProjectId;location.assign('/a/'+(source?'?project='+encodeURIComponent(source):''));return;}
  if((novel()||modern())&&w?.state==='ready')return run('/advance',{advanceMode:'until_choice'});
  if(w?.action==='choose_shooting'||w?.action==='choose_novel'){reader.ui.tab='decisions';reader.mount();return;}
  return previousAdvance();
 };
 reader.click=async e=>{
  if(novel()&&e.target.closest('[data-reader="refine"]')){
   try{const row=reader.selectedRow(),instruction=document.getElementById('rw-instruction')?.value.trim();if(!instruction)return toast('请写一句修改方向。',true);const active=drafts().find(d=>d.id===activeId());await run('/novel/propose',{start:active.start,end:active.end,instruction,sceneIds:[row.externalStorySceneId||reader.aNode(row)?.body.storySceneId]});}catch(error){showError(error)}return;
  }
  return previousClick(e);
 };
 async function createNovel(){
  const root=modal('从小说开始改编',`<p>上传 TXT 或粘贴正文。系统按实际阅读范围改编，先从一个章节单元开始。</p><form id="novel-create"><label>作品名<input name="title" required></label><label>小说 TXT<input id="novel-file" type="file" accept=".txt"></label><label>正文<textarea name="text" rows="12" required></textarea></label><p id="novel-file-note" class="rw-muted"></p><p id="novel-error" role="alert"></p></form>`,`<button form="novel-create" type="submit" class="primary">保存并开始改编</button>`,true);let filename;
  root.querySelector('#novel-file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>100*1024*1024)throw Error('TXT 超过 100 MiB');const bytes=await file.arrayBuffer();let value;try{value=new TextDecoder('utf-8',{fatal:true}).decode(bytes)}catch{value=new TextDecoder('gb18030',{fatal:true}).decode(bytes)}filename=file.name;root.querySelector('[name=text]').value=value;if(!root.querySelector('[name=title]').value)root.querySelector('[name=title]').value=file.name.replace(/\.txt$/i,'');root.querySelector('#novel-file-note').textContent=`已载入 ${file.name} · ${value.length} 字符`;}catch(error){root.querySelector('#novel-error').textContent=error.message}};
  root.querySelector('form').onsubmit=async e=>{e.preventDefault();const submit=root.querySelector('[type=submit]');submit.disabled=true;try{const out=await api('/api/novels','POST',{title:root.querySelector('[name=title]').value,text:root.querySelector('[name=text]').value,filename});closeModal();await reader.selectProject(out.project.id);await reader.advance();}catch(error){if(root.isConnected)root.querySelector('#novel-error').textContent=error.message;else showError(error);submit.disabled=false}};
 }
 function referenceBoundary(kind,stateful){
  if(kind==='character')return {controls:['人物身份','脸部特征','发型','体型与轮廓','已声明的基础服装与外观',...(stateful?['拍摄稿声明的服装、伤势与可见状态']:[])],exclude:['背景','摄影机角度与构图','姿势','表情','光线','未声明的手持物和随身物']};
  if(kind==='location')return {controls:['空间布局','建筑形制','固定入口与结构',...(stateful?['拍摄稿声明的场景状态']:[])],exclude:['人物','临时道具','人物姿势','临时光线、天气与烟雾','摄影机角度与构图']};
  return {controls:['道具形制','材质','颜色与比例',...(stateful?['拍摄稿声明的开合、损坏与内容物状态']:[])],exclude:['背景','持有者','周边物体','摆放位置','摄影机角度与构图']};
 }
 const boundaryList=value=>String(value||'').split(/[\n,，;；]+/).map(x=>x.trim()).filter(Boolean);
 async function reference(id,existing,suppliedFile){
  const d=reader.state.data,v=d.variants.find(x=>x.id===id),master=d.masters.find(x=>x.id===v.masterId);let file=suppliedFile;
  if(file){}else if(existing){const images=d.files.filter(f=>/\.(png|jpg|jpeg|webp)$/i.test(f.filename||f.path));if(!images.length)return toast('项目还没有图片，先上传实际参考图。',true);const selection=await form('选择项目中的图片',[{name:'fileId',label:'图片',type:'select',options:images.map(f=>({value:f.id,label:f.filename}))}],{fileId:images[0].id});if(!selection)return;file=images.find(x=>x.id===selection.fileId);}else file=await upload(reader.project,'.png,.jpg,.jpeg,.webp');if(!file)return;
  const roles=v.roles||['identity'],existingBoundary=v.visualReview?.controlBindings?.[roles[0]],defaults=existingBoundary?{controls:existingBoundary.controls,exclude:existingBoundary.excludeInheritance}:referenceBoundary(master?.kind,Object.keys(v.claims||{}).length>0);
  const result=await form('核对实际参考图',[{name:'evidence',label:'观察依据（身份、状态；背景是否夹带其他道具）',type:'textarea',rows:3,required:true},{name:'controls',label:'这张图只控制什么（每行一项）',type:'textarea',rows:3,required:true},{name:'excludeInheritance',label:'生成时明确不继承什么（每行一项）',type:'textarea',rows:3,required:true},{name:'confirmed',label:'已查看图片，确认适用于所列状态和职责',type:'checkbox'}],{evidence:v.visualReview?.evidence||'',controls:defaults.controls.join('\n'),excludeInheritance:defaults.exclude.join('\n')},`<img class="studio-review-image" src="${esc(file.url)}" alt="待核对的实际图片"><p>所需状态：${text(v.claims||{})}</p><p>职责：${esc(roles.join(' / '))}</p><p>参考图只提供所列视觉属性；旧背景、姿势、表情和未声明道具不会自动继承。</p>`,'采用参考图');if(!result)return;
  const binding={controls:boundaryList(result.controls),excludeInheritance:boundaryList(result.excludeInheritance)},controlBindings=Object.fromEntries(roles.map(role=>[role,binding]));
  await api(path(`/assets/${id}/review-reference`),'POST',{evidence:result.evidence,confirmed:result.confirmed,fileId:file.id,roles,controlBindings,expectedVersion:v._version});await reader.refresh();
 }
 document.addEventListener('click',async e=>{
  const el=e.target.closest('[data-studio]');if(!el||el.disabled)return;e.preventDefault();e.stopPropagation();const action=el.dataset.studio,id=el.dataset.id;
  try{
   if(action==='story-origin'||action==='convert'){
    const source=reader.state.data?.project.sourceProjectId;
    if(/^\/(a|b)\//.test(location.pathname)){location.assign('/a/'+(source?'?project='+encodeURIComponent(source):''));return;}
    modal('剧本创作与比较已移到 A','<p>请从统一工作室启动，在 A 选择呈现方向并采用版本，再进入 B 制作。旧拍摄稿和素材继续保留。</p>');return;
   }
   if(action==='sequence-review'){
    const scene=reader.selectedRow();if(!scene)return;
    const result=await reader.job('/scenes/'+scene.id+'/sequence-review',{});
    modal('连续情节审片',`<p>${text(result.summary||'已保存连续情节检查记录')}</p>${(result.issues||[]).map(issue=>`<p>${text(issue.message||issue)}</p>`).join('')}<details><summary>观察范围与依据</summary><pre>${esc(JSON.stringify(result,null,2))}</pre></details>`,'',true);return;
   }
   if(action==='task-sequence-review'){
    const task=reader.state.data.generation_tasks.find(row=>row.id===id),sceneId=reader.state.data.shots.find(shot=>shot.id===task?.shotIds?.[0])?.sceneId;
    if(!sceneId)return toast('请先采用本段分镜。',true);
    const result=await reader.job('/scenes/'+sceneId+'/sequence-review',{taskId:id});
    modal('这段视频的连续情节审片',`<p>${text(result.summary||'已保存连续情节检查记录')}</p>${(result.issues||[]).map(issue=>`<p>${text(issue.message||issue)}</p>`).join('')}<details><summary>观察范围与依据</summary><pre>${esc(JSON.stringify(result,null,2))}</pre></details>`,'',true);return;
   }
   if(action==='request-to-a'){
    const source=reader.state.data.project.sourceProjectId;
    if(source)location.assign('/a/?project='+encodeURIComponent(source)+'&changeRequest='+encodeURIComponent(id));
    else modal('回 A 完成剧本','<p>请先将此旧项目的原稿关联到 A，再采用并交接。</p>');
    return;
   }
   if(action==='story-change'){
    const source=reader.state.data.project.sourceProjectId,scene=reader.selectedRow();
    if(!source){modal('回 A 完成剧本','<p>此旧项目尚未关联 A。请在 A 导入或整理原稿，采用后交接到此制作分支。</p>');return;}
    const data=await form('向 A 提出情节修改',[{name:'instruction',label:'希望修改什么',type:'textarea',rows:3,required:true}],{},'<p>本场与当前制作版本一起作为修改依据。新剧本仍由你在 A 阅读、比较并采用。</p>','记录并回 A');
    if(data){const request=await api(path('/change-requests'),'POST',{...data,sceneIds:scene?.shootingSceneId?[scene.shootingSceneId]:[],operationId:crypto.randomUUID()});location.assign('/a/?project='+encodeURIComponent(source)+'&changeRequest='+encodeURIComponent(request.id));}return;
   }
   if(action==='key-scenes'){
    const scenes=reader.activeRows(),choices=reader.state.data.project.keySceneChoices||{};
    const fields=scenes.map((scene,index)=>({name:'scene_'+index,label:scene.title,type:'checkbox'})),values=Object.fromEntries(scenes.map((scene,index)=>['scene_'+index,Boolean(choices[scene.id]?.length)]));
    const selected=await form('想比较哪几场的拍法',fields,values,'<p>只为勾选的场次准备两种拍法。其他场次自动完成推荐分镜，也可以之后局部修改。</p>','保存选择');
    if(selected){await api(path(''),'PUT',{keySceneChoices:Object.fromEntries(scenes.filter((scene,index)=>selected['scene_'+index]).map(scene=>[scene.id,['user_selected']]))});await reader.refresh();}return;
   }
   if(action==='new-novel')return await createNovel();
   if(action==='shooting'){reader.ui.tab='shooting';reader.mount();return;}
   if(action==='draft-view'){reader.ui.studioDraft=id;reader.mount();return;}
   if(action==='production'){reader.advanced({stage:'B5',sceneId:reader.selectedRow()?.id});return;}
   if(action==='import-story'){const file=await upload(reader.project,'.json');if(file){const imported=await fetch(file.url).then(r=>r.json());let out;if(imported.format==='ScriptPackage-v1'){const plan=await api(path('/import-script-package/preview'),'POST',imported);if(plan.impacts.length&&!await confirm('更新制作分支',`<p>变化 ${plan.changedSceneIds.length} 场，保留 ${plan.preservedSceneIds.length} 场；相关镜头和媒体需复核，原文件保留。</p>`,'采用并更新'))return;out=await api(path('/import-script-package'),'POST',{package:imported,planHash:plan.planHash});}else out=await api(path('/import-scene-export'),'POST',imported);if(out.url){location.assign(out.url);return;}await reader.refresh();}return;}
   if(action==='convert'){
    const rows=drafts().find(r=>r.id===activeId())?.payload.scenes||[];
    const data=await form('选择呈现方向',[{name:'mode',label:'呈现形态',type:'select',options:Object.entries(modes).map(([value,label])=>({value,label}))},{name:'sceneId',label:'修改范围',type:'select',options:[{value:'',label:'生成完整拍摄版'},...rows.map(s=>({value:s.id,label:'仅修改：'+s.title}))]},{name:'instruction',label:'希望改变什么（可留空）',type:'textarea',rows:3}],{mode:reader.state.data.project.presentationMode||'fast_drama'},'<p>画幅独立设置。旧稿和当前采用版会保留，新结果由你选择。</p>','准备候选');if(data)await run('/shooting/propose',{...data,sceneIds:data.sceneId?[data.sceneId]:[],newCandidate:crypto.randomUUID()});return;
   }
   if(action==='novel-range'){
    const pr=reader.state.data.project,active=drafts().find(d=>d.id===activeId()),chapters=reader.state.data.novelSource.chapters;
    const data=await form('选择阅读与改编范围',[{name:'start',label:'起始章节单元',type:'number',required:true},{name:'end',label:'结束章节单元',type:'number',required:true},{name:'instruction',label:'本轮改编或修订方向',type:'textarea',rows:3}],{start:Math.min(pr.nextChapter||1,chapters.length),end:Math.min(pr.nextChapter||1,chapters.length)},`<p>共 ${chapters.length} 个章节单元。长章节会按段落或句末自动拆成阅读单元；每次只使用已记录的真实选段。</p>`,'生成候选');if(data)await run('/novel/propose',{...data,newCandidate:crypto.randomUUID()});return;
   }
   if(action==='draft-adopt'||action==='draft-adopt-next'){
     const row=drafts().find(r=>r.id===id);let body={};
     if(row.mode&&reader.state.data.project.workflowVersion>=3){const plan=await api(path(endpoint(row)+'/adoption-preview'));const affected=plan.impacts?.reduce((sum,x)=>sum+x.shotsToReview,0)||0,media=plan.impacts?.reduce((sum,x)=>sum+x.rendersAffected,0)||0;if(!await confirm('采用这版拍摄稿',`<p>改变 ${plan.changedStorySceneIds.length} 场，保留 ${plan.preservedStorySceneIds.length} 场。</p><p>需要复核 ${affected} 个既有镜头，影响 ${media} 个已有素材；未变化内容继续保留。</p>`,'确认采用'))return;body={planHash:plan.planHash};}
     el.disabled=true;await api(path(endpoint(row)+'/adopt'),'POST',body);reader.ui.tab='reading';await reader.refresh();toast('已采用，旧版本仍保留。');if(action==='draft-adopt-next')await reader.advance();return;
   }
   if(action==='draft-reject'){
    const row=drafts().find(r=>r.id===id),data=await form('记录本轮修改方向',[{name:'reason',label:'哪里需要改',type:'textarea',rows:3}],{});if(data){await api(path(endpoint(row)+'/reject'),'POST',data);await reader.refresh();}return;
   }
   if(action==='reference-generate'){
    const variant=reader.state.data.variants.find(v=>v.id===id),data={assetId:variant.masterId,variantId:id,quality:'proxy',forceStateReference:!variant.requiresImage},preview=await api(path('/assets/dry-run'),'POST',data);
    if(!await confirm('确认本次补图费用',`<p>本次预计 $${Number(preview.estimatedCost).toFixed(4)} ${esc(preview.currency)}${preview.cacheHit?' · 复用已有生成结果':''}。</p><p>先准备稳定身份主图，再补必要状态；生成结果需查看并核对后采用。</p>`,'生成候选'))return;
    const result=await reader.job('/assets/generate',{...data,confirmed:true,planHash:preview.planHash});reader.ui.tab='assets';reader.mount();
    if(result?.fileId)await reference(id,false,reader.state.data.files.find(f=>f.id===result.fileId));return;
   }
   if(action==='reference'||action==='reference-existing')return await reference(id,action==='reference-existing');
   if(action==='task-render'){
    const data={taskIds:[id],quality:'proxy'},preview=await api(path('/generation-tasks/dry-run'),'POST',data);
    if(preview.blocked.length){modal('需要先处理这些问题','<ul>'+preview.blocked.map(x=>`<li>${text(x.message)}</li>`).join('')+'</ul>');return;}
    if(!await confirm('确认本次生成费用',`<p>本批次预计 $${Number(preview.estimatedCost).toFixed(4)} ${esc(preview.currency)}。</p><p>生成后仍需标定实际镜头区间与审片，不会自动采用。</p>`,'开始生成'))return;
    await reader.job('/generation-tasks/execute',{...data,planHash:preview.planHash});reader.ui.tab='assets';reader.mount();return;
   }
   if(action==='task-import'){
    const task=reader.state.data.generation_tasks.find(t=>t.id===id);let file=task.generationFileId?reader.state.data.files.find(f=>f.id===task.generationFileId):await upload(reader.project,'.mp4,.webm,.mov');if(!file)return;
    let cursor=0;const ranges=task.shots.map(shot=>{const start=cursor;cursor+=shot.duration;const render=(task.renderIds||[]).map(id=>reader.state.data.renders.find(row=>row.id===id)).find(row=>row?.shotId===shot.shotId),interval=render?.selected?render.adoption?.interval||render.proposedInterval:render?.proposedInterval;return {...shot,in:interval?.in??start,out:interval?.out??cursor};});
    const fields=ranges.flatMap((r,i)=>[{name:'in_'+i,label:`镜 ${i+1} 实际起点（秒）`,type:'number',step:.001,min:0,required:true},{name:'out_'+i,label:`镜 ${i+1} 实际终点（秒）`,type:'number',step:.001,min:0,required:true}]);const values=Object.fromEntries(ranges.flatMap((r,i)=>[['in_'+i,Number(r.in.toFixed(3))],['out_'+i,Number(r.out.toFixed(3))]]));
    const result=await form('标定生成单元中的镜头区间',fields,values,`<video class="studio-review-image" src="${esc(file.url)}" controls></video><p>数值先按分镜建议时长排列，请观看实际视频后修正。各镜区间可留间隙，不能重叠或倒序。</p>`,'关联到分镜');if(!result)return;
    await api(path(`/generation-tasks/${id}/import`),'POST',{fileId:file.id,ranges:ranges.map((r,i)=>({shotId:r.shotId,in:result['in_'+i],out:result['out_'+i]}))});await reader.refresh();toast('各镜已关联同一视频，进入审片确认实际末态。');return;
   }
   if(action==='task-adopt'){
    const d=reader.state.data,task=d.generation_tasks.find(row=>row.id===id),clips=(task.renderIds||[]).map(renderId=>d.renders.find(row=>row.id===renderId)),file=d.files.find(row=>row.id===task.generationFileId);
    if(!file||clips.some(row=>!row))return toast('先导入视频并标定实际镜头区间。',true);
    const previews=await Promise.all(clips.map(row=>api(path(`/renders/${row.id}/adoption-preview`))));
    const sceneId=d.shots.find(shot=>shot.id===task.shotIds[0])?.sceneId;
    const review=sceneId?await reader.job('/scenes/'+sceneId+'/sequence-review',{taskId:id}):null;
    const interval=row=>row.selected?row.adoption?.interval||row.proposedInterval:row.proposedInterval;
    const rejected=clips.flatMap(row=>(row.gate?.checks||[]).filter(check=>check.state==='fail').map(check=>`镜头 ${row.shotId}：${check.message}`));
    const html=`<video class="studio-review-image" src="${esc(file.url)}" controls></video><p>连续情节审片：${text(review?.summary||'尚无完整观察依据')}</p>${(review?.issues||[]).map(issue=>`<p>${text(issue.message||issue)}</p>`).join('')}<p>请查看整段视频和各切点；后续承接使用每镜采用区间的实际末态。</p>${clips.map((row,index)=>`<details><summary>镜 ${index+1} · ${Number(interval(row).in).toFixed(2)}–${Number(interval(row).out).toFixed(2)} 秒 · 所需末态</summary><pre>${esc(JSON.stringify(previews[index].expectedEndState,null,2))}</pre></details>`).join('')}${rejected.length?`<details open><summary>技术门禁未通过</summary>${rejected.map(message=>`<p>${text(message)}</p>`).join('')}</details>`:''}`;
    const fields=[{name:'observationEvidence',label:'实际观察（动作是否做出、各切点人物和道具状态）',type:'textarea',rows:3,required:true},{name:'confirmExpectedEndStates',label:'已查看各切点，实际末态与上述所需状态一致',type:'checkbox'},{name:'observedEndStates',label:'若有差异，记录实际末态（镜头 ID → 实体 ID → 字段）',type:'json'},...(rejected.length?[{name:'arbitrationReason',label:'技术门禁失败的人工仲裁依据',type:'textarea',rows:2,required:true}]:[]),{name:'replacePinned',label:'允许替换已经固定采用的视频',type:'checkbox'}];
    const data=await form('成组采用这段视频',fields,{observedEndStates:{}},html,'采用整段');
    if(data){await reader.job(`/generation-tasks/${id}/adopt`,{...data,humanReview:true,operationId:crypto.randomUUID()});toast('整段已采用，实际区间和末态已记录。');}return;
   }
   if(action==='make-tasks'){
    const scene=reader.selectedRow(),shots=reader.state.data.shots.filter(s=>s.sceneId===scene?.id&&s.status!=='archived').sort((a,b)=>a.order-b.order);if(!shots.length)return toast('先采用本场分镜。',true);
    const data=await form('组织生成单元',[{name:'grouping',label:'分组',type:'select',options:[{value:'event',label:'同一呈现事件的相邻镜头合为一组'},{value:'single',label:'每镜一组'}]}],{grouping:'event'},'<p>只准备任务文件；实际图片/视频调用仍需费用预览。时长和参考数量按已配置的平台上限检查。</p>','准备任务');if(!data)return;
    const groups=[];for(const shot of shots){const last=groups.at(-1);if(data.grouping==='event'&&last?.presentationId===shot.presentationId)last.shotIds.push(shot.id);else groups.push({shotIds:[shot.id],presentationId:shot.presentationId,focus:shot.actionLine});}
    const out=await api(path('/generation-tasks'),'POST',{shotIds:shots.map(s=>s.id),groups});const blob=new Blob([JSON.stringify(out,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob);await reader.refresh();modal('生成单元已准备',`<p>${esc(out.note)}</p><p>${out.tasks.length} 个单元 · 不同镜头按既定顺序组织。</p><a download="generation-tasks.json" href="${url}">保存任务文件</a>`);setTimeout(()=>URL.revokeObjectURL(url),60000);return;
   }
  }catch(error){showError(error);if(el.isConnected)el.disabled=false;}
 },true);
 // The established media panel uses the same adoption endpoint; add observed
 // interval/state selection only for the versioned shooting workflow.
 if(reader.system==='B')document.addEventListener('click',async e=>{
  const el=e.target.closest('[data-action="select-render"]');if(!el||!modern())return;const render=reader.state.data.renders.find(r=>r.id===el.dataset.id);if(render?.kind!=='clip')return;e.preventDefault();e.stopImmediatePropagation();
  try{const preview=await api(path(`/renders/${render.id}/adoption-preview`));const dialog=form('采用视频与实际末态',[{name:'in',label:'采用起点（秒）',type:'number',step:.001,required:true},{name:'out',label:'采用终点（秒）',type:'number',step:.001,required:true},{name:'observationEvidence',label:'实际末态观察（人物、道具、持有位置、开合）',type:'textarea',rows:3,required:true},{name:'confirmExpectedEndState',label:'已逐项查看，实际末态与拍摄版所需状态一致',type:'checkbox'},{name:'observedEndState',label:'若不一致，在此记录实际末态（实体 ID → 字段值）',type:'json'},{name:'replacePinned',label:'允许替换已固定采用的视频',type:'checkbox'}],{in:Number((render.adoption?.interval.in??render.proposedInterval?.in??0).toFixed(3)),out:Number((render.adoption?.interval.out??render.proposedInterval?.out??preview.duration).toFixed(3)),observedEndState:{}},`<video class="studio-review-image" src="${esc(render.url)}" controls></video><p>请查看采用区间末尾，不能把未采用部分的末帧当作承接依据。</p><details><summary>本镜所需末态（逐项核对）</summary><pre>${esc(JSON.stringify(preview.expectedEndState,null,2))}</pre></details>`,'采用这段');const video=document.querySelector('.modal video'),endInput=document.querySelector('#f-out');const seek=()=>{if(video&&Number(endInput.value)>0)video.currentTime=Math.max(0,Math.min(video.duration||Infinity,Number(endInput.value))-.04);};if(video)video.onloadedmetadata=seek;if(endInput)endInput.onchange=seek;const data=await dialog;if(data){await api(path(`/renders/${render.id}/review`),'POST',{...data,adoptedInterval:{in:data.in,out:data.out},selected:true,humanReview:true,reason:data.observationEvidence});await reader.refresh();}}catch(error){showError(error)}
 },true);
}
