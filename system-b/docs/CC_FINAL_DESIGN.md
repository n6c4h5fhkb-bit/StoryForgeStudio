明白。pi-agent 通用工具型 → 默认吃 Operator;codex → Builder + Curator;但**路由必须是配置项而非硬编码**,并留出第三方接入位。下面是完整的最终版 System B。

---

# System B — 视听导演系统 · 最终设计

## 0. 定位与三条原则

B 的输入是剧本(来自 A)或小说,输出是可交给 Seedance 等模型生成的完整视听方案与成片素材。**B 是导演 + 制片,不是格式转换器**——它有权改呈现(不改故事),并对"生得出来、接得上、有感觉"负责。

1. **昂贵产物永不隐式重生成**。一切生成由 renderKey 守门,命中即复用。
2. **确定性外壳,非确定性内核**。调度、依赖、编译、校验全是纯代码;只有真正需要应对不稳定性的地方才放 agent,且关在幂等壳里。
3. **雪崩级对象必须显式定稿**。StylePreset 与 MasterAsset 改动会让全片失效,需二次确认并展示影响面与预估成本。

---

## 1. 阶段与闸口

```
B0  Ingest      归一化 · 场次切分 · 平段检测           → 场次表
B1  Treatment   改编 · 风格包 · 情绪/节奏曲线 · 转场    → 风格包定稿 ★雪崩级
B2  Assets      资产图谱 · 主资产/衍生 · 变体 · 伏笔     → 主资产定稿 ★雪崩级
B3  Direction   逐场导演方案:情节/情绪/调度/光/声       → 导演方案
B4  Shot List   分镜表 · 连续性求解 · 运镜/速度/光位      → 分镜表 + 校验通过
B5  Render      关键帧 → 视频片段 · 衔接链               → 10留3 · 片段验收
B6  Assembly    剪辑 · 音乐 · 音效 · 节奏校验             → 成片
```

任一闸口可打回任一上游阶段,由依赖图算出必须重做的范围。

---

## 2. 核心对象

```ts
StylePreset    风格参数包（雪崩级，全片单例，可分集覆盖）
NormalizedScene  归一化场次
SceneDirection   场导演方案
Transition       场间转场（独立对象，挂在两场之间）
MasterAsset / AssetVariant   资产图谱
ShotContract     镜头契约
ContinuityLink   镜间依赖（cut/match_cut/frame_chain/extension/ref_video）
Render           产物（keyframe / clip），以 renderKey 索引
```

统一状态两轴(与 A 同构):

```
status:    draft | accepted | locked | archived
freshness: clean | opportunity | broken
Render 另有 pinned: 人工锁定,重生成时不动
```

---

## 3. B0 — Ingest

### 3.1 小说输入的四类显式决策

小说不是"格式不同的剧本",四样东西在视听上不成立,每样必须留痕决策:

| 问题 | 四选一 |
|---|---|
| 内心独白 | 外化为行为/道具/环境 · 转 VO · 转对白 · 删 |
| 概述段落 | 蒙太奇 · 单镜象征 · 展开成场景 · 删 |
| 叙述视角 | 限知跟随 · 全知 · 主观镜头段 |
| 信息密度错配 | 重新分配时长预算 |

### 3.2 Flatness Detector

每场算四分,任一低于阈值标记 `flat`,并给出改编工单:

```
informationGain · visualizability · emotionDelta · conflictPressure
        ↓
改编候选:加动作线 / 换空间 / 加环境压力 / 压成蒙太奇 / 合并入邻场 / 删
```

**平段不是缺陷,是工单。** 它决定 B1 的改编工作量。

输入若来自 A,`informationPayload`/`tensionType`/`knowledgeDelta` 直接继承,B0 近乎空转。

---

## 4. B1 — Treatment(改编发生在这里)

### 4.1 StylePreset 三档(初始值,按项目回调)

| 参数 | 电影感 | 剧集 | 短剧/竖屏 |
|---|---|---|---|
| ASL 平均镜头时长 | 5–8s | 3–5s | 1.5–2.5s |
| 每场镜头数 | 8–15 | 6–10 | 4–8 |
| 空镜比例 | 15–20% | 5–10% | 0–3% |
| 景别分布 | 全/中为主,特写稀有 | 正反打为主 | 中近/特写为主 |
| 运镜幅度 | 克制,慢推/固定 | 中等 | 大幅、频繁、手持感 |
| 信息密度 | 每 15–30s | 每 8–15s | **每 3–5s** |
| 钩子 | 幕末 | 集末 | **首 3s + 每 30s + 集末断章** |
| 画幅 | 2.39:1 / 16:9 | 16:9 | 9:16 |

