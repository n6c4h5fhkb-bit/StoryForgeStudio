"""Persisted, AI-first topic exploration before a story project exists."""
from __future__ import annotations
import copy
from pydantic import BaseModel, ConfigDict, Field
from .core import ensure, uid, now, canonical

SCOPE = 'story_ideation'


class Idea(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=80)
    genre: str = Field(min_length=1, max_length=60)
    tone: str = Field(min_length=1, max_length=100)
    premise: str = Field(min_length=10, max_length=800)
    protagonist: str = Field(min_length=1, max_length=200)
    conflict: str = Field(min_length=1, max_length=300)
    hook: str = Field(min_length=1, max_length=300)
    appeal: str = Field(min_length=1, max_length=300)
    productionNote: str = Field(min_length=1, max_length=300)


class Ideas(BaseModel):
    ideas: list[Idea] = Field(min_length=4, max_length=4)


PROMPT = '''你是剧本创作的选题搭档。用户可以完全没有故事种子，由你主动给出四个可供选择的原创选题。
不要反问用户先填写标题或梗概，不替用户定稿。用中文，写具体人物、可见行动与选择的代价，不写泛泛类型标签。
每个选题包含 title、genre、tone、premise（起点、因果推进与可能的结局方向）、protagonist、conflict、hook（可拍出的开场）、appeal（观众为何继续看）、productionNote（关键制作难点与可控拍法）。
四个方向在人物关系、核心矛盾或叙事机制上明显不同，不能只换人名职业。兼顾作品质量和小团队制作可行性。
mode=quality 重视人物、情感与完整因果；mode=fast_drama 重视短剧开头吸引力、行动推进和追看欲，不写旁白配图方案。
有 anchor 时围绕该选题探索四种有实质区别的发展方向；没有 anchor 时自由脑暴。有 preferences 时遵守偏好。
避开 previousIdeas 中已有的核心构思。不要声称查过实时热榜、拥有小说版权或改编了未提供的原著。
此时不制定集数和秒数。只输出满足 schema 的 JSON。'''

# Explicitly labelled offline fixtures. Real generation always uses the configured LLM.
DEMO_TOPICS = [
    ('最后一班渡船', '悬疑亲情', '渡船停航前夜，女船长接到失踪父亲预约的船票。她发现每位乘客都隐瞒着同一场救援事故，决定先救下被困的证人，再公开父亲也有责任的真相。', '准备离乡的女船长', '保住父亲名誉，还是完成他未能完成的救援', '检票机吐出一张日期为明天、姓名却属于失踪父亲的船票。'),
    ('临时家属', '都市关系', '急诊陪诊员替陌生老人签字后，被老人认作多年不见的女儿。她想尽快脱身，却发现真正的女儿就在医院工作，最终以自己的失信经历促成一次不被原谅也必须说清的见面。', '擅长应付别人、回避自己家庭的陪诊员', '完成一份工作，还是承担越界帮助的后果', '老人准确叫出陪诊员的乳名，下一句却是：这次别再替她道歉。'),
    ('退货期限', '都市轻奇幻', '二手店老板收到一台能退回昨日一次决定的收银机，每次退货都会让一位熟人忘记他。他为了挽救一场误会不断退货，最后只能在无人认识自己的情况下重新兑现承诺。', '只会用钱补偿关系的二手店老板', '撤销错误的诱惑，与承担错误的能力', '收银机打印出昨天那句伤人的话，退货期限只剩十分钟。'),
    ('冒牌继承人', '快节奏悬疑', '小镇修锁匠被要求冒充豪宅继承人参加遗产宣读。他发现被指控偷窃的佣人是自己的母亲，便利用修锁手艺拆穿遗嘱调包，却必须同时承认自己的冒名骗局。', '急于替母亲还债的修锁匠', '保住到手的身份，还是公开自己也是骗子', '他刚被全家叫作少爷，门外的母亲就被押进来指认为小偷。'),
    ('合租证人', '都市悬疑', '失业剪辑师发现合租人的报警录音中藏着自己的声音。他试图剪掉证据换取安稳，却在追查中发现声音来自一次被自己删去的求救，最终提交未经修饰的全部素材。', '习惯替客户掩饰事实的剪辑师', '用技术脱罪，还是保留不利于自己的证据', '室友失踪后的录音里，传来剪辑师尚未说出口的一句话。'),
    ('倒数第二名', '青春成长', '总拿倒数第二的女生被推选参加辩论赛，搭档却是公开举报她作弊的人。两人为保住被取消的校车争取发言机会，逐渐承认彼此都有不愿公开的家庭处境。', '靠装作不在乎保护自尊的女生', '赢下一场比赛，还是让真正需要帮助的人被听见', '她收到获奖通知，奖项却是全校最不值得被期待的人。'),
    ('失约保管箱', '情感悬疑', '银行清退旧保管箱时，职员发现一封写给自己婚礼当天的信。为了查明寄信人，她必须联系每一个被自己爽约的人，最后发现真正需要面对的是自己一直推迟的离开。', '凡事追求稳妥的银行职员', '维持体面的关系，还是承认不愿继续的生活', '保管箱里是她明天婚礼的照片，照片上新娘的脸被剪掉了。'),
    ('借来的掌门', '古装喜剧', '戏班替身被没落门派请去冒充掌门，原本只想领钱退场，却被弟子当作唯一的依靠。他用舞台机关赢得喘息机会，最终在真正的强敌面前坦承自己不会武功并组织众人自救。', '擅长装英雄却害怕承担责任的替身', '维持无敌形象，还是教会别人不依赖自己', '他第一次坐上掌门座，台下弟子齐声请求他明日出战天下第一。'),
]


