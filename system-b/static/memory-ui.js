import {api,esc,form,modal,toast} from './common.js';

const categoryNames={fact:'事实与连续性',preference:'创作偏好',production:'制作经验',false_positive:'审查裁决'};
const statusNames={active:'正在使用',candidate:'待你确认',suspended:'已停用'};

function anchor(reader){
  const row=reader.selectedRow(),selection=String(window.getSelection?.()||'').trim().slice(0,2000);
  if(reader.system==='B'&&reader.ui.selected?.length===1)return {type:'shot',id:reader.ui.selected[0],selection};
  return {type:reader.system==='A'?'story_node':'scene',id:reader.system==='A'?reader.aNode(row)?.id:row?.id,selection};
}

async function add(reader){
  const fields=[
    {name:'text',label:'问题、要求，或你认可的做法',type:'textarea',rows:5,required:true},
    {name:'category',label:'类型（不确定可自动判断）',type:'select',options:[
      {value:'',label:'自动判断'},{value:'fact',label:'故事事实或连续性'},{value:'preference',label:'创作与审美偏好'},
      {value:'production',label:'图片、视频或模型执行'},{value:'false_positive',label:'审查误报或有意设计'}]},
  ];
  if(reader.system==='B')fields.push({name:'timecode',label:'视频时间点（秒，可留空）',type:'text'});
  const values=await form('告诉系统哪里要改',fields,{},'<p>明确要求会用于本作品；推广到其他作品仍由你确认。</p>','记住这条');
  if(!values)return;
  const target=anchor(reader);
  if(values.timecode!==undefined&&values.timecode!==''){
    const time=Number(values.timecode);if(!Number.isFinite(time)||time<0){toast('视频时间点必须是非负数字。',true);return;}
    target.timecode=time;
  }
  const result=await api(`/api/projects/${reader.project}/feedback`,'POST',{text:values.text,category:values.category||undefined,anchor:target,explicit:true,operationId:crypto.randomUUID()});
  toast(result.remembered?'已记住：后续相关任务会提前使用。':'已保存为待确认经验。');
  await openMemory(reader);
}

const rate=value=>value==null?'证据不足':`${(Number(value)*100).toFixed(1)}%`;
async function validateExperience(reader,row){
  const value=await form('记录这条经验是否有效',[{name:'result',label:'本次结果',type:'select',options:[{value:'resolved',label:'已落实，旧问题没有复发'},{value:'recurred',label:'同一问题再次发生'},{value:'misapplied',label:'经验用错了场景'},{value:'unknown',label:'目前证据不足'}]},{name:'failureStage',label:'问题发生在哪一环',type:'select',options:[{value:'',label:'不确定 / 不适用'},{value:'experience_not_selected',label:'任务没有选中这条经验'},{value:'rule_unclear',label:'经验表述不够准确'},{value:'generation',label:'生成没有落实'},{value:'review',label:'审查漏检'},{value:'scope',label:'适用范围错误'}]},{name:'evidence',label:'你实际看到的结果或例外',type:'textarea',rows:3,required:true}],{},`<p>${esc(row.rule)}</p>`,'记录效果');
  if(!value)return;
  await api(`/api/projects/${reader.project}/experiences/${row.id}/validate`,'POST',{result:value.result,failureStage:value.failureStage||undefined,evidence:value.evidence,target:anchor(reader)});
  toast(value.result==='resolved'?'已记录为有效。':'已记录，系统会据此缩小范围或修订经验。');
  await openMemory(reader);
}

async function importPack(reader){
  const input=document.createElement('input');input.type='file';input.accept='.json,application/json';
  input.onchange=async()=>{try{const file=input.files?.[0];if(!file)return;const pack=JSON.parse(await file.text());const result=await api(`/api/projects/${reader.project}/experience-pack/import`,'POST',pack);toast(`已导入 ${result.experienceIds?.length||0} 条已确认经验。`);await openMemory(reader);}catch(error){toast(error.message||'经验包导入失败',true);}};
  input.click();
}

