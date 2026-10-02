下面是我最终定下的方案。所有争议点都已做决断，不再列选项；只在最后单独列出会改变优先级的待定变量。

---

# Story Decision System — 最终设计

## 0. 定义与三条不可妥协的原则

**产品定义**：人不产出内容，只产出决策；系统把决策编译成越来越完整的故事。它卖的不是"生成质量"，而是**降低选错的代价**——事前用探针看清，事后用契约便宜反悔。

**三条原则**（任何实现细节冲突时以此仲裁）：

1. **LLM 永不直接修改正式内容**。一切生成落为 Candidate，人采纳才进入 Revision。唯一例外：用户显式开启的低风险 polish 自动采纳。
2. **任何时刻项目存在一条可通读的端到端草稿**。分辨率可以很粗，但不允许"第一幕成片、第三幕空白"。
3. **一致性系统只阻塞投入，不阻塞交付**。任何时候都能导出全片。

---

## 1. 架构

```
                    STORY WORKSPACE
              Outline · Workspace · Operation Panel
                          │
        ┌─────────────────┴─────────────────┐
        ↓                                   ↓
 CREATIVE SEARCH ENGINE            STORY INTEGRITY ENGINE
 （决定好不好 = 竞争力）             （决定崩不崩 = 护栏）
   Strategy Pool                     Contract
   Candidate Engine                  Temporal Canon
   Probe                             Continuity（确定性 + 语义）
   Branch / Compare                  Impact Analysis
   Reject-with-reason                Reconcile
        └─────────────────┬─────────────────┘
                          ↓
                      STORY IR
        Composition Tree · Canon · Narrative Graph
              Constraints · Revisions · Ops Log
```

投入优先级固定为：**Story IR（地基）> Candidate Engine（竞争力）> Integrity Engine（护栏）**。Integrity 做到"足够让人敢改上游"即止，不追求完备。

---

## 2. Story IR

### 2.1 层级（六层，定死）

```
L0 Seed      图 / 一句话 / 一个事件          非节点，项目属性
L1 Premise   logline · 主题 · 核心矛盾 · 赌注 · 目标长度
L2 Spine     结构骨架（模板可插拔）+ 每幕价值变化
L3 Sequence  序列：目标—阻碍—转折—代价
L4 Scene     场景：契约 + body（含 beats[]）
L5 Script    对白 + 动作行
```

**Beat 不独立物化**，活在 `scene.body.beats[]`；仅当被 Narrative Edge 引用（某动作是 setup）时提升为 addressable block（promotion-on-reference）。这省掉了整条管线最大的结构税与 token 成本中心。

### 2.2 Node

```ts
type Node = {
  id: string
  level: 'premise'|'spine'|'sequence'|'scene'|'script'
  parentId: string | null
  order: string                    // fractional index，插入不重排

  // 规格：对父与兄弟可见，是解耦与增量的唯一依据
  contract: Contract

  // 实现：只有自己与子节点关心
  body: object                     // 按 level 的 schema

  status:    'draft'|'accepted'|'locked'|'archived'
  freshness: 'clean'|'opportunity'|'broken'
  freshnessNotes: Note[]           // opportunity 的具体建议、broken 的冲突说明

  resolution: number               // 已展开到第几层，供 frontier 计算
  speculative: boolean             // 超出 frontier 深化出来的产物

  currentRevision: string
  candidates: Candidate[]          // 未采纳的备选，永久保留
}

type Contract = {
  summary: string                  // 一句话
  preconditions: StateRef[]        // 进入时世界必须处于什么状态
  postconditions: StateRef[]       // 退出时世界变成什么状态
  valueChange: { axis: string, from: string, to: string }   // 为空则判废
  reveals: string[]                // 向观众/角色释放的信息
  obligations: string[]            // 必须完成的叙事任务
  entities: string[]               // 指向 Canon
  producibility?: Producibility    // 仅 AI 视频管线下启用，见 §13
}
```

**契约自上而下产出，绝不从 body 反推**。`expand` 内部两段执行：

