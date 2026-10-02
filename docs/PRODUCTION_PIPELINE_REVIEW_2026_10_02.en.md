# StoryForge Studio — End-to-End Production Pipeline Review

*2026-10-02 · Branch `claude/youthful-shannon-ph0i3s` @ `ffd8dcf`*

**Scope.** This review covers the whole path from source material to a published, monetized Douyin/TikTok video, treated as one production system.

**Basis.**
- The current source: both workspaces and `studio/`.
- The 2026-09-29 design package and the 2026-09-30 addendum.
- Current public sources on Seedance, the Dreamina CLI, competing platforms and Chinese platform regulation (listed at the end).

**Not done.** No tests, app runs, model calls or paid generations were performed.

**Evidence labels.**
- `file:line` means I read it in the code.
- **[src]** means an external source.
- **[assume]** means an illustrative assumption.
- Everything else is my inference, argued as such.

Some regulatory details come from search summaries because the primary pages were unreachable from this environment. Verify the primary texts before acting on them.

---

## 0. Verdict

**Keep the engineering core.** The continuity ledger, the separation of candidates from adoption, impact previews, content-addressed invalidation, observed-vs-planned end states and paid-request safety are better than what most AI-drama tools do. Keep all of it.

As a production system for monetized short-form video, though, the pipeline has five structural problems. Each matters more than any single stage being slightly out of order.

1. **It optimizes the wrong objective.**
   - It is built to make each artifact correct and premium.
   - Short-form revenue is hit-driven: most titles lose money and a few earn most of it.
   - Nothing in the system decides *what* to make, publishes, measures audience response, or kills a losing series.
   - The learning loop learns the operator's preferences, not the audience's.
2. **It stops before a publishable video.**
   - Voice, dialogue audio, subtitles, music, the edit, cover and title, AI labels and registration metadata all live outside the system.
   - That is where most of the remaining human time goes.
   - The edit is also where retention is won or lost.
3. **Humans produce all the evidence.**
   - A person must review every reference image, mark every shot's in/out points, type every end state as JSON and confirm every paid batch.
   - The AI sequence review cannot remove any of that work. It is advisory only, and by construction it cannot pass a scene with more than six shots.
   - This is the throughput ceiling.
4. **The video model is treated as an executor, not as a constraint source.** Capabilities only enter at execution time.
   - The default generation-unit grouping produces requests that Seedance rejects. The system only discovers this after the user has confirmed the cost.
   - A bad take cannot be re-rolled in the unit path.
   - Prompts are a dump of internal fields, not Seedance's `@图片N` / time-coded format.
   - Voice is not an asset at all.
   - Meanwhile the model changed underneath the design. Seedance 2.5 shipped on July 31, 2026, with 30 s single-pass output, up to 50 references and audio-driven lip-sync [src].
5. **There is no series architecture.**
   - There is no Episode entity.
   - There is no outline of hooks, payoffs, cliffhangers or paywall positions.
   - Adaptation proceeds chapter by chapter. Short-drama adaptation means restructuring the story around payoffs, not compressing it linearly. You cannot pull a later reveal forward if you have not read it yet.

None of this requires discarding the architecture. It needs four additions:
- a market layer in front;
- a post-production and packaging layer behind;
- a layer in the middle where machines, not people, produce the evidence;
- a capability profile that flows *upstream* into writing, directing and asset design.

---

## 1. The eight steps as described vs. what the code does

| # | Your description | What the code actually does | Assessment |
|---|---|---|---|
| 1 | Extract main plot and subplots | Optional per-unit book reading. Each unit sees only the previous unit's summary. Aggregation just merges unique fields; there is no synthesis (`system-a/app/novel.py:164`). The default path skips this and adapts the selected chapter range directly (`novel.py:228`). | There is no global plot/subplot model. Adequate for novel-promotion openings, not for adapting a whole series. |
| 2 | Compress into a faster short-drama version | One call writes the short-drama script *and* the full continuity ledger for the range (`novel.py:267`). Format conversion in A is optional (`system-a/app/formats.py:185`). | Linear compression range by range, with no episode structure. |
| 3 | Lock the script | A adoption → `ScriptPackage-v1` → B import with an impact preview. B may not rewrite the story, add story props or invent intermediate states. It must file a change request back to A (`system-b/app/shooting.py:178`, `:496`). | A good lock on identities. Too strict at the staging level (§6.4). |
| 4 | Storyboard / shot list | Per-scene director plus independent LLM review. Ordinary scenes are adopted automatically. Chosen key scenes get two alternative approaches (`shooting.py:310–344`). | A text shot list only. There is no visual storyboard or animatic gate, and shot durations are model estimates rather than timed to the dialogue. |
| 5 | Extract assets *from the storyboard* | Assets actually come from the **script's event ledger before** storyboarding (`prepare_event_assets`, `shooting.py:560`, which `propose_director` requires at `:379`). Required image variants are recomputed from the adopted shots afterwards (`:548`). | Better than your description. Still misses set dressing, extras and the wardrobe plot, and ignores camera coverage. |
| 6 | Master and child images from shot coverage | A neutral master, plus appearance variants only for real appearance changes. Children derive directly from the master, one level deep (`shooting.py:616`, `asset_policy.py`). Every reference needs a human review with typed evidence (`shooting.py:690`). | The right taxonomy. Missing: location angle plates, voice, and automatic identity verification. |
| 7 | One Seedance prompt per shot | A deterministic per-shot compiler; per-shot prompts are concatenated into a multi-shot unit prompt (`system-b/app/cinema.py:128`, `shooting.py:805`). | Being deterministic is right. The prompt wording is not what Seedance responds to (D12, §6.9). |
| 8 | CLI upload and generation | Dreamina `multimodal2video`. The `submit_id` is persisted, results are queried and downloaded, and a missing ID is recorded as `state_unknown` (`system-b/tools/render.py:111–162`). A human marks per-shot intervals and adopts each unit. | Safe, but sequential, with no re-takes, no audio and manual reconciliation. |

---

## 2. What to keep

- **The authority model.** The program owns the facts. Model outputs are candidates. Adoption checks a plan hash and an impact preview.
- **The continuity ledger.** It records entities, initial state and events, and replays them deterministically (`story_contract.py:99`). It handles containment, visibility, open/closed, destroyed, and the difference between "unknown" and "known to be empty". Most AI-drama tools track none of this; it is the best foundation in the repository.
- **Source mapping.** The fate of every source block is recorded (kept, merged, deleted or rewritten, with a reason), so the adaptation is auditable.
- **Shots are separate from generation units** (`shooting.py:772`). This is correct and still uncommon.
- **Planned vs. observed end state.** Downstream continuity chains from the frame at the end of the *adopted interval*, not from the raw file's last frame (`shooting.py:703–741`).
- **Paid-request safety.** The submission is recorded before the call and the `submit_id` persisted from its response. `state_unknown` is explicit, and nothing is blindly resubmitted (`render.py:135–143`).
- **Content-addressed caching and dependency invalidation** across identities, shots, adoptions and strong links.
- **Epistemic honesty: unknown is never treated as pass.** Keep the principle, but separate the *evidence state* from the *acceptance policy* (§4.3).

