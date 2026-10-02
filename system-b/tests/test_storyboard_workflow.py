import copy
from unittest.mock import Mock

import pytest

from app.core import DomainError,digest,uid
from app.cinema import render_key,PROFILE,validate_shots
from app.runner import RunnerRegistry
from test_common import studio
from test_production import project,render_once


def ready_direction(b,p):
    direction=b.list_active(p,'direction')[0]
    direction['status']='accepted'
    b.s.put('direction',direction,p)


def test_patch_preserves_locked_neighbors_identity_and_selected_media(project):
    b,p,scene,asset,shots=project;ready_direction(b,p)
    locked=b.s.get(shots[0]['id']);locked['status']='locked';b.s.put('shot',locked,p)
    target=b.s.get(shots[1]['id']);target['soundCue']='门铃后保持两秒安静';b.s.put('shot',target,p)
    for shot in shots:
        b.s.put('render',{'id':'render-'+shot['id'],'projectId':p,'shotId':shot['id'],'assetVariants':shot['assetVariants'],'status':'accepted','freshness':'clean','selected':True,'pinned':True},p)
    before={s['id']:b.s.get(s['id']) for s in shots}
    proposal=b.propose(p,'B4',{'sceneId':scene['id'],'shotIds':[shots[1]['id']],'instruction':'让第二镜人物停顿更明确'})
    proposal['payload']['shots'][0]['actionLine']='主角停在门边，听见柜台后传来的声音。'
    b.s.put('proposal',proposal,p)
    b.adopt_proposal(p,proposal['id'])
    assert {s['id'] for s in b.list_active(p,'shot')}==set(before)
    for shot in (shots[0],shots[2],shots[3]):
        assert b.s.get(shot['id'])==before[shot['id']]
        media=b.s.get('render-'+shot['id'])
        assert media['selected'] and media['pinned'] and media['freshness']=='clean'
    changed=b.s.get(shots[1]['id'])
    assert changed['actionLine'].startswith('主角停在门边')
    assert changed['duration']==before[changed['id']]['duration']
    assert changed['soundCue']=='门铃后保持两秒安静'
    assert b.s.get('render-'+changed['id'])['freshness']=='broken'


def test_noop_patch_keeps_versions_and_keys(project):
    b,p,scene,asset,shots=project;ready_direction(b,p)
    before=[b.s.get(s['id']) for s in shots]
    keys=[b.render_request(p,{'shotId':s['id']})['key'] for s in shots]
    proposal=b.propose(p,'B4',{'sceneId':scene['id']})
    b.adopt_proposal(p,proposal['id'])
    assert [b.s.get(s['id']) for s in shots]==before
    assert [b.render_request(p,{'shotId':s['id']})['key'] for s in shots]==keys


def test_patch_cannot_retarget_a_locked_or_unrequested_shot(project):
    b,p,scene,asset,shots=project;ready_direction(b,p)
    proposal=b.propose(p,'B4',{'sceneId':scene['id'],'shotIds':[shots[1]['id']]})
    proposal['payload']['shots'][0]['shotId']=shots[0]['id'];b.s.put('proposal',proposal,p)
    with pytest.raises(DomainError,match='shotId'):b.adopt_proposal(p,proposal['id'])


def test_global_treatment_cannot_overwrite_a_later_scene_edit(project):
    b,p,scene,asset,shots=project
    proposal=b.propose(p,'B1',{})
    current=b.s.get(scene['id']);current['sourceText']='后来决定保留的新剧本。';b.s.put('scene',current,p)
    with pytest.raises(DomainError) as exc:b.adopt_proposal(p,proposal['id'])
    assert exc.value.code=='base_changed'
    assert b.s.get(scene['id'])['sourceText']=='后来决定保留的新剧本。'


def test_direction_proposal_tracks_relevant_asset_identity(project):
    b,p,scene,asset,shots=project
    proposal=b.propose(p,'B3',{'sceneId':scene['id']})
    current=b.s.get(asset['id']);current['freezeString']='一个不同的外形描述。';b.s.put('master',current,p)
    with pytest.raises(DomainError) as exc:b.adopt_proposal(p,proposal['id'])
    assert exc.value.code=='base_changed'


