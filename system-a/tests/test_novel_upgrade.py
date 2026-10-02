import copy,json,hashlib
import pytest
from app.novel import NovelService,chapter_index,entry_context
from app.core import DomainError
from app.story_contract import document_shape, normalize_document, replay
from app.creative_review import CHECKS
from test_common import studio


def test_cancelled_request_does_not_claim_model_has_read_the_excerpt(studio):
    n=NovelService(studio.state.service);p=n.create({'title':'取消读取','text':'第一章\n阿青打开盒子。'})['project']['id']
    def cancel():raise DomainError('任务已取消','cancelled',409)
    with pytest.raises(DomainError,match='取消'):n.propose(p,{},check=cancel)
    assert n.get(p)['source']['readRanges'][0]['status']=='loaded_for_adaptation'
    assert not n.s.list(p,'run')
    draft=n.propose(p,{});assert draft['passed']
    assert n.get(p)['source']['readRanges'][-1]['status']=='demo_loaded'


def test_novel_adopt_export_and_continue_preserves_first_chapter(studio):
    a=studio.state.service;n=NovelService(a);text='第一章 开门\n阿青推开仓库门。\n第二章 来客\n老林敲响仓库门。'
    p=n.create({'title':'小说改编','text':text})['project']['id']
    assert n.get(p)['source']['sha256']==hashlib.sha256(text.encode()).hexdigest()
    draft=n.propose(p,{})
    assert draft['passed'],draft['issues']
    assert draft['start']==draft['end']==1
    n.adopt(p,draft['id']);before={row['id']:row for row in a.nodes(p) if row['level'] in ('scene','script')}
    new=n.propose(p,{})
    assert new['passed'],new['issues']
    n.adopt(p,new['id'])
    for identifier,row in before.items():assert a.s.get(identifier)==row
    out=json.loads(a.export(p,'scene-export')[0])
    assert out['schemaVersion']==4 and len(out['scenes'])==2 and out['storyDocument']['continuity']
    assert out['analysisCoverage']['complete'] and out['analysisCoverage']['analysisFingerprint']
    assert {'knowledgeSnapshot','dramaticFunctions','evidenceSnapshot'}<=set(out)
    assert len(out['source']['readRanges'])==2
    assert n.next_step(p)['state']=='complete'


def test_full_book_analysis_reuses_unchanged_units_after_source_update(studio):
    n=NovelService(studio.state.service);text='第一章\n阿青打开木盒。\n第二章\n老林接过玉牌。'
    p=n.create({'title':'增量分析','text':text})['project']['id']
    first=n.analyze_all(p);before=n.analysis_status(p);rows_before=n.s.list(p,'book_unit_analysis')
    assert before['complete'] and before['analyzedUnits']==before['totalUnits']==2
    assert n.analyze_all(p)['id']==first['id'] and len(n.s.list(p,'book_unit_analysis'))==len(rows_before)
    updated='第一章\n阿青打开木盒。\n第二章\n老林接过玉牌后立即关门。'
    n.update_source(p,{'text':updated,'filename':'更新稿.txt'});second=n.analyze_all(p);status=n.analysis_status(p)
    current=[row for row in n.s.list(p,'book_unit_analysis') if row.get('sourceHash')==status['sourceHash']]
    assert second['id']!=first['id'] and status['complete'] and len(current)==2
    assert sum(bool(row.get('reusedFrom')) for row in current)==1


def test_advance_until_choice_returns_first_adaptation_without_full_book_gate(studio):
    a=studio.state.service;n=NovelService(a)
    p=n.create({'title':'自动推进','text':'第一章\n阿青打开木盒。\n第二章\n老林接过玉牌。'})['project']['id']
    result=a.advance(p,{'mode':'until_choice'})
    assert result['advanced'] and result['analysis'] is None
    assert result['novelDraft']['passed'] and result['nextStep']['state']=='awaiting_choice'
    status=n.analysis_status(p)
    assert not status['complete'] and status['analyzedUnits']==1 and status['totalUnits']==2
    assert len(n.get(p)['source']['readRanges'])==1


def test_selected_range_is_adapted_without_analyzing_unselected_book(studio):
    n=NovelService(studio.state.service)
    text=''.join(f'第{i}章 标题{i}\n角色完成动作{i}。\n' for i in range(1,13))
    p=n.create({'title':'只读所选范围','text':text})['project']['id'];updates=[]
    draft=n.propose(p,{'start':1,'end':5},progress=lambda value,message:updates.append((value,message)))
    assert draft['passed'] and draft['start']==1 and draft['end']==5
    status=n.analysis_status(p)
    assert status['analyzedUnits']==5 and status['totalUnits']==12 and not status['complete']
    assert not n.s.list(p,'book_unit_analysis')
    assert len(n.s.list(p,'chapter_analysis'))==1
    assert updates[0][0]==pytest.approx(.06) and '不会等待全书深读' in updates[0][1]


