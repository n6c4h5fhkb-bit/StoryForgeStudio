"""Direct HTTP calls, explicit result reuse, bounded concurrency and cost accounting."""
from __future__ import annotations
import copy, json, re, time, threading
from concurrent.futures import Future, TimeoutError as FutureTimeout
from contextlib import contextmanager
import httpx, jsonschema
from .core import DomainError, ensure, digest, uid, now, canonical
from .settings import validate_model, number
from . import codex_cli

_flights_lock = threading.Lock()
_flights = {}
from studio.provider_slots import capacity as _capacity, active as _active


def parse_json(text):
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in (text.find('{'), text.find('[')) if i >= 0], default=-1)
        if start >= 0:
            try:
                return json.JSONDecoder().raw_decode(text[start:])[0]
            except json.JSONDecodeError:
                pass
        raise DomainError('模型未返回可解析 JSON', 'invalid_model_output', 422, {'excerpt': text[:1000]})


def normalized_usage(provider, raw):
    """Cached/write counts are subsets of total input; preserve the original usage."""
    def count(value):
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
    result = {'input': 0, 'output': 0, 'cachedInput': 0, 'cacheWrite': 0,
              'cacheWrite5m': 0, 'cacheWrite1h': 0, 'reasoning': 0}
    if provider == 'anthropic':
        result['cachedInput'] = count(raw.get('cache_read_input_tokens'))
        result['cacheWrite'] = count(raw.get('cache_creation_input_tokens'))
        detail = raw.get('cache_creation') or {}
        result['cacheWrite5m'] = count(detail.get('ephemeral_5m_input_tokens'))
        result['cacheWrite1h'] = count(detail.get('ephemeral_1h_input_tokens'))
        result['input'] = count(raw.get('input_tokens')) + result['cachedInput'] + result['cacheWrite']
        result['output'] = count(raw.get('output_tokens'))
        required = ('input_tokens', 'output_tokens')
    elif provider == 'gemini':
        result['input'] = count(raw.get('promptTokenCount'))
        result['cachedInput'] = count(raw.get('cachedContentTokenCount'))
        result['reasoning'] = count(raw.get('thoughtsTokenCount'))
        result['output'] = count(raw.get('candidatesTokenCount')) + result['reasoning']
        required = ('promptTokenCount', 'candidatesTokenCount')
    elif provider == 'codex_cli':
        result['input'] = count(raw.get('input_tokens'))
        result['output'] = count(raw.get('output_tokens'))
        result['cachedInput'] = count(raw.get('cached_input_tokens'))
        result['cacheWrite'] = count(raw.get('cache_write_input_tokens'))
        result['reasoning'] = count(raw.get('reasoning_output_tokens'))
        required = ('input_tokens', 'output_tokens')
    else:
        result['input'] = count(raw.get('prompt_tokens'))
        result['output'] = count(raw.get('completion_tokens'))
        result['cachedInput'] = count((raw.get('prompt_tokens_details') or {}).get('cached_tokens'))
        result['reasoning'] = count((raw.get('completion_tokens_details') or {}).get('reasoning_tokens'))
        required = ('prompt_tokens', 'completion_tokens')
    result['_complete'] = all(isinstance(raw.get(k), int) and not isinstance(raw.get(k), bool) and raw[k] >= 0 for k in required)
    result['_complete'] = result['_complete'] and result['cachedInput'] + result['cacheWrite'] <= result['input'] and result['cacheWrite5m'] + result['cacheWrite1h'] <= result['cacheWrite']
    result['_raw'] = raw
    return result