---

## 3. Concrete defects to fix before scaling paid generation

### D1. Generation-unit duration rules are only checked at execution, after the user confirms the cost

- **Evidence:**
  - The planner checks only the maximum (`shooting.py:806–808`).
  - Dreamina requires a whole number of seconds between 4 and 15 (30 on 2.5) and rejects anything else (`render.py:118`).
  - The UI groups one shot per unit, or one event per unit (`studio-upgrade.js:198`).
  - The default fast-drama preset has an average shot length of 1.5–2.5 s (`cinema.py:10`, `production.py:50`). Single-shot units are therefore *always* under 4 s, and event units are usually a non-integer length.
  - The legacy single-shot path does check this (`production.py:450`); the recommended path does not.
- **Impact:** The default flow builds batches that fail after the user has approved the spend.
- **Fix:** Before the dry run, the planner should enforce the profile's bounds and whole seconds, pack shots automatically (§6.8) and pad units with edit handles.

### D2. A take cannot be re-rolled in the unit path

- **Evidence:**
  - The render key is `digest(inputHash, quality)` (`shooting.py:852`).
  - The runner returns the cached result for that key (`runner.py:50`, `:74`).
  - The seed is derived from `inputHash` (`:884`), and no seed is passed to Dreamina anyway.
- **Impact:** Re-running a unit returns the same file at "cost 0". A random bad result can only be fixed by changing the design.
- **Fix:** Add a `takeIndex` to the key and a take budget per unit. Keep the cache only for identical requests.

### D3. A batch aborts at the first failed unit

- **Evidence:** `ensure(result['status']=='ok')` sits inside the loop (`shooting.py:891`; the loop starts at `:870`).
- **Impact:** A single moderation rejection stops the rest of the batch.
- **Fix:** Record each unit's outcome, continue, and summarize at the end.

### D4. Execution is sequential

- **Evidence:** One unit runs at a time, and each polls for up to the 900 s timeout (`shooting.py:870–895`).
- **Impact:** A batch takes hours, and the account's concurrency goes unused.
- **Fix:** Submit and poll asynchronously, with a concurrency limit per account.

### D5. `proxy`/`final` quality does nothing on Dreamina, yet still forces a new paid take

- **Evidence:**
  - Quality only changes width and height (`shooting.py:883`).
  - Dreamina uses only the aspect ratio plus the configured model and resolution (`render.py:125`).
  - Quality is still part of the render key.
- **Impact:** Requesting "final" pays for a new random performance at identical settings.
- **Fix:** Map quality tiers to model and resolution. More fundamentally, see §6.8: re-rendering a generative video produces a new performance, not a sharper copy of the old one.

### D6. End-state images are sent as ordinary references

- **Evidence:**
  - When a shot's state changes within the shot, `event_manifest` adds `end_state` references (`shooting.py:641`).
  - Every resolved reference that has a file becomes an `--image` input (`:797–804`).
  - Seedance's multi-reference ("omni-reference") mode has no slot that means "end state".
- **Impact:** When a separate end-state image exists (an opened box, a changed costume, damage), the model may show the end state from the very first frame. These are the story-critical shots.
- **Fix:** Use the CLI's `frames2video --first/--last` [src], or describe the change in text and verify it afterwards. Never put an end-state image in the general reference pool.

### D7. The sequence review cannot pass a typical fast-drama scene and never reduces human work

- **Evidence:**
  - It samples at most 18 frames, which covers at most 6 clips (`sequence_review.py:78–79`).
  - Any shot left unobserved forces `passed=False` (`:150`).
  - `requiresHumanSequenceReview=True` is always set (`:156`).
- **Impact:** The AI review adds cost without saving any labor.
- **Fix:** Sample every shot boundary, and introduce policy acceptance (§4.3).

### D8. Humans type observed end states as raw JSON

- **Evidence:** States are keyed shot → entity → field (`studio-upgrade.js:191`, `script_input.py:91`).
- **Impact:** Slow and error-prone; impossible at series scale.
- **Fix:** Pre-fill the states from a vision model and detectors, show a structured diff against the plan, and confirm with one click.

### D9. There is no audio path

- **Evidence:**
  - The Dreamina profile hard-codes `audio=False` (`production.py:419`).
  - `multimodal2video` is called without `--audio` (`render.py:125`), even though the CLI supports it [src].
  - Dialogue goes into the prompt as text, so Seedance invents a fresh voice for every unit.
  - The dialogue check is therefore always "unknown".
- **Impact:** A character's voice changes from unit to unit.
- **Fix:** Make voice an asset and time shots to the recorded dialogue (§6.6, §6.8).

### D10. Capability limits are duplicated, and "verified" only means "configured"

- **Evidence:**
  - The limits are hard-coded in two places (`render.py:118–123`, `production.py:417–418`).
  - `capabilitiesVerified` is true whenever limits exist (`shooting.py:824`), and the Dreamina profile always sets them.
  - A public CLI guide lists `seedance2.0` and `seedance2.0fast` (4–15 s, 720p) but not 2.5 [src]. The code's 2.5 limits (30 s; 30 images, 10 videos, 50 inputs) are therefore unverified.
- **Impact:** The two copies can drift apart, and wrong limits can pass silently.
- **Fix:** Keep one versioned capability profile, checked by a calibration suite (§6.9).

### D11. Recovering from an unknown submission state is manual

- **Evidence:** `render.py:143` stops and asks for manual reconciliation. The CLI has `list_task` [src].
- **Impact:** Operator work, plus a risk of paying twice for the same request.
- **Fix:** Reconcile automatically: list the recent tasks in the submission time window and match on the prompt hash.

### D12. Internal data leaks into prompts

- **Evidence:**
  - The change description `deltaString` is built from raw state dictionaries (`shooting.py:614`).
  - Keyframe prompts embed canonical JSON, including entity IDs (`cinema.py:153`).
  - Lighting is written numerically, e.g. "key light at 45 degrees, ratio 4:1" (`:140`).
  - Every reference gets a multi-line "Do not inherit…" list, repeated for every shot in the unit (`:137`).
- **Impact:** The model's attention is diluted. Negative phrasing tends to prime exactly what you are trying to exclude. IDs may even be rendered as on-screen text.
- **Fix:** A compiler that writes prompts in the form Seedance responds to (§6.9).

### D13. The remote-recovery endpoint is miswired (your item R16)

- **Evidence:** `recover_remote` is nested inside `asset_render` instead of being a service method.
- **Impact:** The recovery endpoint cannot reach its logic.
- **Fix:** Move it to a proper method and add a route-level test.

