import {api,esc,form,modal,closeModal,toast,showError,confirm} from './common.js';
import {readableBody} from './reader.js';
import {intentNotes} from './directing-notes.js';

const modes={cinema:'电影',series:'剧集',fast_drama:'快节奏短剧'};
const button=(action,label,id='',primary=false)=>`<button type="button" data-format="${action}" data-id="${esc(id)}" class="${primary?'primary':''}">${esc(label)}</button>`;
const text=value=>esc(typeof value==='string'?value:JSON.stringify(value??'',null,2)).replace(/\n/g,'<br>');
const names=doc=>Object.fromEntries(Object.entries(doc.continuity?.entities||{}).map(([id,value])=>[id,value.name||id]));
const prose=doc=>(doc.scenes||[]).map(scene=>`<section class="rw-proposal-part" data-read-anchor="${esc(scene.id)}"><h3>${esc(scene.title||'场次')}</h3>${readableBody({blocks:scene.blocks},names(doc))}${intentNotes(scene,doc.continuity?.entities)}</section>`).join('');

export function installFormatReader(reader){
 if(reader.system!=='A')return;
 const path=suffix=>`/api/projects/${reader.project}${suffix}`;
 const versions=()=>reader.state.data?.scriptVersions?.versions||[];
 const active=()=>versions().find(row=>row.id===reader.state.data?.project.activeScriptVersionId);
 const imported=()=>reader.state.data?.project.importedStoryPackage?.storyDocument;
 const previousMount=reader.mount.bind(reader),previousReading=reader.reading.bind(reader),previousDecisions=reader.decisions.bind(reader),previousAdvance=reader.advance.bind(reader),previousRows=reader.activeRows.bind(reader),previousRefine=reader.refineBox.bind(reader);
 reader.activeRows=()=>active()&&!reader.ui.readOriginal?(active().payload.scenes||[]).map(row=>({...row,level:'script',status:'accepted',freshness:'clean',generationComplete:true})):imported()?(imported().scenes||[]).map(row=>({...row,level:'script',status:'accepted',freshness:'clean',generationComplete:true,body:{blocks:row.blocks}})):previousRows();
 function page(rows=versions()){
  const project=reader.state.data.project;
  if(!rows.length)return `<article class="rw-paper"><h2>呈现方向与剧本版本</h2><p>电影、剧集、短剧的转换和比较都在这里完成。采用版本直接交给导演工作区。</p><p>当前方向：${esc(modes[project.presentationMode]||'快节奏短剧')}</p>${button('propose','准备呈现剧本','',true)}${project.activeNovelDraft?button('publish','采用当前改编稿用于制作'):''}</article>`;
  const row=rows.find(item=>item.id===reader.ui.formatVersion)||rows.toReversed().find(item=>item.status==='proposed')||active()||rows.at(-1);
  reader.ui.formatVersion=row.id;const doc=row.payload||{},current=row.id===project.activeScriptVersionId;
  return `<div class="rw-choice-tabs">${rows.map(item=>button('view',`${modes[item.mode]}${item.id===project.activeScriptVersionId?' · 当前采用':item.status==='proposed'?' · 待选':item.status==='adopted'?' · 已采用':' · 历史'}`,item.id)).join('')}</div><article class="rw-paper"><header class="rw-pagehead"><span>${esc(modes[row.mode])} · ${current?'当前采用':row.passed?'已完成情节复核':'需修复'}</span><span>${row.demo?'演示稿，未验证真实文字质量':''}</span></header><h2>${esc(doc.title||project.title)}</h2>${doc.summary?`<p>${text(doc.summary)}</p>`:''}${(row.issues||[]).length?`<div class="rw-warning">${row.issues.map(issue=>`<p>${text(issue.location||issue.code)}：${text(issue.message)}</p>`).join('')}</div>`:''}${doc.storyChanges?.length?`<div class="rw-warning"><strong>需要你确认的故事修改</strong>${doc.storyChanges.map(change=>`<p>${text(change)}</p>`).join('')}</div>`:''}<div class="rw-prose">${prose(doc)}</div><details><summary>改动理由与来源依据</summary>${(doc.changeReasons||[]).map(reason=>`<p>${text(reason)}</p>`).join('')}<ul>${(doc.sourceMapping||[]).map(mapping=>`<li>${esc(mapping.sourceId)}：${text(mapping.reason)}</li>`).join('')}</ul></details><footer class="rw-decision-actions">${row.passed&&!current&&['proposed','adopted'].includes(row.status)?button('adopt','采用这个版本',row.id,true):''}${current?button('handoff','进入导演与制作',row.id,true):''}${button('propose','局部修改 / 换方向',row.id)}${versions().length>1?button('compare','并排比较',row.id):''}${row.status==='proposed'?button('reject','这版不合适',row.id):''}</footer></article>`;
 }
 reader.reading=()=>reader.ui.tab==='formats'?page():active()&&!reader.ui.readOriginal?`<article class="rw-paper"><header class="rw-pagehead"><span>${esc(modes[active().mode])} · 采用剧本</span>${button('original','对照原故事')}</header><div class="rw-prose">${prose({...active().payload,scenes:reader.ui.continuous?active().payload.scenes:active().payload.scenes.filter(scene=>scene.id===reader.selectedRow()?.id)})}</div></article>`:imported()?`<article class="rw-paper"><header class="rw-pagehead"><span>导入的故事原稿 · 待在 A 完成呈现与复核</span></header><div class="rw-prose">${prose({...imported(),scenes:reader.ui.continuous?imported().scenes:imported().scenes.filter(scene=>scene.id===reader.selectedRow()?.id)})}</div></article>`:previousReading();
 reader.decisions=()=>reader.state.data?.workflow?.action==='choose_script'?page(versions().filter(row=>reader.state.data.workflow.scriptVersionIds.includes(row.id))):previousDecisions();
 reader.refineBox=()=>active()&&!reader.ui.readOriginal?`<section class="rw-refine"><h3>打磨「${esc(reader.selectedRow()?.title||'当前情节')}」</h3><label for="rw-format-instruction">希望改变什么？</label><textarea id="rw-format-instruction" rows="3" placeholder="例如：更快进入冲突，保留最后的决定。">${esc(reader.ui.formatInstruction||'')}</textarea><div class="rw-refine-actions"><span class="rw-muted">只修改这场，其他已采用内容保留。</span>${button('refine','准备局部新版本',reader.selectedRow()?.id||'',true)}</div></section>`:imported()?button('propose','准备呈现版本并复核','',true):previousRefine();
 reader.mount=()=>{
  previousMount();const root=document.getElementById('reader-workspace');if(!root||!reader.state.data)return;
  root.querySelector('.rw-tabs')?.insertAdjacentHTML('beforeend',button('versions','呈现版本与比较'));
  root.querySelector('.rw-projectbar')?.insertAdjacentHTML('beforeend',button('mode',modes[reader.state.data.project.presentationMode]||'快节奏短剧'));
  root.querySelector('.rw-header-actions')?.insertAdjacentHTML('beforeend',button('handoff','进入导演与制作','',true));
  const request=(reader.state.data.changeRequests||[]).find(row=>row.id===new URLSearchParams(location.search).get('changeRequest'));
  if(request)root.querySelector('.rw-content')?.insertAdjacentHTML('afterbegin',`<article class="rw-paper"><h3>导演工作区的情节修改建议</h3><p>${text(request.instruction)}</p>${button('propose','根据建议准备新剧本',request.sourceScriptVersionId,true)}<p class="rw-muted">当前采用稿保持可读；新版本通过复核后由你采用。</p></article>`);
  root.querySelectorAll('[data-format]').forEach(el=>{if(reader.busy.has(reader.project))el.disabled=true;});
  if(reader.state.data.workflow?.action==='handoff_script'){
   const primary=root.querySelector('.rw-next-actions [data-reader=advance]');if(primary){primary.removeAttribute('data-reader');primary.dataset.format='handoff';primary.textContent='进入导演与制作';}
  }
 };
 async function run(data){const out=await reader.job('/scripts/propose',{...data,operationId:crypto.randomUUID(),newCandidate:crypto.randomUUID()});reader.ui.tab='formats';reader.ui.formatVersion=out?.id||out?.scriptVersion?.id;reader.ui.readOriginal=false;reader.save();reader.mount();return out;}
 async function propose(id){
  const requests=reader.state.data.changeRequests||[],request=requests.find(row=>row.id===new URLSearchParams(location.search).get('changeRequest')),selected=versions().find(row=>row.id===(id||request?.sourceScriptVersionId))||active();
  const data=await form('选择呈现方向',[{name:'mode',label:'呈现方向',type:'select',options:Object.entries(modes).map(([value,label])=>({value,label}))},{name:'sceneId',label:'修改范围',type:'select',options:[{value:'',label:'完整版本'},...(selected?.payload.scenes||[]).map(scene=>({value:scene.id,label:'仅修改：'+scene.title}))]},{name:'instruction',label:'希望改变什么（可留空）',type:'textarea',rows:3}],{mode:selected?.mode||reader.state.data.project.presentationMode||'fast_drama',sceneId:request?.sceneIds?.length===1?request.sceneIds[0]:'',instruction:request?.instruction||''},'<p>完整推荐稿先供你阅读；不同方向分别保存。未改动内容保留，采用后再交给导演工作区。</p>','准备候选');
  if(data)await run({...data,sceneIds:data.sceneId?[data.sceneId]:[],changeRequestId:request?.id});
 }
 reader.advance=async()=>{
  const step=reader.state.data?.workflow;
  if(step?.action==='prepare_script'){reader.ui.tab='formats';return run({mode:reader.state.data.project.presentationMode||'fast_drama'});}
  if(step?.action==='choose_script'){reader.ui.tab='decisions';reader.mount();return;}
  if(step?.action==='handoff_script')return handoff();
  return previousAdvance();
 };
 async function handoff(){
  if(!active()){
   if(reader.state.data.project.activeNovelDraft){try{await api(path('/scripts/publish-current'),'POST',{});await reader.refresh();}catch(error){if(!['script_review_required','presentation_mode'].includes(error.code))throw error;return propose();}}
   else return propose();
  }
  if(!/^\/(a|b)\//.test(location.pathname)){modal('采用剧本制作包',`<p>当前使用独立启动入口。统一工作室启动后可以直接交接，也可保存采用版本。</p><a href="${path('/scripts/'+active().id+'/package')}" target="_blank" rel="noopener">打开剧本制作包</a>`);return;}
  const data={projectId:reader.project,scriptVersionId:active().id};
  const submit=async body=>{const response=await fetch('/api/handoff',{method:'POST',headers:{'Content-Type':'application/json','x-studio-client':'local-ui'},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Object.assign(new Error(result.error||'交接未完成'),{code:result.code,details:result.details});return result;};
  let result=await submit(data);
  if(result.requiresChoice){const plan=result.preview;if(!await confirm('更新此方向的制作版本',`<p>变化 ${plan.changedSceneIds.length} 场，保留 ${plan.preservedSceneIds.length} 场。</p><p>受影响素材 ${plan.impacts.reduce((sum,row)=>sum+row.rendersAffected,0)} 项。历史原文件保留。</p>`,'采用并进入制作'))return;result=await submit({...data,productionProjectId:result.projectId,planHash:plan.planHash});}
  location.assign(result.url);
 }
 document.addEventListener('click',async event=>{
  const el=event.target.closest('[data-format]');if(!el||el.disabled)return;event.preventDefault();event.stopPropagation();
  const action=el.dataset.format,id=el.dataset.id;
  try{
   if(action==='versions'||action==='view'){reader.ui.tab='formats';reader.ui.formatVersion=id||reader.ui.formatVersion;reader.save();reader.mount();return;}
   if(action==='original'){reader.ui.readOriginal=true;reader.ui.tab='reading';reader.save();reader.mount();return;}
   if(action==='mode'){const data=await form('这部作品的呈现方向',[{name:'presentationMode',label:'呈现方向',type:'select',options:Object.entries(modes).map(([value,label])=>({value,label}))}],reader.state.data.project,'<p>用于接下来的剧本创作；已采用版本保留。画幅在导演工作区独立设置。</p>');if(data){await api(path(''),'PUT',data);await reader.refresh();}return;}
   if(action==='propose')return propose(id);
   if(action==='refine'){const instruction=document.getElementById('rw-format-instruction')?.value.trim();if(!instruction)return toast('请写一句修改方向。',true);reader.ui.formatInstruction=instruction;return run({mode:active().mode,sceneIds:[id],instruction});}
   if(action==='publish'){await api(path('/scripts/publish-current'),'POST',{});reader.ui.tab='formats';await reader.refresh();return;}
   if(action==='adopt'){const row=versions().find(item=>item.id===id);let approveStoryChanges=false;if(row.payload.storyChanges?.length){approveStoryChanges=await confirm('确认这些故事修改',row.payload.storyChanges.map(change=>`<p>${text(change)}</p>`).join(''),'确认故事修改并采用');if(!approveStoryChanges)return;}el.disabled=true;await api(path(`/scripts/${id}/adopt`),'POST',{approveStoryChanges});reader.ui.tab='reading';reader.ui.readOriginal=false;reader.save();await reader.refresh();toast('已采用；其他方向和历史版本保留。');return;}
   if(action==='reject'){const data=await form('记录修改意见',[{name:'reason',label:'哪里需要改',type:'textarea',rows:3}],{});if(data){await api(path(`/scripts/${id}/reject`),'POST',data);await reader.refresh();}return;}
   if(action==='handoff'){el.disabled=true;await handoff();if(el.isConnected)el.disabled=false;return;}
   if(action==='compare'){const rows=versions(),options=rows.map((row,index)=>({value:row.id,label:`${modes[row.mode]} · 版本 ${index+1}`}));const data=await form('比较两个剧本版本',[{name:'left',label:'左侧版本',type:'select',options},{name:'right',label:'右侧版本',type:'select',options}],{left:active()?.id||rows[0].id,right:id||rows.at(-1).id});if(!data)return;const result=await api(path('/scripts/compare')+`?left=${encodeURIComponent(data.left)}&right=${encodeURIComponent(data.right)}`);modal('完整剧本对照',`<p>变化 ${result.changedSceneIds.length} 场，保留 ${result.preservedSceneIds.length} 场。</p><div class="format-compare"><section><h2>${esc(modes[result.left.mode])}</h2>${prose(result.left.payload)}</section><section><h2>${esc(modes[result.right.mode])}</h2>${prose(result.right.payload)}</section></div>`,'',true);return;}
  }catch(error){showError(error);if(el.isConnected)el.disabled=false;}
 },true);
 document.addEventListener('input',event=>{if(event.target.id==='rw-format-instruction')reader.ui.formatInstruction=event.target.value;});
}
