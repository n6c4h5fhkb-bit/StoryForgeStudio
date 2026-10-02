import copy
import io
import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.assembly import get_ffmpeg
from app.cinema import compile_prompt
from app.core import DomainError, digest
from test_common import studio
from test_shooting_upgrade import box_story, modern, provide_references


def imported_v4(studio):
    b=studio.state.service;doc=box_story();p=b.create({'title':'V4 工作流','source':'交接原稿'})['project']['id']
    export={'format':'SceneExport-v1','schemaVersion':4,'project':{'title':'V4 工作流','genre':'都市悬疑'},'source':{'route':'original','projectId':'a-source'},
        'scenes':[{'sceneId':'source-s1','storySceneId':'s1','body':{'blocks':copy.deepcopy(doc['scenes'][0]['blocks'])},'contract':{'summary':'开盒交接'}}],
        'storyDocument':doc,'continuityStatus':'declared','analysisCoverage':{'complete':True},'knowledgeSnapshot':{},'dramaticFunctions':[],'evidenceSnapshot':{},'versionFingerprint':digest(doc)}
    b.import_story_version(p,export);proposal=b.propose_shooting(p,{})
    assert proposal['passed'],proposal['issues']
    return b,p,proposal


def test_v4_requires_impact_preview_and_key_scene_choices_are_materially_different(studio):
    b,p,shooting=imported_v4(studio)
    with pytest.raises(DomainError) as error:b.adopt_shooting(p,shooting['id'])
    assert error.value.code=='plan_required'
    preview=b.shooting_adoption_plan(p,shooting['id']);b.adopt_shooting(p,shooting['id'],{'planHash':preview['planHash']})
    result=b.advance_creative(p,{})
    choices=result['proposals'];assert len(choices)==2 and {x['approachIndex'] for x in choices}=={0,1}
    first,second=choices
    assert first['payload']['direction']['dramaticFunction']!=second['payload']['direction']['dramaticFunction']
    assert first['payload']['rationale']!=second['payload']['rationale']
    with pytest.raises(DomainError) as error:b.adopt_director(p,first['id'])
    assert error.value.code=='plan_required'
    plan=b.director_adoption_plan(p,first['id']);b.adopt_director(p,first['id'],{'planHash':plan['planHash']})
    assert b.s.get(second['id'])['status']=='superseded'
    assert b.adopt_director(p,first['id'])['idempotent']
    assert b.adopt_shooting(p,shooting['id'])['idempotent']


def test_reference_authority_enters_prompt_and_generation_cache(studio):
    b,p,_=modern(studio);proposal=b.advance(p,{})['proposal'];b.adopt_proposal(p,proposal['id']);provide_references(b,p)
    shot=b.list_active(p,'shot')[0];manifest=b.event_manifest(p,shot)
    assert manifest['resolved'] and all(ref['controls'] and ref['excludeInheritance'] and ref['reviewEvidence'] for ref in manifest['resolved'])
    prompt=compile_prompt(b.with_dialogue(p,shot),manifest,b.style(p),b.renderer_profile(p))['videoPrompt']
    assert 'controls only' in prompt and 'Do not inherit' in prompt
    before=b.plan_generation_tasks(p,{'shotIds':[shot['id']],'groups':[{'shotIds':[shot['id']],'focus':'开盒动作'}]})['tasks'][0]
    target=manifest['resolved'][0];variant=b.s.get(target['variantId']);file=b.s.get(variant['referenceFileId']);roles=variant['roles']
    custom={role:{'controls':['身份轮廓','本镜声明状态'],'excludeInheritance':['旧背景','旧姿势','未声明道具']} for role in roles}
    b.review_reference(p,variant['id'],{'fileId':file['id'],'confirmed':True,'evidence':'再次查看图片，只采用身份轮廓与本镜状态。','roles':roles,'controlBindings':custom,'expectedVersion':variant['_version']})
    after=b.plan_generation_tasks(p,{'shotIds':[shot['id']],'groups':[{'shotIds':[shot['id']],'focus':'开盒动作'}]})['tasks'][0]
    assert before['inputHash']!=after['inputHash'] and after['references'][0]['excludeInheritance']