### D14. Text-model throughput is capped at one call at a time

- **Evidence:** `codex_cli` concurrency is set to 1 (`studio/settings.py:43`), on top of persistent sessions.
- **Impact:** Direction and review for every scene, across the whole platform, run one after another.
- **Fix:** See §6.13.

---

## 4. The strategic problems in detail

### 4.1 The objective should be portfolio economics, not perfecting each artifact

AI's real economic advantage is that variation is cheap. The operating model that exploits it is a portfolio: many cheap tests, selection based on audience data, and investment only in the winners. Both of your target businesses already work this way:
- Novel-promotion (推文) creators run many titles, each with personal search keywords, and keep whatever converts [src].
- Short-drama platforms run "horse races" (赛马) between titles on their early metrics.

What the system therefore needs:

- **An opportunity and rights stage before A:**
  - source selection;
  - authorization (推文 authorization comes in tiers, and keywords are issued per promoter [src]);
  - the target platform and monetization model;
  - a format specification;
  - a budget envelope.
- **A pilot fast path.** Produce the hook, the first episode or a trailer quickly. Publish it or test it as an ad, then decide whether to continue.
- **Publishing and metrics ingestion:**
  - 3- and 5-second retention;
  - completion rate;
  - the swipe-away curve;
  - follows;
  - keyword searches;
  - paid conversion.
- **A tiered quality target.** Be excellent at hooks, payoffs (爽点) and cliffhangers (卡点); everywhere else, aim for "does not lose the viewer". Uniform premium quality spends money on footage nobody judges.

**Edit variants are almost free.** With automatic assembly you can cut three different hook variants from the *same* footage, for example by opening on a flash-forward of the climax. Your `presentationPlan` already supports `preview` for this. A/B-testing hooks then costs editing time, not generation spend.

### 4.2 The last mile is outside the system

One community guide estimates a 3-minute AI comic drama (漫剧) at about 160 human-minutes: roughly 40 in post-production and 60 in generation [src]. Ending at "a production package for external editing" makes an editor the throughput ceiling. It also leaves the decisions that matter most for retention unmeasured.

**Add automatic assembly per episode**, producing:
- the adopted intervals on a timeline;
- the locked dialogue audio;
- burned-in subtitles generated from the script lines and aligned with speech recognition;
- music and sound-effect beds, with loudness normalization;
- the cover, the title, the visible AI label and the embedded metadata label.

Export an editable timeline (OTIO, FCPXML or a 剪映/CapCut draft) for optional human polish. `assembly.py` already does FFmpeg assembly with subtitles, audio buses and a still-frame animatic, so extend it rather than replace it.

**Labeling gotcha.** FFmpeg re-encoding strips the provider's embedded AI-content metadata. The Chinese labeling rules require such metadata (GB 45438-2025), so **re-apply it at export** rather than assume it survives [src].

### 4.3 Trust built on typing does not scale

The principle is right: "unknown" is not "pass", and a person stays accountable. The implementation is wrong: the person has to *produce* the evidence.

Invert it. Let machines produce the evidence:
- shot-boundary detection proposes each shot's interval;
- face-identity embeddings compare every take against the approved master;
- speech recognition checks the spoken lines against the script (character error rate, CER);
- OCR catches garbled on-screen text;
- a vision model extracts the observed state and diffs it against the plan.

Humans then attest by exception, backed by sampling audits.

Keep two separate fields:
- **Evidence state** per dimension: `pass`, `fail` or `unknown`. Never inflate it.
- **Acceptance decision:** `auto-accepted under policy P`, `human-accepted`, or `rejected`.

A policy may accept *unknown* on low-risk dimensions, such as background props in an ordinary scene. The residual risk is recorded, and audits measure each policy's real error rate. This keeps the system honest and removes the bottleneck.

### 4.4 The model must shape the design, not just execute it

The current design puts the model behind a profile at the very end. In practice, the model's real behavior should feed back upstream:

| Stage | What the model's behavior should shape |
|---|---|
| Writing | How many characters speak per scene; avoiding crowd action and fine hand work |
| Look development | Face policy and the choice of visual style |
| Directing | Which shot types and camera moves work; how many cuts fit in one unit |
| Packing shots into requests | Duration granularity; reference budget |
| Prompting | The model's own prompt conventions |
| QC | The known failure modes of that model version |

And the model changes. Seedance 2.5 [src] moves the best unit size from "one beat" to "a whole dialogue scene", and it makes local editing a repair option instead of full regeneration. That is why capability must be a versioned, calibrated artifact (§6.9), not two hard-coded tables.

### 4.5 There is no series architecture

"fast_drama" is a tone, not a format. Without an Episode entity you cannot plan, validate, assemble, publish or measure any of:
- episode length windows;
- the hook in the first seconds;
- payoff density;
- the cliffhanger;
- paywall positions.

Chapter-by-chapter adaptation also cannot restructure the story. The `outsideScope:true` flag for reveals in unread text admits as much, honestly. That is fine for novel promotion, which only needs the opening. A 60–100-episode series needs a global source bible and an episode outline *before* any episode is scripted.

---

## 5. Target pipeline

```
M0 Opportunity & rights ─► S1 Source bible ─► S2 Series architecture ══G1══►
S3 Episode scripts (rolling waves) ══G2══►
P1 Breakdown ─► P2 Look-dev · casting · voices · calibration ══G3══►
P3 Dialogue audio (locked voices) ─► D1 Directing & shot list (timed to audio) ─►
D2 Animatic / keyframes ══G4══► D3 Coverage derivatives (plates, looks, states) ─►
G1 Generation planning (packing · mode · prompt format · take budget) ══G5══►
G2 Generation + machine QC + best-take selection ══G6 (exceptions)══►
E1 Auto-assembly per episode ══G7══► E2 Packaging · labels · registration ══G8══►
M1 Publish & measure ─► M2 Learn (patterns, rules, continue/kill) ─► back to M0 / S2
```

Episodes are pipelined: episode *n* can be in generation (G2) while episode *n+3* is still being scripted (S3), as in TV production.