```
expand(node)
  ├─ Phase 1  生成 N 套子节点契约序列   → 人在此选择（结构决策）
  └─ Phase 2  对已采纳契约逐个生成 body（可批量、可异步）
```

UI 上仍是一个"扩展"按钮，但两段之间必须有人类闸口。这条是整个增量系统的地基：如果契约是 LLM 事后总结出来的，"契约未变 ⇒ 下游可复用"就退化成一次概率判断，不如不做。

### 2.3 Canon（时间索引，非事实列表）

```ts
type Entity = { id, kind: 'character'|'location'|'prop'|'rule'|'faction', ... }

type Fact = {                     // 客观事实
  subject: string, predicate: string, object: string
  validFrom: NodeRef, validUntil: NodeRef | null
}

type Belief = {                   // 主观认知，可为假 —— 必须与 Fact 分开
  holder: string | 'AUDIENCE'
  content: string
  truth: boolean                  // false = 故意的误导/骗局
  validFrom: NodeRef, validUntil: NodeRef | null
}
```

`truth: false` 必须显式标注，否则一致性检查会把所有骗局和假线索误报成 broken——这是这套机制最容易翻车的一处。

`holder: 'AUDIENCE'` 让观众成为一等公民，由此得到**知识矩阵**与可计算的张力类型：

```
悬念 suspense = AUDIENCE knows ∧ character ¬knows
惊奇 surprise = 双方 ¬knows
神秘 mystery  = character knows ∧ AUDIENCE ¬knows
戏剧反讽      = |AUDIENCE| > |character|
```

产出**全片张力配比曲线**。诊断价值极高（"你这片 80% 靠 surprise 撑着"），并且反向成为策略池输入。这是继探针规格库之后第二条护城河：它把叙事张力变成可计算量。

### 2.4 Narrative Graph（与树分离）

树管包含关系，图管叙事关系。边类型：`causes` / `setup→payoff` / `character_arc` / `reveal_dependency` / `contrast`。

Setup-Payoff 是带状态机的账本：`open → progressing → paid | orphan`。未回收清单常驻 UI。

### 2.5 Revision vs Branch（不混用）

- **Revision**：默认。局部调整、rewrite、polish 全走 revision 链。
- **Branch**：仅用于结构性探索（"主角杀人 vs 放人，各往后看五场"）。显式创建，可 compare / adopt / abandon。

不让每次修改都产生 branch——否则一个项目三天内会有几百个分支。

### 2.6 Operations Log

所有操作 append-only：`{who, op, scope, instruction, contextDigest, model, params, promptVersion, result, cost}`。当前树是投影。天然得到撤销、时间旅行、可复现、计费、以及"这段是怎么来的"溯源。

---

## 3. 状态传播规则（完整定义）

采纳一个 Candidate 时执行：

```
Commit
 ├─ 1. 写入新 Revision
 ├─ 2. Contract Diff（新旧契约比对）
 ├─ 3. Canon Patch Proposal（draft 阶段自动落 provisional，
 │       节点 accepted 时才进待批准队列 —— 避免边写边弹窗）
 ├─ 4. Impact Analysis
 │      契约未变              → 下游 clean，什么都不做
 │      契约变且与下游冲突     → 下游 broken（阻塞继续投入）
 │      契约未变但语境变化     → 下游 opportunity（非阻塞建议）
 └─ 5. speculative 节点若其上游 frontier 推进 → 自动转 opportunity
```

**broken 与 opportunity 的分工是这套设计里最重要的一条**：前者"必须处理"，后者"也许能更好"。混成一个 stale 标记，上游修改就会引发大面积误报，用户随后再也不敢改上游——这是节点式创作工具的标准死法。

状态语义表：

| 组合 | 含义 | 系统行为 |
|---|---|---|
| accepted + clean | 正常 | — |
| accepted + opportunity | 可优化 | 建议队列，可忽略 |
| accepted + broken | 需修 | 阻塞在其下深化；不阻塞导出 |
| **locked + broken** | **用户押注的节点与上游冲突** | **弹出人类仲裁：改新内容 / 改锁定节点 / 改 Canon，三选一，留审计** |
| locked + opportunity | 锁了但有更优解 | 只提示，绝不自动改 |

