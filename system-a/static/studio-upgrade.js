import {api,esc,form,modal,closeModal,toast,showError,upload,submitJob,confirm} from './common.js';
import {readableBody} from './reader.js';
import {intentNotes} from './directing-notes.js';

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
 const drafts=()=>novel()?reader.state.data.novelDrafts||[]:reader.state.data?.shooting_scripts||[];
 const path=suffix=>`/api/projects/${reader.project}${suffix}`;
 const activeId=()=>novel()?reader.state.data.project.activeNovelDraft:reader.state.data?.project.activeShootingId;
 const draftView=()=>novel()||modern()&&(reader.ui.tab==='shooting'||reader.state.data.workflow?.action==='choose_shooting');
 const previousMount=reader.mount.bind(reader),previousDecisions=reader.decisions.bind(reader),previousReading=reader.reading.bind(reader),previousAssets=reader.assets.bind(reader),previousAdvance=reader.advance.bind(reader),previousClick=reader.click.bind(reader),previousCandidates=reader.candidates.bind(reader);
 reader.candidates=()=>draftView()?drafts().filter(row=>row.status==='proposed'&&(row.baseShootingId??null)===(reader.state.data?.project.activeShootingId??null)&&(row.baseDraftId??null)===(reader.state.data?.project.activeNovelDraft??null)):previousCandidates();
 function draftPage(rows,history=false){
  if(!rows.length)return `<article class="rw-paper"><h2>${novel()?'准备小说改编':'准备拍摄版'}</h2><p>AI 提出完整正文和改编理由，你阅读后采用。选择方向不会覆盖当前采用稿。</p>${button(novel()?'novel-range':'convert',novel()?'选择章节并改编':'生成拍摄版','',true)}</article>`;
  const selected=rows.find(r=>r.id===reader.ui.studioDraft)||rows.toReversed().find(r=>r.status==='proposed'&&r.passed)||rows.toReversed().find(r=>r.status==='proposed')||rows.find(r=>r.id===activeId())||rows.at(-1);reader.ui.studioDraft=selected.id;
  const doc=selected.payload||{},current=selected.id===activeId();
  return `<div class="rw-choice-tabs">${rows.map((r,i)=>button('draft-view',`${r.mode?modes[r.mode]:'改编剧本'} · ${i+1}${r.id===activeId()?' · 当前采用':r.status==='proposed'?(r.passed?' · 可采用':' · 需修复'):''}`,r.id)).join('')}</div><article class="rw-paper" data-read-anchor="${esc(selected.id)}"><header class="rw-pagehead"><span>${selected.mode?modes[selected.mode]:'小说改编'} · ${current?'当前采用':selected.status==='adopted'?'历史版本':selected.passed?'可采用':'需修复'}</span><span>${selected.demo?'离线模板，未验证创作质量':''}</span></header><h2>${esc(doc.title||reader.state.data.project.title)}</h2>${doc.summary?`<p>${text(doc.summary)}</p>`:''}${(selected.issues||[]).length?`<div class="rw-warning">${selected.issues.map(i=>`<p>${text(i.location||i.code)}：${text(i.message)}</p>`).join('')}</div>`:''}${doc.storyChanges?.length?`<div class="rw-warning"><strong>涉及故事事实的修改，需先确认故事新版本</strong>${doc.storyChanges.map(x=>`<p>${text(x)}</p>`).join('')}</div>`:''}<div class="rw-prose">${doc.presentationPlan?.some(x=>x.kind!=='main')?`<details open><summary>观看顺序（含明确的预演、倒叙或跳时）</summary><ol>${doc.presentationPlan.map(item=>`<li>${esc({main:'正篇',preview:'预演',flashback:'倒叙',time_jump:'跳时'}[item.kind]||item.kind)}：${text(doc.continuity.events.find(e=>e.id===item.eventId)?.action)}${item.reason?' · '+text(item.reason):''}</li>`).join('')}</ol></details>`:''}${prose(doc)}</div><details><summary>主要改动与来源</summary>${(doc.changeReasons||[]).map(x=>`<p>${text(x)}</p>`).join('')}<ul>${(doc.sourceMapping||[]).map(x=>`<li>${esc(x.sourceId)}：${text(x.reason)}</li>`).join('')}</ul><p>${selected.start?'实际阅读章节 '+selected.start+'–'+selected.end:'故事版本 '+(selected.sourceHash||'').slice(0,12)}</p></details><footer class="rw-decision-actions">${selected.passed&&!doc.storyChanges?.length&&!current&&selected.status!=='rejected'?button('draft-adopt-next','采用并继续',selected.id,true)+button('draft-adopt','仅采用',selected.id):''}${selected.status==='proposed'&&!selected.passed?button('draft-repair','按问题局部修复',selected.id,true):''}${selected.status==='proposed'?button('draft-reject','这版不合适',selected.id):''}${button(novel()?'novel-range':'convert','提出修改 / 换一版',selected.id)}</footer></article>`;
 }
 reader.decisions=()=>draftView()?draftPage(reader.candidates()):previousDecisions();
 reader.reading=()=>{
  if(modern()&&reader.ui.tab==='shooting')return draftPage(drafts(),true);
  if(modern()&&reader.ui.continuous){const d=reader.state.data,doc=drafts().find(r=>r.id===activeId())?.payload,order=new Map((doc?.presentationPlan||[]).map((item,i)=>[item.id,i])),scenes=new Map(reader.activeRows().map(s=>[s.id,s])),shots=d.shots.filter(s=>s.status!=='archived'&&scenes.has(s.sceneId)).sort((a,b)=>(order.get(a.presentationId)??1e9)-(order.get(b.presentationId)??1e9)||a.order-b.order),groups=[];for(const shot of shots){const group=groups.at(-1);if(group?.sceneId===shot.sceneId)group.shots.push(shot);else groups.push({sceneId:shot.sceneId,shots:[shot]});}if(groups.length)return groups.map(g=>reader.boardPage(scenes.get(g.sceneId),g.shots)).join('');}
  return previousReading();
 };
 const previousBProposal=reader.bProposal.bind(reader);
 reader.bProposal=c=>c.workflowVersion===2?`<p>${text(c.payload?.rationale||'')}</p>${c.payload?.direction?`<p>观看重点：${text(c.payload.direction.dramaticFunction)}</p><p>表演与调度：${text(c.payload.direction.blocking?.description)}</p>`:''}${(c.issues||[]).length?`<div class="rw-warning">${c.issues.map(x=>`<p>${text(x.location||x.code)}：${text(x.message)}</p>`).join('')}</div>`:''}`+previousBProposal(c):previousBProposal(c);
 reader.assets=()=>{
  if(!modern())return previousAssets();
  const d=reader.state.data,used=new Set(d.scenes.filter(s=>s.status!=='archived').flatMap(s=>s.requiredVariantIds||[]));
  const masters=new Set(d.variants.filter(v=>used.has(v.id)).map(v=>v.masterId));
  for(const master of d.masters)if(masters.has(master.id)&&master.defaultVariantId)used.add(master.defaultVariantId);
  const variants=d.variants.filter(v=>used.has(v.id)).sort((a,b)=>Number(a.id!==d.masters.find(m=>m.id===a.masterId)?.defaultVariantId)-Number(b.id!==d.masters.find(m=>m.id===b.masterId)?.defaultVariantId));
  return `<article class="rw-paper"><h2>实际入画素材</h2><p>参考图按镜头所需的身份、状态和职责核对。缺图只影响用到它的任务。</p><p>${esc(d.style.name)} · ${esc(d.style.aspectRatio)} <button data-action="choose-aspect">画幅</button> <button data-action="edit-style">视觉风格</button></p>${d.style.status!=='locked'?`<button data-reader="finalize-style" data-id="${esc(d.style.id)}">采用当前视觉风格</button>`:''}${variants.map(v=>{const master=d.masters.find(m=>m.id===v.masterId),file=d.files.find(f=>f.id===v.referenceFileId);return `<section class="studio-asset"><div>${file?`<img src="${esc(file.url)}" alt="${esc(master?.name||'')} · ${esc(v.name)}">`:'<div class="rw-noimage">待准备实际参考图</div>'}</div><div><h3>${esc(master?.name||'')} · ${esc(v.name)}</h3><p>${text(master?.freezeString)}</p>${Object.keys(v.claims||{}).length?`<p>本镜状态：${text(v.claims)}</p>`:''}<p class="rw-muted">${v.visualReview?'已记录视觉核对依据':'尚未查看并确认实际图片'}</p>${button('reference-generate',file?'生成新候选':'费用预览 → AI 补图',v.id)}${button('reference',file?'核对 / 更换参考图':'上传并核对',v.id)}${file?button('reference-existing','复用项目图片',v.id):button('reference-existing','选择已有图片',v.id)}</div></section>`;}).join('')||'<p>先采用导演分镜，系统会筛出真正入画的状态；无需提前把全书素材都生成。</p>'}<h3>生成单元</h3>${(d.generation_tasks||[]).map(t=>`<section class="rw-proposal-part"><p>${esc(t.focus)} · ${t.shotIds.length} 镜 · ${Number(t.duration).toFixed(1)} 秒</p><p class="rw-muted">${t.freshness==='broken'?'上游已变化，请重新准备':t.generationFileId?'已返回视频，等待标定区间与审片':t.capabilitiesVerified?'按已配置的平台限制检查':'平台限制尚未完整配置，可先导出任务'}</p>${button('task-render','费用预览 → 生成',t.id)}${button('task-import',t.generationFileId?'标定镜头区间':'导入已有单元视频',t.id)}</section>`).join('')}${button('make-tasks','将当前场分镜组成生成单元')}${button('production','进入生成与审片')}</article>`;
 };
 reader.mount=()=>{
  previousMount();const root=document.querySelector('#reader-workspace');if(!root)return;
  if(reader.system==='A')root.querySelector('.rw-header-actions')?.insertAdjacentHTML('afterbegin',button('new-novel','小说改编'));
  if(reader.system==='B'&&!modern()&&reader.state.data)root.querySelector('.rw-header-actions')?.insertAdjacentHTML('afterbegin',button('convert','转换为新拍摄版'));
  if(modern()){
   root.querySelector('.rw-eyebrow').textContent='呈现转换 → 素材 → 分镜与制作';
   root.querySelector('.rw-tabs')?.insertAdjacentHTML('afterbegin',button('shooting','拍摄版与历史'));
   root.querySelector('.rw-tabs [data-reader="assets"]').textContent='素材';
   root.querySelector('.rw-tools')?.insertAdjacentHTML('beforebegin',`<div class="studio-bar"><span>呈现：${esc(modes[reader.state.data.project.presentationMode]||'未选择')}</span>${button('convert','转换 / 局部修改')}${button('import-story','导入 A 剧本')}${button('production','生成与审片')}</div>`);
  }
  if(novel()){const source=reader.state.data.novelSource,done=source?.analysisRanges?.length||0,total=source?.chapters?.length||0;root.querySelector('.rw-tools')?.insertAdjacentHTML('beforebegin',`<div class="studio-bar"><span>已理解 ${done}/${total} 个章节单元</span>${button('novel-range','选择章节 / 局部改编')}${done<total?button('novel-analyze','全书深读（可选）'):''}</div>`)}
  if(modern()){const selected=reader.candidates().find(c=>c.id===reader.ui.candidate)||reader.candidates()[0];if(selected?.workflowVersion===2&&!selected.passed)root.querySelectorAll('[data-reader=adopt],[data-reader=adopt-next]').forEach(el=>el.disabled=true);}
  root.querySelectorAll('[data-studio]').forEach(el=>{if(reader.busy.has(reader.project))el.disabled=true;});
 };
 async function run(suffix,data){
  const out=await reader.job(suffix,data);reader.ui.tab='decisions';reader.ui.reviewIds=out?.proposal?[out.proposal.id]:out?.id?[out.id]:[];reader.ui.studioDraft=out?.shootingScript?.id||out?.novelDraft?.id||out?.id;reader.mount();return out;
 }
 reader.advance=async()=>{
  const w=reader.state.data?.workflow;
  if((novel()||modern())&&w?.state==='ready')return run('/advance',{mode:'until_choice'});
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
  const root=modal('从小说开始改编',`<p>上传 TXT 或粘贴正文。系统先建立章节索引，改编时只深读你选择的范围；全书深读可另行启动并持续复用缓存。</p><form id="novel-create"><label>作品名<input name="title" required></label><label>小说 TXT<input id="novel-file" type="file" accept=".txt"></label><label>正文<textarea name="text" rows="12" required></textarea></label><p id="novel-file-note" class="rw-muted"></p><p id="novel-error" role="alert"></p></form>`,`<button form="novel-create" type="submit" class="primary">保存并准备首段</button>`,true);let filename;
  root.querySelector('#novel-file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>100*1024*1024)throw Error('TXT 超过 100 MiB');const bytes=await file.arrayBuffer();let value;try{value=new TextDecoder('utf-8',{fatal:true}).decode(bytes)}catch{value=new TextDecoder('gb18030',{fatal:true}).decode(bytes)}filename=file.name;root.querySelector('[name=text]').value=value;if(!root.querySelector('[name=title]').value)root.querySelector('[name=title]').value=file.name.replace(/\.txt$/i,'');root.querySelector('#novel-file-note').textContent=`已载入 ${file.name} · ${value.length} 字符`;}catch(error){root.querySelector('#novel-error').textContent=error.message}};
  root.querySelector('form').onsubmit=async e=>{e.preventDefault();const submit=root.querySelector('[type=submit]');submit.disabled=true;try{const out=await api('/api/novels','POST',{title:root.querySelector('[name=title]').value,text:root.querySelector('[name=text]').value,filename});closeModal();await reader.selectProject(out.project.id);await reader.advance();}catch(error){if(root.isConnected)root.querySelector('#novel-error').textContent=error.message;else showError(error);submit.disabled=false}};
 }
 async function reference(id,existing,suppliedFile){
  const d=reader.state.data,v=d.variants.find(x=>x.id===id);let file=suppliedFile;
  if(file){}else if(existing){const images=d.files.filter(f=>/\.(png|jpg|jpeg|webp)$/i.test(f.filename||f.path));if(!images.length)return toast('项目还没有图片，先上传实际参考图。',true);const selection=await form('选择项目中的图片',[{name:'fileId',label:'图片',type:'select',options:images.map(f=>({value:f.id,label:f.filename}))}],{fileId:images[0].id});if(!selection)return;file=images.find(x=>x.id===selection.fileId);}else file=await upload(reader.project,'.png,.jpg,.jpeg,.webp');if(!file)return;
  const result=await form('核对实际参考图',[{name:'evidence',label:'观察依据（身份、状态；背景是否夹带其他道具）',type:'textarea',rows:3,required:true},{name:'confirmed',label:'已查看图片，确认适用于所列状态和职责',type:'checkbox'}],{},`<img class="studio-review-image" src="${esc(file.url)}" alt="待核对的实际图片"><p>所需状态：${text(v.claims||{})}</p><p>职责：${esc((v.roles||[]).join(' / '))}</p>`,'采用参考图');if(!result)return;
  await api(path(`/assets/${id}/review-reference`),'POST',{...result,fileId:file.id,roles:v.roles,expectedVersion:v._version});await reader.refresh();
 }
 document.addEventListener('click',async e=>{
  const el=e.target.closest('[data-studio]');if(!el||el.disabled)return;e.preventDefault();e.stopPropagation();const action=el.dataset.studio,id=el.dataset.id;
  try{
   if(action==='new-novel')return await createNovel();
   if(action==='novel-analyze'){
    const source=reader.state.data.novelSource,done=source?.analysisRanges?.length||0,total=source?.chapters?.length||0;
    if(await confirm('启动全书深读',`<p>将继续分析剩余 ${Math.max(0,total-done)} 个章节单元。长篇小说可能持续较久，但已完成结果会逐单元保存并复用。</p><p>只想先做 1–5 章时不需要运行这里，直接选择章节改编即可。</p>`,'开始后台深读'))await run('/novel/analyze',{});return;
   }
   if(action==='shooting'){reader.ui.tab='shooting';reader.mount();return;}
   if(action==='draft-view'){reader.ui.studioDraft=id;reader.mount();return;}
   if(action==='production'){reader.advanced({stage:'B5',sceneId:reader.selectedRow()?.id});return;}
   if(action==='import-story'){const file=await upload(reader.project,'.json');if(file){await api(path('/import-scene-export'),'POST',await fetch(file.url).then(r=>r.json()));await reader.refresh();}return;}
   if(action==='convert'){
    const rows=drafts().find(r=>r.id===activeId())?.payload.scenes||[];
    const data=await form('选择呈现方向',[{name:'mode',label:'呈现形态',type:'select',options:Object.entries(modes).map(([value,label])=>({value,label}))},{name:'sceneId',label:'修改范围',type:'select',options:[{value:'',label:'生成完整拍摄版'},...rows.map(s=>({value:s.id,label:'仅修改：'+s.title}))]},{name:'instruction',label:'希望改变什么（可留空）',type:'textarea',rows:3}],{mode:reader.state.data.project.presentationMode||'fast_drama'},'<p>画幅独立设置。旧稿和当前采用版会保留，新结果由你选择。</p>','准备候选');if(data)await run('/shooting/propose',{...data,sceneIds:data.sceneId?[data.sceneId]:[],newCandidate:crypto.randomUUID()});return;
   }
   if(action==='novel-range'){
    const pr=reader.state.data.project,active=drafts().find(d=>d.id===activeId()),chapters=reader.state.data.novelSource.chapters;
    const data=await form('选择阅读与改编范围',[{name:'start',label:'起始章节单元',type:'number',required:true},{name:'end',label:'结束章节单元',type:'number',required:true},{name:'instruction',label:'本轮改编或修订方向',type:'textarea',rows:3}],{start:Math.min(pr.nextChapter||1,chapters.length),end:Math.min(pr.nextChapter||1,chapters.length)},`<p>共 ${chapters.length} 个章节单元。长章节会按段落或句末自动拆成阅读单元；每次只使用已记录的真实选段。</p>`,'生成候选');if(data)await run('/novel/propose',{...data,newCandidate:crypto.randomUUID()});return;
   }
   if(action==='draft-adopt'||action==='draft-adopt-next'){
    const row=drafts().find(r=>r.id===id);el.disabled=true;await api(path(endpoint(row)+'/adopt'),'POST',{});reader.ui.tab='reading';await reader.refresh();toast('已采用，旧版本仍保留。');if(action==='draft-adopt-next')await reader.advance();return;
   }
    if(action==='draft-repair'){
     const row=drafts().find(r=>r.id===id);if(!row)return;await run('/novel/propose',{start:row.start,end:row.end,instruction:'仅修复审查列出的具体问题，保留其余正文与稳定 ID。',repairDraftId:id,newCandidate:crypto.randomUUID()});return;
    }
   if(action==='draft-reject'){
    const row=drafts().find(r=>r.id===id),data=await form('记录本轮修改方向',[{name:'reason',label:'哪里需要改',type:'textarea',rows:3}],{});if(data){await api(path(endpoint(row)+'/reject'),'POST',data);await reader.refresh();}return;
   }
   if(action==='reference-generate'){
    const variant=reader.state.data.variants.find(v=>v.id===id),data={assetId:variant.masterId,variantId:id,quality:'proxy'},preview=await api(path('/assets/dry-run'),'POST',data);
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
    let cursor=0;const ranges=task.shots.map(shot=>{const start=cursor;cursor+=shot.duration;return {...shot,in:start,out:cursor};});
    const fields=ranges.flatMap((r,i)=>[{name:'in_'+i,label:`镜 ${i+1} 实际起点（秒）`,type:'number',step:.001,min:0,required:true},{name:'out_'+i,label:`镜 ${i+1} 实际终点（秒）`,type:'number',step:.001,min:0,required:true}]);const values=Object.fromEntries(ranges.flatMap((r,i)=>[['in_'+i,Number(r.in.toFixed(3))],['out_'+i,Number(r.out.toFixed(3))]]));
    const result=await form('标定生成单元中的镜头区间',fields,values,`<video class="studio-review-image" src="${esc(file.url)}" controls></video><p>数值先按分镜建议时长排列，请观看实际视频后修正。各镜区间可留间隙，不能重叠或倒序。</p>`,'关联到分镜');if(!result)return;
    await api(path(`/generation-tasks/${id}/import`),'POST',{fileId:file.id,ranges:ranges.map((r,i)=>({shotId:r.shotId,in:result['in_'+i],out:result['out_'+i]}))});await reader.refresh();toast('各镜已关联同一视频，进入审片确认实际末态。');return;
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
