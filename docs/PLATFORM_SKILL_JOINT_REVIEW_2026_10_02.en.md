# StoryForge Studio × shortdrama-director — Joint Review and Redesign

*2026-10-02 · Branch `claude/youthful-shannon-ph0i3s` · Skill package `shortdrama-director`, runner 1.2.6, method `r3-expression-r2+local-workflow-r2`, 114 files*

This is the companion to [the platform pipeline review](PRODUCTION_PIPELINE_REVIEW_2026_10_02.en.md), called "the platform review" below. Its defect numbers (D1–D14) and stage names are reused here.

**Basis.**
- **Every file in the Skill package.**
  - All text files were read in full.
  - The four largest boards (175–320 KB on disk) and the mid-size boards were processed in full by a script and read selectively. The script covered every shot, state key and dialogue line.
  - `runtime-1.2.4.zip` is a complete copy of an older runtime. I diffed it against the current scripts rather than re-reading it.
- **The Skill's test suite.** 488 tests ran with `PYTHONUTF8=1`; all passed except one, which was skipped.
- **Your real project data inside the Skill's fixtures:**
  - boards and prompts from 仙界 (EP01, EP03), 出狱后的我 (EP03, EP04) and 死后被契约 (EP01);
  - an EP02 from a 1.2.1 run whose novel the fixture does not name;
  - a projection of a fourth project, named `guiyi` in the fixtures (a supernatural story with a mirror, judging by its props).
- **The platform** at the current branch head.
- **Not done.** I rendered prompts with the Skill's current renderer to check its behavior, but generated no images or videos.

**Evidence labels.**
- `file:line` is platform code.
- `skill:path:line` is the Skill package.
- **[measured]** is computed from your real fixtures with `tools/skill_board_metrics.py` (added with this review).
- **[src]** is an external source; they are listed in the platform review.
- **[assume]** is my assumption.

---

## 0. Verdict

**The Skill contains the best craft knowledge in your toolchain, inside a machine that cannot produce video.** Its adaptation and commercial-structure methods, its readable script format and the direction of its prompt renderer are worth keeping. Most of the rest should not survive as it is. Five findings carry the verdict:

1. **It has never touched the renderer.**
   - 0 images and 0 videos have been produced.
   - The evals are `not_run`.
   - Every exported PLAN says `media_status: not_materialized` (`skill:evals/results.json`, `skill:VALIDATION.md`).
   - So the prompt format, the asset sheets, the pacing rules and the reference budget are all untested hypotheses. The 488 tests protect the consistency of text artifacts, not the product.
2. **It uses the model as a database writer.**
   - Each episode board is about 150–160K characters of model-written JSON. More than half of it is state that could be derived, or bookkeeping for each source line: 54% and 57% in your two full episode boards, and up to 70% in single scenes [measured].
   - Required fields get filled with boilerplate. The same sentence fills `blocking` in all 44 shots of 仙界 EP01.
   - That boilerplate then flows into the video prompts.
3. **Its cost structure punishes iteration.**
   - The episode runtime must match exactly (tolerance 0).
   - Contracts are pinned to the board file's exact bytes.
   - Every review and its closure are bound to hashes.
   - A runtime fingerprint turns every code change into a project migration. There have been at least nine runtime versions so far.
   - This, more than any single rule, is why it feels unusable.
4. **Its schema shapes the film badly.**
   - Across your real boards, no shot is under 3 s, and nearly all are 4–6 s.
   - Dialogue windows average about 2 characters per second, against the 4–5 declared in the same boards [measured].
   - It promises a "modern short-drama hard rhythm". It delivers uniform cutting at the slow end of the platform's `series` preset (ASL 3–5 s), about twice the ASL of the platform's fast-drama preset.
5. **It reimplements the platform's core models in incompatible versions:** continuity, the character sheet, the default aspect ratio, capability fields and the prompt compiler. The platform already depends on it by reading one of the Skill's installed files by its heading text (`system-b/app/asset_policy.py:26–45`). The two have started drifting apart before they have shipped one episode together.

**The platform is the mirror image.** It has the right machine:
- an event-sourced ledger;
- adoption on real media;
- safe paid execution.

It has thin craft:
- about fifteen generic method rules;
- no series or format layer;
- prompts that dump internal fields in English.

**The fix is structural, not a list of patches.**
- Build one shared kernel in the platform repository: contracts, a core library, capability profiles and a method corpus.
- Rebuild the Skill from that repository as the conversational front end and field kit.
- Make the platform the authority and the factory.

Each then does what its medium is good at:
- the Skill: conversation, reading, judgment and quick experiments;
- the platform: state, media, money and scale.

**The first step is not code. Run a two-day media test:**
- the face policy;
- the prompt dialect;
- the current and proposed prompts on six of your real units.

It costs a few dozen takes and settles more of the design than any further text tooling (§9, Step 0).

---

## 1. Your production need, reconstructed

### 1.1 What you have actually been making

| Signal | Evidence |
|---|---|
| Source | Web novels in chapter batches. Chapters 1–14 of one novel became three episodes (`skill:VALIDATION.md`). |
| Genres | 东方末法玄幻 (仙界), 都市江湖 (出狱后的我), 都市异能悬疑 (死后被契约), and a supernatural story (`guiyi`) |
| Format | 16:9 episodes of 190–290 s. "用户要求每集180–300秒" is recorded in the 死后被契约 board's runtime basis. |
| Density | 44–64 shots and 20–27 generation requests per episode; about 2.2 shots and 10 s per request [measured] |
| Look | Photoreal East Asian live action: "写实东亚都市奇幻", "写实普通人质感", "克制写实废土东方玄幻" |
| Renderer | Seedance 2.0, planned but never called. Dreamina CLI on the platform side. |
| Operator | You, on Windows, in Codex (and Claude Code). Gemini was used once as an outside reviewer. Your model configuration was lost once in a task handoff (`skill:VALIDATION.md`). |
| Platform target | Douyin/TikTok short-form. The default preset is `vertical`: 9:16, ASL 1.5–2.5 s, a hook every 30 s (`system-b/app/production.py:50`, `system-b/app/cinema.py:10`). |

### 1.2 What that implies

- **The unit of production is a series, not a video.**
  - Many episodes come from one novel.
  - Cost and risk live at series level: cast, looks, voices, world state, and hooks that span episodes.
  - Neither system has a series as a first-class object.
- **The format is undecided.**
  - Your Skill runs match the platform's `series` preset (16:9, ASL 3–5 s), not its `vertical` fast-drama preset.
  - Either the real product is horizontal 3–5-minute episodes, or there are two products: horizontal episodes plus vertical shorts or promotional clips.
  - The aspect ratio decides the location plates and the shot sizes, so the format must be an explicit series-level choice made once (§10).
- **The cost drivers are video takes and your minutes.** Text-model calls are cheap. Both systems spend most of their engineering on the cheap part.
- **The binding constraint is one operator.** Anything that makes you type evidence, approvals or handoffs per scene stops scaling after a few episodes.

### 1.3 Bottlenecks, ranked

1. **No media loop.** No design choice in either system has been checked against Seedance output.
2. **Authoring and governance overhead in the Skill.** Iteration is slow and expensive, context windows are exhausted, and state is lost between task handoffs.
3. **Prompt quality.** Noise, internal leakage and mistranslation (§3.3–3.4).
4. **Pacing realism.** The planned rhythm is slower than the stated target (§3.2).
5. **Series continuity.** There is one project per source window, and state is carried between episodes by hand.
6. **Assets and face policy.**
   - The latest validation run uses 54 image versions, all of them "待制作定义" (definitions still to be made), with no images.
   - Your projects specify a photoreal look.
   - Nothing has been tested against the renderer's face policy.
7. **Post-production lives outside both systems** (platform review §4.2).

### 1.4 What I am assuming