另含:色彩/光比/质感、参考片、音乐节拍密度、转场类型池、promptPrefix、negativePrompt。

同一场戏在三档下镜头数可差 3 倍,所以**必须在任何昂贵工作前锁定**。

### 4.2 全片曲线

情绪曲线(每场进出情绪值)、节奏曲线(每场目标时长与镜头密度)、张力配比(suspense/surprise/mystery,来自 A)。节奏曲线必须先于分镜存在,否则全片会摊平。

### 4.3 Transition 是独立对象

```ts
Transition {
  fromScene, toScene
  type: cut | match_cut | graphic_match | motion_match
      | sound_bridge | color_shift | camera_continuation
  requirement: { fromShotSpec, toShotSpec }   // 反向约束两侧首末镜
}
```

它需要成对设计,不能挂在任一场上。`requirement` 会在 B4 成为硬约束——这是"场景间视觉设计"能落地的唯一方式。

---

## 5. B2 — 资产图谱

```
MasterAsset(角色基准 / 场景 plate / 道具基准)
  └─ Variant: wardrobe · state · accessory · aging
```

### 5.1 哪些变体要独立出图

```
必须独立资产图:观众用来认人认物的(脸、发型、标志性服装、伏笔道具)、
              会被特写的、跨多场复用的
prompt 层即可:只影响氛围的(光线、天气、湿度、轻微脏污)、
              单次出现且非特写的
```

### 5.2 伏笔资产的双向约束

```
埋设:必须入画且可见,但不得给特写 → 约束 B4 景别不小于中近
回收:必须与埋设时可辨识为同一物   → 约束 B5 复用同一 variant,禁止重生成
```

带 `foreshadowRole: setup|payoff`,连到 A 的 Setup-Payoff 账本。

### 5.3 状态时间轴(自动推导,不靠人记)

```ts
AssetState { assetId, variantId, validFrom: sceneId, validUntil: sceneId|null }
```

第 12 场受伤 → 之后所有场自动解析到受伤变体。上百个变体状态人工维护必错,且这类错误观众一眼可见。

### 5.4 每场清单

```ts
SceneAssetManifest { resolved[], missing[], risky[] }
```

`missing` 驱动资产生成队列;`risky`(同框过多、相似角色易混)回流 producibility 警告。

---

## 6. B3 — 场景导演方案

```ts
SceneDirection {
  dramaticFunction, informationPayload[]
  tensionType            // suspense | surprise | mystery
  emotion { entry, turn, exit }
  coverage               // 主镜头、总镜头数、空镜用不用/用在哪
  blocking               // 走位与空间关系 → 决定轴线组
  lighting { keyDirection, ratio, motivation }
  palette, sound { ambience, musicIn/Out, silence }
  transitionIn/Out       // 引用 Transition
  targetDuration         // 来自节奏曲线
}
```

### tensionType → 镜头策略(A 传结构化数据的最大回报)

```
suspense  观众知道、角色不知道 → 必须有观众独知的插入镜头;角色特写拉长;空镜比例上调
mystery   角色知道、观众不知道 → 构图遮挡、不给正脸、切得早;禁止给关键信息清晰画面
surprise  双方都不知道         → 前置镜头刻意平淡,反转点用切换节奏制造冲击
```

### 空镜决策

```
情绪转折后需呼吸 → 给｜时空转换 → 建立镜｜suspense 需观众独知 → 插入镜
短剧档 → 基本不给(不承载信息 = 浪费时长)
```

---

## 7. B4 — 分镜:连续性求解

```ts
ShotContract {
  informationPayload[]
  shotSize, angle, lens
  movement { type, speed, startFraming, endFraming }
  duration
  subjects[], assetVariants[]
  lighting { keyDirection, ratio, motivation }
  continuity { axisGroup, eyeline, screenPosition, matchCut?, linkToPrev }
  producibilityRisk { subjectCount, hasHands, hasText, fastMotion, score }
}
```

### 7.1 硬约束用代码校验(不让模型记)

```
轴线一致性(同 axisGroup 不得越轴,除非显式越轴镜)
视线方向匹配 · 光源方向同场不跳变
景别节奏(连续 3 个同景别 → jump cut 警告)
屏幕位置连续性 · 时长合计 vs targetDuration
镜头数 vs StylePreset 区间
```

