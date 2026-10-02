import copy,json,hashlib,subprocess
from pathlib import Path
import pytest
from app.core import DomainError,digest,uid
from app.cinema import PRESETS,PROFILE,shot_count,allocate_durations,render_dimensions,resolve_manifest,complete_shots,validate_shots,compile_prompt,render_key,strong_order
from app.production import direction_demo
from app.qualification import Qualification
from test_common import studio

@pytest.fixture
def project(studio):
    b=studio.state.service;studio.state.settings.save({'media':{'provider':'demo'}})
    p=b.create({'title':'雨夜便利店','source':'雨夜，一个人进入便利店。','targetDuration':8,'budget':10,'preset':'vertical'})['project']['id']
    st=b.style(p);b.finalize(p,'style',st['id'],st['_version'])
    master=b.save(p,'master',{'name':'小陈','kind':'character','freezeString':'成年男子，深蓝雨衣，短黑发。','identity':{'face':'短黑发、方脸'}})
    b.finalize(p,'master',master['id'],master['_version'])
    scene=b.save(p,'scene',{'title':'便利店入口','sourceText':'雨夜，他收起雨伞。','targetDuration':8,'characters':[master['id']],'informationPayload':['主角进门'],'timeOfDay':'夜','order':0})
    direction=b.save(p,'direction',{**direction_demo(scene,b.style(p)),'sceneId':scene['id']})
    skeleton=[{'shotSize':size,'actionLine':'主角收起雨伞，观察柜台。','subjects':[master['id']],'informationPayload':['主角进门'],'isEmpty':False} for size in ('LS','MS','MCU','CU')]
    shots=complete_shots(skeleton,direction,scene,b.manifest(p,scene['id']),b.style(p))
    for shot in shots:b.save(p,'shot',shot)
    return b,p,scene,master,shots

@pytest.mark.parametrize('preset,duration',[('cinema',60),('series',32),('vertical',12)])
def test_style_duration_solver(preset,duration):
    st=PRESETS[preset];n=shot_count(duration,st)
    assert st['shotCountRange'][0]<=n<=st['shotCountRange'][1]
    assert st['aslRange'][0]<=duration/n<=st['aslRange'][1]

def test_infeasible_duration_is_not_silently_forced():
    with pytest.raises(DomainError):shot_count(100,PRESETS['vertical'])

@pytest.mark.parametrize('total,weights',[(17,[1,2,3,1]),(8,[1,1,1,1]),(36,[.25,4,2]),(3.5,[2,3])])
def test_duration_allocation_sums_exactly(total,weights):
    assert abs(sum(allocate_durations(total,weights))-total)<.001

@pytest.mark.parametrize('aspect',['16:9','9:16','2.39:1','1:1'])
def test_render_dimensions_are_even(aspect):
    w,h=render_dimensions(aspect);assert w%2==h%2==0 and w>0 and h>0

def test_prompt_is_deterministic_and_freeze_is_verbatim(project):
    b,p,scene,asset,shots=project;m=b.manifest(p,scene['id']);a=compile_prompt(shots[0],m,b.style(p));bb=compile_prompt(shots[0],m,b.style(p))
    assert a==bb and asset['freezeString'] in a['imagePrompt'] and asset['freezeString'] in a['videoPrompt']

def test_key_seed_quality_profile_change_but_status_not(project):
    b,p,scene,asset,shots=project;shot=shots[0];st=b.style(p);key=render_key(shot,[],st,PROFILE,1)
    assert key==render_key({**shot,'status':'locked','freshness':'broken'},[],st,PROFILE,1)
    assert key!=render_key(shot,[],st,PROFILE,2)
    assert key!=render_key(shot,[],st,PROFILE,1,quality='final')
    assert key!=render_key(shot,[],st,{**PROFILE,'version':'2'},1)
    assert key!=render_key(shot,[],st,PROFILE,1,references=[{'sha256':'different'}])

def test_baseline_shots_validate(project):
    b,p,scene,asset,shots=project;assert b.validate_scene(p,scene['id'])['passed']

@pytest.mark.parametrize('field,code',[('axis','axis_cross'),('light','light_jump'),('duration','duration')])
def test_continuity_rule_reports_exact_problem(project,field,code):
    b,p,scene,asset,shots=project;ss=copy.deepcopy(shots);direction=b.list_active(p,'direction')[0]
    if field=='axis':ss[1]['continuity']['cameraSide']='negative'
    if field=='light':ss[1]['lighting']['keyDirection']=130
    if field=='duration':ss[0]['duration']=9
    out=validate_shots(ss,direction,b.style(p));assert not out['passed'];assert any(i['code']==code for i in out['issues'])