def test_direction_proposal_ignores_unrelated_asset_edits(project):
    b,p,scene,asset,shots=project
    other=b.save(p,'master',{'name':'无关道具','kind':'prop','freezeString':'另一场的红伞'})
    proposal=b.propose(p,'B3',{'sceneId':scene['id']})
    other['freezeString']='另一场的蓝伞';b.s.put('master',other,p)
    assert b.proposal_current(p,proposal)


def test_repeated_propose_reuses_pending_and_explicit_alternative_is_distinct(project):
    b,p,scene,asset,shots=project
    first=b.propose(p,'B3',{'sceneId':scene['id']})
    calls=len(b.s.list(p,'run'))
    repeated=b.propose(p,'B3',{'sceneId':scene['id']})
    assert repeated['id']==first['id'] and len(b.s.list(p,'run'))==calls
    alternative=b.propose(p,'B3',{'sceneId':scene['id'],'newCandidate':True})
    assert alternative['id']!=first['id']
    b.adopt_proposal(p,alternative['id'])
    assert b.s.get(first['id'])['status']=='superseded'


def test_proposal_readset_ignores_identical_record_revisions(project):
    b,p,scene,asset,shots=project
    proposal=b.propose(p,'B3',{'sceneId':scene['id']})
    b.s.put('scene',b.s.get(scene['id']),p)
    b.s.put('style',b.style(p),p)
    assert b.proposal_current(p,proposal)
    b.adopt_proposal(p,proposal['id'])


def test_rejected_patch_advances_with_feedback_and_does_not_replay_cache(project):
    b,p,scene,asset,shots=project;ready_direction(b,p)
    first=b.propose(p,'B4',{'sceneId':scene['id'],'shotIds':[shots[1]['id']]})
    first['status']='rejected';first['rejectReason']='反转泄露太早，保留遮挡。';b.s.put('proposal',first,p)
    count=len(b.s.list(p,'run'))
    nextstep=b.next_step(p)
    assert nextstep['state']=='ready' and nextstep['stage']=='B4' and nextstep['shotIds']==[shots[1]['id']]
    result=b.advance(p,{})
    assert result['advanced'] and result['proposal']['id']!=first['id']
    assert len(b.s.list(p,'run'))==count+1
    request=b.s.list(p,'run')[-1]['user']
    assert '反转泄露太早' in request and first['id'] in request
    assert not b.advance(p,{})['advanced']
    assert len(b.s.list(p,'run'))==count+1


def test_render_identity_uses_effective_description_not_review_metadata(project):
    b,p,scene,asset,shots=project
    original=b.render_request(p,{'shotId':shots[0]['id']})['key']
    st=b.style(p);b.finalize(p,'style',st['id'],st['_version'])
    assert b.render_request(p,{'shotId':shots[0]['id']})['key']==original
    master=b.s.get(asset['id']);master['freezeString']+=' 雨衣有清晰可见的布料纹理。'
    plan=b.change_plan(p,'master',master);b.save(p,'master',master,plan['planHash'])
    with pytest.raises(DomainError,match='未人工定稿'):
        b.render_request(p,{'shotId':shots[0]['id']})
    b.finalize(p,'master',asset['id'])
    assert b.render_request(p,{'shotId':shots[0]['id']})['key']!=original


def test_equal_media_content_can_bind_to_distinct_shots(project):
    b,p,scene,asset,shots=project
    second={**b.s.get(shots[0]['id']),'id':shots[1]['id'],'order':1};b.s.put('shot',second,p)
    first=render_once(b,p,shots[0]);other=render_once(b,p,second)
    assert other['shotId']==second['id'] and first['id']!=other['id']
    assert other['renderKey']==first['renderKey'] and other['cacheHit']


def test_reference_record_ids_do_not_change_media_content_identity(project):
    b,p,scene,asset,shots=project
    req=b.render_request(p,{'shotId':shots[0]['id']})
    def key(ref):return render_key(req['shot'],[],req['style'],req['profile'],req['seed'],references=[ref],compiled=req['compiled'])
    assert key({'keyframe':'a','sha256':'same'})==key({'keyframe':'b','sha256':'same'})
    assert key({'keyframe':'a','sha256':'same'})!=key({'keyframe':'a','sha256':'changed'})


