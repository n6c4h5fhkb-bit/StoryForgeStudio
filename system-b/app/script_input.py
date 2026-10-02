"""B consumes pinned A scripts; story rewrites return to A as change requests."""
from __future__ import annotations

import copy
from .core import digest, ensure, uid, now
from .story_contract import normalize_document


class ScriptInputWorkflow:
    def script_import_plan(self, p, package):
        ensure(package.get('format') == 'ScriptPackage-v1' and package.get('schemaVersion') == 1 and package.get('adopted') is True,
               '请选择 A 已采用的剧本版本', 'script_package', 422)
        document = normalize_document(package.get('storyDocument') or {})
        ensure(not document.get('storyChanges'), '关键故事修改尚未在 A 确认', 'story_change_required', 409)
        mode = package.get('presentationMode', 'fast_drama')
        ensure(mode in ('cinema', 'series', 'fast_drama'), '剧本呈现方向无效', 'presentation_mode', 422)
        project = self.s.get(p)
        ensure(not project.get('sourceScriptVersionId') or project.get('presentationMode') == mode,
               '另一呈现方向使用独立制作分支，不覆盖已有分支', 'production_branch', 409)
        active = self.active_shooting(p)
        def signatures(doc,execution=False):
            if not doc:
                return {}
            from .story_contract import replay
            from .shooting import scene_continuity_signature
            frames = replay(doc['continuity'])
            return {scene['id']:scene_continuity_signature(doc,scene,frames,execution) for scene in doc['scenes']}
        old, new = signatures((active or {}).get('payload')), signatures(document)
        changed = [identifier for identifier in dict.fromkeys([*old, *new]) if old.get(identifier) != new.get(identifier)]
        kept = [identifier for identifier in old if old.get(identifier) == new.get(identifier)]
        old_execution,new_execution=signatures((active or {}).get('payload'),True),signatures(document,True)
        review_only=[sid for sid in changed if sid in old_execution and old_execution[sid]==new_execution.get(sid)]
        impacts = []
        for scene in self.list_active(p, 'scene'):
            if scene.get('shootingSceneId') not in changed:
                continue
            shots = [shot['id'] for shot in self.list_active(p, 'shot') if shot['sceneId'] == scene['id']]
            impacts.append({'sceneId': scene['id'], 'title': scene['title'], 'shotsToReview': len(shots), 'locked': scene.get('status') == 'locked',
                            'reviewOnly':scene.get('shootingSceneId') in review_only,
                            'rendersAffected':0 if scene.get('shootingSceneId') in review_only else sum(item['kind']=='render' for item in self.change_plan(p,'scene',scene)['items'])})
        plan = {'projectId': p, 'projectVersion': project['_version'], 'scriptVersionId': package.get('scriptVersionId'), 'mode': mode,
                'packageHash': digest(package), 'changedSceneIds': changed, 'reviewOnlySceneIds':review_only,'preservedSceneIds': kept, 'impacts': impacts}
        plan['planHash'] = digest(plan)
        return plan

    def import_script_package(self, p, package, plan_hash=None):
        plan = self.script_import_plan(p, package)
        ensure(not plan['impacts'] or plan_hash == plan['planHash'], '先确认采用版本的实际影响', 'plan_required', 409, plan)
        ensure(not any(row['locked'] for row in plan['impacts']), '受影响场次已保留，请先允许调整', 'locked', 409, plan['impacts'])
        project = self.s.get(p)
        identifier = p + '_script_' + digest([package.get('scriptVersionId'), package.get('versionFingerprint'), package['presentationMode']])[:20]
        if project.get('activeScriptId') == identifier:
            return {'id': identifier, 'idempotent': True}
        document = normalize_document(package['storyDocument'])
        source = copy.deepcopy(document)
        source.update(provenance=copy.deepcopy(package.get('source', {})), versionFingerprint=package.get('versionFingerprint', digest(package)),
                      handoffEvidence={key: copy.deepcopy(package.get(key)) for key in ('analysisCoverage', 'knowledgeSnapshot', 'dramaticFunctions', 'evidenceSnapshot') if package.get(key) is not None})
        row = {'id': identifier, 'projectId': p, 'origin': 'A', 'status': 'proposed', 'passed': True, 'mode': package['presentationMode'],
               'payload': document, 'source': source, 'sourceHash': digest(source), 'sourcePackageHash': digest(package),
               'sourceScriptVersionId': package.get('scriptVersionId'), 'sourceProjectId': package.get('sourceProjectId') or package.get('project', {}).get('sourceId'),
               'baseShootingId': (self.active_shooting(p) or {}).get('id'), 'baseSourceHash': digest(self.source_document(p)) if self.list_active(p, 'scene') or project.get('storySource') or project.get('source', '').strip() else None,
               'baseProjectVersion': project['_version'], 'createdAt': now(), 'requestKey': digest(package),
               'reviewBasis': copy.deepcopy(package.get('reviewBasis', {})), 'issues': []}
        row['methodVersion']=package.get('methodVersion',0)
        self.s.put('adopted_script', row, p)
        internal_plan = self.shooting_adoption_plan(p, identifier)
        result = self.adopt_shooting(p, identifier, {'planHash': internal_plan['planHash']})
        return {**result, 'nextAction': 'prepare_event_assets', 'note': '已固定 A 的采用剧本，直接进入导演与制作。'}

    def create_change_request(self, p, data):
        project = self.s.get(p)
        instruction = str(data.get('instruction', '')).strip()
        ensure(instruction, '请说明需要回到 A 修改的情节')
        key = digest([p, project.get('sourceScriptVersionId'), data.get('sceneIds', []), instruction, data.get('operationId')])
        previous = next((row for row in self.s.list(p, 'change_request') if row.get('requestKey') == key), None)
        if previous:
            return previous
        row = {'id': uid('change_request'), 'projectId': p, 'sourceProjectId': project.get('sourceProjectId'),
               'sourceScriptVersionId': project.get('sourceScriptVersionId'), 'sceneIds': data.get('sceneIds', []),
               'instruction': instruction, 'reason': data.get('reason', ''), 'evidence': data.get('evidence', ''),
               'status': 'pending', 'requestKey': key, 'createdAt': now()}
        if data.get('origin')=='director':row.update(origin='director',directorProposalId=data.get('directorProposalId'))
        self.s.put('change_request', row, p)
        self.s.audit(p, 'request_story_change', data.get('sceneIds', []), {'requestId': row['id']})
        return row

    def adopt_clip_group(self, p, identifier, data, progress=lambda *_: None, check=lambda: None):
        """One human choice for a marked clip; all adoption records commit together."""
        task = self.s.get(identifier)
        ensure(task['projectId'] == p and task.get('freshness') != 'broken', '生成单元已变化，请先复核', 'stale_task', 409)
        ensure(data.get('humanReview') is True and str(data.get('observationEvidence', '')).strip(), '请查看整段视频并记录观察依据', 'end_evidence_required', 422)
        rows = [self.s.get(render_id) for render_id in task.get('renderIds', [])]
        ensure(rows and [row['shotId'] for row in rows] == task['shotIds'], '先标定本段各镜头的实际采用区间', 'adopted_interval', 409)
        active = self.active_shooting(p)
        basis = (active or {}).get('id')
        prepared = []
        supplied_states = data.get('observedEndStates') or {}
        ensure(isinstance(supplied_states, dict), '实际末态需按镜头 ID 填写', 'observed_state', 422)
        for index, row in enumerate(rows):
            check()
            shot = self.s.get(row['shotId'])
            ensure(row['projectId'] == p and row.get('freshness') != 'broken' and shot.get('freshness') != 'broken', '本段视频或分镜已失效', 'stale_task', 409)
            failed = [item for item in (row.get('gate') or {}).get('checks', []) if item.get('state') == 'fail']
            ensure(not failed or str(data.get('arbitrationReason', '')).strip(),
                   '有技术门禁未通过，请先说明人工仲裁依据', 'gate_arbitration_required', 409, failed)
            request = {'humanReview': True, 'observationEvidence': data['observationEvidence'],
                       'adoptedInterval': (row.get('adoption') or {}).get('interval') if row.get('selected') and row.get('adoption') else row.get('proposedInterval'),
                       'confirmExpectedEndState': data.get('confirmExpectedEndStates') is True,
                       'observedEndState': supplied_states.get(row['shotId'])}
            adoption = self.observed_adoption(p, row, request)
            prepared.append((row, adoption))
            progress(.1 + .65 * (index + 1) / len(rows), '记录本段实际采用区间与各切点末态')
        changed = set()
        adopted_ids = {row['id'] for row in rows}
        shot_ids = set(task['shotIds'])
        with self.s.transaction() as conn:
            ensure((self.active_shooting(p, conn) or {}).get('id') == basis, '采用期间剧本版本已变化', 'base_changed', 409)
            for before, adoption in prepared:
                row = self.s.get(before['id'], conn)
                ensure(row['_version'] == before['_version'], '审片期间候选视频已变化，请刷新', 'base_changed', 409)
                previous = [other for other in self.s.list(p, 'render', conn) if other.get('shotId') == row['shotId'] and other.get('kind') == 'clip' and other.get('selected') and other['id'] != row['id']]
                for other in previous:
                    ensure(not other.get('pinned') or data.get('replacePinned'), '有已固定采用的视频，请明确允许替换', 'pinned', 409)
                    other['selected'] = False
                    self.s.put('render', other, p, conn=conn)
                if previous or self.adoption_signature(adoption) != self.adoption_signature(row.get('adoption')):
                    changed.add(row['shotId'])
                row.update(adoption=adoption, selected=True, status='accepted',
                           review={'reason': data['observationEvidence'], 'at': now(), 'scope': 'continuous_clip_group', 'generationTaskId': identifier})
                if data.get('arbitrationReason'):
                    row['arbitrationReason'] = str(data['arbitrationReason']).strip()
                self.s.put('render', row, p, conn=conn)
            affected = set(changed)
            queue = list(changed)
            links = self.s.list(p, 'link', conn)
            while queue:
                parent = queue.pop(0)
                for link in links:
                    if link['from'] == parent and link['type'] in ('frame_chain', 'extension', 'ref_video') and link['to'] not in affected:
                        affected.add(link['to'])
                        queue.append(link['to'])
            for row in self.s.list(p, 'render', conn):
                if row['id'] not in adopted_ids and row.get('shotId') in affected - shot_ids and row.get('kind') == 'clip':
                    row.update(freshness='broken')
                    row.setdefault('freshnessNotes', []).append({'source': identifier, 'message': '依赖的采用区间或实际视频发生变化'})
                    self.s.put('render', row, p, conn=conn)
            for other in self.s.list(p, 'generation_task', conn):
                if other['id'] != identifier and affected.intersection(other.get('shotIds', [])):
                    other['freshness'] = 'broken'
                    self.s.put('generation_task', other, p, conn=conn)
            task.update(status='adopted', adoptedRenderIds=[row['id'] for row in rows], adoptionEvidence=data['observationEvidence'])
            self.s.put('generation_task', task, p, conn=conn)
            self.s.audit(p, 'adopt_continuous_clip', task['shotIds'], {'taskId': identifier, 'renderIds': list(adopted_ids), 'affectedExternalShotIds': sorted(affected - shot_ids)}, conn)
        progress(1, '整段已采用，实际区间和末态已保存')
        return {'taskId': identifier, 'renderIds': [row['id'] for row in rows], 'affectedExternalShotIds': sorted(affected - shot_ids)}