| Stage | Output | LLM does | Code / ML does | Gate |
|---|---|---|---|---|
| M0 Opportunity & rights | Series brief, format spec, budget envelope, rights record | Assesses the source's hook potential and comparable titles | Rights and keyword registry, budget model | **Human:** green-light |
| S1 Source bible | Characters, relationships, world rules, timeline, inventory of payoff moments, subplots, all with evidence spans | Per-unit reading **plus a global synthesis pass** | Chunking, evidence spans, merging duplicate entities | Automatic |
| S2 Series architecture | Adaptation strategy; episode outline (hook / escalation / payoff / cliffhanger); paywall plan; merged cast; location budget | Restructures the story | Soft checks against the format spec; episode-length estimates | **G1, human:** the highest-leverage decision |
| S3 Episode scripts | Script, scene intents, story ledger | Writes; then extracts the ledger in a second pass (§6.3) | Replay, ID stability, dialogue coverage | **G2:** automatic; human read-through for the pilot episodes, sampled afterwards |
| P1 Breakdown | Cast and extras; wardrobe plot by story day; story props vs. set dressing; sets and locations; sound effects | Extracts the items | Deduplicates, normalizes, merges into the asset bible | Automatic |
| P2 Look-dev and casting | Style frames; character, voice and location masters; calibration report | Writes design briefs | Runs a short Seedance smoke test for each master; identity embeddings | **G3, human:** once per series |
| P3 Dialogue audio | One TTS take per line in the locked voice; measured durations | — | TTS, duration measurement | Automatic, with spot listening |
| D1 Directing | Shot list timed to the audio; coverage plan (camera setups) | Directs | Timing feasibility; axis and eyeline rules | Automatic; human for key scenes |
| D2 Animatic | Keyframes or a storyboard grid, assembled with the audio | Writes keyframe prompts | Assembly | **G4:** pilot and key scenes |
| D3 Coverage derivatives | Location plates per camera setup; looks; prop states | Writes briefs | Resolves what is required; verifies identity | Automatic; exceptions go to a human |
| G1 Generation planning | Generation units, modes, prompts, take budgets | Optional "keep these together" hints | **Constraint packing; budget computation** | **G5:** approve the budget envelope once per episode |
| G2 Generation and QC | Scored takes; selected clips | Vision-model state observation | Async execution, shot detection, embeddings, speech recognition, OCR, automatic re-takes | **G6:** exceptions only |
| E1 Assembly | Episode cut plus an editable timeline | Optional pacing critique | Assembly, subtitles, loudness, pacing metrics | **G7:** watch the episode (1.5× speed is fine) |
| E2 Packaging and compliance | Title, cover, tags, keyword overlay, AI labels, registration fields | Titles and descriptions | Labels, metadata, content screening | **G8:** compliance |
| M1–M2 Market loop | Posts, metrics, experiments, decisions | Summarizes what worked | Ingests and attributes metrics | **G9:** continue or kill (data plus a human) |

---

## 6. Answers to your specific questions

### 6.1 Is the order of the stages correct?

The core order is right: story → script → shots → assets → prompts → generation. Five reorderings:

1. **Series architecture comes before scripts.** Outline the whole series before writing any episode in detail.
2. **Look development, casting and voice run in parallel with scripting,** not after the storyboard.
   - The protagonist's face and voice are the IP.
   - They take the longest to settle.
   - They decide what is feasible. Seedance blocks photorealistic face references [src], so whether characters are photoreal or stylized must be settled before any master is approved.
3. **Dialogue audio comes before final shot timing,** because dialogue determines duration. Animation records voices before animating for exactly this reason.
4. **An animatic comes before video.** It is the cheapest place to find pacing and clarity problems.
5. **Generation planning is its own stage,** between the storyboard and the prompts. You are not prompting individual shots; you are packing shots into model requests.

### 6.2 Is any important stage missing?

In order of business impact:
1. Opportunity and rights.
2. Series architecture: episode outline, hooks, cliffhangers, paywall.
3. Publishing, analytics, and learning from the audience.
4. Automatic assembly and packaging: subtitles, music, cover and title, labels.
5. Voice and dialogue audio.
6. Machine quality checks.
7. Look development with model calibration.
8. Script breakdown: set dressing, extras, wardrobe plot.
9. Animatic / keyframe gate.
10. Generation planning.
11. Compliance and registration.

### 6.3 Should some stages be merged or split?

- **Split "extract the plot" in two:** faithful *source analysis*, and the creative *adaptation strategy*. They succeed by different criteria; today they share one call per range.
- **At scale, split script writing from ledger extraction.**
  - **The problem today:** one call must produce creative prose *and* a precise state ledger for the whole range. Any replay failure forces a full repair round.
  - **The alternative:**
    - The writer produces the script with light event annotations.
    - A cheaper extractor builds the ledger scene by scene, and replay validates each scene.
    - A reviewer checks the ledger against the prose for omissions.
    - Editing the prose then only re-extracts that one scene.
  - **The trade-off:** the writer is no longer accountable for state. Keeping the coarse events in the writer's output limits the damage.
- **Merge** "extract assets" and "determine masters and children" into one deterministic step that resolves asset requirements from the breakdown plus the shot list. The LLM only writes design briefs.
- **Keep** compiling and executing separate, as the code already does. Compiling is pure and cacheable; executing has side effects and costs money.
- **Split "generation"** into plan → compile → execute → check → select.

### 6.4 Should the script really be locked before storyboard generation?

Yes, but lock *identities and structure*, not every word. Put the hard lock where costs jump, not at a stage boundary.

**The reason is the cost of a change** (order of magnitude, [assume]):

| When the change is made | Relative cost |
|---|---|
| Script | 1 |
| Shot list | 2 |
| Animatic | 3–5 |
| Asset identity | 5–20 |
| Generated video | 50–200 |
| Fixed in the edit instead | 5–10 |

So text and boards should stay fluid until just before video.

Film and TV "lock" a script by freezing scene numbers. Revisions still flow afterwards, through colored revision pages and inserted scene numbers such as 12A. Your stable IDs and impact previews already provide that mechanism.

**Use three lock levels:**
- **L1, structure lock:** freeze the episode outline before detailed scripting.
- **L2, script freeze:** per episode, before directing. Story-level changes go through A; *staging-level* changes belong to B.
- **L3, generation lock:** per scene or episode, before paid video. After L3, prefer fixes in the edit: trims, cutaways, reordering within the plan.

**The rule that will hurt most in practice is the ban on the director adding props or intermediate states** (`shooting.py:496`). A cup set down or a phone picked up is *stage business*, not story. Add a staging ledger owned by B:
- It is scoped to one scene and holds non-causal props and in-between states.
- It must start from the story state at scene entry and end at the story state at scene exit, unless it explicitly promotes a change.
- Only promoted changes go back to A.

Without this, most director proposals become round-trips to A: rewrite, user adoption, re-handoff, re-import.

### 6.5 Should assets come from the script, the storyboard, or both?

Both, plus a third source.

- **The script breakdown says *what exists*.**
  - Use the standard production categories: cast, extras, wardrobe, props (story props vs. set dressing), sets and locations, vehicles, animals, makeup and injuries, sound effects.
  - The breakdown stays the same whichever directing approach is chosen, so look development can start early.
  - Today's extraction (event participants, locations and changed entities) misses set dressing, extras and the wardrobe plot, as your own R07 notes.
- **The storyboard says *what is seen, and from where*:**
  - which assets are visible in each shot;
  - the camera setup and the direction it faces;
  - the scale (a close-up needs face detail);
  - each asset's state at that moment.

  This drives the derivatives: location plates per facing, the looks that are actually seen, and the prop states that are actually seen.