- **A1.** The main product is serialized episodes adapted from web novels. Vertical clips are either the promotional layer or a second product.
- **A2.** One operator, possibly with helpers later.
- **A3.** Seedance through the Dreamina CLI is the renderer for now.
- **A4.** The intended look is photoreal live action.
- **A5.** Dialogue audio has been assumed to come from Seedance; neither system has a TTS step.

§10 lists what changes if any of these is wrong.

---

## 2. How the Skill works today

### 2.1 Data flow

```
novel ─ select_source ─► selected.txt ─ init ─► project (.sdd/state.sqlite; one source unit per non-blank line)
 ├─ ref 11: event pool → two-layer compression → flat content draft (Markdown, readable)
 ├─ story snapshot (board JSON, stage=story): project, entities, facts, beats + budgets, cuts (every line), setups
 │     commit only if lint passes (CUT_MISSING, STORY_TIME_BUDGET)
 ├─ 04a author / 04b independent content gate (review records, issue lineage)
 ├─ board per scene: shots (~20 required fields + full start/end state), units (+ grouping prose)
 │     lint: STATE_KEYS, STATE_JUMP, CHANGE_COVERAGE, pacing caps, UNIT_TIME, CAP_*
 ├─ review: critic packet, closures with before/after hashes, change_review, grouping_review
 ├─ export DRAFT/PLAN into a new directory (reference slots empty)
 ├─ ref 09: assets after the final board → 资产设定.md + .sdd/资产登记.json (its own version chain)
 ├─ ref 12: reference contract (cases) → resolver → shot_bindings (must equal the resolver) → PLAN reference_ready
 ├─ optional storyboard pages: request / record / review receipts
 ├─ PLAN text handed to another generation Skill or MCP (nothing comes back)
 ├─ adoption per scene: per-shot in/out points + an end state that you describe
 └─ next episode: a new project, with state carried over by hand
```

### 2.2 Stage-by-stage contract review

| Stage | Input → output | What goes wrong at the boundary | Timing | Your load and gates |
|---|---|---|---|---|
| S0 Source and init | Novel + chapter window → project with one unit per non-blank line (`skill:schemas/source.schema.json`) | A new project for every window, and again for every source change (`skill:references/08-operations.md:69`). A series is therefore split across projects. Line granularity sets up S2's bookkeeping. | No series-level analysis ever precedes episode work | Choosing windows |
| S1 Dramatic audit (ref 11) | Selected text → event pool, two-layer compression, **flat content draft** (场景/画面/对白/心声/音效/时间跳转) | The readable draft is not the authority. S2 and S4 re-encode it into JSON, and from then on edits happen in JSON. | Right place | Low; the best stage |
| S2 Story snapshot | Draft → board, stage `story`: project (`target_ms`, `tolerance_ms`, generation evidence), entities, facts, beats with time budgets, **a cut record per source line**, setups | `CUT_MISSING` for any undecided line (`skill:scripts/core.py:257`), so EP04 has 458 cut records. Beat budgets must sum to the target (`:304`), usually with tolerance 0. Seedance's limits are re-researched in every project. | Exact runtime before any shot exists: **too early** | Commit is refused until lint passes, so work in progress cannot be saved |
| S3 Content gate (04a/04b) | Story → review records with issue IDs and closures | The intent is good (an independent cold read). The form is heavy: lineage, closure evidence. | Right place, wrong weight | Host duty, not yours |
| S4 Board per scene | Story + draft → shots with about 20 required fields and start/end snapshots of every scene key; units with grouping prose | `STATE_KEYS` requires every key in every shot (`core.py:353`): 44–89 keys per shot. Required fields fill with boilerplate; one sentence lands in three fields. Dialogue windows are placeholders. Retiming one shot moves `target_ms`, which is part of the story basis, so every story-scope review goes stale (`test_reestimation_updates_story_basis_and_requires_current_review`). | Reference budget and asset cost are still unknown here | — |
| S5 Review | Board + critic packet (which includes the entire asset registry, contract and plans) → issues, per-region closure evidence with before/after hashes, `change_review` covering every changed region (`skill:scripts/review_lineage.py`) | Bookkeeping per region. Reviewers read JSON, not the readable plan. Packets are huge. | Repeats after every fix | Approvals need a `basis_hash` and a file containing your own words |
| S6 Export | Committed board → `PLAN.txt` / `plan.json` per unit, plus episode manifests and review summaries | The output directory must not already exist (`08-operations.md:131`), so every export creates a new folder. Before assets exist the slots are empty, so you export again later. | Before assets: **too early to be final** | Folder proliferation |
| S7 Assets (ref 09) | Final board → `资产设定.md` + `.sdd/资产登记.json` (variants, prompts, revisions, locks) | A second version chain, independent of the board head. By design there are no images, paths or task IDs (`skill:references/09-assets.md:52`). No face-policy or renderer test. | Look development after directing: **too late** | Defining 50+ image versions by hand |
| S8 Reference contract (ref 12) | Board + registry → contract (per-entity cases, per-prop relation cases), resolver report, shot bindings that must **equal** the resolver output (`skill:scripts/reference_contract.py:150`), PLAN slots | The second and third encodings of facts the board already holds. Exact matching on free-text values. Pinned to the board file's bytes (`:47–55`). Boilerplate reasons. Wrong owners slip through (§3.5). | — | High |
| S9 Storyboard pages (optional) | Export + layout → page requests, image receipts and reviews. `pixel_truth_verified` is always false; two attempts per page. | Governance over still images that never feed the video | — | Receipts per page |
| S10 Generation handoff | PLAN text + attachments → an external Skill or MCP | Nothing comes back: file bindings, submit IDs, results, costs | — | You carry everything across |
| S11 Adoption | External videos + your description → per-scene adoption with per-shot intervals and the actual end state | You produce the evidence. The granularity is the scene, although a scene spans several requests. The tool never decodes video. | — | Formal approval with your words |
| S12 Next episode | Previous adoption → a new project with a hand-declared initial state (`inherit_keys`) | Manual by design (ref 11: "no automatic listening or propagation"). Looks and assets are declared again. | Continuity should be continuous, not a step | High |

### 2.3 Too early, too late, missing

| Item | Today | Where it belongs |
|---|---|---|
| Exact episode runtime | Story stage, tolerance 0 | A soft window at outline time; computed from the shots; checked at assembly |
| Per-line cut decisions | Story stage, every line | Span coverage plus a must-keep list at outline time |
| Formal review with lineage | Before the content stabilizes, repeated after each fix | Cold-read notes while drafting; human gates at the outline and the pilot |
| Capability evidence | Re-researched in every project (three different paragraphs in three boards; `max_prompt_chars: null` in all of them, so the prompt-length check never ran) | One shared, calibrated profile, chosen at series setup |
| Look development and face policy | After the final board, never tested | Right after the bible; smoke-tested on Seedance before approval |
| Reference budget | Discovered at contract or PLAN time | Visible while directing |
| Audio timing | Never; estimates only | Before final shot timing (TTS), or at least a realistic planning rate |
| Media validation | Never | From the first week, then on every unit |
| Cross-episode state | Hand-declared at the start of each project | One ledger that runs across episodes |

**Missing stages:**
- a persistent series bible and outline;
- look development with calibration;
- audio;
- generation and QC;
- assembly;
- publishing and metrics.

---

## 3. What your real artifacts show [measured]

### 3.1 The boards

| Board | Shots | State keys per shot | Keys about entities on screen | Shots with no state change | State share of board | State + cut bookkeeping | English-coded state values |
|---|---|---|---|---|---|---|---|
| 仙界 EP01 (board-v3) | 44 | 44 | 24% | 26 | 54% | 57% | 1,936 of 1,936 |
| 仙界 EP03, scene SC04 | 18 | 89 | 17% | 7 | 70% | 70% | 1,602 of 1,602 |
| 出狱后的我 EP04 | 44 | 11.9 | 67% | 30 | 19% | 54% (458 cut records = 34%) | 186 of 523 |
| 死后被契约 EP01, scene SC04 | 2 | 30 | 17% | 2 | 31% | 31% | 12 of 60 |
| `guiyi` (projection) | 40 | 10 | 28% | 36 | — | — | 400 of 400 |