系统**永不**修改 locked 节点。这是用户敢用这个工具的心理基础。

---

## 4. Operation 系统

人类的全部输入都收敛到这张表：

| 类 | 操作 | 说明 |
|---|---|---|
| 扩展 | `expand` `deepen` `interpolate` | expand 两段式；interpolate 补过渡 |
| 变体 | `vary` | 同位置多候选，策略正交 |
| 改写 | `rewrite(instruction)` `restyle` `transform` | 自然语言指令 |
| 强度 | `escalate` `tighten` `compress(ratio)` | 受长度预算约束 |
| 叙事 | `add_setup` `add_payoff` `move_reveal` `twist` | 直接操作 Narrative Graph / 知识矩阵 |
| 结构 | `split` `merge` `reorder` `delete` | |
| 元 | `lock/unlock` `pin(constraint)` `branch/compare/adopt` `probe` | |
| 审计 | `continuity_scan` `foreshadow_audit` `voice_audit` `tension_profile` | 只读 |

**自然语言入口**：`⌘K` → IntentParser（小模型）→ 结构化 Operation。

**Dry-Run 的适用边界**（不做成硬规则，否则纯属折磨用户）：

```
需要 Plan/Diff 预览：可能产生跨节点传播的操作
  rewrite(structure) · delete · reorder · change_motivation · move_reveal · unlock
直接出候选：局部且无传播
  vary · restyle · escalate · tighten · polish
```

预览内容：将动到哪些节点、哪些被 locked 挡住、预计候选数、token 与耗时估算。

---

## 5. Candidate Engine（第一核心）

```
Operation
   ↓
Strategy Selection      从策略池采样 k 个正交策略
   ↓
Generation              k 路并行，每路带不同策略指令
   ↓
Hard Gate               契约符合 / valueChange≠0 / Canon 不冲突 / 格式合法
   ↓                    不过 → 自动重试，2 轮不过则降级交人并标注原因
Quality Scoring         rubric 打分
   ↓
Diversity Selection     不是 Top-3
   ↓
Candidate Tray          3 张卡 + 两两 diff + 风险标签 + 差异说明
```

### 5.1 策略池（正交，按层定义）

不靠 temperature 制造差异，靠**策略正交**。示例（scene 层）：

```
提高外部压力（对手行动）      抽走支撑（盟友/资源/时间消失）
反转内部立场（主角自毁）      引入观众独知信息（→ suspense）
制造角色错误信念（→ 误导）    延迟揭示（信息后置）
让两角色信息不对称            身份/关系揭示
```

采样时保证策略不重复。这是"比裸 ChatGPT 强"的主要来源之一。

### 5.2 Diversity Selection（不许退化成 Top-3）

硬门禁后按三个位次选：

```
最佳稳妥   —— 质量分最高
最佳新颖   —— 新颖度分最高且质量过线
最佳另类   —— 与前两者语义距离最大且质量过线
```

Top-3 会选出同一个答案的三种说法，这是我原方案里被正确批评的一处。

### 5.3 Reject-with-reason

拒绝时给理由（可点选 + 可自由写）。理由进**负面清单**，立刻作用于下一轮候选装配，并作为 rubric 校准数据沉淀。这是 P1 阶段唯一零成本改善候选质量的杠杆。

### 5.4 Merge 的语义

"取 A 的结构 + B 的结尾"**实现为带双参照的重新生成**，不是字面拼接。缝合两个自洽结构只会产出两边都破掉的糊状物。按钮保留，实现换掉。

---

## 6. Probe（Comparable Probe）

解决的问题：**人在抽象层的判断力远弱于所有方案的假设**。读三段大纲选结构，错误要到 L5 才暴露。

### 6.1 规格

```ts
type ProbeSpec = {
  decisionType: string            // 'compare_premise' | 'compare_act2_engine' | ...
  sceneSelector: string           // 功能性描述，非位置性
  renderTo: 'script' | 'keyframe'
  horizontalDepth: number         // 机器用，默认 4
}
```