class IdeationService:
    def __init__(self, story):
        self.story, self.store, self.llm = story, story.s, story.llm

    def batches(self):
        return list(reversed(self.store.list(SCOPE, 'idea_batch')))

    def idea(self, batch_id, idea_id):
        batch = self.store.get(batch_id)
        ensure(batch.get('projectId') == SCOPE and isinstance(batch.get('ideas'), list), '选题批次无效')
        idea = next((i for i in batch['ideas'] if i['id'] == idea_id), None)
        ensure(idea, '选题不存在', 'not_found', 404)
        return batch, idea

    def generate(self, data, progress=lambda *_: None, check=lambda: None):
        mode = data.get('mode', 'quality')
        ensure(mode in ('quality', 'fast_drama'), '请选择有效创作方向')
        preferences = data.get('preferences', '')
        ensure(isinstance(preferences, str) and len(preferences) <= 2000, '偏好最多 2000 字')
        anchor = None
        if data.get('anchor'):
            ref = data['anchor']
            ensure(isinstance(ref, dict), '脑暴来源无效')
            _, anchor = self.idea(ref.get('batchId'), ref.get('ideaId'))
        previous = self.batches()
        context = {'mode': mode, 'preferences': preferences, 'anchor': anchor,
                   'previousIdeas': [{'title': i['title'], 'premise': i['premise']} for b in previous[:3] for i in b['ideas']],
                   'round': data.get('operationId') or uid('round')}
        ensure(len(canonical(context)) <= int(self.story.settings.model('ideation')['contextCharacters']), '选题上下文超过模型限制，请提高上下文字符上限', 'context_budget', 422)
        demo = []
        for index in range(4):
            title, genre, premise, hero, conflict, hook = DEMO_TOPICS[(len(previous) * 4 + index) % len(DEMO_TOPICS)]
            if anchor:
                title = anchor['title'] + ' · ' + ['关系推进', '主动犯错', '信息反转', '两难选择'][index]
                premise = anchor['premise'] + '（离线演示：沿此方向继续探索，真实方案需连接模型。）'
                hero, conflict, hook, genre = (anchor[k] for k in ('protagonist', 'conflict', 'hook', 'genre'))
            demo.append(dict(title=title, genre=genre, tone='人物主动、情绪克制', premise=premise,
                             protagonist=hero, conflict=conflict, hook=hook, appeal='用行动和代价推动关系变化，留下可追看的问题。',
                             productionNote='优先集中在少量主要人物和固定场景，关键物件保持一致。'))
        progress(.12, 'AI 正在准备四个不同的故事选题')
        result = self.llm.json(SCOPE, 'ideation', PROMPT, context, schema=Ideas.model_json_schema(), demo={'ideas': demo}, cache=True, check=check)
        parsed = Ideas.model_validate(result)
        ensure(len({i.title for i in parsed.ideas}) == 4, '选题标题重复，请换一批', 'duplicate_ideas', 422)
        check()
        batch = {'id': uid('ideas'), 'projectId': SCOPE, 'mode': mode, 'preferences': preferences,
                 'anchor': copy.deepcopy(data.get('anchor')), 'createdAt': now(),
                 'demo': self.story.settings.model('ideation')['provider'] == 'demo',
                 'ideas': [{**i.model_dump(), 'id': uid('idea')} for i in parsed.ideas]}
        self.store.put('idea_batch', batch, SCOPE)
        self.store.audit(SCOPE, 'brainstorm', [batch['id']], {'mode': mode, 'anchor': batch['anchor']})
        return batch

    def adopt(self, batch_id, idea_id):
        batch, idea = self.idea(batch_id, idea_id)
        seed = '\n'.join([idea['premise'], '主人公：' + idea['protagonist'], '核心冲突：' + idea['conflict'],
                          '开场钩子：' + idea['hook'], '追看理由：' + idea['appeal'], '制作考虑：' + idea['productionNote']])
        return self.story.create({'title': idea['title'], 'seed': seed, 'genre': idea['genre'], 'tone': idea['tone'],
                                 'compact': True, 'template': 'hook_chain' if batch['mode'] == 'fast_drama' else 'custom'},
                                origin={'batchId': batch_id, 'ideaId': idea_id, 'demo': batch['demo']})
