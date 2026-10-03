---
name: shortdrama-director
description: 把小说或网文改编成可以直接拿去生成的AI短剧：系列设定、人物场景道具表、分集大纲、短剧剧本、分镜，以及给 Seedance 2.0（即梦 / Dreamina）用的视频提示词、参考图清单和提交命令。也用于修改已有一集、检查节奏、转换旧版 shortdrama-director（1.2.x）项目。Use this skill whenever the user wants to adapt a novel, web novel or story into a short drama or AI video series (横屏剧集、竖屏短剧、推文), write or revise a short-drama script or storyboard (剧本、分镜), plan Seedance / 即梦 / Dreamina video generation or reference images, fix slow pacing or bloated prompts, or continue an existing shortdrama-director project — even if they do not name the skill.
---

# shortdrama-director 2

把原文变成一部能直接生成视频的短剧。你写少量、人能读懂的文件；工具推导其余一切：连续性、时长、生成请求的分组、参考图编号和提示词。

**为什么这样分工：** 旧做法让模型手写几十万字的 JSON（每镜几十个状态值、逐行删改记录），结果大量填充文字、节奏变慢、提示词里混进内部代码。现在你只做判断——讲什么、怎么拍——计数、对齐和格式交给代码。

## 你写的文件

| 文件 | 内容 | 写法 |
|---|---|---|
| `series.md` | 片名、格式（横屏剧集 / 竖屏短剧 / 推文）、模型、画风、人脸方案 | 只写一次 |
| `bible.md` | 人物、群演、场景、道具，以及看得见的外观和造型 | [references/assets.md](references/assets.md) |
| `outline.md` | 每集：原文范围、一句话目标、钩子、推进、爽点、卡点 | [references/outline.md](references/outline.md) |
| `episodes/EP01/script.md` | 剧本：场次、画面、台词、心声、【状态】变化 | [references/script.md](references/script.md) |
| `episodes/EP01/shots.md` | 分镜：每镜一行 | [references/directing.md](references/directing.md) |
| `episodes/EP01/notes.md` | 你的取舍理由和冷读意见（可选） | [references/review.md](references/review.md) |

`derived/` 里的东西全部由工具生成，不要手改：分镜表、提示词、提交清单、检查报告、参考图清单。

## 命令

工具是 `scripts/sf.py`（Python 3.10 以上，只用标准库，Windows 可用）。下面的 `<skill>` 指本 Skill 所在目录。

```bash
python <skill>/scripts/sf.py init <项目目录> --title 片名 --format 横屏剧集   # 新建项目和模板
python <skill>/scripts/sf.py check <项目目录> [EP01]   # 检查；自动补行号；只写报告
python <skill>/scripts/sf.py plan <项目目录> [EP01]    # 生成请求、提示词、分镜表、报告
python <skill>/scripts/sf.py assets <项目目录>          # 参考图清单和出图提示词
python <skill>/scripts/sf.py show <项目目录> EP01 [--unit U01-1]   # 看分镜表或某个请求
python <skill>/scripts/sf.py import-legacy <board.json> <项目目录>   # 转换旧版项目
python <skill>/scripts/sf.py doctor <项目目录>          # 格式、模型能力、版本
```

`check` 和 `plan` 永远不拒绝保存：它们列出错误和警告，你改源文件后再运行一次。

## 流程：从原文到第一集

1. **建项目。** 运行 `init`。最多问用户 2–3 件你推断不了的事：发布格式（默认横屏剧集，16:9，每集 3–5 分钟）、画风和是否用写实人脸、每集时长若不同于默认。其余自己判断，写进 `series.md`，以后不再问。
2. **读原文，写 bible.md 和 outline.md。** 先读完要用的一批章节，再定每集讲什么（[references/outline.md](references/outline.md)）。把大纲给用户看，这是最值得用户花时间的一步；用户说直接做完，就记下取舍理由继续。
3. **写剧本。** 按 [references/script.md](references/script.md)：口语短句，画面只写看得见的，会延续的变化写【状态】。
4. **写分镜。** 按 [references/directing.md](references/directing.md)：每镜一行，标出钩子、冲突、反转、爽点、卡点。
5. **运行 `plan`。** 读屏幕上的摘要：时长、平均镜长、请求数、错误和警告。改 script.md、shots.md 或 bible.md，再运行，直到没有错误、警告都已处理或有意保留。
6. **运行 `assets`。** 得到参考图清单。第一次做一个项目时，先按 [references/seedance.md](references/seedance.md) 做冒烟测试，再批量出图。
7. **冷读第一集**（[references/review.md](references/review.md)），再交付。

交给用户的东西：`derived/EP01/storyboard.md`（分镜表）、`derived/EP01/prompts/`（每个请求的提示词）、`derived/EP01/requests.json`（提交清单和命令）、`derived/assets.md`（参考图清单），加上你对检查报告里剩余警告的说明。

## 修改已有的一集

只改受影响的那一场：在 script.md 和 shots.md 里改台词、加镜头、删镜头，然后运行 `plan`。请求编号按场次排（U03-1 是第 3 场的第 1 个请求），其他场的请求和提示词不会变。新加的台词行会自动拿到新行号；已有行号不要改。

## 旧版项目

用 `import-legacy` 把 1.2.x 的 board.json 转成新格式，再 `plan`。转换会保留画面、台词、镜头和状态变化，丢掉逐行删改记录、完整状态快照和审查记录。转换后要检查什么，见 [references/legacy.md](references/legacy.md)。

## 判断要点

- **先有大纲，再写剧本。** 一集一句话：谁要做成什么，什么挡着他，做不成会失去什么。
- **节奏靠切点。** 信息成立、局面翻转、反应出来就切；反应镜 1–2 秒就够。台词按每秒约 5 个字估。
- **画面只写镜头里看得见的。** 理由写进 notes.md，规则和禁令不要写进画面。
- **【状态】只写会延续的变化：** 道具易手、换装、受伤、开合。站位和表情写在画面里。
- **无名的一群人合成一个群演**，写人数和统一造型；不重要的小东西不要登记成道具。
- **不要回避爽点。** 打斗拆成几个决定性瞬间、用切点和反应表现冲击、不拍血，而不是写成「省略交锋」。
- **检查是给你的提示。** 报告里的警告指向观众会困惑或划走的地方；处理掉，或者在交付说明里讲清为什么保留。

## 参考文件

| 什么时候读 | 文件 |
|---|---|
| 选材、分集、写大纲 | [references/outline.md](references/outline.md) |
| 写或改剧本 | [references/script.md](references/script.md) |
| 写或改分镜 | [references/directing.md](references/directing.md) |
| 写人物表、出参考图、人脸政策 | [references/assets.md](references/assets.md) |
| 提交生成、冒烟测试、修视频 | [references/seedance.md](references/seedance.md) |
| 冷读评审、什么时候问用户 | [references/review.md](references/review.md) |
| 转换旧版项目 | [references/legacy.md](references/legacy.md) |
| 看一个完整的小样例 | `examples/sample/`（含生成好的 derived/） |
