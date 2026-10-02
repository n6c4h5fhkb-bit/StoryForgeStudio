import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time

import pytest
from fastapi.testclient import TestClient
from app.core import Store, DomainError
from app.settings import Settings
from app.llm import LLM
from app import codex_cli


@pytest.fixture
def connected(tmp_path, monkeypatch):
    store = Store(tmp_path / 'data')
    settings = Settings(store.root)
    settings.save({'llm': {'provider': 'codex_cli', 'model': 'fixture',
        'codexHome': str(tmp_path / 'home'), 'timeout': 10}})
    fixture = Path(__file__).parent / 'fixtures' / 'codex_process.py'
    monkeypatch.setattr(codex_cli, 'command', lambda _: [sys.executable, str(fixture)])
    return LLM(store, settings)


def call(model, value, **kwargs):
    return model.json('p', 'script', 'Return current supplied facts as JSON.', value,
                      cache=True, session_scope='scene:one', **kwargs)


def test_resume_delta_exact_deletions_cached_result_and_process_restart(connected):
    model = connected
    request = {'source': '原文不重复发送。' * 300, 'instruction': '第一次',
               'assets': [{'id': 'prop', 'box': {'open': False, 'hidden': 'remove me'}}], 'a/b~c': 1}
    first = call(model, request)
    changed = copy.deepcopy(request); changed['instruction'] = '后来“改了”\n$() `引号`'; changed.pop('a/b~c')
    changed['assets'][0]['box'] = {'open': True}
    # New application objects load durable session state from SQLite.
    restarted = LLM(Store(model.store.root), Settings(model.store.root))
    second = call(restarted, changed)
    third = call(restarted, changed)
    assert first['thread'] == second['thread'] == third['thread']
    assert second['context'] == changed
    runs = model.store.list('p', 'run')
    assert len(runs) == 3 and runs[-1]['cacheHit']
    meta = runs[1]['codex']
    assert meta['resumed'] and meta['contextMode'] == 'delta'
    assert meta['sentCharacters'] < meta['fullContextCharacters'] / 2
    assert runs[1]['usage']['input'] == 1000 and runs[1]['usage']['output'] == 50
    assert runs[1]['usage']['cachedInput'] == 800 and runs[1]['usage']['reasoning'] == 20
    assert not runs[1]['costKnown'] and not runs[1]['costEstimated'] and runs[1]['billingMode'] == 'cli_account'
    workspace = model.store.root / 'codex-workspaces' / meta['sessionRecordId']
    calls = [json.loads(s) for s in (workspace / 'fixture-calls.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(calls) == 2 and 'resume' in calls[1]['args'] and first['thread'] in calls[1]['args']
    assert '--last' not in calls[1]['args'] and '--ephemeral' not in calls[1]['args']
    assert '--no-daemon' in calls[0]['args'] and 'sandbox_mode="read-only"' in calls[0]['args']
    assert 'approval_policy="never"' in calls[0]['args'] and 'features.shell_tool=false' in calls[0]['args']
    assert '--dangerously-bypass-approvals-and-sandbox' not in calls[0]['args']
    assert '原文不重复发送' not in json.dumps(calls[1]['request'], ensure_ascii=False)


def test_projects_roles_and_presentation_directions_have_separate_sessions(connected):
    threads = []
    for project, role, scope in [('p', 'treatment', 'cinema'), ('p', 'treatment', 'fast_drama'),
                                 ('p', 'reviewer', 'cinema'), ('other', 'treatment', 'cinema')]:
        result = connected.json(project, role, 'JSON', {'scope': scope}, session_scope=scope)
        threads.append(result['thread'])
    assert len(set(threads)) == 4


def test_concurrent_requests_do_not_fork_or_overwrite_context(connected):
    source = 'large stable source ' * 150
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda i: call(connected, {'source': source, 'i': i, 'fixtureMode': 'delay'}), [1, 2]))
    assert {r['context']['i'] for r in results} == {1, 2}
    assert len({r['thread'] for r in results}) == 1
    assert len(connected.store.list('p', 'codex_session')) == 1


