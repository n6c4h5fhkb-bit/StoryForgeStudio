"""Versioned story interchange and deterministic event continuity.

This module is shipped independently in each application. It validates declared
facts; semantic and actual-media observations remain separately evidenced.
"""
from __future__ import annotations
import copy
from .core import ensure, digest
from studio.directing_methods import validate_scene_intents

VERSION = 3
RELATIONS = {'at', 'inside', 'on', 'held_by', 'worn_by', 'attached_to'}
REFERENCE_ROLES = {'identity', 'environment', 'start_state', 'end_state', 'detail'}


def document_shape():
    """Small illustrative schema; never duplicate the manuscript in prompts."""
    return {'title':'作品名','summary':'本段戏剧变化','scenes':[{'id':'scene_id','title':'场次名','blocks':[{'id':'block_id','type':'action','text':'可表演的动作'},{'id':'line_id','type':'dialogue','speakerId':'person_id','mode':'speech','text':'准确台词'}],'sourceRefs':[{'sourceId':'当前真实来源','charStart':0,'charEnd':20}]}], 'continuity':{'status':'declared','entities':{'room_id':{'kind':'location','name':'场景','identity':'稳定空间','visualStateKeys':[]},'person_id':{'kind':'character','name':'角色名','identity':'稳定身份','visualStateKeys':['wardrobe']},'prop_id':{'kind':'prop','name':'道具','identity':'稳定形制','visualStateKeys':['lid']}},'initialState':{'room_id':{},'person_id':{'pos':{'rel':'at','target':'room_id'},'canSpeak':True,'wardrobe':'已知服装'},'prop_id':{'pos':{'rel':'held_by','target':'person_id'},'lid':'closed'}},'events':[{'id':'event_id','sceneId':'scene_id','locationId':'room_id','participants':['person_id','prop_id'],'action':'角色打开盒盖','origin':'adapted','sourceRefs':[{'sourceId':'当前真实来源'}],'changes':[{'entityId':'prop_id','field':'lid','from':'closed','to':'open'}],'dialogueIds':['line_id']}]}, 'presentationPlan':[{'id':'presentation_id','eventId':'event_id','kind':'main','phase':'before','dialogueIds':['line_id']}], 'protectedFacts':[],'storyChanges':[],'changeReasons':[],'sourceMapping':[{'sourceId':'原稿块 ID','targetIds':['block_id'],'reason':'保留/删除/合并/改写的实际依据'}]}


def stable_blocks(body, namespace):
    blocks = copy.deepcopy(body.get('blocks') or [])
    if not blocks:
        if body.get('action'): blocks.append({'type': 'action', 'text': body['action']})
        blocks.extend({'type': 'dialogue', **line} for line in body.get('dialogue', []))
    seen = set()
    for index, block in enumerate(blocks):
        ensure(isinstance(block.get('text'), str) and block['text'].strip(), '正文块不能为空', 'story_schema', 422)
        block.setdefault('id', namespace + '_block_' + digest([block.get('type'), block['text'], index])[:12])
        ensure(block['id'] not in seen, '正文块 ID 重复', 'duplicate_block', 422)
        seen.add(block['id'])
        if block.get('type') == 'dialogue':
            block.setdefault('mode', 'speech')
            ensure(block['mode'] in ('speech', 'inner', 'narration', 'system'), '发声方式无效', 'story_schema', 422)
            block.setdefault('speakerId', block.get('character'))
            ensure(block['mode'] != 'speech' or block.get('speakerId'), '对白缺少说话者', 'story_schema', 422)
            if block.get('speakerId'):block.setdefault('character',block['speakerId'])
    return blocks


def location_of(state, entities, entity):
    visited = set()
    while entity in entities:
        ensure(entity not in visited, '位置或包含关系形成循环', 'containment_cycle', 422)
        visited.add(entity)
        if entities[entity].get('kind', entities[entity].get('type')) == 'location': return entity
        position = state.get(entity, {}).get('pos')
        if not position or position.get('unknown'): return None
        entity = position['target']
    return None


def visible(state, entities, entity, observer='AUDIENCE'):
    visited = set()
    while entity in entities:
        if entity in visited: return False
        visited.add(entity)
        row = state.get(entity, {})
        if row.get('active') is False or row.get('consumed') is True or row.get('destroyed') is True: return False
        if row.get('visibleTo') is not None and observer not in row['visibleTo']: return False
        position = row.get('pos')
        if not position or position.get('unknown'): return True
        parent = position['target']
        if position['rel'] == 'inside' and state.get(parent, {}).get('lid') == 'closed' and not entities[parent].get('transparent'): return False
        entity = parent
    return True


