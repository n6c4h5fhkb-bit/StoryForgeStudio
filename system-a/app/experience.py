"""Versioned, scoped feedback and experience memory.

The studio never treats a model guess or a plain adoption as a permanent rule.
Explicit, sufficiently specific corrections become project-local guidance;
inferred preferences remain candidates until the user confirms them.  Portable
packs contain only confirmed cross-project lessons and can be imported by the
other studio without sharing either application's database.
"""
from __future__ import annotations

import copy
import re

from .core import canonical, digest, ensure, now, uid


CATEGORIES = {'fact', 'preference', 'production', 'false_positive'}
STATUSES = {'candidate', 'active', 'suspended'}
VALIDATION_RESULTS = {'resolved', 'recurred', 'misapplied', 'unknown'}
SCOPE_LEVELS = {'project', 'genre', 'global'}
VAGUE = re.compile(r'^\s*(?:不好看|不行|不对|有问题|不喜欢|再来|换一个|不满意)[。！!？?\s]*$')


def _trim(value, limit=4000):
    return str(value or '').strip()[:limit]


def _category(text, requested=None):
    if requested:
        ensure(requested in CATEGORIES, '反馈类型无效', 'experience_category', 422)
        return requested
    value = text.lower()
    if any(word in value for word in ('误报', '故意', '不是漏洞', '保留创作意图')):
        return 'false_positive'
    if any(word in value for word in ('视频', '图片', '参考图', '动作没', '模型', 'seedance', '镜头生成')):
        return 'production'
    if any(word in value for word in ('已经', '上一镜', '前一场', '事实', '道具', '开着', '关着', '持有', '位置')):
        return 'fact'
    return 'preference'


def _portable_key(row):
    return digest({k: copy.deepcopy(row.get(k)) for k in ('category', 'rule', 'action', 'exceptions', 'conditions', 'scope', 'portableExample', 'revision')})


