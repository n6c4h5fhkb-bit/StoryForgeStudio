import {esc} from './common.js';

const list=value=>Array.isArray(value)?value:[];
const text=value=>esc(typeof value==='string'?value:'').replace(/\n/g,'<br>');
const line=(label,value)=>value?`<p><strong>${esc(label)}：</strong>${text(value)}</p>`:'';

export function intentNotes(scene,entities={}){
 const intent=scene?.sceneIntent;
 if(!intent||typeof intent!=='object')return '';
 const actors=list(intent.characters).map(actor=>line(entities[actor.entityId]?.name||'人物目的',[actor.goal,actor.obstacle?'阻碍：'+actor.obstacle:''].filter(Boolean).join('；'))).join('');
 const audience=intent.audience||{},labels={mustUnderstand:'本场要理解',withheld:'暂缓揭示',openToInterpretation:'保留解释空间'};
 const information=Object.entries(labels).map(([key,label])=>list(audience[key]).map(item=>line(label,item.information)+(key==='withheld'?line('暂缓依据',item.reason):'')).join('')).join('');
 return `<details class="studio-method-note"><summary>本场故事意图</summary>${line('情节变化',intent.dramaticChange)}${actors}${information}</details>`;
}

export function directorNotes(plan){
 if(!plan||typeof plan!=='object')return '';
 const summary=list(plan.summary).filter(value=>typeof value==='string').slice(0,3);
 const details=[['观看重点','focus'],['表演过程','performance'],['空间组织','space'],['动作与剪辑节奏','rhythm']].map(([label,key])=>line(label,plan[key])).join('');
 if(!summary.length&&!details)return '';
 return `<section class="studio-method-note">${summary.map(value=>`<p>${text(value)}</p>`).join('')}${details?`<details><summary>本场拍法依据</summary>${details}</details>`:''}</section>`;
}

export function shotNotes(shot){
 const beats=list(shot?.performanceBeats),camera=shot?.cameraCue||{},cut=shot?.cutPoint||{};
 const progression=beats.length?`<ol>${beats.map(beat=>`<li>${beat.trigger?text(beat.trigger)+' → ':''}${text(beat.action)}${beat.endCue?'；结束于：'+text(beat.endCue):''}${beat.reason?'<p class="rw-muted">'+text(beat.reason)+'</p>':''}</li>`).join('')}</ol>`:'';
 const cues=[['摄影机开始','start'],['摄影机跟随','follow'],['摄影机停止','end'],['运镜依据','reason']].map(([label,key])=>line(label,camera[key])).join('');
 const detail=progression+cues+line('切镜依据',cut.reason);
 return `${shot?.reviewRequired?'<p class="rw-warning">剧本意图已更新，本镜需复核；已有媒体保留。</p>':''}${cut.cue?`<p class="rw-muted">切点：${text(cut.cue)}</p>`:''}${detail?`<details class="studio-method-note"><summary>表演与切镜依据</summary>${detail}</details>`:''}`;
}