def state_value(state, entity, field):
    row = state.get(entity, {})
    if field == '@contents':
        if row.get('contentsKnown') is not True: return {'unknown': True}
        return sorted(e for e, s in state.items() if s.get('active') is not False and s.get('pos') == {'rel': 'inside', 'target': entity})
    return row.get(field, {'unknown': True})


def visual_claims(state, entities, entity):
    keys = set(entities[entity].get('visualStateKeys', []))
    if state.get(entity, {}).get('lid') == 'closed' and not entities[entity].get('transparent'): keys.discard('@contents')
    return {key: state_value(state, entity, key) for key in sorted(keys)}


def check_world(state, entities):
    ensure(set(state) == set(entities), '实体与初始状态不匹配', 'state_entities', 422)
    for entity, spec in entities.items():
        row = state[entity]
        ensure(isinstance(row, dict), '实体状态必须是对象', 'state_schema', 422)
        position = row.get('pos')
        if position and not position.get('unknown'):
            ensure(position.get('rel') in RELATIONS and position.get('target') in entities, '位置引用无效', 'position_target', 422)
            if position['rel'] in ('held_by', 'worn_by'):
                ensure(entities[position['target']].get('kind') == 'character', '持有者必须是人物', 'position_target', 422)
            if position['rel'] == 'at': ensure(entities[position['target']].get('kind') == 'location', 'at 必须指向地点', 'position_target', 422)
        location_of(state, entities, entity)
        if row.get('consumed') is True or row.get('destroyed') is True:
            ensure(row.get('active') is False and position is None, '已消耗物品不能继续持有或出现', 'consumed_present', 422)


def replay(continuity):
    entities = continuity.get('entities', {})
    state = copy.deepcopy(continuity.get('initialState', {}))
    check_world(state, entities)
    frames = {}
    events = continuity.get('events', [])
    for event in events:
        identifier = event.get('id')
        ensure(isinstance(identifier, str) and identifier and identifier not in frames, '事件 ID 缺失或重复', 'event_id', 422)
        ensure(event.get('locationId') in entities and entities[event['locationId']].get('kind') == 'location', '事件缺少有效地点', 'event_location', 422)
        ensure(set(event.get('participants', [])) <= set(entities), '事件引用未知参与者', 'event_participant', 422)
        before = copy.deepcopy(state)
        for condition in event.get('requires', []):
            ensure(state_value(state, condition['entityId'], condition['field']) == condition['value'], '事件前置状态不成立', 'event_precondition', 422, {'eventId': identifier})
        for change in event.get('changes', []):
            entity, field = change.get('entityId'), change.get('field')
            ensure(entity in state and field in state[entity], '变化必须引用已声明状态', 'undeclared_state', 422,
                   {'eventId': identifier, 'entityId': entity, 'field': field})
            ensure(state[entity][field] == change.get('from'), '事件起始状态与上一事件不符', 'state_from', 422, {'eventId': identifier, 'entityId': entity, 'field': field})
            if field == 'pos':
                old, new = change['from'], change['to']
                for position in (old, new):
                    if position and position.get('rel') == 'inside':
                        ensure(state.get(position['target'], {}).get('lid') != 'closed', '物品取放前需要打开容器', 'closed_container', 422)
                if old and new and not old.get('unknown') and not new.get('unknown') and new['rel'] != 'at' and event.get('transition', 'continuous') == 'continuous':
                    a, b = location_of(state, entities, entity), location_of(state, entities, new['target'])
                    ensure(a is not None and a == b, '道具交接双方不在同一地点', 'remote_transfer', 422,
                           {'eventId': identifier, 'entityId': entity, 'targetId': new['target'], 'entityLocation': a, 'targetLocation': b})
            state[entity][field] = copy.deepcopy(change['to'])
        check_world(state, entities)
        frames[identifier] = {'before': before, 'after': copy.deepcopy(state)}
    return frames