def test_duplicate_requests_make_only_one_cli_call(connected):
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: call(connected, {'fixtureMode': 'delay'}), [1, 2]))
    assert sum(not r['cacheHit'] for r in connected.store.list('p', 'run')) == 1


def test_dead_server_lease_recovers_without_waiting_for_timeout(connected, monkeypatch):
    first = call(connected, {'i': 1})
    row = connected.store.list('p', 'codex_session')[0]
    row.update(state='running', leaseUntil=time.time()+600, ownerPid=12345)
    connected.store.put('codex_session', row, 'p')
    monkeypatch.setattr(codex_cli, 'process_alive', lambda _: False)
    result = call(connected, {'i': 2})
    assert result['thread'] == first['thread']
    assert connected.store.list('p', 'run')[-1]['codex']['contextMode'] == 'snapshot'


@pytest.mark.parametrize('kind', ['timeout', 'cancel'])
def test_cancel_and_timeout_kill_child_tree_and_resume_same_session(connected, kind):
    connected.settings.save({'llm': {'timeout': .6 if kind == 'timeout' else 10}})
    start = time.monotonic()
    def check():
        if kind == 'cancel' and time.monotonic() - start > .4:
            raise DomainError('cancel', 'cancelled', 409)
    with pytest.raises(DomainError) as raised:
        call(connected, {'fixtureMode': 'slow'}, check=check)
    assert raised.value.code == ('model_timeout' if kind == 'timeout' else 'cancelled')
    row = connected.store.list('p', 'codex_session')[0]
    assert row['threadId'] and row['needsResync'] and row['leaseUntil'] == 0
    connected.settings.save({'llm': {'timeout': 10}})
    resumed = call(connected, {'instruction': '继续'})
    assert resumed['thread'] == row['threadId']
    assert connected.store.list('p', 'run')[-1]['codex']['contextMode'] == 'snapshot'
    time.sleep(2.1)
    assert not list(connected.store.root.rglob('orphan-marker.txt'))


def test_failed_auth_has_actionable_error_without_secrets_and_keeps_session(connected):
    with pytest.raises(DomainError) as raised:
        call(connected, {'fixtureMode': 'error'})
    assert raised.value.code == 'codex_auth_required'
    assert 'SECRET' not in str(raised.value) + json.dumps(raised.value.details)
    row = connected.store.list('p', 'codex_session')[0]
    assert row['threadId'] and row['needsResync']


def test_invalid_payload_retains_delivered_context_for_repair(connected):
    source = 'keep this context ' * 300
    with pytest.raises(DomainError, match='JSON'):
        call(connected, {'source': source, 'fixtureMode': 'invalid'})
    row = connected.store.list('p', 'codex_session')[0]
    assert not row['needsResync']
    result = call(connected, {'source': source, 'repair': 'valid json'})
    assert result['thread'] == row['threadId']
    assert connected.store.list('p', 'run')[-1]['codex']['contextMode'] == 'delta'


def test_stale_context_result_is_rejected(connected):
    with pytest.raises(DomainError) as raised:
        call(connected, {'fixtureMode': 'stale'})
    assert raised.value.code == 'codex_context_mismatch'
    assert len(raised.value.cli_meta['transportAttempts']) == 2
    assert raised.value.cli_usage['input_tokens'] == 2000
    assert connected.store.list('p', 'run')[-1]['status'] == 'failed'
    prior = connected.store.list('p', 'codex_session')[0]
    assert prior['needsResync']
    result = call(connected, {'instruction': '重新同步'})
    assert result['thread'] == prior['threadId']
    assert connected.store.list('p', 'run')[-1]['codex']['contextMode'] == 'snapshot'


