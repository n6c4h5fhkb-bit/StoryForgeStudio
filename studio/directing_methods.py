"""Small, versioned creative methods shared by writers and independent reviewers.

Intent and directing notes are evidence-bearing data, never tool instructions.
Execution cues are kept apart from reasons so notes do not invalidate pixels.
"""
from __future__ import annotations

import copy
import hashlib
import json

METHOD_VERSION = 1
MODE_FOCUS = {
    'cinema': '电影：通过具体行为、空间关系、潜台词和节奏对比表达；必要事实清楚，情绪可留解释空间。允许密集对白，不用慢镜或空镜数量冒充电影感。',
    'series': '剧集：人物关系持续发展，场次选择有后果，信息与情绪跨场承接；本场推进和后续期待同时成立。',
    'fast_drama': '快节奏短剧：尽快让观众知道谁想要什么、阻碍是什么；对白推动行动、立场和关系，持续兑现信息与情绪。允许必要停顿，不以不停争吵或频繁运镜冒充节奏。',
}
COMMON = [
    '人物行为从目的、阻碍、性格和处境出发；区分内心情绪与外在表达，不机械地把愤怒写成喊叫。',
    '分清必须理解、刻意暂缓揭示和可以开放解释的信息；留白不能掩盖必要因果，故意误导须有采用稿依据。',
    '空间通过距离、权力位置、遮挡和进入路径参与叙事；重复空间可以积累关系变化。优先使用已登记场景与物件。',
    '关键动作有准备、用力、变化和结束的可见过程，按需要选择，不给每镜套固定五步；停顿、运镜、切镜须有具体作用。',
]
STAGE_METHODS = {
    'script': [
        '在每个新写或修改场次的 sceneIntent 中记录人物目的/阻碍、本场变化和观众信息安排，引用实际正文、事件和实体 ID。沿用已有事实与知情记录，不另造事实。',
        '有剧情作用的新道具、动作和状态变化必须写进正文及 continuity；场次意图不能代替真实事件，也不能用说明补救正文缺失。',
    ],
    'director': [
        '同一输出先形成 direction.directingPlan 的观看重点、表演、空间和节奏，再落实 shots；说明只写两三句有用的话。',
        'B 可补眼神、停顿、走位和动作过程，但不能改变采用稿的身份、动机、知情安排、事件前后状态。需要新道具、信息或实质状态时返回 storyChangeRequests，由 A 修改。',
        'performanceBeats 写按顺序可执行的动作，覆盖 actionLine 的必要行动与结束状态；cameraCue 写 start/follow/end；cutPoint 分开 cue(结束条件) 与 reason(剪辑理由)。无需给静态镜头强加运镜。',
    ],
    'review': [
        '独立阅读连续情节：人物为什么这样行动，观众此时能否跟上，故意暂缓是否有依据，空间与切点是否服务信息或情绪。不要照抄候选的拍法理由作为通过证据。',
        '审美偏好和另一种可行拍法列为 minor 建议，不使正确性检查失败；明确事实、因果、状态、引用或必要信息交付错误才是 major。意图只是核对依据，不能豁免正文矛盾。',
    ],
    'media_review': [
        '按真实采用区间核对可见空间、状态和信息交付。采样帧不足以证明动作全过程、微小时机或声音；这些保持 unknown，交连续播放确认。',
    ],
}


def method_pack(mode, stage):
    """Stable per-mode/per-duty prefix; no conversation transcript or plot examples."""
    result = {'methodVersion': METHOD_VERSION, 'presentationMode': mode, 'stage': stage,
              'focus': MODE_FOCUS.get(mode, MODE_FOCUS['series']),
              'methods': COMMON + STAGE_METHODS.get(stage, [])}
    result['revisionHash'] = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return result


def scene_intent_shape():
    return {'methodVersion': METHOD_VERSION, 'dramaticChange': '本场关系或处境怎样改变',
            'characters': [{'entityId': '实际人物ID', 'goal': '当前目的', 'obstacle': '阻碍', 'blockIds': [], 'eventIds': []}],
            'audience': {'mustUnderstand': [{'information': '本场必须交付的信息', 'blockIds': [], 'eventIds': []}],
                         'withheld': [], 'openToInterpretation': []},
            'blockIds': [], 'eventIds': [], 'entityIds': []}


def directing_plan_shape():
    return {'methodVersion': METHOD_VERSION, 'summary': ['本场推荐拍法及取舍'],
            'focus': '观众先注意什么，在哪里改变判断', 'performance': '目的怎样通过可见行为落实',
            'space': '人物和物件关系怎样参与叙事', 'rhythm': '关键等待、变化与切点',
            'blockIds': [], 'eventIds': [], 'entityIds': []}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _object(value, label):
    _require(isinstance(value, dict), label + ' 必须为对象')


def _strings(value, label):
    _require(isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value), label + ' 必须为字符串列表')


def _version(value, label):
    version = value.get('methodVersion', METHOD_VERSION)
    _require(type(version) is int and version == METHOD_VERSION, label + ' 方法版本不受支持')


def _refs(value, blocks, events, entities, label):
    for key, known in (('blockIds', blocks), ('eventIds', events), ('entityIds', entities)):
        if key in value:
            _strings(value[key], label + '.' + key)
            _require(set(value[key]) <= known, label + ' 引用了范围外或不存在的 ' + key)