- **The generated media says *what was actually produced*.**
  - Adopted takes contain things nobody planned, such as a vase the model added to the background.
  - Once a take is adopted, that vase is canon for the next shot from the same setup.
  - Record a per-setup registry of what was actually generated (a key frame plus the detected objects) and feed it to neighbouring units. Otherwise continuity of these invented details breaks between cuts.

### 6.6 Is "master image → child image → shot reference" right for AI video?

Mostly. Keep deriving every child directly from its master, one level deep; the code already does this (`parentVariantId` is the master, `shooting.py:616`). Refinements:

1. **Verify identity automatically.** Compare face embeddings of each child, and of each generated take, against the master, and reject anything below a threshold. Today the only check is a human typing text.
2. **Separate identity from look when the budget allows.** That means a character × outfit matrix, keyed by story day. When reference slots are tight, keep your combined sheet. For close-up-heavy units, add a dedicated face close-up: in a 2×2 sheet each view gets only a quarter of the resolution.
3. **Derive locations from the coverage.**
   - One empty, high-angle 16:9 overview (`asset_policy.py:64`) is a good *layout* master.
   - It cannot support shot/reverse-shot. The model invents the reverse background differently every time, and tends to copy the reference's high camera angle.
   - Derive **eye-level plates for each camera setup**, in the delivery aspect ratio (9:16), from the overview, plus time-of-day variants.
4. **Add a composed keyframe for high-risk shots:** several characters, prop interactions, payoff moments.
   - One image is far cheaper than a video take.
   - It lets you approve composition and state before the expensive step.
   - It gives an exact start state.

   Ordinary shots can use references only.
5. **Never put end states in the general reference pool (D6).** Use first/last-frame mode, or describe the change in text and verify it.
6. **Manage the reference budget, not just the limit.**
   - Seedance 2.0 accepts 9 images, 3 videos and 3 audio files.
   - Community testing finds reliability drops beyond about 6–7 references [src].
   - Send the fewest references that cover the unit, and state each one's role once (§6.9).
7. **Treat the face policy as a design input.**
   - Since the February 2026 relaunch, photorealistic faces are blocked as references across ByteDance's channels, reportedly including some photoreal AI-generated faces (reports vary) [src].
   - The sanctioned route to photoreal characters is a licensed portrait library. Volcano Engine's 火山剧创 (Huoshan Juchuang) 1.0 ships "real and virtual portrait libraries" for licensing [src].
   - **Smoke-test every master in a 4-second Seedance unit before approving it.** Otherwise you can approve a beautiful photoreal sheet from the image model and have it rejected at video time.
8. **Make voice an asset:** one approved, clean voice reference per character.
   - Use it for TTS, or as an audio reference so Seedance lip-syncs to it.
   - Seedance 2.5 supports audio-driven lip-sync. Its guidance for consistent voices is exactly this: one approved reference per character plus consistent speaker labels [src].

### 6.7 How should continuity and state be tracked across shots?

- **Two ledgers.**
  - The *story ledger* (owned by A) holds cross-scene, protected facts.
  - The *staging ledger* (owned by B) holds in-scene intermediate states and stage-business props.
  - Replay validates both, and the two must agree at every scene entry and exit.
- **Story days.**
  - Add `storyDay` and `timeOfDay` to each scene.
  - Key wardrobe, hair, makeup and injuries to the pair (character, story day).
  - The default rule becomes "same look within a story day", which removes most of the wardrobe events the LLM currently has to declare one by one.
- **A continuity sheet per shot:**
  - screen side, eyelines and axis (these already exist);
  - which hand holds what;
  - hair state;
  - wetness or dirt;
  - background elements;
  - weather.
- **Three versions of state.**
  - *Planned*: what the ledger says.
  - *Requested*: what the compiled unit asked for.
  - *Observed*: what the take shows, extracted by machine and confirmed through a diff rather than typed.
- **Unit-boundary checks for cuts that are not frame-chained** (most of them). Compare the last frame of take *n* with the first frame of take *n+1* in the same scene for identity, wardrobe colour, background plate and lighting.
- **Repair through the edit.** A cheap reaction shot or cutaway can hide a continuity break that would otherwise cost a full regeneration. That is standard editorial practice; make it a first-class repair option.

### 6.8 Should storyboard shots and AI-video generation units be separate concepts?

Yes, and add more layers:

**Event → Shot (editorial intent) → Generation unit (one model request) → Take (one result) → Clip (an interval mapped to a shot) → Timeline (final timing)**

The relationships are many-to-many. One unit covers several shots; a long shot can span several units through extension; one shot can be covered by several takes.

#### Packing shots into units is a job for code, not an LLM

It is a segmentation problem over the ordered shot list.

- **Constraints:**
  - a whole number of seconds from 4 to 15 (30 on 2.5), including handles;
  - the reliable reference budget;
  - the same set and continuous time;
  - no more cuts per unit than calibration shows the model handles;
  - at most one hard dependency on another unit;
  - compatible generation modes.
- **Cost:** seconds generated × price, plus penalties for risk and for reference count.
- **Solver:** dynamic programming, linear in the number of shots (times a small constant).
- **Handles:** add 0.5–1 s before and after each shot; rounding up to whole seconds pays for them anyway.
- **Prompt timing:** emit cumulative time segments ("0–3s", "3–7s").

#### Generate coverage by camera setup, not shots in story order

This is the most important generation-strategy idea in this review. Live-action crews shoot by camera setup: all of A's coverage, then turn the camera around for B. The AI equivalent depends on the kind of scene.

- **Dialogue scenes**, which are most of a short drama's runtime:
  - **Method:**
    - With the dialogue audio locked, generate the *whole* scene once per setup: A's side in medium close-up, B's side, and a wide shot.
    - Give each setup an audio track containing only its on-camera speaker's lines. Replace the other lines with silence and keep the timing, so nobody lip-syncs someone else's lines.
    - Automatic assembly then cuts between setups by rule: the speaker is on camera; reactions land on punchlines.
  - **Benefits:**
    - Backgrounds stay consistent within a setup.
    - The edit gets real coverage to choose from.
    - Shot timing no longer depends on the model cutting exactly where the storyboard said.
  - **Feasibility:** Seedance 2.5's 30-second units and audio-driven lip-sync make this practical.
  - **Calibrate before relying on it.** Lip-sync to a given audio track should be repeatable; body movement will not be.
- **Inserts, cutaways and establishing shots:**
  - Batch them by setup into one unit and cut them apart later.
  - Your contiguity rule currently forbids this ("a generation unit cannot skip over shots that play in between", `shooting.py:786`). Relax it for shots that do not depend on any state change between them.
