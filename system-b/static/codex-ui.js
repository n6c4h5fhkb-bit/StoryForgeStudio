import {api,modal,closeModal,$,$$,esc,fieldHtml,toast,showError,form,roleLabels} from './common.js';

export const providers=[{value:'demo',label:'离线演示（模板）'},{value:'codex_cli',label:'本地 Codex CLI（复用账号与会话）'},{value:'openai',label:'OpenAI 兼容 API'},{value:'anthropic',label:'Anthropic API'},{value:'gemini',label:'Gemini API'}];

export const codexPresets=[
 {value:'custom',label:'自定义当前设置'},
 {value:'inherit',label:'继承本机 Codex 默认',model:'',reasoning:''},
 {value:'gpt-5.6-sol-high',label:'GPT-5.6 Sol · High（精品质量）',model:'gpt-5.6-sol',reasoning:'high',timeout:600,contextCharacters:96000}
];

function codexPresetValue(model){
 const exact=codexPresets.find(p=>p.model===model.model&&p.reasoning===(model.codexReasoning||''));
 return exact?.value||'custom';
}

export function modelFields(model){
 const cli=model.provider==='codex_cli';
 const fields=[{name:'provider',label:'调用方式',type:'select',options:providers}];
 if(cli)fields.push({name:'codexPreset',label:'Codex 快捷预设',type:'select',options:codexPresets,default:codexPresetValue(model),transient:true,wide:true,help:'一键填入模型、推理强度、等待时间与任务资料上限；也可以继续在下方单独修改。'});
 fields.push({name:'model',label:'模型名称',help:cli?'可选 gpt-5.6-sol；留空继承本机 Codex 的默认模型。':'填写服务商的准确 model ID。'});
 if(cli)fields.push({name:'codexReasoning',label:'推理强度',type:'select',options:[{value:'',label:'继承本机 Codex'},'low','medium','high','xhigh','max','ultra']},
  {name:'codexPath',label:'CLI 路径',wide:true,help:'留空自动寻找已安装的 codex。无需填写 API 密钥。'},
  {name:'timeout',label:'单次等待上限（秒）',type:'number',min:1,help:'复杂创作建议 600 秒。超时或取消会终止本地调用，可恢复任务。'});
 else fields.push({name:'baseUrl',label:'API 基础地址',wide:true,placeholder:'https://.../v1'},
  {name:'apiKey',label:'API Key',type:'password',wide:true,help:'__KEEP__ 保留已存密钥。'},
  {name:'inputPerMillion',label:'每百万输入 token · USD',type:'number',min:0,step:.001},
  {name:'outputPerMillion',label:'每百万输出 token · USD',type:'number',min:0,step:.001},
  {name:'cachedInputPerMillion',label:'缓存读取 / 百万 token · USD（可留空）',type:'number',min:0,step:.001},
  {name:'cacheWritePerMillion',label:'缓存写入 / 百万 token · USD（可留空）',type:'number',min:0,step:.001},
  {name:'priceConfigured',label:'已确认该模型的单价',type:'checkbox'},
  {name:'maxTokens',label:'单次输出 token 上限',type:'number',min:1},
  {name:'format',label:'结构化输出',type:'select',options:['json_object','json_schema','text']});
 fields.push({name:'contextCharacters',label:'当前任务资料字符上限',type:'number',min:1000,help:cli?'限制本次所需资料；续接时只补变化，平台保存完整版本用于检查。':''});
 return fields;
}

export function modelNotice(model){return model.provider==='codex_cli'?
 '<div class="callout info">复用本机 Codex 登录。主调度管理采用版本，创作与复核分别续用自己的会话；返修自动补充变化。CLI 按账号额度或服务商结算，本平台记录 token，不把未知金额记成免费。</div><p><button type="button" data-codex-status>检查本地 Codex</button> <span data-codex-result class="muted smalltext"></span></p>':
 '<div class="callout info">演示模式使用本地模板。正式创作可选择本地 Codex CLI，或连接已定价的模型 API。</div>'}

export function readModel(root,model){
 const out={};for(const f of modelFields(model)){if(f.transient)continue;const el=$('[name="'+f.name+'"]',root);if(!el)continue;out[f.name]=f.type==='checkbox'?el.checked:f.type==='number'?(el.value===''&&f.name.includes('PerMillion')?null:Number(el.value)):el.value}
 return out;
}