def test_lost_context_recovers_once_in_same_session_and_counts_both_calls(connected):
    source = '稳定原文与事实' * 800
    first = call(connected, {'source': source, 'box': {'heldBy': '小林', 'contentsKnown': False}})
    changed = {'source': source, 'box': {'destroyed': True}, 'fixtureMode': 'lost_context'}
    output = call(connected, changed)
    assert output['thread'] == first['thread'] and output['context'] == changed
    run = connected.store.list('p', 'run')[-1]
    assert run['codex']['contextRecovered'] and run['usage']['input'] == 2000
    assert [a['contextMode'] for a in run['codex']['transportAttempts']] == ['delta', 'snapshot']
    calls = len(connected.store.list('p', 'run'))
    assert call(connected, changed) == output
    assert connected.store.list('p', 'run')[-1]['cacheHit']
    assert len(connected.store.list('p', 'run')) == calls + 1


def test_long_delta_chain_checkpoints_without_new_session_or_extra_call(connected, monkeypatch):
    monkeypatch.setattr(codex_cli, 'MAX_DELTA_TURNS', 3)
    source = '稳定原文' * 1500
    results = [call(connected, {'source': source, 'step': i}) for i in range(6)]
    assert len({r['thread'] for r in results}) == 1
    assert [r['context']['step'] for r in results] == list(range(6))
    runs = connected.store.list('p', 'run')
    assert [r['codex']['contextMode'] for r in runs] == ['snapshot', 'delta', 'delta', 'delta', 'snapshot', 'delta']
    assert runs[4]['codex']['checkpointReason'] == 'maintenance'
    assert all('transportAttempts' not in r['codex'] for r in runs)
    assert len(runs) == 6


def test_exact_previous_result_is_bound_for_repair_but_not_after_resync(connected):
    first = call(connected, {'source':'实际原文'*2000,'instruction':'开盒'})
    request = {'source':'实际原文'*2000,'previousCandidate':first,'instruction':'只调整动作'}
    second = call(connected, request)
    assert second['context']['previousCandidate'] == first
    run = connected.store.list('p','run')[-1]
    assert run['codex']['reusedLastResult'] and run['codex']['sentCharacters'] < 1000
    row = connected.store.list('p','codex_session')[0]
    row['needsResync'] = True;connected.store.put('codex_session',row,'p')
    third = call(connected,{**request,'previousCandidate':second,'instruction':'同步后修订'})
    assert third['context']['previousCandidate'] == second
    meta = connected.store.list('p','run')[-1]['codex']
    assert meta['contextMode']=='snapshot' and not meta['reusedLastResult']


def test_manual_reset_is_project_scoped_and_resets_usage(connected):
    first = call(connected, {'i': 1})
    sessions = codex_cli.CodexSessions(connected.store)
    row = sessions.summaries('p')[0]
    assert 'input' not in row
    with pytest.raises(DomainError):
        sessions.reset('other', row['id'])
    sessions.reset('p', row['id'])
    second = call(connected, {'i': 2})
    assert first['thread'] != second['thread']
    assert connected.store.list('p', 'run')[-1]['usage']['input'] == 1000


def test_monetary_api_price_confirmation_not_required_for_cli(connected):
    assert not connected.settings.model('script')['priceConfigured']
    call(connected, {'works': True})
    assert connected.store.list('p', 'run')[-1]['billingMode'] == 'cli_account'


def test_status_and_session_endpoints_are_safe(tmp_path, monkeypatch):
    from app.main import create_app
    app = create_app(tmp_path / 'web')
    monkeypatch.setattr(codex_cli, 'status', lambda _: {'installed': True, 'loggedIn': True, 'ready': True})
    try:
        with TestClient(app) as client:
            assert client.get('/api/codex/status').json()['ready']
            assert client.get('/api/projects/p/codex-sessions').json() == []
            assert client.post('/api/projects/p/codex-sessions/x/reset').status_code == 403
    finally:
        app.state.jobs.pool.shutdown(wait=True, cancel_futures=True)