LLM 负责创意,validator 负责纪律。

### 7.2 能算的不让模型出

| 模型出(创意) | 代码算 |
|---|---|
| 景别、机位、运镜、动作行、是否空镜 | 单镜时长(ASL × 情绪权重)、镜头总数、axisGroup、screenPosition、eyeline、光位光比(继承 B3)、assetVariants(解析 manifest)、producibilityRisk |

输出 token 砍掉约 2/3,格式错误率大幅下降。

两段式:先出"镜头骨架"(景别 + 一句动作 + 是否空镜)供人快速过,再批量补全。

---

## 8. B5 — 渲染与衔接

### 8.1 Prompt 是编译产物,零 token

```
[StylePreset.promptPrefix]
+ [景别·机位·镜头]            枚举映射
+ [主体: freezeString]        ★ 原样注入,禁止任何改写
+ [变体 deltaString]
+ [动作: shot.actionLine]     唯一自然语言槽,B4 已生成
+ [环境: location.plate]
+ [光线: keyDirection · ratio]
+ [negativePrompt]
```

**绝不用 LLM 编译 prompt**:800 shot × 每次重渲 = 调用量最大的一环;同输入不同输出会让幂等键失效;freezeString 被改写会直接毁掉角色一致性。

换生图/生视频模型 = 换一份 `RendererProfile`(前缀词、负面词、枚举映射),分镜数据一行不动。

### 8.2 ContinuityLink:镜间生成依赖

```ts
type ContinuityLinkType =
  | 'cut'          // 无依赖,可并行
  | 'match_cut'    // 构图需对齐,两边一起设计
  | 'frame_chain'  // 前镜末帧 = 后镜首帧,强依赖
  | 'extension'    // 同一连续动作拆两段,用视频延长
  | 'ref_video'    // 以前镜成片作参考视频
```

后三种是**有向强依赖**:前段重生成,后段必须跟着重生成。这就是"某个分镜有问题,前面也要重生"的机械解释——可以算,不是玄学。

**风险预判在生成前跑**:跨镜大幅运动、走位越框、手部精细动作、说话口型、多人同框、快速运动 → 高风险镜自动建议改用 frame_chain / extension,或回退到更保守的镜头设计。

### 8.3 便宜代理物先行

```
资产层  低分辨率小批量确认风格 → 再出全套
分镜层  先出关键帧静图确认    → 再出视频(贵 10~100×)
视频层  先出短片段/低分辨率    → 再出成片
```

### 8.4 三级门禁漏斗

```
一级 纯程序(近乎免费):画幅/构图规则、人脸数量、
     角色相似度(embedding 距离 vs MasterAsset) → 淘汰大部分
二级 专用小模型:手/脸/文字崩坏检测
三级 小 VLM,是非题:"画面中是否出现 X?" → 只校验 informationPayload
```

通过后人做 **10 留 3**。

---

## 9. B6 — Assembly

剪辑、音乐进出点、音效、字幕。实际 ASL vs 目标 ASL 校验、钩子间隔校验、总时长校验。不达标回流到 B4(改镜头数/时长)或 B1(改节奏曲线)。

---

## 10. 贯穿机制一:依赖图与失效传播

```
StylePreset ─────→ 全部 SceneDirection ──→ 全部 ShotContract
MasterAsset ──→ Variant ──→ Render
SceneDirection ──→ ShotContract ──→ Prompt ──→ Render
ShotContract ──ContinuityLink(强)──→ ShotContract
Transition ──→ 两侧首末镜
```

| 变更 | 影响 | 成本 |
|---|---|---|
| Prompt 表达层 | 只重渲染,设计不动 | 低 |
| AssetVariant | 引用它的 Render broken | 中 |
| ShotContract | 本 shot + chain 下游 broken | 中 |
| SceneDirection | 本场全部 shot broken;邻场 transition opportunity | 高 |
| **MasterAsset(identity)** | 全片引用处 broken | **雪崩** |
| **StylePreset(identity)** | 全片 shot 设计 broken | **雪崩** |

**identity vs 非 identity 的区分能救大量返工**:

```
MasterAsset  identity = 脸/发型/体型/标志性服装 → 真的全片重来
             非identity = 追加参考图/措辞优化   → 只影响未生成的,pinned 不动
StylePreset  identity = ASL/镜头数区间/画幅
             非identity = promptPrefix 微调
```

`pinned + upstream broken` → 弹人类仲裁,系统绝不自动覆盖(与 A 的 `locked + broken` 同构)。

