# SceneExport v3 与 B 制作协议

交换格式仍为 `SceneExport-v1`，版本字段为 `schemaVersion: 3`。v1/v2 保持兼容；任何缺少完整连续性的来源都先进入补全与拍摄版候选阶段。

## A 文件边界

| 字段 | 含义 |
| --- | --- |
| `source` | `route` 为 original/novel；小说含 sourceId、规范化文本 SHA-256、文件名、章节单元、readRanges、adoptedDraftId |
| `scenes` | 原有交接场次、正文、契约、canonSlice、narrativeContext、来源修订及哈希；每个正文块有稳定 ID |
| `storyDocument` | 采用剧本正文、事件、初始状态和播放计划；旧原创缺少物理状态时明确 needs_completion |
| `continuityStatus` | 连续性是否需要补全；不能把缺失资料推断成不存在 |
| `versionFingerprint` | 正文、事件、来源等实际交接内容的版本指纹 |

小说 SHA-256 基于换行规范化为 LF 后的 UTF-8 文本，不是原上传 TXT 的二进制文件哈希。字符区间采用 Python 字符索引 `[start, end)`。章节单元保留原章编号和分段位置。`readRanges.status=loaded_for_adaptation` 表示已载入当前选段；取消或请求未完成不会把它升级为模型已读。`demo_loaded` 表示离线演示。`delivered_not_semantically_verified` 表示真实改编请求已完成；语义复核结果另记 `reviewPassed`，不能据此声称成片验证已完成。

## 剧本文档

`scenes[].blocks[]` 保存 `id/type/text`。对白另含 `speakerId` 与 `mode`，发声方式为 speech、inner、narration、system。兼容字段 `character` 保存同一人物引用。`dialogueLines` 由代码从正文推导，不接受第二份独立台词成为制作依据。

`continuity.entities` 以稳定实体 ID 为键；实体包含 `kind/name/identity/visualStateKeys`。身份包含实际视觉设定，不只以名称判断同一角色或道具。

`initialState` 以同一组实体 ID 为键。`pos` 使用 `{rel, target}`；rel 可为 at、inside、on、held_by、worn_by、attached_to。未知位置使用 `{unknown: true}`；不在场可用 null 并结合明确的 active 状态。隐藏用 `visibleTo`；未知内容用 `contentsKnown: false`；已知空容器用 `contentsKnown: true` 且无内部实体。销毁或消耗需同时设置 `active: false` 和空位置。

`events[]` 为故事发生顺序，每项含 `id/sceneId/locationId/participants/action/changes/dialogueIds`，并含来源 `sourceRefs` 或 `origin: adapted`。每个变化为 `{entityId, field, from, to}`。前值必须匹配上一事件计算结果；有要求时使用 `requires` 明示前提。

`presentationPlan[]` 是播放顺序，每项含 `id/eventId/kind/phase/dialogueIds`。kind 为 main、preview、flashback、time_jump；非 main 需 reason。phase 为 before 或 after。预演不会覆盖正篇事件状态，全部正篇事件和实际交付台词必须有覆盖。

## B 拍摄版与采用

`shooting_script` 保存 `source/sourceHash/baseShootingId/mode/payload/attempts/issues/passed/status`。mode 为 cinema、series、fast_drama；画幅保存在独立风格对象中。

`payload.sourceMapping[]` 为 `{sourceId,targetIds,reason}`，每个 A 原文块恰有一项去向。删句使用空 targetIds；合并允许不同源块映射到同一目标块。目标正文也必须有来源依据。`storyChanges` 非空时先确认故事新版本，不能直接进入制作。

采用动作核对当前来源哈希和候选基准，重新计算场次的局部事件、相关实体、状态与播放顺序。只有实际变化的场次和依赖结果失效；版本历史保留。

## 分镜、引用与媒体

新版镜头包含 `eventId/presentationId/dialogueIds`。导演候选提交时检查播放顺序与完整覆盖，台词文本从采用拍摄版推导。

`variant` 保存身份版本、状态 claims、容纳物 embedded、实际 referenceFileId 和 visualReview。引用职责为 identity、environment、start_state、end_state、detail。visualReview 记录实际字节哈希、身份哈希、状态哈希、职责、method 和人工观察 evidence。声明通过不替代看图。

`generation_task` 保存多个镜头的顺序、时长、实际引用、编译提示词、外部承接和 inputHash。费用预览返回 planHash；执行必须使用最新 planHash。结果视频返回后为 awaiting_segmentation，再标定各镜区间；区间不得倒序、重叠或超出真实媒体长度。

`render.adoption` 保存 fileId、fileHash、interval、actualDuration、endFrameTime、observedEndState、observation。强承接比较实际采用末态与下镜起态，不能以目标末态冒充观察值。用户明确确认“观察与目标一致”时才保存相应观察记录；未知值不会默认为正确。

## 主要接口

| 应用 | 接口 | 用途 |
| --- | --- | --- |
| A | `POST /api/novels` | 保存 TXT 解码文本或粘贴正文 |
| A | `POST /api/projects/{p}/novel/propose` | 指定阅读或局部修订范围，异步生成并复核 |
| A | `POST /api/projects/{p}/novel/drafts/{id}/adopt` | 采用剧本 |
| A | `GET /api/projects/{p}/export/scene-export` | 导出 schema 3 |
| B | `POST /api/projects/{p}/import-scene-export` | 保存新来源版本 |
| B | `POST /api/projects/{p}/shooting/propose` | 生成指定形态的拍摄版 |
| B | `POST /api/projects/{p}/shooting/{id}/adopt` | 采用制作版本 |
| A/B | `POST /api/projects/{p}/advance` | 自动运行到下一项必要选择；保留 single 兼容 |
| A/B | `POST /api/jobs/{id}/resume` | 恢复允许的文字任务，保持请求去重 |
| B | `POST /api/projects/{p}/assets/dry-run` | 素材补图费用与依据预览 |
| B | `POST /api/projects/{p}/assets/generate` | 确认费用后生成候选图片 |
| B | `POST /api/projects/{p}/assets/{variantId}/review-reference` | 记录实际参考图及视觉核对 |
| B | `POST /api/projects/{p}/generation-tasks` | 编译一个或多个镜头组成的单元 |
| B | `POST /api/projects/{p}/generation-tasks/dry-run` | 本批次费用预览 |
| B | `POST /api/projects/{p}/generation-tasks/execute` | 经确认生成视频单元 |
| B | `POST /api/projects/{p}/generation-tasks/{id}/import` | 关联实际文件和各镜采用建议区间 |
| B | `GET /api/projects/{p}/renders/{id}/adoption-preview` | 真实时长及待核对末态 |
| B | `POST /api/projects/{p}/renders/{id}/review` | 记录实际区间、观察依据与终选 |

实际配置项和剩余接口以各应用自己的 `/openapi.json`、设置页及配置文档为准；无需同时启动两个服务。