- **Action and state-change sequences:** contiguous multi-shot units, anchored with first/last frames and chained frame to frame.
- **Hooks and payoffs:** keyframe first, more takes, and a human gate.

#### What "proxy" and "final" should mean (D5)

- **In CG**, you approve a proxy and then render a final of the *same* performance.
- **In generative video**, a "final" re-generation is a *new* performance that has to be reviewed again.

So:
- the proxy is the animatic or the keyframes;
- the approved take *is* the final;
- "final quality" means upscaling or enhancing that take without changing its content, not re-rolling it.

### 6.9 Where should model capability constraints enter the workflow?

At five points, all fed from **one versioned capability profile**. The profile holds:
- the model and its version;
- hard limits;
- the reliable reference count;
- the prompt format the model expects;
- supported modes;
- known failure modes;
- calibration results.

| Entry point | What the profile contributes |
|---|---|
| S2/S3 writing | A producibility budget per episode: speaking characters per scene, plus an allowance of "hard shots" (crowds, fights, fine hand work, on-screen text, liquids, physical contact). Don't sanitize the drama; *price* it. |
| P2 look development | Face policy, which styles are feasible, the reference-sheet formats |
| D1 directing | Shot types and camera moves that work, lip-sync reliability by shot size, cuts per unit |
| G1 planning | Hard limits, reliable budgets, modes, price, concurrency |
| G2 quality checks | The failure-mode checklist for this model version decides which detectors run |

**How to write prompts for Seedance.** Community practice [src]:
- Name each reference's role once: `@图片1 是女主林晚的身份参考` ("@image1 is the identity reference for the heroine Lin Wan"), `@图片2 为场景` ("@image2 is the set").
- Use time-coded segments for anything longer than about 8 seconds.
- Keep subject-verb-object sentences short.
- Phrase things positively.

Replace the per-shot "controls only… / do not inherit…" lines and the numeric lighting with that. Also check exactly how the CLI expects references to be written in the prompt; the code currently writes `参考图 N` ("reference image N").

**Calibration.** Keep a fixed suite of 20–40 representative units: a two-person dialogue, a prop handover, a costume change, a walk-and-talk, a reverse shot. Run it on every model or profile change, and record the success rate per shot type. Moving from Seedance 2.0 to 2.5 is exactly such a change.

### 6.10 Which parts belong to the LLM, and which to deterministic code?

**The LLM handles language and judgment:**
- source synthesis, adaptation strategy, the outline;
- the script, dialogue and scene intents;
- directing choices and design briefs;
- critique against a rubric;
- observing state in frames via a vision model, as a producer of evidence, not the judge of record;
- titles and descriptions.

**Code and specialist ML handle anything counted, timed, matched, packed or verified:**
- ledger replay, ID stability, invalidation and caching (already code);
- dialogue duration via TTS, and timing feasibility;
- packing shots into units, packing references, compiling prompts;
- budget envelopes, scheduling, rate limits, submission and reconciliation;
- shot-boundary detection, face embeddings, speech recognition and CER, OCR;
- loudness, subtitles, assembly;
- embedded labels and C2PA credentials, content screening, analytics.

**Hybrid work:**
- The LLM tags beats as hook, payoff or cliffhanger; code assigns the review tier.
- The LLM extracts breakdown items; code deduplicates them.
- Detectors and a vision model produce scores; code decides whether to auto-accept, re-take or escalate.

**Two cautions:**
- **A reviewer from the same model family shares the author's blind spots.** Use a different model family or a human for high-leverage gates, and deterministic validators for routine ones.
- **You are optimizing the cheap part.**
  - Session continuity, deltas, checkpoints and three cache layers mostly save text-model calls. Those cost cents each on an API, or quota on a subscription.
  - The expensive resources are video takes (dollars each) and human minutes [assume].
  - Spending *more* LLM effort to raise the share of video takes that are usable the first time is the economically rational trade.

### 6.11 Where should validation, rollback, retry and approval gates exist?

**Put human gates on taste and on irreversible spend:**
- G1, the outline;
- G3, cast, voice and style;
- G4, the animatic for the pilot;
- G5, the budget;
- G7, watching each episode;
- G8, compliance;
- G9, continue or kill.

Everything else is validated by machine, and only exceptions go to a person.

**How much humans review:** 100% of the pilot episodes. After calibration, 10–20% sampled, plus everything flagged.

**Retry policy by failure class:**

| Failure class | What to do |
|---|---|
| Transient (timeout, 5xx, failed download) | Query and download the same `submit_id`. Never resubmit before reconciling via `list_task`. |
| Moderation (face detected, content flagged) | No blind retry. Route to remediation: stylize the asset or rephrase the prompt. |
| Random bad result (artifacts, wrong action) | Re-take automatically within the take budget (D2). |
| Not producible as designed | Automatically suggest a simplification (split the unit, change the shot size, drop the hand interaction) and send it to B. |
| Story problem | Back to A. Rare after the generation lock. |
| Systematic (the same failure across many units) | A circuit breaker per model/profile, plus an alert. |

**Rollback** is just moving a pointer. Never delete takes; keep the adoption history for each episode.

**Approve budgets, not batches.**
- Approve one envelope per episode: units × expected takes × price.
- Inside the envelope, retries happen automatically. Exceeding it needs approval.
- This conflicts with your current rules ("no automatic paid retries; no cumulative cap"), and I think those rules should change. Today the human *is* the scheduler.

### 6.12 How do you avoid rerunning the whole pipeline when one shot, asset or prompt fails?

You are mostly there. The gaps:
- **Re-takes (D2).** Today a single bad unit can only be fixed by changing the design upstream, which is exactly the rerun you want to avoid.
- **Per-unit failure isolation (D3).**
- **Repair without regenerating:** local editing on Seedance 2.5 [src], video-to-video fixes, and editorial cutaways.
- **Narrower invalidation.**
  - An identity change should invalidate only the units where that character is *visible*.
  - A plate change should invalidate only the units that use that plate.
- **An explicit artifact graph.**
  - Your hashes and impact plans already form an implicit build graph; make it explicit, with each artifact a function of its inputs and the version of the recipe that made it.
  - That gives you "why is this stale?" explanations, parallel scheduling, and partial rebuilds from any node.

### 6.13 How do you make the system suitable for large-scale automated production?

**First, decide your target tier.**

| Tier | Output | What it implies |
|---|---|---|
| T1, solo | 1–3 series a month | The current local design is fine. |
| T2, studio | 10–30 series a month | Needs everything listed below. |
| T3, factory | 100+ series a month | Also needs multi-tenant operations. |

The data-model choices you make now set the cost of migrating later.