三条铁律：

1. **功能性选择器**，如"主角第一次因该方案付出不可逆代价的那场"，由各候选各自解析到自己的场次。禁止"第 8 场"这类位置性描述。
2. **规格在候选生成之前预注册**。否则你会在看完候选后挑一个偏袒某方案的规格——这是实验者偏差，做的时候毫无自觉。
3. **纵横分工**：

```
纵向臂  穿透生成到 Script/关键帧  → 给人读，做品味判断
横向臂  后续 4 场摘要级 rollout   → 只给机器，出 3~5 个红绿灯
```

横向臂**绝不给人读**：摘要仍是抽象物，让人读 12 条摘要恰好把探针要解决的问题请回来，还叠加了决策疲劳。它只跑结构 flag：是否必须引入新角色才能续、主角是否连续三场被动、是否与已 locked 下游契约冲突、冲突源是否重复。

**人读三场戏，机器给三个红绿灯。**

### 6.2 派生机制

- **解析失败即诊断**：某候选找不到符合 selector 的场景（如"没有不可逆代价"），这本身是强结构缺陷信号，免费获得。
- **探针产物 non-canonical**：以 spike 身份入库，不进树，不计入 coverage。
- **风格锁来源**：被选中方案的探针产物抽为 few-shot 样例（句长、语气、禁忌词），供下游防漂移。

### 6.3 ProbeSpec 注册表是专有资产

`DecisionType → ProbeSpec` 这张表和策略池一样，靠人的品味长期积累，不是 prompt 技巧。它是护城河之一。

### 6.4 Probe 与"便宜反悔"是替代品

两者解决同一问题（选错的代价），成本结构相反：

```
Probe        每个决策都付费，包括本来就会选对的
便宜反悔     只在真的选错时付费
```

决策规则：**选错率低 → 反悔赢；选错率高 → Probe 赢**。而反悔机制几乎免费（Contract 已经带来了下游可复用）。所以 Probe 必须打赢"裸结构 + 便宜反悔"这个基线才配全量投入，见 §12 P0。

---

## 7. Integrity Engine

**确定性检查（纯代码，不用 LLM）**：时间线、人物位置、生死、道具状态、知识状态时序、setup/payoff 生命周期、长度预算。可判定的前提是 §2.3 的时间索引事实——这是"确定性 vs 语义分工"能落地的唯一原因。

**语义检查（LLM，低温）**：动机合理性、情绪转变有无铺垫、OOC、主题一致、逻辑跳跃。

**Voice 策略**：生成合一（一场戏由一个 agent 写，注入各角色声线卡），审计分离（跨全片按角色抽出所有台词做区分度检查）。不用 per-character 生成——对白是互动，不是各写各的台词；但区分度是逐场生成结构上看不到的。

**误报治理**：语义检查必然误报，因此 broken 只阻塞下游投入，不阻塞导出；且每条 broken 可一键标记"不是问题"，进负面清单。

---

## 8. Context Assembler（工程核心）

单次生成的上下文恒定在数千 token，无论剧本多长：

```
[Pin 约束]        用户硬性要求，最高优先级
[Bible 摘要]      主题 + 主要角色一句话 + 世界规则
[祖先链契约]      根→父，只取 contract，不取 body
[邻接]            前后 1~2 个同级节点（scene 层取全文，其余取契约）
[相关 Canon]      涉及实体的时点事实 + 未回收伏笔（检索）
[风格锁]          已采纳片段抽出的 few-shot
[负面清单]        已用桥段 + 被拒候选的理由
[任务]            Operation + 指令 + 目标契约
```

**负面清单里"用户拒过的东西"是性价比最高的一项**：它让系统显得记得你的偏好，且几乎零成本。

---

## 9. 收敛机制

**默认工作方式 = Progressive Resolution**（逐级细化，非 depth-first）：

```
第一遍 完整 Premise → 第二遍 完整 Spine → 第三遍 完整 Sequence
→ 第四遍 完整 Scene List（此时已可从头到尾通读）→ 第五遍 Script
```