def test_runtime_update_invalidates_result_cache_but_preserves_session_identity(connected, monkeypatch, tmp_path):
    cfg = connected.settings.model('script')
    fake_runtime = tmp_path / 'codex.exe'
    fake_runtime.write_bytes(b'runtime version one')
    monkeypatch.setattr(codex_cli, 'command', lambda _: [str(fake_runtime)])
    before = codex_cli.prepare(cfg)
    fake_runtime.write_bytes(b'runtime version two, updated')
    after = codex_cli.prepare(cfg)
    assert before['_codexIdentity'] != after['_codexIdentity']
    assert before['_codexSessionIdentity'] == after['_codexSessionIdentity']


def test_compatible_upgrade_reuses_prior_result_and_prior_conversation(connected, monkeypatch):
    prepare = codex_cli.prepare
    def older(cfg):
        value = prepare(cfg)
        value['_codexIdentity'] = value['_codexCompatibleCaches'][0]
        value['_codexSessionIdentity'] = value['_codexLegacyIdentities'][0]
        value['_codexCompatibleCaches'] = []
        value['_codexLegacyIdentities'] = []
        return value
    monkeypatch.setattr(codex_cli, 'prepare', older)
    request = {'source': 'stable story ' * 150, 'instruction': 'one'}
    first = call(connected, request)
    monkeypatch.setattr(codex_cli, 'prepare', prepare)
    cached = call(connected, request)
    assert cached == first and connected.store.list('p', 'run')[-1]['cacheHit']
    second = call(connected, {**request, 'instruction': 'two'})
    third = call(connected, {**request, 'instruction': 'three'})
    assert first['thread'] == second['thread'] == third['thread']
    assert len(connected.store.list('p', 'codex_session')) == 1


def test_instruction_wording_change_does_not_create_a_new_specialist(connected, monkeypatch):
    before = codex_cli.prepare(connected.settings.model('script'))
    monkeypatch.setattr(codex_cli, 'INSTRUCTIONS', codex_cli.INSTRUCTIONS + '\nClarification for a compatible protocol.')
    after = codex_cli.prepare(connected.settings.model('script'))
    assert before['_codexIdentity'] != after['_codexIdentity']
    assert before['_codexSessionIdentity'] == after['_codexSessionIdentity']


def test_unused_api_controls_do_not_invalidate_cli_results(connected):
    first=call(connected,{'source':'same facts'})
    connected.settings.save({'llm':{'temperature':1.5,'maxTokens':9900,'baseUrl':'https://unused.invalid','extraBody':{'top_p':.4}}})
    second=call(connected,{'source':'same facts'})
    assert first==second and connected.store.list('p','run')[-1]['cacheHit']
    assert len(connected.store.list('p','codex_session'))==1


def test_live_session_cannot_be_stolen_or_reset_when_queue_wait_exceeds_lease(connected):
    call(connected,{'i':1})
    row=connected.store.list('p','codex_session')[0]
    row.update(state='running',leaseUntil=0,ownerPid=__import__('os').getpid())
    connected.store.put('codex_session',row,'p')
    sessions=codex_cli.CodexSessions(connected.store)
    with pytest.raises(DomainError) as error:sessions.reset('p',row['id'])
    assert error.value.code=='session_busy'
    checks=0
    def cancel_wait():
        nonlocal checks
        checks+=1
        if checks>3:raise DomainError('cancel','cancelled',409)
    cfg=codex_cli.prepare(connected.settings.model('script'))
    with pytest.raises(DomainError) as error:sessions._claim(row['id'],'p','script','scene:one',cfg,cancel_wait)
    assert error.value.code=='cancelled'


def test_gpt_5_6_sol_high_configuration_is_forwarded_exactly(connected):
    connected.settings.save({'llm': {'model': 'gpt-5.6-sol', 'codexReasoning': 'high'}})
    call(connected, {'preset': 'gpt-5.6-sol-high'})
    run = connected.store.list('p', 'run')[-1]
    workspace = connected.store.root / 'codex-workspaces' / run['codex']['sessionRecordId']
    invocation = json.loads((workspace / 'fixture-calls.jsonl').read_text(encoding='utf-8').splitlines()[-1])
    args = invocation['args']
    assert args[args.index('--model') + 1] == 'gpt-5.6-sol'
    assert 'model_reasoning_effort="high"' in args