**For T2:**
- **Durable workflows** (Temporal or Hatchet, or at least Postgres plus a worker queue) instead of the in-process thread pool and SQLite.
- **Object storage for media.**
- **Pools of provider accounts.** Several Dreamina accounts, or the Volcano Engine API for enterprise concurrency and service guarantees. Check balances with `user_credit` [src].
- **Asynchronous submission and polling,** rate-limited per account.
- **Stateless, fully specified LLM calls** instead of persistent CLI sessions.
  - When the context is built purely from stored artifacts, outputs are reproducible and calls can run in parallel.
  - Provider prompt caching of the stable prefix (method packs, the bible) recovers most of what sessions saved.
  - Batch APIs suit analysis that isn't urgent.
  - Sessions also carry the anchoring risk your own Q8 worries about.
  - If you stay on a subscription CLI, confirm its terms allow automated batch production.
- **Team roles:** writer, director/reviewer, QC operator, editor, publisher.
- **Reusable libraries.**
  - Keep "standing sets" (CEO office, villa, hospital and banquet hall recur across the genre), the way studios reuse backlots.
  - Keep series bibles.
- **Observability per stage:**
  - throughput;
  - first-pass success rate;
  - cost per accepted second;
  - human minutes per finished minute;
  - rework by cause.

### 6.14 Where are the bottlenecks likely to be?

**A rough model for one series** [assume, illustrative]:
- 60 episodes × 90 s = 5,400 s of finished footage.
- 1.4× more video generated than used (handles and rounding).
- 2.5 takes per accepted unit (40% first-take acceptance).
- 12-second units.

| Quantity | Estimate |
|---|---|
| Video generated | 5,400 × 1.4 × 2.5 ≈ **18,900 s, or about 1,575 takes** |
| Generation wall time | About 5 minutes per take on 4 concurrent slots ≈ **33 h**. Sequential execution (D4) makes it about 4× that. |
| Human review, current design | Watch each take, mark each shot's in/out points, type evidence and states: 3–4 minutes per take ≈ **about 90 h per series** |
| Human review, with machine evidence and exception-only review | ≈ **10–15 h** |
| Video spend | About 3.5 × price per second × finished seconds |

Raising first-take acceptance from 40% to 60% cuts video spend by about a third. Keyframe gates and calibration are the main levers.

**Ranked bottlenecks:**
1. Human media review and annotation.
2. The share of takes that are usable, plus moderation rejections.
3. Post-production outside the system.
4. Round-trips from B back to A for changes.
5. LLM calls running one at a time (concurrency 1, review and repair loops).
6. Approving reference images by typing evidence.
7. Confirming the cost of every batch.
8. Rework caused by inconsistent voices.
9. Lead time for registration.
10. Understanding long novels (a quality bottleneck rather than a throughput one).

### 6.15 What do community and market practice suggest?

- **The model vendor has already productized the plumbing.**
  - Volcano Engine's 火山剧创 1.0 (May 2026) runs script parsing → series-wide asset setup → storyboard video generation → preview and merge, editable at every step.
  - It adds licensed real and virtual portrait libraries and team credit allocation, and it claims production cycles more than 80% shorter [src].
  - **So don't compete on the "script → assets → shots → video" plumbing.** Compete on what it doesn't do well:
    - adaptation intelligence;
    - continuity rigor;
    - the market feedback loop;
    - automation at volume;
    - routing across several models.
  - Consider using its APIs as an execution backend.
- **How prompts are written:** `@` role assignment, time codes, concise structure [src].
- **First frames and storyboard grids.**
  - "The first frame decides the shot" is common wisdom.
  - Multi-panel grids (九宫格) generated as one image keep characters consistent across panels.
  - Crop the panels into first frames, or feed the whole grid in as a sequence reference.
  - Worth adding to the animatic (D2) toolset.
- **Episode structure:** hook → development → reversal → ending. Shot tables list segment, picture, dialogue, shot size, camera move and emotion [src]. Your fields cover most of this; what is missing is the *episode* itself.
- **How novel promotion (推文) works:** authorization tiers and personal keywords; the video exists to hook viewers and drive them to search for the keyword [src]. That calls for a **lightweight novel-promotion profile**:
  1. Take an excerpt.
  2. Write a hook-first script (use `preview` for the flash-forward).
  3. Apply fewer gates.
  4. Assemble automatically with the keyword overlay.
  5. Publish.
  6. Iterate on the hooks.
- **Regulation in China, 2026:**
  - AI labeling has been mandatory since 2025-09-01, both visible and embedded, and publishers must declare AI content before posting [src].
  - AI comic dramas (漫剧) have had to be **registered before going online** since 2026-04-01 [src].
  - The *Micro-Short Drama Development Management Measures* (微短剧发展管理办法), in force since 2026-09-01, add AI-labeling and anti-addiction provisions, with tiered review [src].
  - Registration may require the complete series before release, which limits a pilot-first strategy. Confirm with the platform.

---

## 7. Compliance as a pipeline stage

- **Rights:**
  - Source authorization: the 推文 tier and keyword, or adaptation rights.
  - **Likeness provenance** for every character master: generated or licensed, never a real person.
  - Voice provenance: no cloning without consent.
  - Music licenses.
- **Labels:**
  - A visible on-screen AI label.
  - Embedded metadata, re-applied after assembly (§4.2).
  - For international posts, TikTok's AI-generated-content label and C2PA content credentials.
- **Registration:** the registration (备案) fields for each series, the review tier, and the registration ID shown in the packaging.
- **Content safety:** screen prompts *before* generation, which is cheaper than moderation failures, and screen outputs *after* it.

---

## 8. Data model additions

| Entity | Holds |
|---|---|
| `Series` | Format spec, platforms, budget envelope, rights, registration |
| `Episode` | Beats, hook, cliffhanger, paywall flag, lock levels |
| `StoryDay` | Story-day grouping that wardrobe, makeup and injuries are keyed to |
| `StagingState` | B's scene-scoped stage-business props and in-between states |
| `VoiceAsset` | One approved voice reference per character |
| `AudioLine` | Line → voice → TTS take → duration |
| `Look` | Character × outfit × story day |
| `LocationPlate` | Set × facing × time of day |
| `CapabilityProfile`, `CalibrationRun` | Versioned model limits, prompt format, failure modes, and calibration results |
| `GenerationUnit.mode` | One of: references only, first/last frame, extension, setup pack |
| `Take` | Scores, cost, provider IDs |
| `Clip` | An interval of a take mapped to a shot |
| `Timeline` | The edit, stored as OTIO |
| `Publication` | A post on a platform |
| `MetricSnapshot` | Audience metrics captured at a point in time |
| `Experiment` | A variant test, such as alternative hooks |
| `ComplianceRecord` | Rights, labels and registration evidence |

---

## 9. Roadmap

### P0: before any paid scale-up (days)

**Work:**
- Fix D1–D6, D11 and D13.
- Create a single capability profile, with the 2.5 limits checked against `dreamina multimodal2video -h`.