def usage_cost(cfg, usage, estimate):
    ordinary = float(cfg.get('inputPerMillion', 0))
    cached, written = usage.get('cachedInput', 0), usage.get('cacheWrite', 0)
    known = usage.get('_complete', True)
    amount = max(0, usage['input'] - cached - written) * ordinary + usage['output'] * float(cfg.get('outputPerMillion', 0))
    if cached:
        known = known and cfg.get('cachedInputPerMillion') is not None
        amount += cached * float(cfg.get('cachedInputPerMillion', ordinary))
    if written:
        five, hour = usage.get('cacheWrite5m', 0), usage.get('cacheWrite1h', 0)
        if five + hour == written and (five or hour):
            for tokens, field in ((five, 'cacheWrite5mPerMillion'), (hour, 'cacheWrite1hPerMillion')):
                if tokens:
                    rate = cfg.get(field, cfg.get('cacheWritePerMillion'))
                    known = known and rate is not None
                    amount += tokens * float(rate if rate is not None else ordinary * 2)
        else:
            rate = cfg.get('cacheWritePerMillion')
            known = known and rate is not None
            amount += written * float(rate if rate is not None else ordinary * 2)
    cost = amount / 1e6
    if not usage.get('_complete', True):
        cost = max(cost, estimate)
    return cost, bool(known)