def validate_scene_intents(document):
    """Validate declared references only; absence is compatible with old documents."""
    entities = set(document['continuity']['entities'])
    all_events = {e['id'] for e in document['continuity']['events']}
    for scene in document['scenes']:
        intent = scene.get('sceneIntent')
        if intent is None:
            continue
        _object(intent, 'sceneIntent'); _version(intent, 'sceneIntent')
        blocks = {b['id'] for b in scene['blocks']}
        events = {e['id'] for e in document['continuity']['events'] if e['sceneId'] == scene['id']}
        _refs(intent, blocks, events, entities, 'sceneIntent')
        _require(isinstance(intent.get('dramaticChange', ''), str), 'sceneIntent.dramaticChange 必须为文字')
        _require(isinstance(intent.get('characters', []), list), 'sceneIntent.characters 必须为列表')
        for actor in intent.get('characters', []):
            _object(actor, '人物目的'); _refs(actor, blocks, events, entities, '人物目的')
            _require(actor.get('entityId') in entities and document['continuity']['entities'][actor['entityId']]['kind'] == 'character', '人物目的引用了未知人物')
            _require(all(isinstance(actor.get(key, ''), str) for key in ('goal', 'obstacle')), '人物目的和阻碍必须为文字')
        audience = intent.get('audience', {}); _object(audience, 'sceneIntent.audience')
        for category in ('mustUnderstand', 'withheld', 'openToInterpretation'):
            values = audience.get(category, [])
            _require(isinstance(values, list), '观众信息必须为列表')
            for item in values:
                _object(item, '观众信息'); _refs(item, blocks, events, entities, '观众信息')
                _require(isinstance(item.get('information'), str) and item['information'].strip(), '观众信息缺少具体说明')
                if category == 'withheld':
                    _require(isinstance(item.get('reason'), str) and item['reason'].strip(), '暂缓揭示须声明理由')
                    reveal = item.get('revealEventId')
                    _require(reveal in all_events if reveal else item.get('outsideScope') is True, '暂缓揭示须引用揭示事件，或明确说明在本次范围之外')


def require_scene_intents(document, target_ids=None):
    """New model outputs supply intent; historical out-of-scope scenes stay intact."""
    targets=set(target_ids or [s['id'] for s in document['scenes']])
    for scene in document['scenes']:
        if scene['id'] not in targets: continue
        intent=scene.get('sceneIntent') or {}
        _require(isinstance(intent.get('dramaticChange'),str) and intent['dramaticChange'].strip(), '新写或修改场次须补充 sceneIntent.dramaticChange：'+scene['id'])
        audience=intent.get('audience',{})
        _require(any(audience.get(key) for key in ('mustUnderstand','withheld','openToInterpretation')), '新写或修改场次须声明观众信息安排：'+scene['id'])


def validate_directing_fields(direction, shots, scene, events, entities):
    blocks = {b['id'] for b in scene.get('blocks', [])}; event_ids = {e['id'] for e in events}; entity_ids = set(entities)
    plan = direction.get('directingPlan')
    if plan:
        _object(plan, 'directingPlan'); _version(plan, 'directingPlan')
        _refs(plan, blocks, event_ids, entity_ids, 'directingPlan')
        if 'summary' in plan: _strings(plan['summary'], 'directingPlan.summary')
        _require(all(isinstance(plan.get(key, ''), str) for key in ('focus', 'performance', 'space', 'rhythm')), '拍法说明必须为文字')
    for shot in shots:
        _version(shot, '镜头')
        beats = shot.get('performanceBeats', [])
        _require(isinstance(beats, list), 'performanceBeats 必须为列表')
        for beat in beats:
            _object(beat, '表演动作'); _refs(beat, blocks, event_ids, entity_ids, '表演动作')
            _require(isinstance(beat.get('action'), str) and beat['action'].strip(), '表演动作缺少可执行 action')
            _require(all(isinstance(beat.get(key, ''), str) for key in ('trigger', 'endCue', 'reason')), '动作触发、结束条件和理由必须为文字')
            if beat.get('entityId'): _require(beat['entityId'] in entity_ids, '表演动作引用了未知实体')
            if beat.get('eventId'): _require(beat['eventId'] == shot.get('eventId'), '表演动作不能引用另一事件')
        for field, keys in (('cameraCue', ('start', 'follow', 'end', 'reason')), ('cutPoint', ('cue', 'reason'))):
            value = shot.get(field, {}); _object(value, field)
            _require(all(isinstance(value.get(key, ''), str) for key in keys), field + ' 条件与理由必须为文字')


def execution_cues(shot):
    """Observable cues only; narrative explanations never become media input."""
    beats = [{key: beat[key] for key in ('trigger', 'action', 'endCue') if beat.get(key)} for beat in shot.get('performanceBeats', [])]
    camera = {key: value for key, value in shot.get('cameraCue', {}).items() if key in ('start', 'follow', 'end') and value}
    return {'performanceBeats': beats, 'cameraCue': camera, 'cutCue': shot.get('cutPoint', {}).get('cue', '')}


def without_explanations(value):
    """Stable execution/state comparison, also used for script-import impact."""
    if isinstance(value, list):
        return [without_explanations(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {key: without_explanations(item) for key, item in value.items()
            if key not in ('sceneIntent', 'directingPlan', 'methodVersion', 'reason', 'rationale', 'reviewRequired', 'reviewNotes', 'protectedFacts', 'storyFacts', 'dramaticFunctions')}


def review_view(candidate):
    """Reviewer sees execution and A intent; B's persuasive rationale is excluded."""
    result = copy.deepcopy(candidate)
    if isinstance(result, dict) and isinstance(result.get('direction'), dict):
        result.pop('rationale', None)
        result['direction'].pop('directingPlan', None)
        for shot in result.get('shots', []):
            for beat in shot.get('performanceBeats', []): beat.pop('reason', None)
            for field in ('cameraCue', 'cutPoint'):
                if isinstance(shot.get(field), dict): shot[field].pop('reason', None)
    return result