**Resolution Frontier**：不禁止超前深化，但给经济代价而非弹窗说教——

```
超出 frontier 的产物  → speculative = true，不计入 coverage
上游 frontier 推进时  → 自动转 opportunity（因为它写于信息不足时）
```

**长度预算**：目标时长/集数在 L1 设定，L3 场景数与之挂钩，`compress`/`deepen` 以此为预算。没有预算，AI 一定越写越长。

**一键通读**：必须在 P1 就有，线性阅读视图，读当前分辨率的全片。这可能是整个产品最有用的单一功能——它比任何 Critic 都更能发现结构问题。顺带记录**用户通读后的第一个操作**，那是最真实的问题定位信号。

---

## 10. Agent 与模型分层

P1 只要两个：**Generator** + **Validator**（确定性代码 + 小模型格式/契约校验）。

**P1 不做用户可见的 Critic**。没有校准过的 rubric，它只会输出"可以加强人物动机"这种话，用户三次之后永久忽略它——一个被忽略的功能比没有更糟，因为它教会用户不信任系统的判断。评价能力先藏在 Candidate Engine 内部（hard gate + diversity selector）。

模型分层（成本必需项，非优化项）：

```
L1/L2 结构层    全项目仅几十次调用  → 用最强模型
L3/L4           数百次              → 中档
L5 Script       上千次              → 中档
Validator/格式  → 小模型或纯代码
IntentParser    → 小模型
```

量级参考：长片含约 3 倍返工系数，候选全开约**数百万 output token**。砍掉 Beat 层省掉其中最大一块。

---

## 11. 指标

```
质量  ≈ 采纳率 × Survival@5/@20 × 下游展开后的 Lock 转化率
```

- **不要用裸采纳率做北极星**：平庸但无攻击性的候选采纳率最高，决策疲劳也会推高它。优化它会收敛到"生成安全的候选"。
- **Survival 是真信号**：采纳后 20 次操作仍未被 rewrite/删除。"采纳 → 写三场 → 发现不行 → rewrite"本质是一次迟到的 reject。
- **防御性 Lock 不是噪声，是信任仪表**：早期 Lock 率高 = 用户不信传播机制。它是 Integrity Engine 的 KPI。
- 后悔信号：短期 undo、同节点重复 vary、branch abandoned 率。
- **Switch Rate**：见 P0。

---

## 12. 路线图

### P0 — 改选率实验（不写代码，1~2 天）

**唯一目的**：定 P1 是 probe-first 还是 revert-first。这是目前唯一未定、却会改变 P1 形状的变量。

```
1. 只给结构候选（纯大纲），用户选定并写下理由
2. 立刻生成 Comparable Probe（三个，不标注对应关系）
3. 再问一次：现在选哪个
   Switch Rate = 大纲层判断被自己推翻的比例
```

对照组是**"裸结构 + 便宜反悔"**，不是裸结构。判读：

```
< 20%  → Probe 是昂贵的仪式感，P1 走 revert-first
> 40%  → Probe 是最难被聊天式工具复制的一层，P1 走 probe-first
```

设计优点：被试内对比、无需等 20 次操作、测的是显示偏好而非回忆。锚定效应使人不愿承认改主意，所以它**系统性低估 Probe**——方向上是保守估计。

### P1 — 最小可用软件

```
层级        Premise → Sequence → Scene（Script 仅由 Probe 临时生成）
对象        Node(contract+body) / Candidate / Operation / Revision / Canon-lite
状态        status 四态 × freshness 三态，完整传播规则
操作        expand(两段) / vary / rewrite / lock / reorder / delete
Candidate   策略正交 + 硬门禁 + 多样性三位次 + reject-with-reason
Probe       手动触发，仅限 2~3 个最高风险决策点（全量投入待 P0 判读）
收敛        Progressive Resolution + Coverage + 一键通读
Canon       手工维护的结构化面板，全量注入，无 RAG、无自动抽取
Agent       Generator + Validator
UI          左大纲 + 中候选/正文 + 右操作台。不上画布。
```

