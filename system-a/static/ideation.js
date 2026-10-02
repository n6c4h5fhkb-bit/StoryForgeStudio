import {api,esc,modal,closeModal,form,trackJob,settingsDialog,costDialog} from './common.js';

export class IdeaStart {
  constructor({select,manual}) {
    Object.assign(this,{select,manual,batches:[],batch:null,busy:false,error:'',preferences:'',mode:'quality'});
  }
  async open() {
    this.root=modal('先让 AI 帮你找故事','<p role="status">正在读取选题…</p>','',true);
    this.root.addEventListener('click',e=>this.click(e));
    this.root.addEventListener('change',e=>{
      if(e.target.id==='idea-history'){this.batch=this.batches.find(b=>b.id===e.target.value);this.paint();}
      if(e.target.name==='idea-mode')this.mode=e.target.value;
    });
    if(this.busy){this.paint();return;}
    try {
      const data=await api('/api/brainstorms');
      this.batches=data.batches;this.batch=this.batches.find(b=>b.id===this.batch?.id)||data.batches[0]||null;
      if(this.batch){this.mode=this.batch.mode;this.preferences=this.batch.preferences;}
      this.paint();
      const pending=data.jobs.find(j=>['queued','running'].includes(j.state));
      if(pending)await this.run(pending);
      else if(!this.batch&&!data.jobs.length&&this.root.isConnected)await this.generate();
      else if(!this.batch&&data.jobs.length){this.error=data.jobs[0].error||'上次脑暴未完成，可以重新生成。';this.paint();}
    } catch(e){this.error=e.message;this.paint();}
  }
  button(action,label,attrs='',primary=false){return `<button data-idea-action="${action}" ${attrs} ${this.busy?'disabled':''} class="${primary?'primary':''}">${label}</button>`;}
  paint() {
    if(!this.root?.isConnected)return;
    const batch=this.batch;
    this.root.querySelector('.modal-body').innerHTML=`<div class="idea-start">
      <p class="idea-intro">不用先想标题、写种子。AI 先给四个故事方向，你挑感兴趣的，再继续展开。</p>
      <div class="idea-toolbar"><label>创作倾向 <select name="idea-mode" ${this.busy?'disabled':''}><option value="quality" ${this.mode==='quality'?'selected':''}>原创 · 人物与故事质量</option><option value="fast_drama" ${this.mode==='fast_drama'?'selected':''}>短剧 · 强开场与追看欲</option></select></label>
        ${this.button('generate',batch?'换一批选题':'AI 帮我想选题','',true)}${this.button('preferences','补充偏好（可选）')}
      </div>
      ${this.preferences?`<p class="idea-muted">当前偏好：${esc(this.preferences)}</p>`:''}
      ${this.busy?'<div class="callout" role="status"><span class="spinner"></span> AI 正在脑暴，结果会自动保存。你可以稍后回来选择。</div>':''}
      ${this.error?`<div class="callout danger" role="alert">${esc(this.error)}<p>已生成的选题会保留。可重试，或检查服务连接。</p>${this.button('settings','服务设置')}</div>`:''}
      ${batch?.demo?'<p class="idea-demo">离线演示 · 以下是流程样例。连接模型后，AI 会按你的偏好生成真实选题。</p>':''}
      ${batch?.anchor?'<p class="idea-muted">这一批沿你选中的故事方向继续探索。</p>':''}
      <div class="idea-grid">${(batch?.ideas||[]).map(i=>`<article class="idea-card"><span class="idea-genre">${esc(i.genre)} · ${esc(i.tone)}</span><h3>${esc(i.title)}</h3><p>${esc(i.premise)}</p><dl><dt>开场怎么抓人</dt><dd>${esc(i.hook)}</dd><dt>核心两难</dt><dd>${esc(i.conflict)}</dd><dt>为什么值得追</dt><dd>${esc(i.appeal)}</dd></dl><details><summary>人物与制作考虑</summary><p>${esc(i.protagonist)}</p><p>${esc(i.productionNote)}</p></details><div class="idea-card-actions">${this.button('adopt','用这个开始',`data-id="${esc(i.id)}"`,true)}${this.button('explore','沿这个方向脑暴',`data-id="${esc(i.id)}"`)}</div></article>`).join('')}</div>
      <div class="idea-footer">${this.batches.length?`<label>保留的选题 <select id="idea-history" ${this.busy?'disabled':''}>${this.batches.map((b,i)=>`<option value="${esc(b.id)}" ${b.id===batch?.id?'selected':''}>第 ${this.batches.length-i} 批 · ${esc(b.ideas[0]?.title)}</option>`).join('')}</select></label>`:''}${this.button('costs','脑暴调用与费用')}${this.button('manual','我已有故事种子')}</div>
    </div>`;
  }
  async run(job) {
    this.busy=true;this.error='';this.paint();
    try {
      this.batch=await trackJob(job);
      this.batches=(await api('/api/brainstorms')).batches;
    } catch(e){this.error=e.message;}
    finally {this.busy=false;this.paint();}
  }
  async generate(anchor=null) {
    if(this.busy)return;
    this.busy=true;this.error='';this.paint();
    try {
      const job=await api('/api/brainstorms','POST',{mode:this.mode,preferences:this.preferences,anchor,operationId:crypto.randomUUID()});
      await this.run(job);
    } catch(e){this.busy=false;this.error=e.message;this.paint();}
  }
  async click(event) {
    const el=event.target.closest('[data-idea-action]');if(!el||this.busy)return;
    const action=el.dataset.ideaAction;
    try {
      if(action==='generate')return await this.generate();
      if(action==='explore')return await this.generate({batchId:this.batch.id,ideaId:el.dataset.id});
      if(action==='adopt'){
        this.busy=true;this.paint();
        const out=await api(`/api/brainstorms/${this.batch.id}/ideas/${el.dataset.id}/adopt`,'POST',{});
        closeModal();await this.select(out);return;
      }
      if(action==='manual'){closeModal();return await this.manual();}
      if(action==='settings')return await settingsDialog('A');
      if(action==='costs')return await costDialog('story_ideation');
      if(action==='preferences'){
        const value=await form('选题偏好（全部可留空）',[{name:'preferences',label:'想看的类型、人物关系、拍摄条件，或不想要的套路',type:'textarea',rows:4}],{preferences:this.preferences},'<p>留空也可以直接脑暴，不需要先写故事。</p>','保存偏好');
        if(value)this.preferences=value.preferences;
        // Reopen locally: do not overwrite edited preferences with the last batch.
        this.root=modal('先让 AI 帮你找故事','','',true);
        this.root.addEventListener('click',e=>this.click(e));
        this.root.addEventListener('change',e=>{if(e.target.name==='idea-mode')this.mode=e.target.value;if(e.target.id==='idea-history'){this.batch=this.batches.find(b=>b.id===e.target.value);this.paint();}});
        this.paint();
      }
    } catch(e){this.error=e.message;}
    finally {if(action==='adopt')this.busy=false;this.paint();}
  }
}