def test_empty_shot_stays_empty(project):
    b,p,scene,asset,shots=project;direction=b.list_active(p,'direction')[0]
    skeleton=[{'shotSize':'LS','actionLine':'店外雨滴。','subjects':[],'informationPayload':[],'isEmpty':True}]*4
    result=complete_shots(skeleton,direction,scene,b.manifest(p,scene['id']),b.style(p))
    assert all(x['subjects']==[] for x in result)

def test_strong_dependency_topological_order_and_cycle():
    ss=[{'id':'a'},{'id':'b'},{'id':'c'}];links=[{'from':'c','to':'b','type':'frame_chain'},{'from':'b','to':'a','type':'extension'}]
    assert strong_order(ss,links)==['c','b','a']
    with pytest.raises(DomainError):strong_order(ss,links+[{'from':'a','to':'c','type':'ref_video'}])

def test_cut_does_not_create_strong_dependency():
    assert set(strong_order([{'id':'a'},{'id':'b'}],[{'from':'a','to':'b','type':'cut'},{'from':'b','to':'a','type':'cut'}]))=={'a','b'}

def test_finalized_identity_requires_second_confirmation(project):
    b,p,scene,asset,shots=project;st=b.style(p);new={**st,'aspectRatio':'16:9'}
    plan=b.change_plan(p,'style',new);assert plan['cost']=='avalanche' if 'cost' in plan else plan['costLevel']=='avalanche'
    with pytest.raises(DomainError):b.save(p,'style',new)
    b.save(p,'style',new,plan['planHash']);assert all(x['freshness']=='broken' for x in b.list_active(p,'shot'))

def test_nonidentity_prefix_change_does_not_break_shot_design(project):
    b,p,scene,asset,shots=project;st=b.style(p);new={**st,'promptPrefix':'adjust expression only'};plan=b.change_plan(p,'style',new);b.save(p,'style',new,plan['planHash'])
    assert all(x['freshness']=='clean' for x in b.list_active(p,'shot'))

def test_asset_state_resolves_variant_without_manual_shot_edit(project):
    b,p,scene,asset,shots=project
    variant=b.save(p,'variant',{'masterId':asset['id'],'name':'淋湿','deltaString':'雨衣湿透','requiresImage':False})
    b.save(p,'asset_state',{'assetId':asset['id'],'variantId':variant['id'],'validFrom':scene['id'],'validUntil':None})
    assert b.manifest(p,scene['id'])['resolved'][0]['variantId']==variant['id']

def test_foreshadow_closeup_is_rejected(project):
    b,p,scene,asset,shots=project;variant=asset['defaultVariantId'];f={'variantId':variant,'setupScene':scene['id']}
    out=validate_shots(shots,b.list_active(p,'direction')[0],b.style(p),foreshadows=[f]);assert any(x['code']=='setup_closeup' for x in out['issues'])

def test_concurrent_cost_reservations_are_recorded_without_budget_cap(project):
    from concurrent.futures import ThreadPoolExecutor
    b,p,*_=project;pr=b.s.get(p);pr['budget']=1;b.s.put('project',pr,p)
    def reserve(i):
        try:b.reserve(p,'reserve_'+str(i),.6);return True
        except DomainError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,range(2)))
    assert results.count(True)==2
    assert b.cost(p)['reserved']==pytest.approx(1.2)

def test_final_media_needs_proxy_approval(project):
    b,p,scene,asset,shots=project
    with pytest.raises(DomainError):b.render_request(p,{'shotId':shots[0]['id'],'kind':'keyframe','quality':'final'})

def test_clip_needs_selected_keyframe(project):
    b,p,scene,asset,shots=project
    with pytest.raises(DomainError):b.render_request(p,{'shotId':shots[0]['id'],'kind':'clip','quality':'proxy'})

def render_once(b,p,shot,kind='keyframe'):
    data={'shotIds':[shot['id']],'kind':kind,'quality':'proxy'};plan=b.dry_run(p,data)
    assert not plan['blocked'],plan
    result=b.render(p,{**data,'planHash':plan['planHash']})
    return result[0] if isinstance(result,list) else result['renders'][0]