Canon-lite 必须在 P1：没有它，三层生成就在人名和事实上漂移，Contract 的 `entities` 指向空气。但它只是个手工文本面板，几乎零成本。

### P2 — 从"能玩"到"能用"

Temporal Canon + 知识矩阵 + 确定性一致性检查 + Canon Patch Proposal + Impact Analysis 完整版 + Diff 预览 + Branch/Compare + Narrative Graph + Setup/Payoff 账本 + Script 层正式落地 + ProbeSpec 注册表。

### P3 — 产品化

画布视图 + 时间线 + 张力配比曲线 + Voice Audit + 偏好学习 + 协作批注 + 导出 Fountain/FDX（或分镜下译，见 §13）。

---

## 13. 待定变量（会改变优先级）

### A. 用户是谁

Probe 的价值是用户依赖的，不是普适的：

- **职业编剧** — 有结构直觉，Probe 是浪费；要极好的反悔与快速结构草图。
- **短剧/内容工厂** — 要吞吐与一致性，决策越少越好；Probe 是道慢闸，会被关掉。
- **无结构经验者** — 最需要 Probe，因为确实读不出大纲好坏。

这个决定 P0 测什么。

### B. 下游是文字剧本，还是 AI 生成视频

如果是后者（分镜 / image_prompt / 生图生视频），以下全部翻转：

1. **Probe 穿透到关键帧图像**。视觉材料对人的判断力远强于文字，且这条管线里渲染便宜。§6.4 的天平明显向 Probe 倾斜。
2. **结构模板换成钩子链 + 每集断章**。迭代单元是集不是片，"结构选错"代价大幅下降，又反向削弱 Probe 必要性。
3. **Canon 第一字段不是 want/need/wound，是角色冻结视觉描述串**。观众一眼看出的不一致是脸，不是动机。这是前面所有架构讨论的共同盲区。
4. **Contract 增加 `producibility` 维度**：这场戏能否被现有生图/生视频模型稳定产出。写得漂亮但生不出来，在这条管线里等于 broken。
5. **多一层 Scene → 分镜的下译**，Contract 思路直接复用：分镜是 Scene 的实现，Scene 契约不变则分镜不必重出。

架构不变，优先级重排。

---

## 14. 明确不做（反清单）

| 不做 | 原因 |
|---|---|
| Beat 作为独立层 | 结构税 + 最大 token 中心，折进 scene body |
| per-character 对白生成 | 对白是互动；改为跨片审计 |
| 用户可见的 Critic（P1） | 未校准的点评会训练用户忽略系统判断 |
| 自动回写 Canon | 走 Patch Proposal；draft 阶段落 provisional |
| 每次修改都建 Branch | 项目三天内会有几百分支；默认 Revision |
| 所有操作都强制 Dry-Run | 只有可能传播的操作才要 |
| broken 阻塞导出 | 语义误报会升级成故障，用户会关掉整个一致性系统 |
| 候选一次给 5+ | 决策疲劳是第一杀手；固定 3 + 重新生成 |
| Merge 做字面拼接 | 缝合两个自洽结构 = 两边都破 |
| 全文塞 prompt | Context Assembler 恒定预算 |
| P1 上画布 / 向量库 / 多 Agent | 都不解决 P1 要验证的问题 |
| 一切皆节点 | Canon 实体、Narrative 边、Content 块各自建模 |

---

## 一句话收束

**Story IR 是地基，Candidate Engine 是竞争力，Integrity Engine 是护栏，Probe 是待验证的高赔率赌注。**编译器那套（契约、增量、类型检查）只负责让它不崩；让它好看的是策略正交的候选生成，加上让人尽早看见"这个选择将来长成什么样"的能力。

下一步我建议只做 P0 的改选率实验——它半天到两天能跑完、不需要代码，却决定 P1 的形状。你把 §13 的两个变量定了（用户是谁、下游是文字还是 AI 视频），我可以直接给出**改选率实验的完整规格**（决策点选取、ProbeSpec 预注册、记录字段、判读阈值）或 **ProbeSpec 注册表的首批 6 条**（含探针 context 装配与风格锁抽取规则）。