def normalize_document(payload, namespace='script'):
    doc = copy.deepcopy(payload)
    ensure(isinstance(doc.get('scenes'), list) and doc['scenes'], '拍摄版缺少场次', 'story_schema', 422)
    scene_ids, block_ids, dialogue = set(), set(), []
    for index, scene in enumerate(doc['scenes']):
        scene.setdefault('id', namespace + '_scene_' + str(index + 1))
        ensure(scene['id'] not in scene_ids, '场次 ID 重复', 'story_schema', 422)
        scene_ids.add(scene['id'])
        scene['blocks'] = stable_blocks(scene.get('body', scene), scene['id'])
        for block in scene['blocks']:
            ensure(block['id'] not in block_ids, '跨场正文块 ID 重复', 'duplicate_block', 422)
            block_ids.add(block['id'])
            if block.get('type') == 'dialogue': dialogue.append({**block, 'sceneId': scene['id']})
    doc['dialogueLines'] = dialogue
    continuity = doc.get('continuity')
    ensure(isinstance(continuity, dict), '缺少事件连续性，请先完成拍摄版转换', 'continuity_required', 422)
    frames = replay(continuity)
    ensure(frames, '拍摄版必须包含事件', 'continuity_required', 422)
    lines = {line['id']: line for line in dialogue}
    assigned = []
    for event in continuity['events']:
        ensure(event.get('sceneId') in scene_ids, '事件引用未知场次', 'event_scene', 422)
        ensure(event.get('sourceRefs') or event.get('origin') == 'adapted', '事件缺少来源或改编声明', 'event_source', 422)
        for identifier in event.get('dialogueIds', []):
            ensure(identifier in lines, '事件引用未知对白', 'dialogue_reference', 422)
            line = lines[identifier]
            ensure(line['sceneId'] == event['sceneId'], '对白与事件场次不符', 'dialogue_reference', 422)
            if line['mode'] == 'speech':
                ensure(line['speakerId'] in continuity['entities'], '说话者未登记', 'dialogue_reference', 422)
                ensure(frames[event['id']]['before'][line['speakerId']].get('canSpeak') is not False, '人物在能力解锁之前说话', 'speech_before_unlock', 422)
            assigned.append(identifier)
    duplicates=sorted({identifier for identifier in assigned if assigned.count(identifier)>1})
    missing=sorted(set(lines)-set(assigned))
    ensure(not duplicates and not missing, '事件必须完整且唯一地分配拍摄版对白', 'dialogue_coverage', 422,
           {'missingDialogueIds':missing,'duplicateDialogueIds':duplicates})
    plan = doc.get('presentationPlan') or [{'id': event['id'] + '_main', 'eventId': event['id'], 'kind': 'main', 'phase': 'before', 'dialogueIds': event.get('dialogueIds', [])} for event in continuity['events']]
    event_order = {event['id']: i for i, event in enumerate(continuity['events'])}
    seen, delivered, last = set(), [], -1
    for index, item in enumerate(plan):
        item.setdefault('id', namespace + '_presentation_' + str(index + 1))
        ensure(item.get('eventId') in frames and item.get('phase', 'before') in ('before', 'after'), '呈现顺序引用无效', 'presentation_reference', 422)
        event=next(e for e in continuity['events'] if e['id']==item['eventId'])
        ensure(set(item.get('dialogueIds',[]))<=set(event.get('dialogueIds',[])),'呈现对白与引用事件不一致','dialogue_reference',422)
        kind = item.get('kind', 'main')
        ensure(kind in ('main', 'preview', 'flashback', 'time_jump'), '呈现方式无效', 'presentation_kind', 422)
        order = event_order[item['eventId']]
        if kind == 'main':
            ensure(order >= last, '正文事件乱序，倒叙需要明确声明', 'presentation_order', 422)
            last = order
        else: ensure(item.get('reason'), '预演、倒叙或跳时需要说明接法', 'presentation_reason', 422)
        if kind != 'preview': seen.add(item['eventId'])
        delivered.extend(item.get('dialogueIds', []))
    ensure(seen == set(frames), '正文没有覆盖全部事件', 'event_coverage', 422)
    duplicates=sorted({identifier for identifier in delivered if delivered.count(identifier)>1})
    missing=sorted(set(lines)-set(delivered))
    ensure(not duplicates and not missing, '呈现对白缺失或重复', 'dialogue_coverage', 422,
           {'missingDialogueIds':missing,'duplicateDialogueIds':duplicates})
    ensure(len({x['id'] for x in plan}) == len(plan), '呈现 ID 重复', 'presentation_reference', 422)
    doc['presentationPlan'] = plan
    try:
        validate_scene_intents(doc)
    except ValueError as error:
        ensure(False, str(error), 'scene_intent', 422)
    doc['schemaVersion'] = VERSION
    return doc


def readable_scene(scene, entities=None):
    entities=entities or {}
    return '\n\n'.join((str(entities.get(b.get('speakerId',b.get('character','')),{}).get('name',b.get('speakerId',b.get('character','')))) + '：' if b.get('type') == 'dialogue' else '') + b['text'] for b in scene['blocks'])