def test_real_keyframe_then_cache_skips_runner_and_gates(project,monkeypatch):
    b,p,scene,asset,shots=project;r=render_once(b,p,shots[0]);assert Path(b.s.get(r['fileId'])['path']).is_file()
    def fail(*a,**k):raise AssertionError('cache hit called an external component')
    monkeypatch.setattr(b.runners,'execute',fail);monkeypatch.setattr(b.gates,'inspect',fail)
    again=render_once(b,p,shots[0]);assert again['cacheHit'] and again['id']==r['id']

def test_pinned_media_survives_upstream_change(project):
    b,p,scene,asset,shots=project;r=render_once(b,p,shots[0]);b.select_render(p,r['id'],{'selected':True,'pinned':True,'humanReview':True,'reason':'测试人工终选'})
    shot=b.s.get(shots[0]['id']);b.save(p,'shot',{**shot,'actionLine':'动作已变化'})
    after=b.s.get(r['id']);assert after['pinned'] and after['freshness']=='broken'
    assert Path(b.s.get(after['fileId'])['path']).is_file()

def test_real_video_audio_subtitles_assembly(project,tmp_path):
    import wave,math,struct
    b,p,scene,asset,shots=project;shot=shots[0];frame=render_once(b,p,shot);b.select_render(p,frame['id'],{'selected':True,'humanReview':True,'reason':'确认测试图'})
    clip=render_once(b,p,shot,'clip');b.select_render(p,clip['id'],{'selected':True,'humanReview':True,'reason':'确认测试视频'})
    audio=b.s.root/'media'/p/'tone.wav'
    with wave.open(str(audio),'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(b''.join(struct.pack('<h',int(1800*math.sin(2*math.pi*440*i/16000))) for i in range(32000)))
    f=b.register_file(p,audio);data={'shotIds':[shot['id']],'audio':[{'fileId':f['id'],'start':0,'gain':.3}],'subtitles':[{'start':0,'end':1,'text':'实际字幕测试'}],'quality':'proxy'}
    plan=b.assembler.plan(p,data);out=b.assembler.run(p,{**data,'planHash':plan['planHash'],'acknowledgeWarnings':True},lambda *_:None,lambda:None)
    media=b.s.get(out['fileId']);assert Path(media['path']).stat().st_size>1000
    assert out['hasConfiguredAudio'] and out['subtitleFile'] and out['edlFile']
    probe=b.gates.probe(media['path']);kinds={x['codec_type'] for x in probe['streams']};assert {'video','audio','subtitle'}<=kinds

def test_builtin_runner_passes_all_twelve_real_cases(studio):
    result=Qualification(studio.state.runners).run('subprocess');assert result['passed'],result
    assert len(result['results'])==12

def test_runner_route_manual_override_has_priority(studio):
    r=studio.state.runners;st=studio.state.settings
    st.save({'routing':{'roles':{'operator':'pi-agent'},'overrides':[{'match':{'stage':'B5'},'runner':'codex'}]}})
    task={'role':'operator','stage':'B5'}
    assert r.route(task)=='codex'
    assert r.route(task,'subprocess')=='subprocess'


def test_missing_specialist_models_never_report_full_pass(project):
    b,p,scene,asset,shots=project;r=render_once(b,p,shots[0]);gate=b.s.get(r['gateReportId'])
    assert gate['status']=='review'
    assert any(c['name']=='identity' and c['state']=='unknown' for c in gate['checks'])

def test_image_video_settings_are_independent(studio):
    st=studio.state.settings;st.save({'media':{'provider':'manual'},'mediaImages':{'provider':'openai','model':'image-model'},'mediaVideos':{'provider':'generic','model':'video-model'}})
    assert st.media('keyframe')['model']=='image-model'
    assert st.media('clip')['model']=='video-model'

def test_ffmpeg_fallback_reads_video_without_ffprobe(project,monkeypatch):
    b,p,scene,asset,shots=project;r=render_once(b,p,shots[0]);b.select_render(p,r['id'],{'selected':True,'humanReview':True,'reason':'fixture'})
    clip=render_once(b,p,shots[0],'clip');path=b.s.get(clip['fileId'])['path']
    import shutil
    original=shutil.which;monkeypatch.setattr('app.gates.shutil.which',lambda cmd:None if cmd=='ffprobe' else original(cmd))
    probe=b.gates.probe(path);assert probe['probeMethod']=='ffmpeg-stderr-fallback'
    assert {'video','audio'}<={s['codec_type'] for s in probe['streams']}