**Done when:**
- A fast-drama scene with 1.5–2.5 s shots plans into valid whole-second units *before* the dry run.
- A failed unit can be re-taken without editing the design.
- A batch with one rejected unit still completes the rest.

### P1: make it a production line (weeks)

**Work:**
- An Episode entity and an outline stage.
- Audio first: voice assets, shots timed to TTS, and an explicit decision between native and dubbed audio.
- A prompt compiler that writes in Seedance's expected form, plus a calibration suite.
- Machine evidence:
  - shot detection that proposes intervals;
  - identity embeddings;
  - speech-recognition CER;
  - OCR;
  - vision-model state diffs.
- Policy acceptance.
- Automatic assembly and packaging, with labels.
- Location plates.
- The staging ledger.
- Experiments with generating coverage by camera setup.

**Done when:** one pilot episode goes from outline to a publishable file within a target number of human minutes, measured.

### P2: scale (months)

**Work:**
- Durable workflows, Postgres and object storage; pools of provider accounts.
- Budget envelopes.
- Publishing and analytics, hook experiments, and continue/kill decisions.
- Rules learned from audience metrics.
- Team roles.
- Routing across several models, for example falling back to another model when moderation blocks a unit.

---

## 10. Metrics

- **North star:** contribution margin per published episode, or ROI per series.
- **Market:**
  - 3- and 5-second retention;
  - completion rate;
  - the swipe-away curve;
  - follows;
  - keyword searches;
  - paid conversion.
- **Production:**
  - cost per accepted second;
  - takes per accepted unit;
  - human minutes per finished minute;
  - cycle time from source to publication;
  - rework by cause;
  - moderation rejection rate.
- **Quality:**
  - the distribution of identity-similarity scores;
  - dialogue CER;
  - continuity defects found in sampled audits.

---

## 11. Assumptions I would challenge

1. **"Premium quality everywhere."** Tier it: excellent at hooks, payoffs and cliffhangers, sufficient elsewhere.
2. **"Never retry paid media automatically; no cumulative cap."** Use budget envelopes, with automatic retries inside them.
3. **"Every unknown needs a human."** Use policy acceptance plus audits.
4. **"No fixed durations or cadence."** For monetized short drama, episode length windows and hook timing are *business requirements*. Make them parameters per platform and learn their values from data, rather than refusing structure.
5. **"Sessions save cost."** At scale, stateless calls with prefix caching are cheaper, run in parallel and are reproducible.
6. **"Limits come from configuration."** Configuration is not verification. Calibrate.
7. **"Voice, subtitles and editing happen in external software."** That is where retention is won and where the human time goes.
8. **"B must never add props or intermediate states."** Add a staging ledger.
9. **"Local, single-user."** Decide the scale tier now.
10. **"Another LLM session counts as independent review."** Not for high-leverage gates.

---

## 12. Decisions only you can make

1. **Business model:** novel promotion (推文), paywalled series, ad creatives (投流素材), TikTok creator rewards, or a mix. Each changes the unit of production and the metrics.
2. **Target tier:** T1, T2 or T3.
3. **Look:** photoreal through licensed portraits, or stylized.
4. **Audio:** Seedance's native audio with voice references, or a separate TTS-plus-lip-sync pipeline. The separate pipeline is required if the same footage must ship in several languages (Douyin plus TikTok).
5. **Who owns "the episode as a viewing experience"** (the showrunner/editor role)? Today nobody does.

---

## Sources

**Seedance 2.0 limits and reference behavior:**
- [Morphic: Seedance 2.0 guide](https://morphic.com/resources/how-to/seedance-2-guide)
- [Clipdance: omni-reference behavior](https://clipdance.ai/blog/seedance-2-reference-video-rejected)
- [SeedanceAI: multimodal references](https://www.seedanceai.cc/guides/seedance-2-0-multimodal)
- [Seedance 2.0 technical report](https://arxiv.org/pdf/2604.14148)

**Seedance 2.5:**
- [The Decoder](https://the-decoder.com/bytedances-seedance-2-5-generates-30-second-video-clips-with-built-in-audio/)
- [The Next Web](https://thenextweb.com/news/bytedance-seedance-2-5-ai-video-4k-30-seconds)
- [ByteDance Seed blog](https://seed.bytedance.com/en/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5)
- [MindStudio on 50 references](https://www.mindstudio.ai/blog/seedance-2-5-50-reference-multimodal-input-consistency)
- [Voice consistency in 2.5](https://www.seedance.tv/blog/how-to-keep-voices-consistent-in-seedance-2-5)

**Face policy:**
- [TechNode (Feb 2026)](https://technode.com/2026/02/10/bytedance-suspends-seedance-2-0-feature-that-turns-facial-photos-into-personal-voices-over-potential-risks/)
- [Phemex: relaunch with real-face upload ban](https://phemex.com/news/article/bytedance-relaunches-seedance-20-globally-with-restrictions-on-realface-uploads-68605)
- [VicSee: content filter tests](https://vicsee.com/blog/seedance-content-filter)

**Dreamina CLI:**
- [Dreamina CLI](https://dreamina.capcut.com/tools/dreamina-cli)
- [CLI command guide](https://github.com/simonjiang99/dreamina-cli)

**火山剧创 1.0:**
- [Sina Tech](https://finance.sina.com.cn/tech/digi/2026-05-21/doc-inhyrvzm6383242.shtml)
- [Sohu](https://www.sohu.com/a/1025749550_121956424)
- [AIHub](https://www.aihub.cn/tools/huoshan-juchuang/)

**Prompt practice:**
- [seedance2-skill](https://github.com/dexhunter/seedance2-skill/blob/main/zh/SKILL.md)
- [Zhihu prompt formula](https://zhuanlan.zhihu.com/p/2005428746417640272)

**Workflow benchmarks:**
- [Tahou: AI short-drama full workflow](https://www.tahou.com/article/214766891445907461)
- [Zhihu: Seedance 2.0 short-drama manual](https://zhuanlan.zhihu.com/p/2030282234528260520)

**Novel promotion (推文):**
- [Zhihu: authorization and keywords](https://zhuanlan.zhihu.com/p/712136515)
- [Sohu: 2026 tutorial](https://www.sohu.com/a/1024638341_122594654)

**Regulation:**
- [Xinhua: labeling measures in force](http://www.news.cn/tech/20250909/fb164c6d092146aa8e13ddc283fe416a/c.html)
- [China Law Translate: labeling measures](https://www.chinalawtranslate.com/ai-labeling/)
- [GB 45438-2025](https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=F32EA2A561F1886CD8D606513512D547&refer=outter)
- [AI 漫剧 registration from April 1](https://news.qq.com/rain/a/20260320A08O2800)
- [微短剧发展管理办法 (IT之家)](https://www.ithome.com/0/984/306.htm)
- [CNSA on AI micro-drama policy](http://www.cnsa.cn/art/2026/8/13/art_1955_49173.html)