export function bindCodexPreset(root){
 const preset=$('[name="codexPreset"]',root),model=$('[name="model"]',root),reasoning=$('[name="codexReasoning"]',root),timeout=$('[name="timeout"]',root),context=$('[name="contextCharacters"]',root);
 if(!preset||!model||!reasoning)return;
 const sync=()=>{const match=codexPresets.find(p=>p.model===model.value.trim()&&p.reasoning===reasoning.value);preset.value=match?.value||'custom'};
 preset.onchange=()=>{const choice=codexPresets.find(p=>p.value===preset.value);if(!choice||choice.value==='custom')return;model.value=choice.model;reasoning.value=choice.reasoning;if(timeout&&choice.timeout)timeout.value=choice.timeout;if(context&&choice.contextCharacters)context.value=choice.contextCharacters;model.dispatchEvent(new Event('input',{bubbles:true}));reasoning.dispatchEvent(new Event('change',{bubbles:true}));sync()};
 model.addEventListener('input',sync);reasoning.addEventListener('change',sync);sync();
}

export function bindCodexStatus(root,role=''){
 const button=$('[data-codex-status]',root);if(!button)return;
 button.onclick=async()=>{button.disabled=true;const output=$('[data-codex-result]',root);output.textContent='正在检查已保存的连接…';try{const s=await api('/api/codex/status'+(role?'?role='+encodeURIComponent(role):''));output.textContent=s.ready?`${s.version} · 已登录 · ${s.model} · ${s.reasoning||'默认强度'}`:s.message||'CLI 尚未就绪';}catch(e){output.textContent=e.message}finally{button.disabled=false}};
}

export function editModelDialog(title,values,role=''){
 return new Promise(resolve=>{let model={...values};let completed=false;const finish=value=>{if(!completed){completed=true;closeModal();resolve(value)}};
 const draw=()=>{const root=modal(title,`${modelNotice(model)}<form id="role-model-form"><div class="form-grid">${modelFields(model).map(f=>fieldHtml(f,model[f.name])).join('')}</div></form>`, '<button data-model-cancel>取消</button><button form="role-model-form" type="submit" class="primary">保存</button>',true);
 $('[data-model-cancel]',root).onclick=()=>finish(null);$('[data-close]',root).onclick=()=>finish(null);root.addEventListener('click',e=>{if(e.target===root)finish(null)});
 $('[name="provider"]',root).onchange=e=>{const old=model.provider;model={...model,...readModel(root,model),provider:e.target.value,priceConfigured:false};if(old!=='codex_cli'&&model.provider==='codex_cli'){model.model='';model.timeout=600}draw()};
 $('#role-model-form',root).onsubmit=e=>{e.preventDefault();finish(readModel(root,model))};bindCodexStatus(root,role);bindCodexPreset(root);};draw();
 });
}

export async function codexSessionsDialog(project){
 const rows=await api(`/api/projects/${project}/codex-sessions`);
 const root=modal('创作会话',`<p>主调度以平台采用稿为准。每项任务保留自己的 Codex 会话，重启平台后仍可续接；历史草稿不会自动变成正式事实。</p><div class="stack">${rows.map(r=>`<div class="panel"><strong>${esc(roleLabels[r.role]||r.role)}</strong><p class="muted smalltext">${esc(r.scope)} · ${r.turns||0} 轮 · ${esc(r.state)}</p><p>上次：${r.lastContext?.resumed?'续用会话':'建立会话'} · ${r.lastContext?.contextMode==='delta'?'增量资料':'完整任务资料'} · 发送 ${r.lastContext?.sentCharacters||0} 字符</p><details><summary>会话详情与恢复</summary><p class="mono smalltext">${esc(r.threadId||'尚未建立 CLI 会话')}</p><p class="smalltext">仅在记录丢失或上下文错误时重建。正常返修、取消与平台重启都可以继续原会话。</p><button data-session-reset="${esc(r.id)}">重建此任务会话</button></details></div>`).join('')||'<p>首次真实创作后，会话会自动保存在这里。</p>'}</div>`,'',true);
 $$('[data-session-reset]',root).forEach(button=>button.onclick=async()=>{const answer=await form('重建任务会话',[{name:'confirm',label:'此任务下一次调用重新发送完整资料',type:'checkbox'}],{},'<p>采用稿和其他会话会保留。此操作只用于修复当前会话。</p>','重建');if(!answer?.confirm)return;try{await api(`/api/projects/${project}/codex-sessions/${button.dataset.sessionReset}/reset`,'POST',{});toast('已重建任务会话，请恢复创作任务');await codexSessionsDialog(project)}catch(e){showError(e)}});
}