def test_duplicate_download_headings_are_collapsed_and_metadata_does_not_shift_chapters(studio):
    text='书名：测试\n作者：甲\n\n第1章 开门\n\n　　第1章 开门\n阿青开门。\n第2章 来客\n\n第2章 来客\n老林进门。'
    units=chapter_index(text,6000)
    assert len(units)==2 and [u['chapterNumber'] for u in units]==[1,2]
    assert units[0]['start']==0 and units[0]['title']=='第1章 开门'
    assert ''.join(text[u['start']:u['end']] for u in units)==text


def test_legacy_unadopted_project_reindexes_duplicate_units_lazily(studio):
    n=NovelService(studio.state.service);text='第1章 开门\n第1章 开门\n阿青开门。\n第2章 来客\n第2章 来客\n老林进门。'
    p=n.create({'title':'旧索引','text':text})['project']['id'];source=n.s.get(n.s.get(p)['sourceId'])
    source.pop('chapterIndexVersion');source['chapters']=[{'id':'legacy_'+str(i),'number':i+1,'chapterNumber':i+1,'part':1,'title':'旧单元','start':0,'end':len(text)} for i in range(4)]
    n.s.put('novel_source',source,p)
    repaired=n.get(p)['source']
    assert repaired['chapterIndexVersion']==2 and len(repaired['chapters'])==2


def test_novel_local_revision_preserves_unselected_scene(studio):
    a=studio.state.service;n=NovelService(a);p=n.create({'text':'第一章\n甲进门。\n第二章\n乙离开。'})['project']['id']
    first=n.propose(p,{});n.adopt(p,first['id']);second=n.propose(p,{});n.adopt(p,second['id'])
    scene=a.nodes(p)[-1];source=n.get(p)['source'];assert len(source['readRanges'])==2
    assert a.get(p)['project']['creationMode']=='novel'


def test_pending_draft_deduplicated_and_cannot_adopt_rejected(studio):
    a=studio.state.service;n=NovelService(a);p=n.create({'text':'风吹开了窗。'})['project']['id']
    one=n.propose(p,{});count=len(a.s.list(p,'run'));two=n.propose(p,{})
    assert one['id']==two['id'] and len(a.s.list(p,'run'))==count
    assert a.advance(p,{})['advanced'] is False
    one['status']='rejected';a.s.put('novel_draft',one,p)
    with pytest.raises(DomainError):n.adopt(p,one['id'])


def test_long_chapter_is_split_without_gaps_or_claimed_unread_range():
    text='序\n第一章\n'+('阿青走进仓库。\n'*1200)+'第二章\n老林到了。'
    units=chapter_index(text,1000)
    assert ''.join(text[u['start']:u['end']] for u in units)==text
    assert all(u['end']-u['start']<=1000 for u in units)
    assert len({u['id'] for u in units})==len(units)


def test_continuing_context_does_not_send_whole_adopted_manuscript(studio):
    a=studio.state.service;n=NovelService(a);p=n.create({'text':'第一章\n甲进门。\n第二章\n乙离开。\n第三章\n甲关门。'})['project']['id']
    one=n.propose(p,{});n.adopt(p,one['id']);two=n.propose(p,{});n.adopt(p,two['id'])
    original=a.llm.json;seen=[]
    def capture(project,role,system,context,*args,**kwargs):
        if role=='structure':seen.append(context)
        return original(project,role,system,context,*args,**kwargs)
    a.llm.json=capture;three=n.propose(p,{})
    assert three['passed'] and len(three['payload']['scenes'])==3
    assert len(seen[0]['shapeExample']['scenes'])==1
    assert 'scenes' not in seen[0]['previousAdopted'] and len(seen[0]['previousAdopted']['tailScenes'])==1


def test_long_history_context_keeps_holders_hidden_contents_and_named_returning_entities():
    entities={eid:{'kind':kind,'name':name} for eid,kind,name in [
        ('room','location','仓库'),('hero','character','阿青'),('box','prop','黑盒'),('hidden','prop','玉牌'),('old_friend','character','老林')]}
    state={'room':{},'hero':{'pos':{'rel':'at','target':'room'}},'box':{'pos':{'rel':'held_by','target':'hero'},'lid':'closed','contentsKnown':True},
           'hidden':{'pos':{'rel':'inside','target':'box'},'visibleTo':[]},'old_friend':{'pos':{'rel':'at','target':'room'}}}
    for index in range(500):
        identifier='past_'+str(index);entities[identifier]={'kind':'prop','name':'旧道具'+str(index)}
        state[identifier]={'pos':{'rel':'at','target':'room'}}
    document={'scenes':[{'id':'last','blocks':[]}],'continuity':{'entities':entities,'events':[{'sceneId':'last','locationId':'room','participants':['hero']}]}}
    before=copy.deepcopy(document)
    scoped=entry_context(document,'老林回来敲门。',state)
    assert set(scoped['entities'])=={'room','hero','box','hidden','old_friend'}
    assert scoped['stateAtEntry']['hidden']['visibleTo']==[] and document==before
    assert len(json.dumps(scoped,ensure_ascii=False))<2000