**Required free-text fields collapse into boilerplate:**

| Board | Field | Distinct values across shots | The repeated text |
|---|---|---|---|
| 仙界 EP01 | `blocking` | 1 of 44 | 人物看向当前动作或对方，依已声明位置；不看镜头，不加无关身体动作。 |
| 仙界 EP01 | `cut_reason` | 1 of 44 | 信息成立或动作落定时切镜 |
| 仙界 EP03, SC04 | `blocking`, `lighting`, `sound`, `cut_reason` | 1 of 18 each | — |
| 出狱后的我 EP04 | `emotion` | 1 of 44 | 当格表演随可见动作，不提前表演之后节拍的结果。 (an instruction to the author, not an emotion) |
| 出狱后的我 EP04 | `sound` | 2 of 44 | 现场对白及低环境声；无BGM，无新增伤害音效。 |
| 死后被契约 SH017 | `intent` = `visual` = `camera.composition` | the same sentence three times | 沈父站在客位前，没有坐下；陆父仍背向他，苏云抬眼听。 |

**What the numbers mean.**

- **The state in every shot is mostly about things off screen.**
  - The 仙界 EP03 scene carries 89 keys through each of its 18 shots, twice (start and end). Only 17% describe entities that are on screen.
  - The 死后被契约 living-room scene carries the coffin's lid, the hospital's time of day and the study computer's power state.
  - This follows directly from `STATE_KEYS`: every shot must list every key declared for its scene.
- **Most shots change nothing.** 26 of 44 shots in 仙界 EP01, 30 of 44 in 出狱后的我 EP04 and 36 of 40 in the `guiyi` project have an end state identical to their start state. All that text is copied, not authored.
- **State vocabularies differ between projects, and even between rounds of the same novel.**
  - The latest 仙界 boards and the `guiyi` project code every value in English (`bed_foot`, `thin_qi`, `night`, `office`).
  - The earlier round-2 仙界 project used Chinese values (暮色, 夜间, 粗布灰褐旧衣) for the same world.
  - 出狱后的我 mixes the two.
  - The renderer then needs a dictionary to translate English codes back into Chinese (§3.4).
- **The bookkeeping crowds out the craft.** Your boards include `author_context` paragraphs in which the model defends its own process ("非自动跨项目传递……无媒体、adopt或批准……不是事后声称旧版已检查"). A system that rewards proof of compliance teaches the model to write compliance.

### 3.2 Shot length and dialogue timing

| Board | ASL | Shot lengths | Shots under 3 s | Dialogue rate in the board vs declared |
|---|---|---|---|---|
| 仙界 EP01 | 4.82 s | 8 × 4 s, 36 × 5 s | 0 | 1.87 vs 4 chars/s |
| 仙界 EP03, SC04 | 4.67 s | 6 × 4 s, 12 × 5 s | 0 | 1.59 vs 4; all 10 lines span exactly [0.2 s, end − 0.2 s] |
| EP02, 1.2.1 run (novel not named) | 4.90 s | 4 × 3 s, 11 × 4 s, 21 × 5 s, 14 × 6 s | 0 | — (50 shots, 50 single-shot requests) |
| 出狱后的我 EP04 | 5.09 s | 8 × 4 s, 24 × 5 s, 12 × 6 s | 0 | 2.02 vs 5 |
| Latest validation run, three episodes (`skill:VALIDATION.md`) | 4.19, 4.53, 4.56 s | not in the package | unknown | — |

**Why the rhythm is slow.**

- **The hard rules are ceilings only.**
  - Shots may run at most 8 s, and anything over 6 s must contain progress (`core.py:332–337`).
  - The average shot may run at most 6 s (`:443`).
  - Nothing pushes shots *down*, so the model settles just inside the ceilings.
- **The cost of each shot pushes the other way.**
  - Each shot costs about 20 required fields plus two copies of the full state.
  - The rational response is fewer, longer, more uniform shots.
  - When a beat needs several framings, the model writes them into one "fixed" shot. The independent review of 出狱后的我 EP03 flags exactly this ("three framings within one declared fixed shot", V2-SHOT-02).
- **The schema is a directing decision.**
- **Dialogue timing is a placeholder, not an estimate.**
  - The windows give lines roughly twice the time implied by the board's own `zh_chars_per_second`.
  - The renderer prints these windows into the prompt ("本镜约第0.1–4.9秒的对白节奏"). That precision is false, and the model cannot use it.

### 3.3 The prompts