---

## 11. 贯穿机制二:幂等与缓存

```
renderKey = hash(
  shotContract, assetVariantVersions, stylePresetVersion,
  rendererProfile, promptCompilerVersion, seed
)
```

- **seed 绑定到 MasterAsset 并进 key**。随机 seed = 每次重生成换脸。
- **promptCompilerVersion 必进 key**。否则改过模板后会出现"同一场两种风格"。
- **runner 身份不进 key**(见 §12)。
- 命中即复用,不调用任何模型或生成服务。

---

## 12. 贯穿机制三:执行层抽象 —— Agent Runner

### 12.1 三条使用边界

```
① Build-time  写代码/改模板/调参     → codex,产物进 git 经 review
② Run-time 推理  SceneDirection/ShotList → 绝不走 agent CLI,SDK 直调
③ Run-time 执行  调生图生视频、失败自愈  → pi-agent,关在幂等壳里
```

②必须单独强调:用 agent CLI 做推理会一次性废掉 caching 分层、structured output、可复现性,**实际 token 通常是直调的 5~20 倍**,而质量并不更好——生成 shot list 是纯结构化转换,不需要自主工具调用。

### 12.2 Runner 注册表(可插拔)

```ts
type RunnerProfile = {
  id: string                       // 'codex' | 'pi-agent' | 未来任意
  kind: 'coding' | 'general_tool'
  adapterVersion: string
  capabilities: {
    customTools: boolean           // 能否挂自定义 CLI
    maxTurns: boolean              // 原生轮次上限
    budgetLimit: boolean
    structuredReport: boolean      // 能否稳定回传 JSON
    sandbox: 'none'|'dir'|'container'
    usageReport: boolean
    concurrencySafe: boolean
  }
  limits: { maxConcurrency, defaultTimeout, costPerRunEstimate }
  invoke: { cmd, argsTemplate, env, cwdStrategy }
}
```

**能力缺口由适配器补齐**:不支持 maxTurns → 外层 timeout + 进程守护;不支持 usage → 按"调用次数 × 经验值"估算并定期对账;sandbox 不足 → 外层用只读挂载 + 临时目录。**能力声明 + 优雅降级**,而不是要求所有 runner 一致。

### 12.3 统一 TaskSpec / RunResult(runner 无关)

```ts
type TaskSpec = {
  taskId, renderKey?
  role: 'builder' | 'operator' | 'curator'
  objective: string                // 自包含,不让 agent 去项目里找上下文
  inputs: {}                       // 结构化,路径绝对化
  tools: ToolRef[]                 // CLI 白名单
  workdir: string                  // 限定可写目录
  acceptance: AcceptanceSpec       // 机器可判的验收标准
  limits: { maxTurns, timeout, budget }
  reportSchema: JSONSchema
}

type RunResult = {
  status: 'ok'|'failed'|'timeout'|'budget_exceeded'|'rejected'
  artifacts: ArtifactRef[]
  report: { actions[], actualPrompt?, failureClass?, notes? }
  usage:  { tokens?, cost?, wallTime, turns }
  runner: { id, version, invocation }     // provenance
}
```

适配器的全部职责:**TaskSpec → 该 CLI 的调用形式**,以及 **该 CLI 的输出 → 归一化 RunResult**。新接一个 agent CLI 只写一个适配器。

### 12.4 幂等壳

```python
def execute(task, runner=None):
    if task.render_key and cache.has(task.render_key):
        return cache.get(task.render_key)          # runner 根本不启动

    runner = runner or routing.resolve(task.role, task.stage)
    r = registry[runner].run(task)                 # 三上限由适配器保证

    if r.report.actual_prompt and r.report.actual_prompt != task.inputs.prompt:
        actual_key = hash(r.report.actual_prompt)  # ★ 自愈改了输入
        cache.put(actual_key, r)
        cache.redirect(task.render_key, actual_key, self_healed=True)
        curator_queue.push(diff(task.inputs.prompt, r.report.actual_prompt))
    else:
        cache.put(task.render_key, r)

    audit.log(task, r)                             # 含 runner provenance
    return r
```

**自愈改 prompt 是最阴的坑**:agent 改了几个词才成功,产物却存在原 key 下,你以为拿到的是原 prompt 的结果。上面的 `actualPrompt` 重定向解决它,并且 `curator_queue` 会自动变成**模板缺陷采集器**——哪些词经常被改掉一目了然,直接反哺模板。

### 12.5 路由与手动切换