def test_ui_foreshadow_fields_enforce_setup_size(project):
    b,p,scene,asset,shots=project
    rule={'variantId':asset['defaultVariantId'],'setupSceneId':scene['id']}
    report=validate_shots(shots,b.list_active(p,'direction')[0],b.style(p),foreshadows=[rule])
    assert not report['passed'] and any(i['code']=='setup_closeup' for i in report['issues'])


def test_advance_stops_for_choice_and_finishes_at_storyboard(studio):
    b=studio.state.service
    p=b.create({'source':'一个人进入便利店。','targetDuration':8,'preset':'vertical'})['project']['id']
    assert b.next_step(p)['stage']=='B0'
    first=b.advance(p,{})
    assert first['advanced'] and first['nextStep']['state']=='awaiting_choice'
    count=len(b.s.list(p,'run'));assert not b.advance(p,{})['advanced'];assert len(b.s.list(p,'run'))==count
    b.adopt_proposal(p,first['proposal']['id'])
    assert b.next_step(p)['action']=='finalize_style'
    st=b.style(p);b.finalize(p,'style',st['id'],st['_version'])
    for expected in ('B1','B2'):
        result=b.advance(p,{})
        assert result['proposal']['stage']==expected
        b.adopt_proposal(p,result['proposal']['id'])
    assert b.next_step(p)['action']=='finalize_assets'
    for asset in b.list_active(p,'master'):b.finalize(p,'master',asset['id'],asset['_version'])
    for expected in ('B3','B4'):
        result=b.advance(p,{})
        assert result['proposal']['stage']==expected
        b.adopt_proposal(p,result['proposal']['id'])
    assert b.next_step(p)['state']=='complete'
    assert not b.s.list(p,'render') and not b.s.list(p,'reservation')


@pytest.mark.parametrize('source',['scene','direction'])
def test_workflow_requests_timing_review_before_any_more_model_calls(project,source):
    b,p,scene,asset,shots=project;ready_direction(b,p)
    pr=b.s.get(p);pr['curves']=[{'sceneId':scene['id'],'targetDuration':8}];b.s.put('project',pr,p)
    obj=b.s.get(scene['id']) if source=='scene' else b.list_active(p,'direction')[0]
    obj['targetDuration']=32;b.s.put(source,obj,p)
    runs=len(b.s.list(p,'run'));step=b.next_step(p)
    assert step['state']=='needs_attention' and step['action']=='review_timing' and step['stage']=='B1'
    assert step['sceneId']==scene['id'] and step['feasibleDuration']==[6,20]
    assert step['timingSource']==source and '32' in step['reason'] and '6–20' in step['reason']
    result=b.advance(p,{})
    assert not result['advanced'] and result['nextStep']['action']=='review_timing'
    assert len(b.s.list(p,'run'))==runs
    assert b.s.get(obj['id'])['targetDuration']==32


def test_default_single_scene_duration_stops_after_treatment(studio):
    b=studio.state.service;p=b.create({'source':'主角进入便利店。','targetDuration':32,'preset':'vertical'})['project']['id']
    first=b.advance(p,{});b.adopt_proposal(p,first['proposal']['id'])
    st=b.style(p);b.finalize(p,'style',st['id'],st['_version'])
    treatment=b.advance(p,{});assert treatment['proposal']['stage']=='B1';b.adopt_proposal(p,treatment['proposal']['id'])
    step=b.next_step(p)
    assert step['action']=='review_timing' and step['feasibleDuration']==[6,20]
    assert not b.advance(p,{})['advanced']
    assert not b.list_active(p,'direction') and not b.list_active(p,'shot')


def export_scene(**overrides):
    e={'sceneId':'source-scene','revision':'source-revision','order':0,'contract':{'summary':'进入便利店','reveals':['进门']},'body':{'action':'主角进入便利店。','dialogue':[]},'canonSlice':{'characters':[],'location':[],'props':[],'facts':[],'beliefs':[]},'narrativeContext':{'knowledgeDelta':[]},'directives':{'targetDuration':8},'tensionType':'mystery','visualMotifs':[]}
    e.update(overrides)
    e.update(contractHash=digest(e['contract']),bodyHash=digest(e['body']),canonHash=digest(e['canonSlice']),narrativeHash=digest(e['narrativeContext']),directivesHash=digest({'directives':e['directives'],'tensionType':e['tensionType'],'visualMotifs':e['visualMotifs']}))
    return {'format':'SceneExport-v1','schemaVersion':2,'scenes':[e]}