The same unit (出狱后的我 EP04 U01: 李树 and 刘军 in the manager's office, two shots, 12 s) in three versions:

| Version | Characters | State-line share | English tokens | Internal or author-facing phrases |
|---|---|---|---|---|
| PLAN before 1.2.5 | 1,951 | 35% | 17 (`C_LISHU`, `costume`, `injury`, `worn`…) | 12 |
| Renderer 1.2.6 (today) | 1,091 | 10% | 1 (`KTV`) | 7 |
| Proposed (below) | 314 | 0 | 1 (`KTV`) | 0 |

The 1.2.6 renderer is a real improvement, and it deserves credit for it. What still reaches the video model:

| What reaches the model | The text | Belongs to |
|---|---|---|
| Directing method | 只在观众判断或控制权发生变化时切镜；每镜头单一连续取景…… | The director's method |
| Project-wide content notes | 暴力非血腥；朵朵普通非性化衣着 (朵朵 is not in this unit) | The content policy |
| Workflow status | 参考图按下列编号准备并上传后使用；尚未物化或上传参考图。 | The tool |
| Defensive notes | 李树的伤情为左额角仍有敷料，伤未宣称痊愈 | The author |
| Meta-instruction posing as emotion | 表演要求：当格表演随可见动作，不提前表演之后节拍的结果。 | The author |
| Editorial handles | 开头约0.5秒留作剪辑余量…… | The editor |
| Cut reason | 随后切镜：开场把前集任命翻成新风险成立后切出…… | The editor |
| False timing | （本镜约第0.1–4.9秒的对白节奏） | — |
| A trivial prop given a reference slot | 图片4：头部敷料…… | It could be half a sentence |

**Proposed** (untested; calibrate it in Step 0):

```
16:9，写实电影质感，2000年代初北方城市，KTV经理办公室，暖白顶灯混合日间侧光，低饱和。
@图片1 是李树：白衬衫、黑马甲、黑裤的服务生制服，左额角贴一块白色方形纱布。
@图片2 是刘军：四十岁左右，中等身材，短发，深色衬衫。
@图片3 是经理办公室：办公桌在房间北侧，门在南侧。

0–6秒，中景，固定机位，李树在画左、刘军在画右，办公桌在两人之间：刘军撑着桌沿起身，右腿不敢吃力；李树看见，脸上的笑收住。李树：“军哥，你腿怎么了？”
6–12秒，过肩中景，刘军在前景画右，李树在画左：刘军慢慢坐回椅子，揉着右膝，抬头看李树。刘军：“昨晚去动李老三的场子，一组伤了不少人。”

同期对白和环境声，无背景音乐，无字幕。
```

**What the proposed prompt keeps:**
- the uniform and the gauze, in the reference roles;
- the leg injury, shown through action;
- the positions and the screen axis;
- both lines;
- each reference's role, stated once.

**What it drops:** every line that addresses the author, the editor or the tool.

**How references are written** (`@图片N`, `图片N` or `参考图 N`) must be checked against the CLI (platform review §6.9).

### 3.4 Renderer defects I reproduced

The renderer translates English state codes through global dictionaries filled with words from your past projects (`skill:scripts/prompt_renderer.py:11–28`):
- 47 field labels, including `knows_aunt_player`, `san='理智值'`, `brake='轮椅刹车'` and `lid='棺盖'`;
- 45 value translations;
- 57 named places, such as `left_door_recoil`;
- regular-expression grammar such as `grips_(.+)_collar` → 抓住…衣领.

**Reproduction.** I took the neutral box fixture and set `P_BOX.lid` to `open`. The current renderer writes "开镜时，box的棺盖为open。" The box gains a *coffin* lid, carried over from 死后被契约, and the value is left untranslated.

**Further defects:**
- **It rewrites English words inside your free text.** `prose()` replaces `light`, `scene`, `shot` and `visual` wherever they appear (`prompt_renderer.py:40–42`). "Even soft light" became "Even soft 光照".
- **The `power` mistranslation.** "陆震天 通电状态=熄灭" and "云清禾 通电状态=depleted": `power` was translated as electrical power. It was fixed by adding entries to the dictionary (`test_cross_novel_power_values_stay_non_electrical`).
- **Every new novel needs a new patch.** Each novel brings new codes, and the runtime fingerprint (§4, F6) makes each patch a version bump plus a migration.

### 3.5 Other defects found in the natural fixtures

- **A fix that had to wait for a new runtime.**
  - In 1.2.4 the renderer dropped the 仙界 EP01 time skip (an `ellipsis` while a crystal charges). The fixture is marked `status: unresolved_in_frozen_skill`.
  - The workaround was for the author to repeat the skip inside `visual`. That duplicated text is still in the boards.
  - 1.2.6 now emits a generic "省略一段时间后" boundary (`test_natural_crystal_jump_has_before_shot_ellipsis`), but only after a runtime version and a migration.
- **Props get the wrong owner.**
  - In the 出狱后的我 batons shot, four batons held by four attackers are bound to the protagonist.
  - The relation text reads "详见起止状态及本镜动作" ("see the states and action").
  - The four nameless attackers are four separate character assets, which take four of the nine reference slots.
- **Payoffs are elided.**
  - The climax of 出狱后的我 EP03, where 李树 beats four attackers, is written as "快速省略交锋后……" ("after a quickly elided exchange…").
  - In a 都市江湖 story the fight *is* the payoff. Content-safety wording repeated in every field ("暴力非血腥", "无追打与伤口"), with no method for staging action safely, pushes the model to skip the very moments the audience came for.
- **The contracts are boilerplate and brittle.**
  - In the 死后被契约 contract, every key that does not drive an image variant carries the same reason string.
  - Cases match exact free-text values such as "暗冰融合，排斥止息". Rewording a state value in the board silently breaks the mapping.
- **The character-sheet design carries two risks** (`C_LISHU-BASE`). The prompt asks for a photoreal 9:16 sheet: a face close-up on top, and three body views with the "head completely out of frame".
  - It is exactly the photoreal face reference that ByteDance channels reportedly block [src].
  - Headless body views are an unusual identity reference, and their effect on Seedance is unknown.
  - Neither risk was tested.

### 3.6 What the tests protect

Breakdown of the 447 test methods (488 test runs):

| Area | Methods | Share |
|---|---|---|
| Governance and integrity (lineage, storyboard receipts, migration, legacy rechecks, authority) | 129 | 29% |
| Asset and reference contracts | 114 | 26% |
| Prompt compilation | 58 | 13% |
| Unit grouping | 43 | 10% |
| Dramatic checks | 26 | 6% |
| Other | 77 | 17% |
| Anything involving media | 0 | 0% |

**No test measures what the product needs:**
- prompt length;
- leakage into prompts;
- the shot-length distribution against the format;
- dialogue rate;
- anything about video.

The package also carries:
- 21 KB of `SKILL.md`, loaded on every use;
- about 195 KB of references;
- release and provenance documents;
- a complete 1.2.4 runtime as a zip, so that migration can be tested.

---

## 4. Where the Skill's design is fundamentally wrong

Each entry gives the evidence, the consequence and the replacement.

**F1. The model writes the database, and code checks it.**
- *Evidence:* §3.1.
- *Consequence:* token cost, slow iteration, boilerplate, and attention spent on bookkeeping instead of drama.
- *Replace with:* invert the roles. The model writes the smallest creative surface: what is seen, heard and changed, and why. Code derives everything derivable:
  - state snapshots, by replay;
  - visible state;
  - durations, from the dialogue;
  - units;
  - references;
  - prompts;
  - grouping explanations.

**F2. State is a set of full snapshots of free-text keys.**
- *Evidence:* 44–89 keys per shot, English codes, exact-string matching.
- *Consequence:* errors that cannot be caught (a transition reason saying 坐 while the state says 站立), vocabulary bleeding between projects, and a renderer patched for each novel.
- *Replace with:*
  - events over typed state: the platform's ledger, with typed `pos` relations, `from`/`to` changes, replay and visibility (`system-a/app/story_contract.py:12–99`);
  - values in the project's own language;
  - a per-project glossary that the agent writes once.

**F3. The same fact is encoded three times:** in the board state, in the contract cases and in the shot bindings, which must agree exactly.
- *Consequence:* consistency checks that only catch the typos the redundancy itself created.
- *Replace with:* the ledger is the single statement of the fact. Asset variants declare when they apply (a look, a condition, a time of day). A resolver derives the bindings, which are never authored.

**F4. A local edit invalidates everything.**
- *Evidence:*
  - tolerance 0 on the runtime;
  - `target_ms` is inside the story basis;
  - contracts are pinned to the board file's bytes;
  - export folders can never be reused;
  - changing the source means a new project.
- *Consequence:* every small fix costs a full round of reviews.
- *Replace with:*
  - invalidation by content address, per dependency: a line → its shots → their units → their prompts → their takes, which are marked stale but never deleted;
  - soft duration windows;
  - git for text history.

  The Skill's own storyboard pages already invalidate per page; generalize that.

**F5. Governance stands in for verification.**
- *Evidence:*
  - closure hashes and full change-review coverage;
  - approvals backed by a file of your own words;
  - `pixel_truth_verified` hard-wired to false;
  - `semantic_status: requires_review` on every plan.
- *Consequence:* a great deal of ceremony, and no evidence about the video.
- *Replace with:* machine checks on outputs, human taste gates where money is spent, and adoption on real media (platform review §4.3).

**F6. The code is frozen, so the method lives in prose.**
- *Evidence:*
  - The runtime fingerprint covers every script and schema (`skill:scripts/store.py:14–28`).
  - Any change requires `migrate` with the original runtime directory.
  - Known bugs stay "unresolved_in_frozen_skill".
- *Consequence:* the knowledge accretes as 220 KB of dense Markdown that every session must re-read. Freezing the code moved the cost into every future context window.
- *Replace with:*
  - version the *data* (schema versions with upgrade functions);
  - record the core version inside every derived plan, which gives reproducibility;
  - keep the code evolvable, behind golden tests.

**F7. A project is one source selection.**
- *Consequence:* there is no series, a new project for every window, manual handoffs, and asset definitions repeated per project.
- *Replace with:* a project is a series, and episodes live inside it. The ledger and the asset bible persist across episodes. The adopted end state of episode *n* is the initial state of episode *n+1*.

**F8. It stops at PLAN and does not track media.**
- *Evidence:* `skill:references/09-assets.md:52` says generation is "separately authorized work" and needs no records.
- *Consequence:* the system can never learn what the renderer does.
- *Replace with:* real files and hashes for the assets, a generation journal, and observations of each take. The media loop *is* the product.

**F9. It keeps a private copy of what the platform has.**
- *Evidence:* continuity, asset policy, capability fields, renderer, adoption and IDs (§6).
- *Consequence:* the drift is guaranteed, and it has already begun.
- *Replace with:* the shared kernel (§7.5).

---

## 5. What the Skill gets right, and where it should go

| Keep | Why it matters | Destination |
|---|---|---|
| Event pool → two-layer compression; the double-peak structure; the 240 s reference axis; opening candidates; ending kinds (refs 10, 11) | The series and episode architecture the platform lacks entirely (platform review §4.5) | `methods/` series outline; outline checks in core |
| Attention checks R1–R7 (opening by 7 s, first counteraction by 20 s, a bridge every 30 s) | Measurable hook and payoff density | Core checks, run on scripts and on the assembled cut |
| Flat content draft (场景/画面/对白/心声/音效/时间跳转) | The right human-facing script | **The** script format for both systems |
| Information ledger (fact / belief / uncertain; introduces / requires / withholds); setups paid or deferred; subplots kept, deferred or cut with a due point | Managing reveals and promises across episodes | Outline fields; not per shot |
| The cold-read review protocol in two stages | A fresh reader catches what the author cannot | `methods/review`; a subagent step, not a gate |
| Natural-Chinese prompts that bind each image to its shots | The right direction | The shared renderer, rewritten (§7.5) |
| Shot ≠ unit, with handles | Correct, and already shared with the platform | The core packer |
| Asset ontology: who or what something is, versus its state; props separate from characters; a state is not a new image | Correct, and the platform already copies it | `methods/assets` |
| "Difference from parent" instructions for child images | Good image-editing practice | `methods/assets` |
| Self-contained requests: every request restates its starting situation, with no "same as before" (`skill:helpers/prompt_handoff_check.py`) | Each request is generated independently | A renderer rule plus a lint |
| Off-screen voice and inner voice never drive lip-sync | Real failure mode | Renderer rule |
| Zero-configuration start; "do not ask for the duration first" (`skill:agents/openai.yaml`) | Low friction | Keep in the new Skill |

---

## 6. The platform, seen through the Skill

These findings add to the platform review.

- **J1. Hidden, fragile coupling.**
  - `asset_policy.guidance()` reads `~/.agents/skills/shortdrama-director/references/09-assets.md` and keeps three sections found by searching for their heading text (`system-b/app/asset_policy.py:26–45`). If a heading changes, the guidance silently disappears; only the recorded hash changes.
  - The naming section it excerpts recommends IDs (A01/S01/D01) that neither system uses.
  - Its own character brief, a 2×2 sheet of two head views and two body views (`asset_policy.py:60–64`), contradicts the Skill's face-plus-headless-views sheet. Neither has been tested.
  - The location and prop briefs are English restatements of the Skill's Chinese layouts (16:9 at a 45–65° high angle; a 2×2 prop sheet), from its "默认资产图布局" section (`skill:references/09-assets.md:54–58`). The two systems share by copying, not from one source.
- **J2. The format is in conflict.**
  - The default preset `vertical` is 9:16 with ASL 1.5–2.5 s (`production.py:50`, `cinema.py:10`).
  - The Skill defaults to 16:9, and your real outputs run at an ASL of 4.2–5.1 s.
  - The format should be an explicit series profile, not each system's own default.
- **J3. "No fixed length."** The adaptation prompt for workspace A says "镜长按内容估算，无固定片长或反转间隔" (`system-a/app/formats.py:230`). That contradicts your stated 180–300 s requirement and the Skill's commercial structure.
- **J4. Both systems demand exact durations.**
  - The platform requires the shots to sum to the scene budget within 0.08 s (`system-b/app/cinema.py:83`).
  - The Skill requires `TIME_BUDGET` within a tolerance of 0.
  - Both breed false precision. Durations should be derived and checked against soft windows.
- **J5. Both copy scene properties into every shot.**
  - The platform copies the direction's lighting into each shot (`cinema.py:69`).
  - The Skill repeats the same blocking, lighting and sound in every shot.
  - Use scene defaults with per-shot overrides instead.
- **J6. Both make you account for every source unit.**
  - The platform requires a `sourceMapping` entry for every source block (`system-a/app/formats.py:213`).
  - The Skill requires one for every line.
  - Replace both with span coverage plus a must-keep list.
- **J7. The platform drifts internally too.** `story_contract.py` is copied into A and B ("shipped independently in each application"), and the two copies already differ: B adds a shot-state-order check (`system-b/app/story_contract.py:247–256`). `llm.py`, `creative_review.py` and `reading_export.py` also differ between A and B.
- **J8. The craft is thin.**
  - The platform's method pack is fifteen generic rules (`studio/directing_methods.py:13–41`).
  - It has no hook, payoff or cliffhanger structure and no attention checks.
  - The Skill's refs 10–11 are exactly what is missing.
- **J9. There are two prompt compilers.** The platform's builds English spec text (D12); the Skill's builds natural Chinese. Keep one.

---

## 7. Target design: one pipeline, one kernel, two front ends

### 7.1 Principles

1. **One source of truth per kind of thing.** Schemas, the continuity model, asset definitions, capability profiles, the compiler and the methods each live in exactly one place.
2. **The model writes intent; code derives facts.** An authored field must carry information that cannot be computed.
3. **Readable artifacts are the authority.** The script and the shot plan are files you can read in five minutes.
4. **Invalidate narrowly, never cascade by default.**
5. **Trust comes from evidence about the output.** People decide taste and spend; machines produce evidence.
6. **Each front end does what its medium is good at.** Conversation for development and judgment; the application for state, media, money and scale.
7. **The renderer is a design input from the first day.** The face policy, dialect, budgets and failure modes feed writing and directing (platform review §4.4).

### 7.2 The pipeline and its contracts

| # | Stage | Input → output (artifact) | Authored by | Derived by code | Leads | Gate |
|---|---|---|---|---|---|---|
| 0 | Series setup | Your intent + source files → `series.yaml` (format profile, look and face policy, capability profile, rights) | Agent with you (2–3 questions at most) | Defaults; profile lookup | Skill | — |
| 1 | Source bible | Chapters → `bible/` (characters with aliases, relationships, rules, locations, props, timeline, payoff inventory, each with source spans) | LLM | Merge, dedupe, span index | Skill (long reading) | Automatic |
| 2 | Series outline | Bible → `outline.md` (per episode: source span, hook, payoffs, cliffhanger, subplots due, cast, locations) | LLM with you | Must-keep coverage, R-checks, length estimate | Skill | **G1, human** |
| 3 | Episode script | Outline row + bible + ledger state at episode start → `episodes/EPnn/script.md` (flat format plus 【状态】 event annotations) | LLM | Line anchors, ledger events, replay, duration estimate, R-checks | Skill; the platform can batch routine episodes | **G2:** automatic, human for the pilot |
| 4 | Breakdown and looks | Scripts (incrementally) → `assets/briefs.yaml` (looks by story day, crowds, story props, locations × setups, voices) | LLM briefs | Requirements from the ledger and the scripts | Skill drafts, the platform owns | — |
| 5 | Look development and calibration | Briefs → approved images + Seedance smoke-test results | — | Image generation, smoke tests, identity embeddings | Platform | **G3, human, once per series** |
| 6 | Audio (optional) | Script → line audio and measured durations | — | TTS | Platform | — |
| 7 | Shot plan | Script + assets + profile → `episodes/EPnn/shots.yaml` | LLM | Durations from lines, visibility, axis checks, reference-budget preview | Skill for key scenes, the platform in batch | Automatic |
| 8 | Generation plan | Shots + ledger + assets + profile → `derived/plans/EPnn/Uxx.json` (units, references, prompts, cost) | — | Packing, resolving, rendering, linting, budgeting | Core, from either front end | **G5:** budget, in the platform |
| 9 | Generation and QC | Plans → takes + QC scores | — | Adapter, journal, detectors | Platform; the Skill for smoke tests and small jobs | **G6:** exceptions only |
| 10 | Adoption | Takes → clips (interval → shot) + observed end states | — | Shot detection, vision diff | Platform | Part of G6 |
| 11 | Assembly and packaging | Clips + audio + script → timeline, subtitles, labels, cover, title, format variants | LLM titles | Assembly | Platform | **G7:** watch through |
| 12 | Publish and learn | Episode files → posts, metrics, method updates | LLM summaries | Ingestion | Platform; the Skill analyzes | G9 |

### 7.3 Who does what

- **The Skill: writers' room, director's desk, field kit.**
  - Reading the whole novel, building the bible and the outline.
  - Writing and rewriting scripts; cold reads.
  - Directing key scenes, with alternatives.
  - Diagnosing failures ("why do U12's takes keep breaking identity?").
  - Small productions: pilots, trailers, promotional clips, 推文 videos.
  - Evolving the methods.
- **The platform: the studio and the post house.**
  - Authoritative state.
  - Assets with real files, calibration, batch generation, QC and adoption.
  - Assembly, publishing and metrics.
  - The review interface for media.
- **The kernel: shared by both.**
  - Contracts.
  - `sf_core`: replay, derivation, packing, resolving, rendering, linting and checks.
  - Capability profiles.
  - Methods.

**Three operating modes**, by task and by the stage of a series' life:

| Mode | When | Flow |
|---|---|---|
| 1. Field kit (Skill alone) | Pilots, promotional clips, experiments, calibration | The Skill runs stages 0–8 and generates a handful of takes through the shared adapter, with a journal |
| 2. Writers' room → factory | A new series | The Skill runs stages 0–4 and 7 for key scenes, then exports a bundle. The platform imports it and runs stages 5–12. |
| 3. Factory (Skill on call) | Routine episodes once the method is settled | The platform's own LLM stages run stages 3 and 7 with the same methods. You review by exception and use the Skill for diagnosis and changes. |

### 7.4 Overlap and difference

**Where they overlap on purpose.** Both use the same code, so overlap is safe:
- editing scripts and shot plans (the Skill for deep rewrites, the platform for quick fixes);
- previewing compiled prompts;
- small-scale generation through the same adapter and journal format.

**Where they must differ:**

| | Skill | Platform |
|---|---|---|
| Interaction | Conversation, files | Interface, jobs |
| Validation | Advisory: it reports and never blocks saving | Enforced at the points where money is spent |
| Storage | A folder plus git | Database plus object storage |
| Governance | A decision log (`decisions.md`) | Adoption records, budgets, locks |
| Media | Smoke tests and small jobs | Everything at volume, plus the review interface |
| Strength | Judgment, reading, iteration speed | Correctness, throughput, history |

### 7.5 The shared kernel

**Continuity model.** Start from the platform's ledger and extend it:
- **Entities:** `id`, `kind` (character, prop, location, crowd, set dressing), name and aliases, identity anchors, looks, voice.
- **Typed state:**
  - `pos {rel: at|inside|on|held_by|worn_by|attached_to, target}`;
  - `look`;
  - conditions (injury, dirt, wet: a list of `{part, desc}`);
  - open/closed, `count`, active/consumed/destroyed, `visibleTo`.

  Free descriptive fields are allowed but never used for resolution.
- **Events, written in the script as short Chinese annotations with a fixed verb list:**
  - 拿起 / 放下 / 交给 / 收起;
  - 穿上 / 换成 / 脱下;
  - 受伤 / 包扎 / 痊愈;
  - 打开 / 关上;
  - 进入 / 离开;
  - 出现 / 消失 / 消耗 / 毁坏.

  Each verb compiles to typed changes.
- **Story days.** Scenes carry a story day, and looks persist within a day unless an event changes them. This removes most wardrobe bookkeeping (platform review §6.7).
- **A staging ledger.** Scene-scoped stage business, such as a cup set down, is declared in the shot plan. It does not enter the story ledger unless it is promoted.
- **Planned, requested and observed versions of state.** An adopted take's observed end state overrides the plan for everything downstream (the platform already does this).

**Asset definition:**
- **A master per entity:** neutral, with its identity.
- **Variants keyed by what they represent:**
  - a look, for characters;
  - a condition, for props;
  - a time of day or a camera setup, for locations (plates).
- **Each variant records:**
  - the brief (LLM-written);
  - image files and hashes;
  - a status;
  - the Seedance smoke-test result;
  - its direct parent.
- **Crowds are one asset**, either a group sheet or text only. Extras never take individual reference slots.
- **Sheet layouts come from calibration** and are written down once, in the methods. Prior: keep the head visible in every view, and add a face close-up only for characters who are often in close-up (to be tested).

**Capability profile.** One versioned file per model and channel, read by both systems:

```yaml
id: seedance-2.0@dreamina-cli
calibrated: null            # set by the Step 0 run; "configured" is not "verified"
duration: {min_s: 4, max_s: 15, whole_seconds: true}
references: {images_max: 9, videos_max: 3, audio_max: 3, images_reliable: 6}   # reliable count: community reports [src]; calibrate
modes: [multimodal2video, frames2video, multiframe2video]
prompt: {language: zh, reference_token: "@图片{n}", segment: "{a}–{b}秒，", target_chars: [250, 600], reliable_cuts_per_unit: 3}
audio: {native_dialogue: true}
faces: {photoreal_reference: unknown}                  # must be tested; reported blocked [src]
aspect: ["16:9", "9:16"]
hard_shots: [多人肢体接触, 连续打斗, 手部精细操作, 屏幕文字, 液体]   # each with a success rate after calibration
price: {per_second: null}
```

**Generation logic** (one implementation, in `sf_core`):
- `pack(shots, profile)` → units. This is dynamic programming over the ordered shots, with these constraints:
  - whole seconds within the profile's bounds;
  - the reliable number of cuts;
  - the same location and continuous time;
  - the reference budget.

  It minimizes generated seconds plus risk penalties, and it writes its own grouping explanation.
- `resolve(unit, ledger, assets)` → references, in priority order:
  1. speaking characters;
  2. other principals on screen;
  3. the location plate;
  4. story props involved in the action.

  Anything else becomes text.
- `render(unit, refs, glossary, profile)` → the prompt. The rules:
  - **One header line:** aspect ratio and look.
  - **Each reference's role stated once.**
  - **One time-coded segment per shot:** shot size, camera, positions, then the action as verbs, then the dialogue with speakers.
  - **Starting positions** only in the first segment of a unit, and only for what is on screen.
  - **One footer:** audio and subtitles.
  - **Never included:** IDs, versioned asset names, status text, cut reasons, emotion arcs, handles, or lists of prohibitions.
- `lint(prompt, profile)` flags:
  - English tokens outside a whitelist;
  - author-facing phrases;
  - length over budget;
  - unused references, or entities that are mentioned but not visible;
  - decimal timing.
- `budget(units, profile, takes)` → expected cost.
- `adapter`: submit, poll, reconcile through `list_task`, and journal everything (the platform's paid-request safety, extracted).

**Methods.** A Markdown corpus with stable section IDs: series outline, script format, pacing, directing, continuity, assets, generation dialect, review, action staging. The Skill reads them as references. The platform's method packs are built from the same sections by ID, not by searching heading text.

### 7.6 Authority and sync

- **The bundle** is a folder in the shared format (§8.1). The Skill works on it directly; the platform imports and exports it without loss.
- **Before import, the bundle is the authority. After import, the platform is.** To change an imported series in the Skill, export it, edit it, and import it again through the platform's existing import plan with its impact preview (`system-b/app/script_input.py:10–48`).
- **Conflicts are detected per scene.** Each file records the hash of the version it was derived from. If the platform changed a scene since then, the import shows a three-way diff for that scene only.
- **Images live in the bundle** (`assets/images/<variant>@<rev>.png` plus its hash). This closes the "empty slot" gap.

### 7.7 How the two stop drifting apart

1. **One repository owns everything.**
   ```
   contracts/   JSON Schemas, capability profiles, glossary schema
   sf_core/     stdlib-only Python: replay, derive, pack, resolve, render, lint, checks, bundle I/O
   methods/     the craft corpus with stable section IDs
   skill/       SKILL.md source, templates, a sample series
   tools/build_skill.py   assembles the installable Skill = skill/ + methods/ + a vendored copy of sf_core + contracts
   ```
2. **The platform imports `sf_core`** for replay, rendering and capability limits. This removes the duplicated `story_contract.py` copies in A and B (J7), the duplicated limit tables (D10) and the English prompt dump (D12).
3. **The platform never reads the installed Skill.** Delete the heading search in `asset_policy.py`; both read `methods/` from the repository.
4. **Versioning:**
   - schemas and core use semantic versions;
   - each bundle records the versions that wrote it;
   - the core upgrades older minor versions;
   - the platform refuses a newer major version with a clear message.
   - There are no runtime fingerprints.
5. **One test set runs against both:**
   - golden bundles;
   - golden rendered prompts;
   - an export → Skill validation → import round trip that must be identity;
   - your converted real episodes as fixtures.
6. **A doctor command on both sides** reports the installed Skill version, the platform version and the capability profile, and warns on any mismatch.
7. **One rule for changes:**
   - a method change lands in `methods/` first;
   - a schema change lands in `contracts/` first;
   - nobody edits the vendored copy inside the Skill.

---

## 8. The redesigned Skill

### 8.1 Layout

**The installed Skill:**

```
shortdrama-director/
  SKILL.md            ≤ 150 lines: when to use it, the three modes, the pipeline, the file map, the commands, which method to read when
  references/         = methods/ (series-outline, script-format, pacing, directing, continuity, assets, generation-seedance, review, action-staging)
  templates/          series.yaml, script.md, shots.yaml
  scripts/sf.py       a thin CLI
  scripts/sf_core/    vendored; carries the version and hash
  examples/sample/    one representative multi-scene episode: script, shots, assets, a derived plan
```

**A series folder**, which is also the bundle:

```
<series>/
  series.yaml
  source/             chapters plus a span index
  bible/              characters.yaml, locations.yaml, props.yaml, world.md, glossary.yaml
  outline.md
  episodes/EP01/      script.md, shots.yaml, notes.md
  assets/             briefs.yaml, images/, calibration.yaml
  derived/            ledger.json, plans/, prompts/, reports/   (written by sf, never by hand)
  journal/            generation submissions, if run from the Skill
  decisions.md        what was decided, when, and why
```

### 8.2 What the agent writes

**The script** (`episodes/EP04/script.md`). This is the format of ref 11, with tool-assigned anchors:

```markdown
## 场1 经理办公室 · 日 · 第2天
【状态】刘军 受伤：右腿，跛行（昨夜，画外）
【画面】刘军撑着桌沿起身，右腿不敢吃力。
李树：军哥，你腿怎么了？ ^L012
刘军：（慢慢坐回，揉着右膝）昨晚去动李老三的场子，一组伤了不少人。 ^L013
刘军：不求你打赢。护住场子，等一组养好伤。 ^L014
```

**How the annotations work in this scene:**
- 刘军 was hurt off screen the night before, so the scene declares it once, at the top.
- 李树's gauze needs no annotation. The ledger carries it forward from the earlier scene where he was hurt (for example `【状态】李树 受伤：左额角（贴纱布）`).
- Nothing in this scene changes state, so nothing else is annotated.

**The shot plan** (`episodes/EP04/shots.yaml`):

```yaml
scene: 场1
defaults: {light: 暖白顶灯混合日间侧光, sound: 同期对白，低环境声, axis: 李树画左，刘军画右}
shots:
  - {id: S1, lines: [L012], size: 中景, who: [李树, 刘军], do: 刘军撑着桌沿起身，右腿不敢吃力；李树笑意收住}
  - {id: S2, lines: [L013], size: 过肩中景，刘军前景, who: [刘军, 李树], do: 刘军慢慢坐回，揉着右膝，抬头看李树}
  - {id: S3, lines: [L014], size: 近景, who: [刘军], do: 刘军盯着李树，手掌压在桌沿, tag: hook}
```

Optional per-shot fields are `dur`, `angle`, `move`, `transition` and `stage` (stage business). No state snapshots, visibility lists, reference lists or grouping prose are written by hand.

**Asset briefs** (`assets/briefs.yaml`):

```yaml
李树:   {kind: character, identity: 成年男子，短黑发，瘦劲结实, looks: {便服: 旧深灰T恤、深色长裤、旧鞋, 制服: 白衬衫、黑马甲、黑裤}, marks: 左臂青龙纹身，只在露出皮肤时可见, voice: 低沉，短句}
袭击者: {kind: crowd, count: 4, look: 深色夹克，平头，统一造型}
```

**Size of what is authored** [assume]:
- A 4-minute episode is about 4–6K characters of script plus 4–5K characters of shot plan.
- Today's boards are about 150K characters.
- That is more than an order of magnitude less to write, read and review.

### 8.3 What code derives

- Line anchors.
- The ledger (from the annotations), replay, and the state per shot.
- Visible entities and their appearance-relevant state.
- Durations:
  - from measured audio when it exists;
  - otherwise from the profile's planning rate (e.g. 5–6 characters per second for fast drama [assume]) plus allowances for action;
  - always overridable.
- The episode length against the format window (soft).
- Attention checks R1–R7 and must-keep coverage.
- Units, references, prompts, lint, cost.
- A readable storyboard table: time, shot size, action, dialogue, sound (the five columns of ref 10).

### 8.4 Commands

| Command | Does |
|---|---|
| `sf init <dir> --format <profile>` | Creates the series folder and `series.yaml`, and runs `git init` if git is available |
| `sf source add <file> [--chapters 1-14]` | Adds chapters and indexes their spans |
| `sf check [EP]` | Validates every authored file, replays the ledger, runs the R-checks, estimates timing, previews the reference budget and lints the prompts. **It reports and never blocks saving.** |
| `sf plan EP04` | Writes derived units, prompts, cost and a storyboard table |
| `sf show EP04 [--unit U03]` | Readable views |
| `sf bundle export` / `sf bundle import` | Interchange with the platform |
| `sf gen U03 --takes 2 --budget <n>` | Small generation through the shared adapter, with a journal. It requires an explicit budget. |
| `sf import-legacy <old project>` | Converts 1.2.x boards: shots become script lines and the shot plan; differences between consecutive states become events; entities become the bible; the registry becomes briefs |
| `sf doctor` | Versions, the capability profile, whether the platform is reachable |

### 8.5 Gates and review inside the Skill

- **Nothing blocks saving.**
- **`sf bundle export`** refuses errors, but not warnings.
- **`sf gen`** requires a budget.
- **The human gates are G1 (outline) and G2 (pilot script).** They are conversation checkpoints: the agent shows a compact view and records your decision in `decisions.md`.
- **Review is the two-stage cold read** from ref 06, done in a fresh context. It produces `notes.md` items with no lineage records.
- **The platform keeps the gates where money is spent** (G3, G5–G7).

### 8.6 From the old package to the new

| Today | Becomes |
|---|---|
| `SKILL.md` (21 KB) | Rewritten in 150 lines or fewer |
| refs 01, 10, 11 | `series-outline` and `script-format`. Keep almost everything except per-line cuts. |
| ref 02 | `pacing`: targets by format, measured dialogue, no tolerance-0 rule |
| ref 03 | `directing` |
| ref 04 | `continuity`, rewritten on the shared ledger |
| ref 05 | `generation-seedance`, plus the capability profile |
| ref 06 | `review`: the cold read and the rubrics. The lineage machinery is dropped. |
| refs 07, 08 | `contracts/` plus a short command list |
| ref 09 | `assets`, shared with the platform; layouts come from calibration |
| ref 12; `reference_contract.py` | Dropped. Replaced by derived resolution. |
| `core.py` lint | Lint rules in `sf_core`, rewritten for derived state |
| `prompt_renderer.py` | The `sf_core` renderer, driven by the glossary and with no global dictionaries |
| `grouping.py` | The `sf_core` packer (an optimizer, not a reviewer of hand-made groupings) |
| `drama.py` | The `sf_core` checks (kept) |
| `assets.py` | The platform's asset registry and the bundle's `assets/`; the Skill keeps the briefs |
| `review_lineage.py`; `store.py`, `migration.py` (fingerprints); approval files | Dropped. Replaced by git, `decisions.md` and data upgraders. |
| `storyboard.py` | Platform keyframes and animatic for hooks and payoffs; the receipt governance is dropped |
| FREEZE, PATCH, PROVENANCE, VALIDATION | Release notes in the repository, outside the Skill |
| 447 test methods | Contract and golden tests plus product evals (prompt lint, pacing distribution, calibration results) |
| Two toy examples | One representative multi-scene sample |

### 8.7 Your existing projects

Keep 1.2.6 installed **read-only** until `sf import-legacy` exists, and stop adding features or runtime versions to it.

The conversion is mechanical, because the old boards contain full snapshots: the events are simply the differences between consecutive states. Reviews, approvals and lineage are archived, not migrated.

Your converted episodes become the first regression fixtures of the new kernel.

---

## 9. Joint roadmap

**Step 0. Media test (about two days, 30–40 takes).** Do this before writing any new code.

1. **Face policy.**
   - Make masters for three characters in two looks: photoreal-generated and stylized realism.
   - Use both sheet layouts: the Skill's and the platform's.
   - Put each master in a 4–5 s Seedance unit.
   - Record whether it is accepted and whether the identity holds.
2. **Prompt dialect.**
   - Take six real units: 出狱后的我 EP04 U01, 仙界 EP01 U0401, 死后被契约 EP01 U010, plus three with props or action.
   - Render each with the 1.2.6 renderer and with the proposed rules, and generate two takes of each version.
   - Score identity, action adherence, cut placement, dialogue and artifacts.
3. **Reference token:** `@图片1` vs `图片1` on two units.

*Done when:*
- the capability profile, the asset sheet specification and the prompt dialect are written from evidence;
- you have a baseline first-take acceptance rate.

**Step 1. The kernel (1–2 weeks).**
- `contracts` v1.
- `sf_core`:
  - replay, extracted from the platform's `story_contract.py`;
  - the new packer, resolver and renderer;
  - lint.
- The capability profile from Step 0.
- `methods` v1, condensed from refs 01–03 and 09–11.
- The platform switches its prompt compiler and limit tables to the kernel. This also fixes D10, D12 and the planner part of D1.

**Step 2. One real episode end to end (2–4 weeks).**
- Build Skill v2, the bundle format and `import-legacy`.
- Convert 出狱后的我 EP04 and produce it through the platform: assets → smoke tests → generation → QC → assembly. It is a good first target:
  - modern setting;
  - few principals;
  - one fight;
  - an existing board to convert.

*Done when:*
- the episode is publishable;
- you have measured human minutes per finished minute, takes per accepted unit and cost per accepted second.

**Step 3. Series scale (1–2 months).**
- A ledger and story days that span episodes.
- Asset reuse.
- Batch production driven by the outline.
- Mode 3 for routine episodes.
- Metrics fed back into the methods.

**Track these from Step 0 onwards, in both front ends:**

| Area | Metric |
|---|---|
| Authoring | Authored characters per episode; time from chapters to first plan |
| Prompts | Prompt length; lint findings |
| Pacing | ASL and the shot-length distribution against the format; dialogue rate |
| Production | First-take acceptance; takes per accepted unit; cost per accepted second |
| Quality | Continuity defects per episode |
| Your time | Human minutes per finished minute |

---

## 10. Decisions only you can make

1. **Business model and delivery format.** Each option changes the outline template, the format profile, the length window and the location plates:
   - horizontal 3–5-minute series episodes, which is what your Skill runs produce;
   - vertical paid short drama of 1–2 minutes, which is the platform's default;
   - 推文 promotional clips;
   - a horizontal master plus vertical cuts.

   A dual delivery needs framing that is safe for both aspect ratios, from the asset stage onward.
2. **Look and face policy.**
   - If Step 0 shows photoreal faces are blocked, you choose between licensed portraits (火山剧创-style libraries [src]) and a stylized-realism look.
   - The choice changes every asset brief, so make it before Step 2.
3. **Audio.**
   - Seedance's native dialogue keeps the pipeline short.
   - TTS with lip-sync or dubbing gives consistent voices and real timing, and it is required if the same footage ships in several languages.
4. **Where you work day to day, and with whom.**
   - If you mostly work in conversation, invest in the Skill's views and the platform's command line.
   - If others will review media, invest in the platform's interface.
5. **Rights.** 推文 authorization tiers and keywords, or adaptation rights. This decides whether Mode 1's promotional path is a business or only a test bench.

---

## Appendix A. How the large fixtures were analyzed

**The tool.** `tools/skill_board_metrics.py` is read-only and uses only the standard library. Run `python tools/skill_board_metrics.py <board.json>` on any of your projects; add `--prompt` to measure prompt text instead.

**How each board metric is counted:**
- **Characters** are compact JSON with `ensure_ascii=False`.
- **"State share"** counts the start and end state of every shot.
- **"Keys about entities on screen"** uses each shot's declared `visible_entities`.
- **"No state change"** means the end state equals the start state.
- **The dialogue rate** is characters without punctuation divided by the declared window.

**How the prompt metrics are counted:**
- lines that list state;
- English tokens;
- a fixed list of author-, editor- and tool-facing phrases.

**Fixtures processed in full this way:**
- `prompt-usability/office/board.json` (出狱后的我 EP04);
- `compiler-projection/transition-projection/before-board-v3.json` (仙界 EP01);
- `compiler-projection/power-holdout/{temporary,depleted}.json` (仙界 EP03 SC04, EP01 SC01);
- `compiler-projection/power-label/fixture.json` (死后被契约 SC04);
- `novel-diagnoses/*.board.json`;
- `asset-state-guard/novel.board.json`.

**`runtime-1.2.4.zip`** holds the 1.2.4 scripts and schemas.
- The board schema is byte-identical to today's.
- `core.py` changed mostly because the renderer moved into `prompt_renderer.py`; `compile_prompt` now delegates to it.
- `store.py` also changed.

## Appendix B. Files read

| Group | Files |
|---|---|
| Top level (7) | `SKILL.md`, `README.md`, `FREEZE.json`, `LOCAL_WORKFLOW_PATCH_20261002.json`, `PROVENANCE.md`, `VALIDATION.md`, `SHA256SUMS.txt` |
| Agent and helpers (3) | `agents/openai.yaml`, `helpers/asset_state_guard.py`, `helpers/prompt_handoff_check.py` |
| References (12) | `01-story` … `12-asset-state-contract` |
| Schemas (4) | `adoption`, `board`, `review`, `source` |
| Scripts (15) | `assets`, `core`, `demo`, `drama`, `episode`, `grouping`, `install`, `migration`, `prompt_renderer`, `reference_contract`, `review_lineage`, `sdd`, `select_source`, `store`, `storyboard` |
| Examples (12) | `01-outlet/*`, `02-empty-chair/*`: board, lint, script, source, story, walkthrough |
| Evals (4) | `README.md`, `blind.py`, `cases.json`, `results.json` |
| Tests (18) | All 18 `test_*.py` modules |
| Fixtures (39) | Small and medium fixtures read in full, including the fixture README; the boards listed in Appendix A processed in full by script and read selectively; the 1.2.4 runtime zip diffed |
