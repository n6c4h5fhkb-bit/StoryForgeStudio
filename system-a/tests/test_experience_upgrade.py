import pytest

from app.core import DomainError
from test_common import studio


def project(service,title,genre='都市悬疑'):
    return service.create({'title':title,'seed':'一个必须付出代价的选择','genre':genre})['project']['id']


def test_feedback_scope_pack_revocation_and_effect_metrics(studio):
    service=studio.state.service;memory=studio.state.experience
    first=project(service,'作品一');second=project(service,'作品二');other=project(service,'作品三','古装奇幻')
    saved=memory.record(first,{'text':'人物作出关键选择前，要让欲望和代价都清楚。','category':'preference','explicit':True,'anchor':{'type':'project'}})['experience']
    assert saved['status']=='active' and saved['id'] in {row['id'] for row in memory.applicable(first,{'stage':'scene'})}
    promoted=memory.confirm(first,saved['id'],{'level':'genre'})
    assert promoted['id'] in {row['id'] for row in memory.applicable(second,{'stage':'scene'})}
    assert promoted['id'] not in {row['id'] for row in memory.applicable(other,{'stage':'scene'})}
    pack=memory.export_pack(first);assert pack['format']=='ExperiencePack-v1' and len(pack['items'])==1
    imported=memory.import_pack(second,pack);assert imported['experienceIds']==[promoted['id']]
    guidance=memory.guidance(second,{'stage':'scene'});application=memory.applied(second,{'type':'scene','id':'candidate'},guidance,'v2')
    memory.validate(second,promoted['id'],{'result':'resolved','evidence':'新候选在选择前明确展示了失败代价。','applicationId':application['id']})
    memory.validate(second,promoted['id'],{'result':'unknown','evidence':'本次片段没有出现可验证的关键选择。'})
    metrics=memory.list(second)['metrics'];assert metrics['observedChecks']==1 and metrics['repeatRate']==0 and metrics['byExperience'][promoted['id']]['unknown']==1
    old_hash=memory.revision_hash(second,{'stage':'scene'})
    memory.validate(second,promoted['id'],{'result':'misapplied','failureStage':'scope','evidence':'纯氛围场没有角色选择，套用后破坏了留白。'})
    assert memory.s.get(promoted['id'])['status']=='candidate'
    assert memory.revision_hash(second,{'stage':'scene'})!=old_hash and not memory.applicable(second,{'stage':'scene'})


def test_vague_feedback_stays_candidate_until_reason_is_specific(studio):
    service=studio.state.service;memory=studio.state.experience;p=project(service,'模糊反馈')
    result=memory.record(p,{'text':'不好看','explicit':True,'anchor':{'type':'story_node'}});lesson=result['experience']
    assert lesson['status']=='candidate' and lesson['diagnosticSuggestions'] and not result['remembered']
    with pytest.raises(DomainError) as error:memory.confirm(p,lesson['id'],{'level':'project'})
    assert error.value.code=='experience_ambiguous'
    memory.update(p,lesson['id'],{'rule':'开场两段都只在解释背景，冲突进入太晚。','action':'短剧开场先出现人物正在承受的冲突，再补最少背景。'})
    confirmed=memory.confirm(p,lesson['id'],{'level':'project'})
    assert confirmed['status']=='active' and confirmed['confirmationReason'] is None