```yaml
# routing.yaml
roles:
  builder:  codex
  operator: pi-agent
  curator:  codex
overrides:
  - match: { stage: B5, task: video_render }
    runner: pi-agent
  - match: { stage: B2, task: asset_gen }
    runner: pi-agent
fallback:
  enabled: false        # 默认关。手动控制优先,避免账单不可预期
```

三级覆盖,优先级由高到低:

```
单次运行的 --runner / UI 下拉      ← 手动切,最高优先
routing.yaml 的 overrides
roles 默认映射
```

每次选择写进 Operation Log,便于事后按 runner 统计成功率/成本/耗时/自愈率。

### 12.6 **runner 身份不进 renderKey**(重要决定)

产物取决于生图 CLI + prompt + seed,**不取决于谁包装了这次调用**。若把 runner 写进 key,从 codex 切到 pi-agent 会让整个缓存失效——这会让"手动切"变成一个极其昂贵的动作,直接违背你的需求。

runner 只记在 provenance 里。两个 runner 的行为差异(自愈方式不同)已经被 `actualPrompt → actualKey` 这条机制捕获了,不需要再进 key。

### 12.7 接入新 runner 的验收套件

这是"未来还有其他 agent CLI"的真正答案——**需要的是验收台,不只是接口**。固定 12 个任务,新 runner 必须全过才允许进 routing:

```
正常成功 ×2        超时中断是否生效 ×1
需要自愈才成功 ×2   预算超限是否中止 ×1
应当拒绝的任务 ×1   maxTurns 是否生效 ×1
CLI 报错归一化 ×2   越界写文件是否被挡 ×1
并发 8 路是否稳定 ×1
```

外加 A/B 对账:同一批真实任务分流给两个 runner,比成功率、单位成本、自愈率。这是判断"新工具值不值得换"的唯一可靠方式。

---

## 13. 模型使用总表

| 环节 | 用什么 | 调用量 |
|---|---|---|
| 幂等键/依赖传播/失效标记 | 纯代码 | — |
| 轴线·光位·景别节奏校验 | 纯代码 | — |
| 镜头数/时长分配/变体解析 | 纯代码 | — |
| **Prompt 编译** | **纯代码(模板拼装)** | — |
| 调度/重试/成本记账 | 纯代码 | — |
| 平段检测 | 小模型,单次 | 每场 1 |
| 资产抽取 | 大模型,单次 | 每场 1 |
| SceneDirection | 大模型,单次 | 每场 1 |
| Shot List | 大模型,**场级批处理** | 每场 1(出 6~15 镜) |
| 改编方案候选 | 大模型 | 全项目几十次 |
| 图像门禁 | CV → 小模型 → 小 VLM | 三级漏斗 |
| 生图/生视频执行 | **pi-agent(幂等壳)** | 按 cache miss |
| 代码/模板/schema 维护 | **codex** | build-time |

### Context 分层(吃 prompt caching)

```
稳定(全片不变)  系统指令 + 镜头语法规则 + 输出 schema + StylePreset 全文 + Canon 摘要
半稳定          节奏曲线片段 · 主要角色 freezeString
易变(几百 token) 本场 SceneDirection · 资产切片 · 前后镜 · 本次指令
```

顺序排错就完全吃不到缓存。**B 不需要向量库**——关联全是确定的,manifest 已算好。

---

## 14. 成本控制

```
成本结构(20 集短剧 ≈ 100 场 / 800 shot)
  LLM   约 200 次调用,含返工 1~1.5M output token   → 总成本 <5%
  图像  约 3000 张                                  → 中
  视频  约 2000 段                                  → 主成本
```

配套四件:

- **dry-run 预估**:任何批量生成前显示"将生成 N 张 / M 秒,预估 ¥X,预计 Y 分钟"。
- **失败分类后再重试**:
  | 类型 | 动作 | 能否自动 |
  |---|---|---|
  | 抽卡失败 | 换 seed,上限 3 | ✅ |
  | prompt 表达问题 | 调权重/负面词,上限 2 | ⚠️ 规则表 |
  | 设计不可生成 | 回 B4 改设计 | ❌ 要人 |
  | 资产问题 | 回 B2 补资产 | ❌ 要人 |
- **三个硬闸**:单 shot 重试上限、整场连续失败熔断、项目级预算硬上限。
- **全量落盘**:每次调用的 task/actions/actualPrompt/产物路径/seed/耗时/成本。

