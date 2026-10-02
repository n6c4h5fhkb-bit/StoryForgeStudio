// Clipboard export uses the adopted shot and its own shooting-script version.
// No generation, prompt compilation, or request is involved.
const plain=value=>typeof value==='string'?value:Array.isArray(value)?value.map(plain).filter(Boolean).join('；'):value&&typeof value==='object'?Object.values(value).map(plain).filter(Boolean).join(' · '):value==null?'':String(value);
const sizes={ELS:'大远景',LS:'远景',MS:'中景',MCU:'中近景',CU:'近景',ECU:'特写'};
const angles={eye:'平视',low:'低机位',high:'高机位',overhead:'俯拍',pov:'主观',shoulder:'过肩'};
const movements={static:'固定',push:'推镜',pull:'拉镜',pan:'横摇',tilt:'俯仰',track:'跟拍',dolly:'移动',handheld:'手持'};
const modes={speech:'对白',inner:'内心独白',narration:'旁白',system:'系统音'};

export function selectedShots(data,ids){
  const selected=new Set(ids),scenes=new Map((data.scenes||[]).filter(s=>s.status!=='archived').map(s=>[s.id,s]));
  const doc=[...(data.adopted_scripts||[]),...(data.shooting_scripts||[])].find(s=>s.id===(data.project?.activeScriptId||data.project?.activeShootingId))?.payload;
  const playback=new Map((doc?.presentationPlan||[]).map((s,i)=>[s.id,i]));
  return (data.shots||[]).filter(s=>selected.has(s.id)&&s.status!=='archived'&&scenes.has(s.sceneId))
    .sort((a,b)=>(playback.get(a.presentationId)??1e9)-(playback.get(b.presentationId)??1e9)||(scenes.get(a.sceneId).order??0)-(scenes.get(b.sceneId).order??0)||String(a.sceneId).localeCompare(String(b.sceneId))||(a.order??0)-(b.order??0)||String(a.id).localeCompare(String(b.id)));
}

export function selectedShotText(data,ids){
  const shots=selectedShots(data,ids);if(!shots.length)return '';
  const output=[`${data.project?.title||'分镜'} · 已选 ${shots.length} 镜`];let currentScene;
  for(const shot of shots){
    const scene=(data.scenes||[]).find(s=>s.id===shot.sceneId);
    const doc=[...(data.adopted_scripts||[]),...(data.shooting_scripts||[])].find(s=>s.id===scene.shootingScriptId)?.payload;
    const entities=doc?.continuity?.entities||{};
    const names={...Object.fromEntries((data.masters||[]).map(s=>[s.id,s.name])),...Object.fromEntries(Object.entries(entities).map(([id,e])=>[id,e.name]))};
    if(currentScene!==scene.id){output.push('',`【${scene.title||'场景'}】`);currentScene=scene.id;}
    const details=[sizes[shot.shotSize]||shot.shotSize,angles[shot.angle]||shot.angle,shot.lens?`${shot.lens}mm`:null,Number.isFinite(shot.duration)?`${Number(shot.duration.toFixed(2))} 秒`:null].filter(Boolean);
    output.push('',`镜头 ${String((shot.order??0)+1).padStart(2,'0')}｜${details.join(' · ')}`);
    if(shot.freshness==='broken'||scene.presentationFreshness==='broken')output.push('状态：上游已变化，待复核');
    const line=(label,value)=>{const valueText=plain(value);if(valueText)output.push(`${label}：${valueText}`);};
    const presentation=doc?.presentationPlan?.find(p=>p.id===shot.presentationId);
    if(presentation?.kind&&presentation.kind!=='main')line('观看方式',({preview:'预演',flashback:'倒叙',time_jump:'跳时'}[presentation.kind]||presentation.kind)+(presentation.reason?' · '+presentation.reason:''));
    line('画面',shot.actionLine);line('观看重点',shot.informationPayload);
    const movement=shot.movement||{};
    line('运镜',[movements[movement.type]||movement.type,movement.speed==='slow'?'缓慢':movement.speed==='fast'?'快速':movement.speed]);
    line('起幅',movement.startFraming);line('落幅',movement.endFraming);
    line('构图',shot.framing);
    line('出镜',shot.subjects?.map(id=>names[id]||'待核对的主体'));
    if(Array.isArray(shot.dialogueIds)){
      const lines=new Map((doc?.dialogueLines||scene.body?.blocks?.filter(b=>b.type==='dialogue')||[]).map(d=>[d.id,d]));
      for(const id of shot.dialogueIds){const d=lines.get(id);if(!d){output.push('对白：[引用待核对]');continue;}
        const speaker=names[d.speakerId]||'人物';
        output.push(`${modes[d.mode]||'对白'}｜${speaker}${d.parenthetical?`（${d.parenthetical}）`:''}：${d.text||''}`);
      }
    }else line('对白',shot.dialogueText);
    const direction=(data.directions||[]).find(d=>d.sceneId===scene.id&&d.status!=='archived');
    line('声音',shot.soundCue||direction?.sound?.ambience);
    const lighting=shot.lighting||{};
    line('光影',[lighting.keyDirection!=null?`主光方向 ${lighting.keyDirection}°`:null,lighting.ratio!=null?`光比 ${lighting.ratio}:1`:null,lighting.motivation]);
  }
  return output.join('\n');
}