def test_gate_records_real_sample_times_and_dialogue_audio_unknown(studio):
    b,p,_=modern(studio);proposal=b.advance(p,{})['proposal'];b.adopt_proposal(p,proposal['id']);shot=b.list_active(p,'shot')[-1]
    folder=b.s.root/'media'/p;folder.mkdir(parents=True,exist_ok=True);video=folder/'observed.mp4'
    subprocess.run([get_ffmpeg(b.settings.read()),'-y','-v','error','-f','lavfi','-i','color=c=blue:s=96x96:r=10:d=4','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(video)],check=True,capture_output=True)
    file=b.register_file(p,video,'clip');render=b.attach_render(p,{'shotId':shot['id'],'fileId':file['id'],'kind':'clip','proposedInterval':{'in':1,'out':3}});report=b.s.get(render['gateReportId'])
    times=[row['time'] for row in report['sampledFrames']]
    assert len(times)>=2 and min(times)>=1 and max(times)<=3
    assert any(check['name']=='sampled_frames' and check['state']=='pass' for check in report['checks'])
    audio=next(check for check in report['checks'] if check['name']=='dialogue_audio');assert audio['state']=='unknown' and audio['details']['hasAudio']
    adopted=b.select_render(p,render['id'],{'selected':True,'humanReview':True,'reason':'已人工查看演示片段。','adoptedInterval':{'in':0,'out':4},'observedEndState':{},'observationEvidence':'已查看采用区间首尾，测试完整时长靠近最后一帧的取证。'})
    points=adopted['adoption']['observation']['timepoints']
    assert [row['kind'] for row in points]==['interval_start','interval_end'] and points[-1]['time']<4
    assert all(len(row['frameSha256'])==64 for row in points)


def test_production_package_maps_adopted_files_intervals_and_reference_boundaries(studio):
    b,p,_=modern(studio);proposal=b.advance(p,{})['proposal'];b.adopt_proposal(p,proposal['id']);provide_references(b,p);shot=b.list_active(p,'shot')[0]
    folder=b.s.root/'media'/p;clip=folder/'selected.mp4';clip.write_bytes(b'original-video-placeholder');file=b.register_file(p,clip,'clip')
    render={'id':'selected-clip','projectId':p,'shotId':shot['id'],'kind':'clip','fileId':file['id'],'url':file['url'],'selected':True,'freshness':'clean','status':'accepted','adoption':{'fileId':file['id'],'fileHash':file['sha256'],'interval':{'in':0.5,'out':2.5},'endFrameTime':2.46,'observedEndState':{},'observation':{'method':'human_observation','evidence':'制作包测试观察'}}}
    b.s.put('render',render,p)
    client=TestClient(studio,base_url='http://localhost',headers={'x-studio-client':'local-ui'});response=client.get(f'/api/projects/{p}/export/production-package')
    assert response.status_code==200,response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names=set(archive.namelist());manifest=json.loads(archive.read('production-package.json'))
        assert {'production-package.json','storyboard.html','README.txt'}<=names
        adopted=next(row for row in manifest['media'] if row['role']=='adopted_clip')
        assert adopted['adoption']['interval']=={'in':0.5,'out':2.5} and adopted['packagePath'] in names
        references=[row for row in manifest['media'] if row['role']=='asset_reference']
        assert references and all(row['packagePath'] in names and row['controlBindings'] for row in references)
        assert manifest['versions']['compilerVersion']=='2.1.0' and manifest['versionFingerprint']


def test_short_drama_experience_does_not_apply_to_cinema(studio):
    b=studio.state.service;memory=studio.state.experience
    def make(title,mode):
        p=b.create({'title':title,'source':'一场戏','presentationMode':mode})['project']['id'];row=b.s.get(p);row['genre']='小说推文';row['presentationMode']=mode;b.s.put('project',row,p);return p
    fast=make('快节奏','fast_drama');film=make('电影','cinema');same=make('同类短剧','fast_drama')
    lesson=memory.record(fast,{'text':'开场尽早让主角正在承受的冲突入画。','category':'preference','explicit':True})['experience'];memory.confirm(fast,lesson['id'],{'level':'genre'})
    assert lesson['id'] in {row['id'] for row in memory.applicable(same,{'stage':'director'})}
    assert lesson['id'] not in {row['id'] for row in memory.applicable(film,{'stage':'director'})}


def test_dreamina_model_specific_limits_are_validated_from_current_adapter(studio):
    settings=studio.state.settings;b=studio.state.service;p=b.create({'source':'一场戏'})['project']['id']
    with pytest.raises(DomainError):settings.save({'mediaVideos':{'provider':'dreamina','videoModel':'seedance2.0fast','videoResolution':'1080p'}})
    settings.save({'mediaVideos':{'provider':'dreamina','videoModel':'seedance2.5','videoResolution':'1080p'}})
    profile=b.renderer_profile(p,'clip')
    assert profile['maxSeconds']==30 and profile['maxImages']==30 and profile['maxVideos']==10


def dreamina_task(tmp_path,**inputs):
    ref=tmp_path/'ref.png';ref.write_bytes(b'png')
    base={'prompt':'角色打开盒子','width':720,'height':1280,'duration':5,'kind':'clip','referencePaths':[str(ref)],'referenceVideoPath':None,'media':{'videoModel':'seedance2.0fast','videoResolution':'720p','session':0,'timeout':2,'pollSeconds':0}}
    base.update(inputs);return {'inputs':base,'workdir':str(tmp_path)}


def test_dreamina_submit_persists_id_and_resume_only_queries(monkeypatch,tmp_path):
    from tools import render as renderer
    calls=[];monkeypatch.setattr(renderer,'dreamina_command',lambda cfg:'dreamina');monkeypatch.setattr(renderer,'dreamina_help_evidence',lambda *args:{'subcommand':args[1],'helpSha256':'help','checkedAt':1,'required':args[2]})
    def run(args,out,timeout):
        calls.append(args)
        if args[1]=='multimodal2video':return {'submit_id':'remote-1','gen_status':'querying'},SimpleNamespace(returncode=0)
        (out/'clip.mp4').write_bytes(b'video');return {'submit_id':'remote-1','gen_status':'success'},SimpleNamespace(returncode=0)
    monkeypatch.setattr(renderer,'dreamina_run',run)
    file,remote=renderer.dreamina(dreamina_task(tmp_path),tmp_path);assert file.name=='clip.mp4' and remote['submitId']=='remote-1'
    submitted=json.loads((tmp_path/'provider-submit.json').read_text(encoding='utf-8'));assert submitted['submitId']=='remote-1' and submitted['capabilityEvidence']['helpSha256']=='help'
    assert '--model_version' in calls[0] and 'seedance2.0fast' in calls[0] and '--video_resolution' in calls[0]
    calls.clear();(tmp_path/'clip.mp4').unlink();task=dreamina_task(tmp_path,resumeSubmitId='remote-1')
    file,_=renderer.dreamina(task,tmp_path);assert file.name=='clip.mp4' and all(args[1]=='query_result' for args in calls)


def test_dreamina_unknown_submit_state_is_recorded_without_blind_retry(monkeypatch,tmp_path):
    from tools import render as renderer
    monkeypatch.setattr(renderer,'dreamina_command',lambda cfg:'dreamina');monkeypatch.setattr(renderer,'dreamina_help_evidence',lambda *args:{'subcommand':args[1],'helpSha256':'help'})
    monkeypatch.setattr(renderer,'dreamina_run',lambda args,out,timeout:({'gen_status':'querying'},SimpleNamespace(returncode=0)))
    with pytest.raises(renderer.RemoteStateUnknown):renderer.dreamina(dreamina_task(tmp_path),tmp_path)
    record=json.loads((tmp_path/'provider-submit.json').read_text(encoding='utf-8'))
    assert record['status']=='state_unknown' and record['submitId'] is None and record['submissionAttempted']