export async function openMemory(reader){
  const data=await api(`/api/projects/${reader.project}/experiences`),rows=[...data.experiences].reverse(),metrics=data.metrics||{},stats=metrics.byExperience||{};
  const root=modal('反馈与记忆',`<div class="rw-actions"><button data-memory-add class="primary">指出问题或记住偏好</button><button data-memory-import>导入经验包</button><a href="/api/projects/${encodeURIComponent(reader.project)}/experience-pack" target="_blank" rel="noopener">导出跨作品经验</a></div><p class="muted">本作品的明确纠正自动生效；从选稿推测的偏好确认后才使用。</p><div class="rw-warning"><strong>改进证据</strong><p>已用于 ${metrics.appliedTasks||0} 个任务 · 已观察 ${metrics.observedChecks||0} 次 · 重复问题率 ${rate(metrics.repeatRate)} · 规则误用率 ${rate(metrics.misuseRate)}</p><small>${esc(metrics.evidence||'尚无验证记录')}</small></div>${rows.length?`<div class="stack">${rows.map(x=>{const s=stats[x.id]||{},owned=x.projectId===reader.project;return `<article class="list-row"><div class="grow"><h4>${esc(x.rule)}</h4><p>${esc(categoryNames[x.category]||x.category)} · ${esc(statusNames[x.status]||x.status)} · ${esc(x.scope?.level==='genre'?'同类型作品':x.scope?.level==='global'?'全部作品':'本作品')}</p>${x.action!==x.rule?`<small>下次：${esc(x.action)}</small>`:''}${x.diagnosticSuggestions?.length?`<p class="rw-warning">请先定位：${x.diagnosticSuggestions.map(esc).join(' / ')}</p>`:''}<p class="rw-muted">应用 ${s.applications||0} · 有效 ${s.resolved||0} · 复发 ${s.recurred||0} · 误用 ${s.misapplied||0} · 证据不足 ${s.unknown||0}</p></div><div>${x.status==='candidate'&&x.confirmationReason!=='ambiguous_feedback'?`<button data-memory-confirm="${esc(x.id)}">用于本作品</button>`:''}${owned&&x.status==='active'&&x.scope?.level==='project'?`<button data-memory-genre="${esc(x.id)}">同类作品也这样</button>`:''}${x.status==='active'?`<button data-memory-effect="${esc(x.id)}">记录效果</button>`:''}${owned?`<button data-memory-edit="${esc(x.id)}">${x.confirmationReason==='ambiguous_feedback'?'补充具体原因':'修改'}</button><button data-memory-toggle="${esc(x.id)}" data-status="${esc(x.status)}">${x.status==='suspended'?'重新启用':'停用'}</button>`:'<small>来自跨作品经验库</small>'}</div></article>`;}).join('')}</div>`:'<p class="rw-muted">还没有记录反馈。你可以在阅读时直接告诉系统哪里不符合要求。</p>'}`,'',true);
  root.querySelector('[data-memory-add]').onclick=()=>add(reader);
  root.querySelector('[data-memory-import]').onclick=()=>importPack(reader);
  root.querySelectorAll('[data-memory-effect]').forEach(el=>el.onclick=()=>validateExperience(reader,rows.find(x=>x.id===el.dataset.memoryEffect)));
  root.querySelectorAll('[data-memory-confirm]').forEach(el=>el.onclick=async()=>{await api(`/api/projects/${reader.project}/experiences/${el.dataset.memoryConfirm}/confirm`,'POST',{level:'project'});toast('已用于本作品。');await openMemory(reader);});
  root.querySelectorAll('[data-memory-genre]').forEach(el=>el.onclick=async()=>{await api(`/api/projects/${reader.project}/experiences/${el.dataset.memoryGenre}/confirm`,'POST',{level:'genre'});toast('以后同类作品也会使用。');await openMemory(reader);});
  root.querySelectorAll('[data-memory-toggle]').forEach(el=>el.onclick=async()=>{await api(`/api/projects/${reader.project}/experiences/${el.dataset.memoryToggle}`,'PUT',{status:el.dataset.status==='suspended'?'active':'suspended'});await openMemory(reader);});
  root.querySelectorAll('[data-memory-edit]').forEach(el=>el.onclick=async()=>{const row=rows.find(x=>x.id===el.dataset.memoryEdit),value=await form('修改经验',[{name:'rule',label:'什么时候要注意',type:'textarea',rows:3,required:true},{name:'action',label:'下次应该怎样做',type:'textarea',rows:3,required:true}],row,'','保存');if(value){await api(`/api/projects/${reader.project}/experiences/${row.id}`,'PUT',value);await openMemory(reader);}});
}