@pytest.mark.parametrize('phantom',[False,True])
def test_scoped_continuation_preserves_full_registry_and_rejects_phantom_contents(studio,phantom):
    a=studio.state.service;n=NovelService(a)
    p=n.create({'text':'第一章\n阿青打开盒子。\n第二章\n阿青合上盒盖。'})['project']['id']
    initial=document_shape();initial['continuity']['initialState']['prop_id']['contentsKnown']=True
    for index in range(200):
        eid='unused_'+str(index)
        initial['continuity']['entities'][eid]={'kind':'prop','name':'远处旧物'+str(index),'identity':'旧物独立编号'+str(index),'visualStateKeys':[]}
        initial['continuity']['initialState'][eid]={'pos':{'rel':'at','target':'room_id'},'condition':'unchanged'}
    initial=normalize_document(initial)
    original=a.llm.json;contexts=[]
    def model(project,role,system,context,*args,**kwargs):
        if role!='structure':return original(project,role,system,context,*args,**kwargs)
        contexts.append(copy.deepcopy(context))
        if not context.get('continueReading'):return copy.deepcopy(initial)
        new=document_shape();new['scenes'][0]['id']='next_scene'
        for block in new['scenes'][0]['blocks']:block['id']='next_'+block['id']
        new['continuity']['entities']=copy.deepcopy(context['previousAdopted']['entities'])
        new['continuity']['initialState']=copy.deepcopy(context['previousAdopted']['stateAtEntry'])
        event=new['continuity']['events'][0]
        event.update(id='next_event',sceneId='next_scene',action='角色合上盒盖',dialogueIds=['next_line_id'],
                     changes=[{'entityId':'prop_id','field':'lid','from':'open','to':'closed'}])
        new['presentationPlan']=[{'id':'next_presentation','eventId':'next_event','kind':'main','phase':'before','dialogueIds':['next_line_id']}]
        if phantom:
            new['continuity']['entities']['phantom']={'kind':'prop','name':'凭空出现的玉牌','identity':'无来源玉牌','visualStateKeys':[]}
            new['continuity']['initialState']['phantom']={'pos':{'rel':'inside','target':'prop_id'}}
        return new
    a.llm.json=model
    # Seed a large, already reviewed registry, then return to the normal budget
    # for continuation. The test concerns history accumulated across chapters.
    studio.state.settings.save({'llm':{'contextCharacters':100000}})
    first=n.propose(p,{});assert first['passed'];n.adopt(p,first['id'])
    studio.state.settings.save({'llm':{'contextCharacters':32000}})
    second=n.propose(p,{})
    if phantom:
        assert not second['passed'] and any(x.get('code')=='continuation_contents' for x in second['issues'])
        assert a.s.get(p)['activeNovelDraft']==first['id']
    else:
        assert second['passed'],second['issues'];n.adopt(p,second['id'])
        assert len(contexts[-1]['previousAdopted']['entities'])==3
        assert len(second['payload']['continuity']['entities'])==203
        final=list(replay(second['payload']['continuity']).values())[-1]['after']
        assert final['prop_id']['lid']=='closed' and final['unused_199']['condition']=='unchanged'


def test_dialogue_coverage_error_names_the_exact_missing_lines():
    document=document_shape();event=document['continuity']['events'][0]
    missing=event['dialogueIds'].pop()
    with pytest.raises(DomainError) as error:normalize_document(document)
    assert error.value.code=='dialogue_coverage'
    assert error.value.details=={'missingDialogueIds':[missing],'duplicateDialogueIds':[]}


def test_failed_novel_candidate_can_be_repaired_with_patches_without_full_rewrite(studio):
    service=studio.state.service;novel=NovelService(service)
    project=novel.create({'text':'第一章\n阿青打开盒子。'})['project'];source=service.s.get(project['sourceId'])
    failed={'id':'failed_novel','projectId':project['id'],'payload':document_shape(),'passed':False,'attempts':[],
            'issues':[{'code':'presentation','message':'调整呈现顺序'}],'status':'proposed','sourceId':source['id'],
            'sourceHash':source['sha256'],'start':1,'end':1,'requestKey':'old','baseDraftId':None,'createdAt':'2026-01-01T00:00:00Z','demo':True}
    service.s.put('novel_draft',failed,project['id']);calls=[]
    def model(project_id,role,system,request,*args,**kwargs):
        calls.append((role,copy.deepcopy(request)))
        if role=='reviewer':
            assert request['candidate']['title']=='局部修复稿'
            return {'checks':[{'id':name,'passed':True,'evidence':'已核对具体位置'} for name in CHECKS],'issues':[]}
        assert request['repairFormat']=='json_patch' and request['previousCandidate']['title']==failed['payload']['title']
        return {'patches':[{'op':'replace','path':'/title','value':'局部修复稿'}]}
    service.llm.json=model
    result=novel.propose(project['id'],{'repairDraftId':failed['id'],'newCandidate':'repair-1'})
    assert result['passed'] and result['repairedFrom']==failed['id'] and result['payload']['title']=='局部修复稿'
    assert [role for role,_ in calls]==['structure','reviewer']