class ExperienceService:
    def __init__(self, store, system):
        self.s = store
        self.system = system

    def _project(self, project):
        row = self.s.get(project)
        ensure(row.get('id') == project, '项目不存在', 'not_found', 404)
        return row

    def _anchor(self, project, raw):
        anchor = copy.deepcopy(raw or {})
        anchor.setdefault('type', 'project')
        identifier = anchor.get('id')
        if identifier:
            target = self.s.get(identifier, required=False)
            ensure(not target or target.get('projectId', project) == project, '反馈目标不属于当前项目', 'feedback_anchor', 422)
            if target:
                anchor.setdefault('version', target.get('_version'))
        if anchor.get('timecode') is not None:
            value = float(anchor['timecode'])
            ensure(value >= 0, '时间点不能为负数', 'feedback_anchor', 422)
            anchor['timecode'] = round(value, 3)
        anchor['selection'] = _trim(anchor.get('selection'), 2000)
        return anchor

    def record(self, project, data):
        pr = self._project(project)
        text = _trim(data.get('text') or data.get('rule') or data.get('reason'))
        ensure(text, '请说明哪里不符合要求', 'feedback_required', 422)
        operation = _trim(data.get('operationId'), 200)
        if operation:
            old = next((row for row in self.s.list(project, 'feedback') if row.get('operationId') == operation), None)
            if old:
                lesson = self.s.get(old['experienceId'])
                return {'feedback': old, 'experience': lesson, 'idempotent': True}
        explicit = bool(data.get('explicit', True))
        ambiguous = bool(VAGUE.match(text))
        category = _category(text, data.get('category'))
        anchor = self._anchor(project, data.get('anchor'))
        conditions = copy.deepcopy(data.get('conditions') or {})
        conditions.setdefault('route', pr.get('creationMode') or pr.get('sourceType'))
        conditions.setdefault('presentationMode', pr.get('presentationMode'))
        conditions = {k: v for k, v in conditions.items() if v not in (None, '', [])}
        feedback = {
            'id': uid('feedback'), 'projectId': project, 'system': self.system,
            'source': data.get('source', 'direct'), 'explicit': explicit,
            'text': text, 'category': category, 'anchor': anchor,
            'before': _trim(data.get('before')), 'after': _trim(data.get('after')),
            'desired': _trim(data.get('desired') or text), 'conditions': conditions,
            'operationId': operation or None, 'createdAt': now(),
        }
        if ambiguous:
            feedback['diagnosticSuggestions'] = (['身份是否漂移', '动作是否完成', '构图与观看重点', '节奏与切点', '前后状态连续性', '声音是否兑现'] if anchor.get('type') in ('shot', 'render', 'video') or anchor.get('timecode') is not None else ['人物动机是否清楚', '冲突是否及时进入', '信息揭示是否顺畅', '因果是否成立', '情绪是否兑现', '内容是否可视化'])
        key = digest({'project': project, 'category': category, 'text': re.sub(r'\s+', '', text), 'anchor': anchor, 'conditions': conditions})
        lesson = next((row for row in self.s.list(project, 'experience') if row.get('dedupeKey') == key and row['status'] != 'suspended'), None)
        if lesson:
            lesson['feedbackIds'] = list(dict.fromkeys([*lesson.get('feedbackIds', []), feedback['id']]))
            lesson['updatedAt'] = now()
        else:
            active = explicit and not ambiguous and not data.get('inferred')
            lesson = {
                'id': uid('experience'), 'projectId': project, 'system': self.system,
                'category': category, 'rule': _trim(data.get('rule') or text, 1200),
                'action': _trim(data.get('action') or data.get('desired') or text, 1200),
                'exceptions': [_trim(x, 500) for x in data.get('exceptions', []) if _trim(x, 500)],
                'conditions': conditions, 'scope': {'level': 'project', 'projectId': project},
                'status': 'active' if active else 'candidate',
                'confirmationReason': 'ambiguous_feedback' if ambiguous else 'inferred_preference' if not explicit or data.get('inferred') else None,
                'feedbackIds': [feedback['id']], 'dedupeKey': key,
                'portableExample': copy.deepcopy(data.get('portableExample')),
                'diagnosticSuggestions': copy.deepcopy(feedback.get('diagnosticSuggestions', [])),
                'createdAt': now(), 'updatedAt': now(), 'revision': 1,
            }
        feedback['experienceId'] = lesson['id']
        with self.s.transaction() as conn:
            stored_lesson = self.s.put('experience', lesson, project, conn=conn)
            stored_feedback = self.s.put('feedback', feedback, project, conn=conn)
            self.s.audit(project, 'feedback_recorded', [anchor.get('id')] if anchor.get('id') else [], {
                'feedbackId': feedback['id'], 'experienceId': lesson['id'], 'status': lesson['status'], 'category': category,
            }, conn)
        return {'feedback': stored_feedback, 'experience': stored_lesson, 'remembered': lesson['status'] == 'active'}

    def signal(self, project, data):
        """Store selection evidence without inventing a preference from adoption alone."""
        self._project(project)
        operation = _trim(data.get('operationId'), 200)
        if operation:
            old = next((row for row in self.s.list(project, 'preference_signal') if row.get('operationId') == operation), None)
            if old:
                return old
        row = {
            'id': uid('signal'), 'projectId': project, 'system': self.system,
            'kind': data.get('kind', 'adopted'), 'targetId': data.get('targetId'),
            'beforeHash': data.get('beforeHash'), 'afterHash': data.get('afterHash'),
            'note': _trim(data.get('note'), 1000), 'operationId': operation or None,
            'createdAt': now(), 'summarized': False,
        }
        saved = self.s.put('preference_signal', row, project)
        self.s.audit(project, 'preference_signal', [row['targetId']] if row.get('targetId') else [], {'signalId': row['id'], 'kind': row['kind']})
        return saved

    def migrate_legacy(self, project):
        """Convert old unscoped lists to evidence without activating guessed rules."""
        receipt_id = 'experience_migration_v1_' + project
        if self.s.get(receipt_id, required=False):
            return
        pr = self._project(project)
        migrated = []
        for index, item in enumerate(pr.get('negativeList', [])):
            reason = _trim(item.get('reason') if isinstance(item, dict) else item)
            if not reason:
                continue
            result = self.record(project, {'text': reason, 'source': 'legacy_negative', 'explicit': False, 'inferred': True,
                'anchor': {'type': 'legacy', 'id': item.get('nodeId') if isinstance(item, dict) else None},
                'operationId': f'legacy-negative:{project}:{index}'})
            migrated.append(result['experience']['id'])
        for index, item in enumerate(pr.get('styleExamples', [])):
            if not isinstance(item, dict) or not item.get('candidateId'):
                continue
            signal = self.signal(project, {'kind': 'legacy_adopted_example', 'targetId': item['candidateId'],
                'note': '旧版采用样本仅作为偏好证据，需提炼并确认后才能成为规则。',
                'operationId': f'legacy-style:{project}:{index}'})
            migrated.append(signal['id'])
        self.s.put('experience_migration', {'id': receipt_id, 'projectId': project, 'version': 1,
            'migratedIds': migrated, 'createdAt': now()}, project)

    def list(self, project):
        self._project(project); self.migrate_legacy(project)
        owned = self.s.list(project, 'experience')
        shared = [row for row in self.s.list(kind='experience') if row.get('projectId') != project and row.get('status') == 'active' and self._matches(row, project, {})]
        lessons = [*owned, *shared]
        validations = self.s.list(project, 'experience_validation')
        applications = self.s.list(project, 'experience_application')
        counts = {key: 0 for key in VALIDATION_RESULTS}
        for row in validations:
            counts[row['result']] = counts.get(row['result'], 0) + 1
        observed = counts['resolved'] + counts['recurred'] + counts['misapplied']
        by_lesson = {}
        for lesson in lessons:
            own = [row for row in validations if row['experienceId'] == lesson['id']]
            by_lesson[lesson['id']] = {'applications': sum(lesson['id'] in row.get('experienceIds', []) for row in applications),
                'resolved': sum(row['result'] == 'resolved' for row in own), 'recurred': sum(row['result'] == 'recurred' for row in own),
                'misapplied': sum(row['result'] == 'misapplied' for row in own), 'unknown': sum(row['result'] == 'unknown' for row in own)}
        return {
            'experiences': lessons,
            'feedback': self.s.list(project, 'feedback'),
            'signals': self.s.list(project, 'preference_signal'),
            'suggestions': [row for row in owned if row.get('status') == 'candidate'],
            'validationSummary': counts,
            'metrics': {'appliedTasks': len(applications), 'observedChecks': observed,
                'repeatRate': round(counts['recurred'] / observed, 4) if observed else None,
                'misuseRate': round(counts['misapplied'] / observed, 4) if observed else None,
                'byExperience': by_lesson, 'evidence': '仅统计已记录的验证；unknown 不算成功或失败'},
            'revisionHash': self.revision_hash(project),
        }

    def _matches(self, lesson, project, context):
        scope = lesson.get('scope', {'level': 'project', 'projectId': lesson.get('projectId')})
        level = scope.get('level', 'project')
        if level == 'project' and lesson.get('projectId') != project:
            return False
        pr = self._project(project)
        if level == 'genre' and scope.get('genre') and scope['genre'] != pr.get('genre'):
            return False
        values = {**{'route': pr.get('creationMode') or pr.get('sourceType'), 'presentationMode': pr.get('presentationMode')}, **(context or {})}
        return all(values.get(key) == value for key, value in lesson.get('conditions', {}).items())

    def applicable(self, project, context=None, limit=8):
        self.migrate_legacy(project)
        candidates = [row for row in self.s.list(kind='experience') if row.get('status') == 'active' and self._matches(row, project, context or {})]
        priority = {'project': 0, 'genre': 1, 'global': 2}
        candidates.sort(key=lambda row: (priority.get(row.get('scope', {}).get('level'), 3), row.get('updatedAt', '')), reverse=False)
        chosen = candidates[:max(1, min(int(limit), 20))]
        return [{k: copy.deepcopy(row.get(k)) for k in ('id', 'category', 'rule', 'action', 'exceptions', 'conditions', 'scope', 'revision')} for row in chosen]

    def guidance(self, project, context=None, limit=8):
        lessons = self.applicable(project, context, limit)
        return {'revisionHash': digest(lessons), 'lessons': lessons}

    def revision_hash(self, project, context=None):
        return self.guidance(project, context)['revisionHash']

    def confirm(self, project, identifier, data):
        lesson = self.s.get(identifier)
        ensure(lesson['projectId'] == project, '经验不属于当前项目', 'experience_scope', 404)
        level = data.get('level', 'project')
        ensure(level in SCOPE_LEVELS, '经验范围无效', 'experience_scope', 422)
        ensure(lesson.get('confirmationReason') != 'ambiguous_feedback', '请先把“不好看/不行”修改成具体原因和做法', 'experience_ambiguous', 409, {'suggestions': lesson.get('diagnosticSuggestions', [])})
        pr = self._project(project)
        scope = {'level': level}
        if level == 'project': scope['projectId'] = project
        elif level == 'genre':
            ensure(pr.get('genre'), '项目没有可用于同类作品的类型', 'experience_scope', 422)
            scope['genre'] = pr['genre']
        lesson.update(status='active', scope=scope, confirmationReason=None, confirmedAt=now(), updatedAt=now(), revision=int(lesson.get('revision', 1)) + 1)
        saved = self.s.put('experience', lesson, project, expected=data.get('expectedVersion'))
        self.s.audit(project, 'experience_confirmed', [identifier], {'scope': scope, 'revision': saved['revision']})
        return saved

    def update(self, project, identifier, data):
        lesson = self.s.get(identifier)
        ensure(lesson['projectId'] == project, '经验不属于当前项目', 'experience_scope', 404)
        for field in ('rule', 'action'):
            if field in data:
                value = _trim(data[field], 1200); ensure(value, field + ' 不能为空', 'experience_rule', 422); lesson[field] = value
        if 'exceptions' in data: lesson['exceptions'] = [_trim(x, 500) for x in data['exceptions'] if _trim(x, 500)]
        if 'conditions' in data: lesson['conditions'] = {k: v for k, v in copy.deepcopy(data['conditions']).items() if v not in (None, '', [])}
        if 'status' in data:
            ensure(data['status'] in STATUSES, '经验状态无效', 'experience_status', 422); lesson['status'] = data['status']
        if lesson.get('confirmationReason') == 'ambiguous_feedback' and any(field in data for field in ('rule', 'action')):
            lesson['confirmationReason'] = 'edited_candidate'
        lesson.update(updatedAt=now(), revision=int(lesson.get('revision', 1)) + 1)
        saved = self.s.put('experience', lesson, project, expected=data.get('expectedVersion'))
        self.s.audit(project, 'experience_updated', [identifier], {'status': saved['status'], 'revision': saved['revision']})
        return saved

    def validate(self, project, identifier, data):
        lesson = self.s.get(identifier)
        ensure(lesson['projectId'] == project or lesson.get('scope', {}).get('level') in ('genre', 'global'), '经验不适用于当前项目', 'experience_scope', 404)
        result = data.get('result')
        ensure(result in VALIDATION_RESULTS, '验证结果无效', 'experience_validation', 422)
        application = next((row for row in reversed(self.s.list(project, 'experience_application')) if identifier in row.get('experienceIds', [])), None)
        failure_stage = data.get('failureStage')
        if result == 'recurred' and not failure_stage:
            failure_stage = 'generation_or_review' if application else 'experience_not_selected'
        evidence = _trim(data.get('evidence'), 3000)
        ensure(evidence, '请记录实际观察依据；不确定时选择证据不足', 'experience_evidence', 422)
        row = {
            'id': uid('experience_validation'), 'projectId': project, 'experienceId': identifier,
            'result': result, 'target': copy.deepcopy(data.get('target') or {}),
            'evidence': evidence, 'createdAt': now(),
            'experienceRevision': lesson.get('revision', 1), 'applicationId': data.get('applicationId') or (application or {}).get('id'),
            'failureStage': failure_stage, 'ruleSelected': bool(application),
            'generationEvidence': _trim(data.get('generationEvidence'), 2000), 'reviewEvidence': _trim(data.get('reviewEvidence'), 2000),
        }
        saved = self.s.put('experience_validation', row, project)
        if result == 'misapplied' or (result == 'recurred' and failure_stage in ('rule_unclear', 'scope')):
            lesson.update(status='candidate', confirmationReason='validation_' + result, updatedAt=now(), revision=int(lesson.get('revision', 1)) + 1)
            self.s.put('experience', lesson, lesson['projectId'])
        self.s.audit(project, 'experience_validated', [identifier], {'result': result, 'validationId': row['id']})
        return saved

    def applied(self, project, target, guidance, result_version=None):
        if not guidance.get('lessons'):
            return None
        row = {
            'id': uid('experience_application'), 'projectId': project,
            'target': copy.deepcopy(target or {}), 'experienceIds': [x['id'] for x in guidance['lessons']],
            'revisionHash': guidance['revisionHash'], 'resultVersion': result_version, 'createdAt': now(),
        }
        return self.s.put('experience_application', row, project)

    def export_pack(self, project):
        self._project(project)
        rows = [row for row in self.s.list(kind='experience') if row.get('status') == 'active' and row.get('scope', {}).get('level') in ('genre', 'global')]
        items = []
        for row in rows:
            item = {k: copy.deepcopy(row.get(k)) for k in ('category', 'rule', 'action', 'exceptions', 'conditions', 'scope', 'portableExample', 'revision')}
            item['portableKey'] = _portable_key(item)
            item['origin'] = {'system': row.get('system'), 'experienceId': row['id']}
            items.append(item)
        pack = {'format': 'ExperiencePack-v1', 'schemaVersion': 1, 'items': items, 'exportedAt': now(), 'sourceSystem': self.system}
        pack['fingerprint'] = digest({'items': items, 'schemaVersion': 1})
        return pack

    def import_pack(self, project, pack):
        self._project(project)
        ensure(pack.get('format') == 'ExperiencePack-v1' and pack.get('schemaVersion') == 1 and isinstance(pack.get('items'), list), '经验包格式无效', 'experience_pack', 422)
        ensure(pack.get('fingerprint') == digest({'items': pack['items'], 'schemaVersion': 1}), '经验包指纹不一致', 'experience_pack', 422)
        imported = []
        for item in pack['items']:
            ensure(item.get('category') in CATEGORIES and item.get('scope', {}).get('level') in ('genre', 'global'), '经验包包含无效规则', 'experience_pack', 422)
            key = item.get('portableKey') or _portable_key(item)
            old = next((row for row in self.s.list(kind='experience') if row.get('portableKey') == key or _portable_key(row) == key), None)
            if old:
                imported.append(old['id']); continue
            row = {
                'id': uid('experience'), 'projectId': project, 'system': self.system,
                **{k: copy.deepcopy(item.get(k)) for k in ('category', 'rule', 'action', 'exceptions', 'conditions', 'scope', 'portableExample')},
                'status': 'active', 'feedbackIds': [], 'portableKey': key,
                'origin': copy.deepcopy(item.get('origin')), 'revision': int(item.get('revision', 1)),
                'createdAt': now(), 'updatedAt': now(),
            }
            self.s.put('experience', row, project); imported.append(row['id'])
        receipt = {'id': uid('experience_pack'), 'projectId': project, 'fingerprint': pack['fingerprint'], 'experienceIds': imported, 'sourceSystem': pack.get('sourceSystem'), 'createdAt': now()}
        self.s.put('experience_pack', receipt, project)
        self.s.audit(project, 'experience_pack_imported', imported, {'fingerprint': pack['fingerprint']})
        return receipt
