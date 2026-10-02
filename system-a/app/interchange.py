"""Independent SceneExport-v1 schema 4 boundary."""
import copy
from .core import digest, ensure
from .story_contract import stable_blocks, conservative_document, normalize_document


def scene_export(service, project, scenes):
    rows = copy.deepcopy(scenes)
    for row in rows:
        row['body']['blocks'] = stable_blocks(row['body'], row['sceneId'])
        row['bodyHash'] = digest(row['body'])
        row['semanticHash'] = digest({k: row[k] for k in ('contractHash', 'bodyHash', 'canonHash', 'narrativeHash', 'directivesHash', 'order')})
    provenance = {'route': project.get('creationMode', 'original'), 'projectId': project['id']}
    if project.get('activeNovelDraft'):
        draft = service.s.get(project['activeNovelDraft'])
        document = normalize_document(draft['payload'])
        source = service.s.get(project['sourceId'])
        provenance.update(sourceId=source['id'], sha256=source['sha256'], name=source['name'], chapters=source['chapters'], readRanges=source['readRanges'], analysisRanges=source.get('analysisRanges',[]), adoptedDraftId=draft['id'])
        by_story = {n.get('externalStorySceneId'): n['id'] for n in service.nodes(project['id']) if n['level'] == 'scene' and n['status'] != 'archived'}
        by_id = {r['sceneId']: r for r in rows}
        for scene in document['scenes']:
            row = by_id.get(by_story.get(scene['id']))
            ensure(row and row['body']['blocks'] == scene['blocks'], '小说采用稿之后正文被单独修改，请在改编入口复核新版本后导出', 'story_version_mismatch', 409)
            row['storySceneId'] = scene['id']
        analyses=[x for x in service.s.list(project['id'],'book_unit_analysis') if x.get('sourceHash')==source['sha256']]
        overview=next((x for x in reversed(service.s.list(project['id'],'book_analysis')) if x.get('sourceHash')==source['sha256'] and x.get('status')=='complete'),None)
        recorded_ranges=copy.deepcopy(source.get('analysisRanges',[]))
        by_range={(x.get('charStart'),x.get('charEnd')):x for x in analyses}
        analysis_coverage={'sourceHash':source['sha256'],'totalUnits':len(source['chapters']),
            'analyzedRanges':[{'charStart':x.get('charStart'),'charEnd':x.get('charEnd'),'unitHash':by_range.get((x.get('charStart'),x.get('charEnd')),{}).get('unitHash'),'purpose':x.get('purpose')} for x in recorded_ranges],
            'readRanges':copy.deepcopy(source['readRanges']),'analysisRanges':recorded_ranges,'analysisFingerprint':overview.get('fingerprint') if overview else None,
            'complete':bool(overview) and len({(x.get('charStart'),x.get('charEnd')) for x in recorded_ranges})>=len(source['chapters'])}
    else:
        document = conservative_document([{'id': r['sceneId'], 'title': r['contract']['summary'], 'blocks': r['body']['blocks'], 'location': r['body'].get('location'), 'sourceRefs': [{'sceneId': r['sceneId'], 'revision': r['revision']}]} for r in rows], project['id']) if rows else None
        analysis_coverage={'sourceHash':None,'totalUnits':0,'analyzedRanges':[],'readRanges':[],'complete':True}
    dramatic=[{'sceneId':row['sceneId'],'summary':row.get('contract',{}).get('summary'),'valueChange':copy.deepcopy(row.get('contract',{}).get('valueChange')),
        'reveals':copy.deepcopy(row.get('contract',{}).get('reveals',[])),'obligations':copy.deepcopy(row.get('contract',{}).get('obligations',[]))} for row in rows]
    knowledge={'facts':copy.deepcopy(project.get('canon',{}).get('facts',[])),'beliefs':copy.deepcopy(project.get('canon',{}).get('beliefs',[])),
        'byScene':[{'sceneId':row['sceneId'],'knowledgeAtEntry':copy.deepcopy(row.get('narrativeContext',{}).get('knowledgeAtEntry',[])),
            'knowledgeDelta':copy.deepcopy(row.get('narrativeContext',{}).get('knowledgeDelta',[]))} for row in rows]}
    evidence={'sourceFingerprint':provenance.get('sha256') or digest(project.get('seed','')),
        'sceneRevisions':[{'sceneId':row['sceneId'],'revision':row.get('revision'),'sourceRevisions':copy.deepcopy(row.get('sourceRevisions',{}))} for row in rows]}
    result = {'format': 'SceneExport-v1', 'schemaVersion': 4, 'completeManifest': True, 'project': {'title': project['title'], 'sourceId': project['id'], 'genre':project.get('genre'), 'tone':project.get('tone')}, 'source': provenance, 'scenes': rows, 'storyDocument': document, 'continuityStatus': document['continuity'].get('status', 'declared') if document else 'needs_completion',
        'analysisCoverage':analysis_coverage,'knowledgeSnapshot':knowledge,'dramaticFunctions':dramatic,'evidenceSnapshot':evidence}
    result['versionFingerprint'] = digest({'scenes': rows, 'document': document, 'sourceHash': provenance.get('sha256'), 'route': provenance['route'],
        'analysisCoverage':analysis_coverage,'knowledgeSnapshot':knowledge,'dramaticFunctions':dramatic,'evidenceSnapshot':evidence})
    return result