def conservative_document(scenes, namespace='demo'):
    """Structural/demo seed only. Never invent prop transitions from prose."""
    entities, initial, events, output = {}, {}, [], []
    for index, original in enumerate(scenes):
        scene = copy.deepcopy(original)
        scene.setdefault('id', namespace + '_scene_' + str(index + 1))
        scene.setdefault('blocks', [{'type': 'action', 'text': scene.get('sourceText') or scene.get('presentation') or '待完善的场次'}])
        scene['blocks'] = stable_blocks(scene, scene['id'])
        location = scene.get('locationId') or scene['id'] + '_location'
        scene['locationId'] = location
        entities.setdefault(location, {'kind': 'location', 'name': scene.get('location', '本场地点'), 'identity': scene.get('location', '本场地点'), 'visualStateKeys': []})
        initial.setdefault(location, {})
        speakers = {b['speakerId'] for b in scene['blocks'] if b.get('type') == 'dialogue' and b.get('speakerId')}
        changes = []
        for speaker in speakers:
            entities.setdefault(speaker, {'kind': 'character', 'name': speaker, 'identity': speaker, 'visualStateKeys': []})
            if speaker not in initial: initial[speaker] = {'pos': {'rel': 'at', 'target': location}, 'canSpeak': True}
            previous = next((e['locationId'] for e in reversed(events) if speaker in e['participants']), initial[speaker]['pos']['target'])
            if previous != location: changes.append({'entityId': speaker, 'field': 'pos', 'from': {'rel': 'at', 'target': previous}, 'to': {'rel': 'at', 'target': location}})
        events.append({'id': scene['id'] + '_event', 'sceneId': scene['id'], 'locationId': location, 'participants': sorted(speakers), 'action': readable_scene(scene), 'changes': changes, 'origin': 'adapted', 'sourceRefs': scene.get('sourceRefs', []), 'dialogueIds': [b['id'] for b in scene['blocks'] if b.get('type') == 'dialogue']})
        output.append(scene)
    return normalize_document({'scenes': output, 'continuity': {'status': 'needs_completion', 'entities': entities, 'initialState': initial, 'events': events}}, namespace)


def validate_shot_coverage(shots, document, scene_id):
    local = [item for item in document['presentationPlan'] if next(e for e in document['continuity']['events'] if e['id'] == item['eventId'])['sceneId'] == scene_id]
    positions = {item['id']: i for i, item in enumerate(local)}
    known_lines = {line['id'] for line in document['dialogueLines'] if line['sceneId'] == scene_id}
    ordered = sorted(shots, key=lambda s: s['order'])
    seen, dialogue, previous = set(), [], -1
    for shot in ordered:
        reference = shot.get('presentationId')
        ensure(reference in positions, '分镜缺少采用版事件定位', 'shot_event', 422, {'shotId': shot['id']})
        ensure(positions[reference] >= previous, '分镜与已采用的呈现顺序不一致', 'shot_order', 422)
        previous = positions[reference]; seen.add(reference)
        expected = local[previous]
        ensure(shot.get('eventId') == expected['eventId'], '镜头事件与呈现定位不匹配', 'shot_event', 422)
        ids = shot.get('dialogueIds', [])
        ensure(set(ids) <= set(expected.get('dialogueIds', [])), '镜头分配了其他事件的对白', 'dialogue_reference', 422)
        dialogue.extend(ids)
    ensure(seen == set(positions), '分镜漏掉采用版事件', 'shot_coverage', 422)
    ensure(set(dialogue) == known_lines and len(dialogue) == len(set(dialogue)), '分镜对白缺失或重复', 'dialogue_coverage', 422)
    for index,shot in enumerate(ordered):
        if 'endEventPhase' not in shot:
            continue  # Legacy plans retain their original review evidence.
        start,end=shot.get('eventPhase','before'),shot['endEventPhase']
        ensure(start in ('before','after') and end in ('before','after') and not (start=='after' and end=='before'), '同一事件内状态不能无声明倒退', 'shot_state_order', 422, {'shotId':shot['id']})
        following=ordered[index+1] if index+1<len(ordered) else None
        if following and following.get('presentationId')==shot.get('presentationId'):
            ensure(end==following.get('eventPhase','before'),'同一事件的切点末态与下一镜起态不一致','shot_state_continuity',422,{'shotId':shot['id'],'nextShotId':following['id']})
        else:
            ensure(end=='after','事件最后一镜尚未交付声明的动作结果','shot_state_delivery',422,{'shotId':shot['id']})
    return True