**执行层先 subprocess 后 agent**:纯 subprocess 跑两周,把失败模式全量记录 → 能规则化的进规则表(零 token、可复现)→ 长尾才交给 pi-agent 兜底。通常 80% 的失败集中在三五种形态。

---

## 15. 自动化边界

| 可全自动 | 先人后机 | 永远留人 |
|---|---|---|
| Prompt 编译、渲染调度、幂等缓存 | 平段改编策略 | **StylePreset 定稿** |
| 连续性硬校验、变体状态推导 | 空镜决策、转场设计 | **MasterAsset 定稿** |
| 门禁一二级初筛 | 分镜初稿、高风险镜策略 | 关键场导演方案 |
| 失败分类与规则化重试 | 10留3 初筛 | 关键帧终选、伏笔镜头、成片验收 |

两条雪崩级定稿永远不自动化——错误代价是整部片重来,而人判断只需几分钟。

---

## 16. A→B 接口

```ts
SceneExport {
  sceneId, revision
  contractHash, bodyHash, canonHash      // 三级失效判定
  contract, body{action,dialogue,beats[informationPayload]}
  canonSlice{characters[freezeString,refImages,stateAt], location, props}
  narrativeContext{entryState,exitState,reveals,knowledgeDelta,setups,payoffs}
  directives{tone,pacing,targetDuration,hookRequirement}
  tensionType, visualMotifs
}
```

三级失效:

```
contractHash 变 → shot BROKEN(设计重做)
bodyHash 变     → shot OPPORTUNITY(重渲/改字幕/对口型,机位不动)
canonHash 变    → RESTAGE(只重渲染,设计不动)
```

反向 `ProducibilityReport` 进 A 的 opportunity/broken 队列,人仲裁。A 只保留轻量 `producibilityHints`,**判定权全在 B**。

同一人闭环使用 → 两套系统共享工作台与 entityId,不需要交付物式的冻结签收。

---

## 17. 落地顺序

```
第 1 步  B2+B4+B5 最小闭环:手填一份 SceneDirection → 资产图 → 分镜表 → 关键帧
         验收:一致性与三级门禁能跑通
第 2 步  B1 风格包 + 节奏曲线,验证三档风格是否真能拉开差异
第 3 步  Runner 抽象 + 幂等壳(此时接 pi-agent),先 subprocess 打底
第 4 步  依赖图 + renderKey 缓存 —— 重生成变便宜,这时才敢大规模迭代
第 5 步  B0 小说归一化 + 平段检测
第 6 步  B5 视频层 ContinuityLink 与衔接策略
第 7 步  接 A
```

第 4 步之前都用文件夹 + 脚本,不建平台。**但三个 hash + freshness 字段要从第 1 步就埋进 JSON**,否则第 4 步推倒重来。

---

## 18. 坑点速查

```
1  用 agent CLI 做推理层        → token 翻 5~20 倍,缓存全废
2  用 LLM 编译 prompt           → 调用量最大、不可复现、freezeString 被改
3  逐 shot 调模型               → 改场级批处理,调用数 800→100
4  让模型输出能算的字段          → 只让它出创意字段,省 2/3 输出
5  context 未按稳定性排序        → 吃不到 prompt caching
6  门禁全上 VLM                 → 三级漏斗
7  重试无分类无上限              → 夜里烧钱,且 3/4 的失败重试无效
8  MasterAsset 变更不分 identity → 用户不敢碰资产
9  seed 随机 / compilerVersion 不进 key → 换脸、风格混杂
10 agent 自愈静默改 prompt       → 缓存内容与 key 不符
11 runner 进 renderKey          → 切 runner 等于清空缓存
12 无 dry-run 成本预估           → B 独有,必须有
13 中间产物不落盘                → 半个月后无法回答"脸为什么变了"
```

---

## 需要你拍板的两件小事

1. **pi-agent 是否支持自定义工具白名单与工作目录限制?** 支持的话 Operator 的沙箱直接用它原生能力;不支持就得在适配器里加只读挂载 + 临时目录,工作量差一天左右。
2. **视频层一步到位还是先只做关键帧?** 先做关键帧(漫剧形态)能把闭环缩短一半,ContinuityLink 里的 frame_chain/extension 可以整体推后——这是我倾向的路径。

接下来可以直接产出的,按对你最急的顺序:**Runner 适配器接口 + TaskSpec 完整规格**(接 pi-agent 当天能用)、**Prompt Compiler 模板 + 三档 RendererProfile**、或 **ShotContract/SceneDirection 的完整 JSON Schema**。