class LLM:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    @contextmanager
    def _slot(self, cfg, check):
        limit = int(number(self.settings.read().get('llmConcurrency', {}).get(cfg['provider'], 2), '模型并发', 1, 32, True))
        identity = digest({'provider': cfg['provider'], 'endpoint': cfg.get('baseUrl'), 'account': str(codex_cli.cli_home(cfg)) if cfg['provider'] == 'codex_cli' else cfg.get('apiKey', '')})
        while True:
            check()
            with _capacity:
                if _active.get(identity, 0) < limit:
                    _active[identity] = _active.get(identity, 0) + 1
                    break
                _capacity.wait(.1)
        try:
            yield
        finally:
            with _capacity:
                _active[identity] -= 1
                if not _active[identity]:
                    del _active[identity]
                _capacity.notify_all()

    def _cache_hit(self, project, role, cfg, key, hit, check):
        check()
        run = {'id': uid('run'), 'projectId': project, 'role': role, 'model': cfg.get('model'),
               'provider': cfg['provider'], 'contextDigest': key, 'status': 'succeeded',
               'createdAt': now(), 'promptVersion': '2.0', 'cacheHit': True,
               'sourceRunId': hit.get('sourceRunId'), 'output': copy.deepcopy(hit['output']),
               'usage': {'input': 0, 'output': 0}, 'rawUsage': {}, 'cost': 0,
               'costKnown': True, 'costEstimated': False, 'wallTime': 0}
        self.store.put('run', run, project)
        self.store.event(project, 'model_completed', {'runId': run['id'], 'role': role,
                         'cost': 0, 'cacheHit': True, 'sourceRunId': run['sourceRunId']})
        return copy.deepcopy(hit['output'])

    def json(self, project, role, system, user, schema=None, demo=None, cache=False, images=None, check=lambda: None, session_scope=None):
        cfg = self.settings.model(role)
        validate_model(cfg)
        if cfg['provider'] == 'codex_cli':
            cfg = codex_cli.prepare(cfg)
            cfg['_sessionScope'] = codex_cli.scope_for(role, system, user, session_scope)
            cfg['_accountConcurrency'] = self.settings.read().get('llmConcurrency', {}).get('codex_cli', 1)
        if schema:
            system += '\n必须满足以下 JSON Schema：\n' + canonical(schema)
        key_material = {'version': 2, 'project': project, 'role': role, 'model': cfg.get('model'),
                      'provider': cfg['provider'], 'endpoint': cfg.get('baseUrl'), 'system': system,
                      'user': user, 'schema': schema, 'images': images, 'format': cfg.get('format'),
                      **({'codexRuntime': cfg['_codexIdentity'], 'sessionScope': cfg['_sessionScope']} if cfg['provider'] == 'codex_cli' else {}),
                      'params': cfg.get('extraBody'), 'temperature': cfg.get('temperature'), 'maxTokens': cfg.get('maxTokens')}
        previous_key_material = key_material
        if cfg['provider'] == 'codex_cli':
            # API controls not sent to CLI cannot change the generated result.
            key_material = {k: v for k, v in key_material.items() if k not in ('endpoint', 'format', 'params', 'temperature', 'maxTokens')}
        key = digest(key_material)
        check()
        if not cache:
            return self._generate(project, role, cfg, key, system, user, schema, demo, False, images, check)['output']
        hit = self.store.cached('llm:' + key)
        if not hit and cfg['provider'] == 'codex_cli':
            # Compatible transport-prompt upgrades preserve already validated
            # results only when the entire task/model/schema identity matches.
            for material in (key_material, previous_key_material):
                for legacy in [cfg['_codexIdentity'], *cfg.get('_codexCompatibleCaches', [])]:
                    hit = self.store.cached('llm:' + digest({**material, 'codexRuntime': legacy}))
                    if hit:break
                if hit:break
            if hit:self.store.cache_put('llm:' + key, hit)
        if hit:
            return self._cache_hit(project, role, cfg, key, hit, check)
        flight_key = (str(self.store.path.resolve()), key)
        with _flights_lock:
            future = _flights.get(flight_key)
            leader = future is None
            if leader:
                future = _flights[flight_key] = Future()
        if not leader:
            while True:
                check()
                try:
                    hit = future.result(timeout=.1)
                    return self._cache_hit(project, role, cfg, key, hit, check)
                except FutureTimeout:
                    if future.done():
                        raise
                    continue
        try:
            hit = self.store.cached('llm:' + key)
            if hit:
                future.set_result(hit)
                return self._cache_hit(project, role, cfg, key, hit, check)
            result = self._generate(project, role, cfg, key, system, user, schema, demo, True, images, check)
            future.set_result(result)
            return copy.deepcopy(result['output'])
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            with _flights_lock:
                _flights.pop(flight_key, None)

    def _generate(self, project, role, cfg, key, system, user, schema, demo, cache, images, check):
        start = time.monotonic()
        run = {'id': uid('run'), 'projectId': project, 'role': role, 'model': cfg.get('model'),
               'provider': cfg['provider'], 'contextDigest': key, 'system': system, 'user': user,
               'schema': schema, 'createdAt': now(), 'promptVersion': '2.0', 'status': 'running', 'cacheHit': False}
        self.store.put('run', run, project)
        hold, submitted = None, False
        try:
            if cfg['provider'] == 'demo':
                ensure(demo is not None, '演示模式不支持此操作；请配置真实模型', 'demo_not_supported')
                output = demo() if callable(demo) else copy.deepcopy(demo)
                raw, usage, cost, cost_known = canonical(output), {'input': 0, 'output': 0}, 0, True
                run['rawUsage'] = {}
            elif cfg['provider'] == 'codex_cli':
                run.update(billingMode='cli_account', cost=0, costKnown=False, costEstimated=False)
                with self._slot(cfg, check):
                    submitted = True
                    raw, cli_usage, session_meta = codex_cli.CodexSessions(self.store).request(
                        project, role, cfg, system, user, images, check, cfg.get('_sessionScope'))
                usage = normalized_usage('codex_cli', cli_usage)
                run.update(raw=raw, rawUsage=cli_usage, codex=session_meta, usageKnown=usage['_complete'])
                usage = {k: v for k, v in usage.items() if not k.startswith('_')}
                run['usage'] = usage
                cost, cost_known = 0, False
                check()
                output = parse_json(raw)
            else:
                ensure(cfg.get('baseUrl') and cfg.get('model'), '请在设置里填写模型地址与名称', 'configuration_required')
                ensure(cfg.get('priceConfigured'), '请先确认模型单价；本地免费模型可填 0。未定价时不提交付费推理', 'price_required', 409)
                input_bound = len((system + canonical(user) + canonical(schema)).encode('utf-8')) + 256 + len(images or []) * int(cfg.get('imageTokenReservation', 8192))
                input_rate = max(float(cfg.get('inputPerMillion', 0)) * (2 if cfg['provider'] == 'anthropic' else 1),
                                 *[float(cfg.get(k, 0)) for k in ('cachedInputPerMillion', 'cacheWritePerMillion', 'cacheWrite5mPerMillion', 'cacheWrite1hPerMillion')])
                estimate = (input_bound * input_rate + int(cfg['maxTokens']) * float(cfg.get('outputPerMillion', 0))) / 1e6
                with self._slot(cfg, check):
                    check()
                    budget = float(self.settings.read()['budget']['project'])
                    project_data = self.store.get(project, required=False)
                    if project_data and isinstance(project_data.get('budget'), (int, float)):
                        budget = float(project_data['budget'])
                    with self.store.transaction() as conn:
                        spent = sum(float(x.get('cost', 0)) for x in self.store.list(project, 'run', conn))
                        spent += sum(float(x['estimate']) for x in self.store.list(project, 'llm_hold', conn) if x['status'] == 'reserved')
                        spent += sum(float(x.get('actual', x['estimate'])) if x['status'] in ('spent', 'unknown') else float(x['estimate']) if x['status'] == 'reserved' else 0 for x in self.store.list(project, 'reservation', conn))
                        ensure(spent + estimate <= budget, '项目预算不足，推理未提交', 'budget_exceeded', 409, {'used': spent, 'reservation': estimate, 'budget': budget})
                        hold = {'id': uid('llm_hold'), 'projectId': project, 'runId': run['id'], 'estimate': estimate, 'status': 'reserved'}
                        self.store.put('llm_hold', hold, project, conn=conn)
                    check()
                    submitted = True
                    raw, usage = self._request(cfg, system, user, schema, images)
                cost, cost_known = usage_cost(cfg, usage, estimate)
                run.update(raw=raw, rawUsage=usage.get('_raw', {}), cost=cost, costKnown=cost_known, costEstimated=not cost_known)
                truncated = usage.get('_truncated', False)
                usage = {k: v for k, v in usage.items() if not k.startswith('_')}
                run['usage'] = usage
                ensure(not truncated, '输出达到长度上限，请提高 maxTokens 或缩小操作范围', 'truncated_output', 422)
                ensure(isinstance(raw, str) and raw.strip(), '模型返回空内容/拒绝，请查看服务商响应', 'empty_model_output', 502)
                check()
                output = parse_json(raw)
            if schema:
                try:
                    jsonschema.validate(output, schema)
                except jsonschema.ValidationError as exc:
                    raise DomainError('模型输出未通过 schema 校验：' + exc.message, 'schema_validation', 422, {'path': list(exc.path), 'output': output})
            run.update(status='succeeded', output=output, raw=raw, usage=usage, cost=cost, costKnown=cost_known,
                       costEstimated=not cost_known and cfg['provider'] != 'codex_cli', wallTime=round(time.monotonic() - start, 3))
            self._settle(run, hold, project)
            result = {'output': output, 'sourceRunId': run['id']}
            if cache:
                self.store.cache_put('llm:' + key, result)
            self.store.event(project, 'model_completed', {'runId': run['id'], 'role': role, 'cost': cost, 'costKnown': cost_known, 'cacheHit': False})
            return result
        except Exception as exc:
            if cfg['provider'] == 'codex_cli' and hasattr(exc, 'cli_meta'):
                run.update(codex=exc.cli_meta, rawUsage=exc.cli_usage,
                           usage={k: v for k, v in normalized_usage('codex_cli', exc.cli_usage).items() if not k.startswith('_')})
            if submitted and hold and 'cost' not in run:
                run.update(cost=hold['estimate'], costKnown=False, costEstimated=True)
            run.update(status='failed', error=str(exc), wallTime=round(time.monotonic() - start, 3))
            self._settle(run, hold, project)
            self.store.event(project, 'model_failed', {'runId': run['id'], 'role': role, 'code': getattr(exc, 'code', 'model_error'), 'cost': run.get('cost', 0)})
            raise

    def _settle(self, run, hold, project):
        with self.store.transaction() as conn:
            self.store.put('run', run, project, conn=conn)
            if hold:
                hold['status'] = 'settled'
                self.store.put('llm_hold', hold, project, conn=conn)

    def _request(self, cfg, system, user, schema, images):
        validate_model(cfg)
        provider, base = cfg['provider'], cfg['baseUrl'].rstrip('/')
        headers, api_key = {'Content-Type': 'application/json'}, cfg.get('apiKey', '')
        usertext = user if isinstance(user, str) else canonical(user)
        if provider == 'anthropic':
            url = base + '/messages'
            headers.update({'x-api-key': api_key, 'anthropic-version': '2023-06-01'})
            content = ([{'type': 'text', 'text': usertext}] + [{'type': 'image', 'source': {'type': 'base64', 'media_type': i['mime'], 'data': i['data']}} for i in images]) if images else usertext
            body = {'model': cfg['model'], 'max_tokens': cfg['maxTokens'], 'system': system, 'messages': [{'role': 'user', 'content': content}], 'temperature': cfg.get('temperature', .7)}
        elif provider == 'gemini':
            url = base + '/models/' + cfg['model'] + ':generateContent'
            headers['x-goog-api-key'] = api_key
            parts = [{'text': usertext}] + [{'inlineData': {'mimeType': i['mime'], 'data': i['data']}} for i in images or []]
            body = {'systemInstruction': {'parts': [{'text': system}]}, 'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': {'responseMimeType': 'application/json', 'maxOutputTokens': cfg['maxTokens'], 'temperature': cfg.get('temperature', .7)}}
        else:
            url = base + '/chat/completions'
            headers['Authorization'] = 'Bearer ' + api_key
            content = ([{'type': 'text', 'text': usertext}] + [{'type': 'image_url', 'image_url': {'url': 'data:' + i['mime'] + ';base64,' + i['data']}} for i in images]) if images else usertext
            body = {'model': cfg['model'], 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': content}], 'temperature': cfg.get('temperature', .7), 'max_tokens': cfg['maxTokens']}
            if cfg.get('format', 'json_object') == 'json_schema' and schema:
                body['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'studio_output', 'strict': False, 'schema': schema}}
            elif cfg.get('format', 'json_object') == 'json_object':
                body['response_format'] = {'type': 'json_object'}
        body.update(cfg.get('extraBody', {}))
        try:
            with httpx.Client(timeout=float(cfg['timeout']), follow_redirects=False) as client:
                response = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException:
            raise DomainError('模型接口超时，未自动重试以免重复计费', 'model_timeout', 504)
        except httpx.RequestError as exc:
            raise DomainError('模型接口连接失败：' + str(exc), 'model_network', 502)
        ensure(response.is_success, f'模型接口返回 HTTP {response.status_code}：{response.text[:600]}', 'model_http', 502)
        data = response.json()
        if provider == 'anthropic':
            text = ''.join(i.get('text', '') for i in data.get('content', []))
            usage = normalized_usage(provider, data.get('usage') or {})
            usage['_truncated'] = data.get('stop_reason') == 'max_tokens'
        elif provider == 'gemini':
            candidate = (data.get('candidates') or [{}])[0]
            text = ''.join(p.get('text', '') for p in (candidate.get('content') or {}).get('parts', []) if not p.get('thought'))
            usage = normalized_usage(provider, data.get('usageMetadata') or {})
            usage['_truncated'] = candidate.get('finishReason') == 'MAX_TOKENS'
        else:
            choice = (data.get('choices') or [{}])[0]
            text = (choice.get('message') or {}).get('content', '')
            usage = normalized_usage(provider, data.get('usage') or {})
            usage['_truncated'] = choice.get('finish_reason') == 'length'
        return text, usage