@pytest.mark.parametrize('field,value',[('narrativeContext',{'knowledgeDelta':['观众知道门后有人']}),('directives',{'targetDuration':9})])
def test_scene_export_v2_invalidates_local_direction_and_shots(project,field,value):
    b,p,scene,asset,shots=project
    payload=export_scene();sid=b.import_scene_export(p,payload)['sceneIds'][0]
    direction={**b.list_active(p,'direction')[0],'id':uid('direction'),'sceneId':sid,'status':'locked'};b.s.put('direction',direction,p)
    imported={**shots[0],'id':uid('shot'),'sceneId':sid};b.s.put('shot',imported,p)
    b.import_scene_export(p,export_scene(**{field:value}))
    assert b.s.get(imported['id'])['freshness']=='broken'
    assert b.s.get(direction['id'])['freshness']=='broken' and b.s.get(direction['id'])['status']=='locked'
    assert all(b.s.get(s['id'])['freshness']=='clean' for s in shots)
    assert b.s.get(sid)[field]==value


def test_unchanged_source_export_preserves_local_adaptation(project):
    b,p,scene,asset,shots=project;payload=export_scene()
    sid=b.import_scene_export(p,payload)['sceneIds'][0]
    local=b.s.get(sid);local['presentation']='导演在 B 中选择的改编。';local['bodyHash']=digest(local['presentation']);b.s.put('scene',local,p)
    before=b.s.get(sid)
    assert b.import_scene_export(p,payload)['sceneIds']==[]
    assert b.s.get(sid)==before


def test_blocks_only_source_preserves_order_names_and_stage_directions(project):
    b,p,*_=project
    body={'sceneHeading':'INT. 便利店 - 夜','blocks':[{'type':'action','text':'他先放下雨伞。'},{'type':'dialogue','character':'source-char','text':'有人吗？','parenthetical':'低声'},{'type':'action','text':'灯突然熄灭。'},{'type':'dialogue','character':'source-char','text':'别动。'}]}
    canon={'characters':[{'id':'source-char','name':'小陈'}],'props':[],'location':[]}
    sid=b.import_scene_export(p,export_scene(body=body,canonSlice=canon))['sceneIds'][0]
    text=b.s.get(sid)['sourceText']
    assert text=='INT. 便利店 - 夜\n\n他先放下雨伞。\n\n小陈（低声）：有人吗？\n\n灯突然熄灭。\n\n小陈：别动。'
    assert 'source-char' not in text


def test_updated_blocks_archive_stale_presentation_without_hiding_new_script(project):
    b,p,*_=project;first=export_scene()
    sid=b.import_scene_export(p,first)['sceneIds'][0]
    local=b.s.get(sid);local['presentation']='本地旧版导演呈现。';local['bodyHash']=digest(local['presentation']);b.s.put('scene',local,p)
    body={'action':'不应优先显示的旧兼容动作','dialogue':[{'character':'source-char','text':'不应重复显示的旧兼容对白'}],'blocks':[{'type':'action','text':'新版先关门。'},{'type':'dialogue','character':'source-char','text':'新版台词。'}]}
    updated=export_scene(body=body,canonSlice={'characters':[{'id':'source-char','name':'小陈'}]})
    b.import_scene_export(p,updated);scene=b.s.get(sid)
    assert scene.get('presentation') is None
    assert scene['presentationFreshness']=='broken'
    assert scene['stalePresentation']['text']=='本地旧版导演呈现。'
    assert scene['sourceText']=='新版先关门。\n\n小陈：新版台词。'
    assert scene['presentationHistory'][-1]['sourceBodyHash']==first['scenes'][0]['bodyHash']


def test_windows_failed_taskkill_falls_back_to_direct_kill(monkeypatch):
    proc=Mock();proc.poll.return_value=None
    monkeypatch.setattr('app.runner.os.name','nt')
    monkeypatch.setattr('app.runner.subprocess.run',lambda *a,**kw:Mock(returncode=1))
    RunnerRegistry.kill(proc)
    proc.kill.assert_called_once()
