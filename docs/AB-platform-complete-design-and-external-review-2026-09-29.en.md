# A/B Platforms: Complete Design and External Review Document

> Historical code snapshot dated September 29, 2026. Presentation conversion moved entirely to A on September 30; the application now has one database and two workspaces. See the [current implementation addendum](UNIFIED_WORKSPACES_2026_09_30.en.md). Earlier test evidence does not validate this refactor.

Consolidated version: 1.0 | Code snapshot: September 29, 2026 | Purpose: external product, AI engineering, and architecture evaluation

**This is a self-contained English edition of the Chinese review document.** It combines the design, review brief, implementation and API index, concrete scenarios, source fingerprints, and document validation information. Reviewers do not need to open the original multi-file package.

The document distinguishes implemented mechanisms, product requirements, static risks, confirmed defects, and unverified outcomes. Consolidating or translating the material does not fix application code or initiate model or paid media calls. The original evidence boundaries remain unchanged.

## Reading order

| Part | Contents | Review purpose |
|---|---|---|
| I | Review context and current maturity | Understand goals, actual status, and limits |
| II | Complete A/B design | Workflows, agent control, sessions, data, continuity, caching, costs, recovery, and learning |
| III | Concrete scenarios and task traces | Examine user actions and data flow |
| IV | External review brief | Questions, recommendation format, and a reusable evaluation prompt |
| V | Code, API, and evidence index | Locate implementations, endpoints, and existing evidence |
| VI | Snapshot metadata and source fingerprints | Verify the code version and document provenance |

The document includes the agent session tree, complete workflow, and 16 identified review priorities. The code index provides locations rather than a source-code attachment. A code audit requires the matching source snapshot. Production databases, full novel texts, account credentials, and API keys are excluded.

## Part I: Review context and current maturity

### Platform responsibilities

**A develops original stories or novel adaptations into an adopted story script. B adapts that story again for a chosen screen format, produces an adopted shooting script, and then organizes storyboards, assets, generation, and review.** The platforms run and store data independently, exchanging SceneExport v4 files.

A programmatic controller schedules work and persists authoritative state. Authors, presentation modes, scene directors, and independent reviewers use separate persistent sessions scoped to their responsibilities. Sessions continue within the same responsibility and task, receiving incremental changes; users do not repeatedly paste all background information. Media execution submits only tasks covered by a confirmed plan.

### How to assess maturity

The platforms provide runnable local workflows and several kinds of engineering evidence. Their complete product goals still exceed the current implementation. In particular, distinguish:

- Saved shooting-script histories for different formats from fully independent production branches.
- Importing a complete novel and adapting selected chapters from dedicated whole-book analysis.
- Valid declared events, passed semantic review, and verified actual media.
- Stored feedback rules from an autonomous learning and verification loop.
- Low-level Dreamina query support from a working platform recovery endpoint.
- Business-level candidate reuse from lower-level model caching, including experience and source versions.

The review identifies 16 gaps or risks. The recovery method's incorrect nesting has been confirmed through AST inspection; other issues require targeted reproduction or outcome evaluation. They remain visible so the external reviewer receives an accurate snapshot.

### Scope and evidence

The original package was based on static code inspection. Release manifests report 164 tests for A and 218 for B. Earlier evidence includes desktop and narrow-screen workflows, offline handoff, and small real-text/session trials. These are not new full-suite results obtained during document consolidation. Earlier reports contain different counts; their paths and historical status are retained separately.

Whole-novel trials, multi-day session stress, complete paid-media quality evaluation, and longitudinal learning effectiveness have not been completed. There is no basis for claiming that every premium-production capability has passed acceptance.

## Part II: Complete A/B design

### 1. Product goals, constraints, and maturity

#### 1.1 Product positioning

System A, StoryLab, handles original storytelling and novel adaptation, producing a story script adopted by the user. System B, FrameLab, performs a further audiovisual adaptation of that story, producing an adopted shooting script and then organizing directing, storyboards, assets, image/video production, media review, and the production package.

Both systems aim to balance premium quality with invocation cost. AI should prepare analyses, creative drafts, checks, and the next result proactively. The user's primary activities are reading, comparing, requesting changes, and adopting results. The workflow retains meaningful creative choices while avoiding clicks for every internal processing node.

| Business route | A's responsibility | B's responsibility | Quality criteria |
|---|---|---|---|
| Original premium work | Concepts, character desires, conflict, active choices, causality, and story script | Film/series/short-drama adaptation and production | Coherent story, credible characters, intentional audiovisual expression |
| Novel-promotion short drama | Adapt the selected source range with key facts and evidence preserved | Fast-paced short drama; configurable Seedance 2.0 Fast to reduce video cost | Early conflict, information progression, emotional payoff, compelling segment endings, and prop continuity |

Original/novel adaptation selects the source route. Film/series/fast-paced short drama selects the presentation format. Aspect ratio is an independent production choice. Novel promotion may use acting and dialogue; it is not limited to narration over illustrations.

#### 1.2 Fixed constraints

- A and B run independently, own separate data, and exchange files rather than a shared business database.
- Initial setup does not require a fixed runtime. Fixed minutes, shot counts, or reversal intervals do not replace directing judgment.
- Multiple candidates and local revisions are supported. AI approval is separate from user adoption.
- Adopted scripts, event states, and asset records are stored by the program; session history is not the authoritative fact store.
- Each paid-media batch requires a preview of tasks, references, and costs, followed by confirmation. Paid retries are not automatic.
- Voice-over, subtitles, and final editing primarily take place in external software. B retains its legacy assembler for compatibility and rough cuts.
- Deployment currently targets a single-user local workstation, not a public multi-tenant service.

#### 1.3 Accurate maturity statement

The current system is a runnable local source release with persistence, automated tests, and a few real-text trials. This does not establish that every complete-version requirement has passed acceptance or that real finished videos consistently reach premium quality.

| Evidence layer | What it establishes | What it does not establish |
|---|---|---|
| Static inspection | Modules, endpoints, fields, checks, and control paths exist | Every business combination works in real operation |
| Automated regression | Structure, recovery, caching, and continuity within tested cases | Undeclared facts, aesthetics, or actual video quality |
| Offline UI/demo workflow | Specified interactions and handoff can complete | Demo media has realistic acting quality |
| Small real-text trials | Some model calls, session continuation, edits, and independent reviews work | Whole novels, multi-day workloads, and all models remain reliable |
| Actual media | Requires separate batch trials and human evaluation | Complete paid-media quality acceptance is not available |

The manifests record A: 164 tests and B: 218 tests; historical browser evidence includes desktop and 390px layouts. The document task did not rerun all business tests. Keep `paidProvidersLiveVerified=false`. Historical UI results cannot substitute for UI verification after the latest changes.

### 2. Architecture and deployment

#### 2.1 Runtime architecture

```text
User browser
├─ System A / default 127.0.0.1:8787
│  ├─ Reader, candidate comparison, natural-language edits, feedback/memory
│  ├─ FastAPI → StoryService / NovelService / IdeationService
│  ├─ Store + Jobs + LLM + ExperienceService
│  └─ Own data/studio.sqlite3, settings.json, media, exports
│
├─ SceneExport-v1 / schemaVersion:4 file
│  └─ Adopted story and versioned evidence only
│
└─ System B / default 127.0.0.1:8788
   ├─ Shooting script, approaches, storyboards, assets, generation/review
   ├─ FastAPI → ProductionService + ShootingWorkflow + ProposalWorkflow
   ├─ Store + Jobs + LLM + ExperienceService
   ├─ RunnerRegistry → media Provider / Dreamina CLI / manual import
   ├─ Gates / FFmpeg / Assembly / production-package export
   └─ Own data/studio.sqlite3, settings.json, media, exports

Text: A/B → respective LLM adapters → shared-account queue → local Codex CLI
Other text configurations: OpenAI / Anthropic / Gemini API / demo
Media: B's execution records and cost previews; never freely submitted by author sessions
```

The manifest minimum is Python 3.11. The backend uses FastAPI, Pydantic/JSON Schema validation, and SQLite WAL. The frontend is local HTML/CSS/JavaScript with reader and upgrade layers. Jobs uses a thread pool with three workers by default; this does not authorize three simultaneous Codex submissions.

Each platform packages its own foundational modules, including `core.py`, `llm.py`, `codex_cli.py`, `story_contract.py`, and `experience.py`. Independent distribution is preserved, but duplicated implementations can drift; contract tests and synchronization checks are needed.

#### 2.2 Data ownership

| Data | Within A or B | Account-level sharing |
|---|---|---|
| Authoritative works, candidates, asset objects | Separate SQLite documents | None |
| Audit and UI events | operations/events | None |
| Jobs and deduplication | jobs/job_idempotency | None |
| Result cache and redirects | cache/redirects | None |
| Role session records | Each platform's codex_session documents | CLI history belongs to the configured login directory |
| Media and work directories | Each platform's data/media and codex-workspaces | None |
| Invocation coordination | Platform requests enter the queue | `<CodexHome>/story-studio/call-queue.sqlite3` |

`_version` is an optimistic concurrency version. `digest` computes SHA-256 over canonical JSON. Adopted work versions, file SHA-256 values, and session input hashes have distinct purposes and are not interchangeable.

### 3. Complete user workflow and automatic advancement

```text
A: original concept / import complete novel
→ select this task's goal: creative stage or chapter range
→ AI candidate → program checks → independent review → bounded local repair
→ user reads, adopts, or requests changes
→ export adopted story as SceneExport v4

B: import A → choose film / series / fast-paced short drama
→ complete shooting script, change rationale, and source mapping
→ program checks + independent review
→ user previews impact and adopts
→ event-based asset requirements
→ compare approaches for key scenes; advance recommendations for ordinary scenes
→ scene direction and storyboards → verify references for actual visible objects
→ generation units → batch dry-run → user confirmation
→ execution/recovery → actual-file screening → user review and adopted interval
→ local revision or production-package export → external final edit
```

Automation means the program schedules the next authorized task. It does not silently adopt core story directions, let models expand scope freely, or bypass media cost confirmation.

#### 3.1 Required choice points

| Choice | User sees | Background processing |
|---|---|---|
| Original story direction/candidate | Complete recommended content and meaningful alternatives | Strategy lanes, structural checks, quality review, differences |
| Selected novel adaptation | Adapted draft, localized issues, source range | Source locations, relevant prior context, event checks, independent review |
| B shooting script | Complete readable script, reasons, story-change proposal | Format adaptation, mapping, coverage, version impact |
| Key scene approach | Different focus, blocking, cut points, and sound | Complete direction and shots, independently checked |
| References and paid batch | Real references, missing items, tasks, known/unknown prices | Prompt compilation, dependency ordering, caching, capability validation |
| Media adoption | Candidate files, observations, actual interval/end state | Screening, evidence frames, dependency invalidation, file registration |
| Cross-work experience | Rule, scope, exceptions, examples | Project-local recording, applicability, application tracking |

#### 3.2 States

Workflow states include `ready`, `awaiting_choice`, `needs_attention`, and `complete`. Job states include `queued`, `running`, `succeeded`, `failed`, `cancelled`, and `interrupted`. Candidates usually have `proposed`, `adopted`, and `rejected` statuses. Authoritative objects also use `draft`, `accepted`, `locked`, `archived`, and freshness.

`passed=true` means checks passed; `status=adopted` means the user adopted the result. A succeeded job may only have produced a candidate needing a choice or attention; it does not mean the work is complete.

`/advance` is bounded workflow progression, not a free agent loop. A's original route normally advances to the next candidate batch. Its novel route handles the selected segment directly. B's new route can prepare assets and advance ordinary scenes until a key approach or issue needs attention. `single/until_choice` compatibility remains separate from `presentationMode` to avoid interpreting advancement controls as screen formats.

### 4. System A: original storytelling

#### 4.1 Hierarchy and contracts

Compact hierarchy: `premise → sequence → scene → script`. Full hierarchy: `premise → spine → sequence → scene → script`. Scene bodies may contain beats, but beat is not a top-level node type. The reader reduces interaction density while internal nodes retain parentage, order, and constraints.

A node contract describes its summary, preconditions, postconditions, value change, revelations, downstream obligations, and entities. Bodies, contracts, and adopted revisions are recorded separately. Canon holds characters/locations/props, facts, and beliefs; narrative edges express information and causal relationships.

Order uses rational indices so insertion does not require renumbering all siblings. Nodes retain revision pointers, locks, and freshness. Branches, restoration, undo, and structural operations preserve history.

#### 4.2 Original workflow

1. Start with AI concept cards or a user story seed, genre, and tone.
2. The controller reads the adopted premise, constraints, ancestor contracts, adjacent scenes, relevant canon, and applicable experiences.
3. Generate candidates by strategy, reusing separate strategy-role sessions where appropriate.
4. Validate structure and hard constraints. Independent reviewers examine source fidelity, causality, dialogue, events, continuity, and presentation, and evaluate quality and substantive diversity.
5. Repair only failed candidates with remaining repair allowance. Reuse valid reviews for unchanged, already-passed content and evidence.
6. The user adopts. Proposed entities, facts, and beliefs follow confirmation paths before becoming authoritative.
7. Expand toward full script, read, revise locally, scan, and export.

`StoryService.context()` organizes constraints, bible, ancestors, neighbors, canon, narrative edges, experiences, and task. When over the character limit, neighboring bodies are reduced first. If essential constraints still exceed the limit, submission is explicitly blocked. This is programmatic scope filtering, not a mature semantic retrieval system.

#### 4.3 Edits and impact

Operations include fill, variations, rewriting, deepening, splitting, merging, interpolation, revelation movement, and structural changes. Some operations require a `planHash` for the current impact preview. Ordinary rewrites cannot overwrite locked nodes. Freshness and issue records identify affected objects.

Adopted material can be retained, but reviewers should examine whether all original-story paths produce complete structured states. Original exports construct `storyDocument` conservatively; they are not equivalent to the novel route's detailed generated event ledger. B may need continuity completion.

### 5. System A: complete novel, selected range, and continuation

#### 5.1 Loading is separate from understanding

TXT and pasted text are supported. The frontend tries UTF-8, then GB18030. The backend normalizes line endings and stores full text, SHA-256, source name, and chapter index, with a 100 MiB text limit.

Current default: **save complete book → index → process selected chapters only → produce adaptation candidate**. Explicit whole-book deep reading is a separate task, not a prerequisite for adapting the first few chapters.

| Stage | Records | Understanding claim |
|---|---|---|
| Source saved | novel_source.text/sha256 | None |
| Index built | Chapter title, offsets, reading-unit ID | None |
| Loaded for a model task | readRanges and excerpt | Loading receipt only; correlate calls and review |
| Adaptation review passed | chapter_analysis, analysisRanges, purpose | Evidence of adaptation review for that range, not whole-book analysis |
| Dedicated unit analysis | book_unit_analysis | Conclusions for that reading unit |
| Summary completed | book_analysis | Coverage-based aggregate; assess conclusion sufficiency separately |

`CHAPTER_INDEX_VERSION=2` collapses consecutive duplicated headings, avoiding two units for a doubled chapter title. Legacy sources with no adopted draft or candidate history can be safely reindexed; historical numbering is not silently replaced.

Long chapters may split into units. `number` identifies the unit; `chapterNumber` may identify the original chapter. UI units 1–5 therefore do not always equal original chapters 1–5. This semantic distinction needs explicit review and possible improvement.

#### 5.2 Selected-range adaptation

```text
Select start/end units
→ validate range and excerpt size: currently ≤80,000 characters per source excerpt
→ persist readRange receipt
→ use existing whole-book/partial analyses; do not wait for complete-book analysis
→ include relevant identities, entry states, prior context, and applicable experiences
→ complete candidate and event states
→ structural validation → independent review → at most two automatic creative repairs
→ persist proposed candidate; authoritative story changes only after adoption
```

Direct adaptation may also produce a reviewed range summary. The code does not guarantee a dedicated analysis-agent call before every adaptation-agent call. Combined analysis/adaptation must be distinguished from dedicated deep reading.

`activeNovelDraft` and `nextChapter` govern continuation. Related registered entities and previous end states are provided. New segments merge into the adopted draft after checks protecting old scenes, identities, and known container contents; invented extra contents or reused old scene IDs are rejected.

Local revisions specify `sceneIds` and protect unrelated adopted scenes. Failed proposed drafts may supply `repairDraftId`, tied to the original source, range, and adopted baseline. JSON Patch repairs avoid rewriting from scratch; a new result records `repairedFrom`.

#### 5.3 Optional whole-book deep reading

`analyze_all()` processes reading units, saving summaries, characters, relationships, timelines, foreshadows, props, rules, protected facts, adaptation opportunities, and uncertainties. Unchanged units can reuse `unitHash` results; interrupted tasks continue with incomplete units.

Each unit analysis receives that unit's text and the preceding unit summary. Aggregation mainly merges unique fields. No independent whole-book synthesis/integrity-review stage was identified. Complete relationship inference, cross-chapter foreshadow interpretation, and comprehensive retrieval should not be claimed. When an unchanged unit is reused after an earlier chapter changes, its interpretation may also need reevaluation.

#### 5.4 The 2% incident and current fixes

Previously, importing a whole novel and selecting chapters 1–5 triggered mandatory whole-book analysis. Duplicated headings inflated the index, turning a small-range task into hundreds of units. Long candidates also made repair/review inputs exceed the previous 32,000-character guard. Jobs' initial `.02` progress was not evidence that 2% of the text had been processed.

Selected ranges now run first, whole-book analysis is separate, and failed drafts have a local-repair path. The `GPT-5.6 Sol · High` UI preset uses a 600-second timeout and 96,000-character task guard. This guard is not the model's token window.

A real trial of chapters 1–5 from the same complete book produced a reviewed candidate awaiting choice. This does not establish that every long-text case is solved. Automatic decomposition of oversized ranges, end-to-end input sizing, and continuous progress reporting still need assessment.

### 6. A-to-B handoff protocol

The format identifier is `SceneExport-v1`, currently `schemaVersion:4`. B's new import path reads versions 1–4; legacy workflow import remains.

| Field group | Purpose |
|---|---|
| project/source | Work, source route, fingerprint, source locations, adopted draft |
| scenes | Bodies, stable block/dialogue IDs, revisions, contracts, relevant canon |
| storyDocument | Replayable events, entities, initial state, presentation plan |
| analysisCoverage | Loaded/analyzed ranges, purpose, whole-book completion |
| knowledgeSnapshot | Facts, beliefs, scene-entry knowledge and changes |
| dramaticFunctions | Value changes, revelations, downstream obligations |
| evidenceSnapshot | Source fingerprint and revision evidence |
| versionFingerprint | Fingerprint of this handoff content |

Novel exports verify node bodies match the adopted novel document. If another entry point changed a body without renewed novel review, the exporter rejects combining inconsistent authorities.

B retains imported-source history. New A imports do not immediately overwrite production. A new shooting draft is generated, differences and impact are shown, and only adoption updates downstream work. Missing legacy continuity is marked incomplete instead of treated as fully evidenced.

Fingerprints establish content consistency, not cryptographic authorization. Review import coverage, the knowledge model, and stable IDs after deletion, merging, and reordering.

### 7. System B: further audiovisual adaptation

#### 7.1 Presentation modes

| mode | Creative emphasis | Facts protected by default |
|---|---|---|
| cinema | Scene construction, visual storytelling, subtext, setup, silence, rhythmic contrast | Identity, key motivations, rules, major causes and outcomes |
| series | Relationships, continuing plot, scene organization, episode linkage | Same |
| fast_drama | Early conflict, revelations, dialogue density, emotional payoff, segment-end appeal | Same |

B may compress/rewrite/merge dialogue, externalize interior narration, reorganize scenes, and reorder presentation. Protected changes must appear in `storyChanges`. Current adoption blocks these changes and requires a confirmed A story version. This is not a completed one-click cross-platform story-change workflow. Undisclosed semantic changes still rely on independent review for detection.

#### 7.2 Shooting-script record

`shooting_script` stores the source snapshot/hash, mode, complete payload, sourceMapping, change reasons, storyChanges, review attempts, passed/status, baseShootingId, and requestKey.

Every source block needs a mapping: retain/delete/merge/rewrite → target IDs → reason. Mappings must cover every source and target block. Programs validate references and coverage; reviewers judge whether information and dramatic function survive.

Adoption preview lists changed/preserved scenes, affected shots/media, story changes, candidate version, source, and `planHash`. Adoption rechecks the preview and source.

#### 7.3 Actual multi-format boundary

Film, series, and short-drama candidates are saved separately, with format-specific CLI sessions. **A B project nevertheless currently has one `activeShootingId`; adoption updates the same active scene/direction/shot collection.**

The implementation preserves multi-format shooting histories and switches the active adopted draft. It does not provide simultaneously active, fully isolated assets, shots, generation tasks, and adoption pointers for each format. Re-adopting a historical draft may update/archive active objects and invalidate downstream results.

Complete production branching is unfinished. Assess `productionBranchId`, per-branch adopted pointers, shared identity assets, and format-specific states/shots/media. Separate B projects currently provide explicit isolation, but are not an automatic within-project branch feature.

### 8. Events, props, and knowledge continuity

#### 8.1 Model

`continuity.entities` stores identity and visual-state keys; `initialState` stores all entity initial states; `events` records actual occurrence order. Events bind scenes, locations, participants, actions, preconditions, changes, dialogue, and source evidence.

`presentationPlan` separately records audience order, referencing events and declaring main/preview/flashback/time_jump, before/after, reasons, and dialogue allocation. Preview does not rewrite initial story state. Playback order is not physical occurrence order.

#### 8.2 Physical states

| State | Example | Meaning |
|---|---|---|
| Open/closed | lid: closed/open | Open a container before extracting objects; a closed reference cannot expose contents |
| Held | pos: held_by, target: person_a | Prop transfers require holder/location evidence |
| Contained | pos: inside, target: box | Moving the container moves its contents through relationships |
| Worn/attached | worn_by/attached_to | Clothing, accessories, injuries have ownership |
| Unknown | `{unknown:true}` | Unknown contents cannot be treated as empty |
| Explicitly empty | contentsKnown:true, no active contained object | Observed empty is different from not observed |
| Hidden | visibleTo/closed opaque container | Present but not currently visible to the audience |
| Damaged/consumed/destroyed | Declared fields, destroyed/consumed/active | Destroyed items cannot remain held or visible |

`replay()` computes before/after frames. A change's `from` must equal the preceding state. Programs check positions, containment cycles, extraction through closed lids, remote transfers, and destroyed-object appearance.

#### 8.3 Validation layers

1. Programs verify declared entities, states, references, coverage, and order.
2. Independent text review checks ledger/source alignment, omitted objects, causality, and knowledge.
3. Actual-media observations establish what visibly happened and whether adoption states agree.

Declared-state validation cannot prove that arbitrary prose has no omissions or that the model extracted every state correctly. Character knowledge/misbelief and audience knowledge have handoff snapshots and some narrative checks, but complex misdirection, flashbacks, and unreliable narration require further assessment.

### 9. Assets, identity, and reference responsibilities

#### 9.1 Three-stage asset governance

The product goal is shooting-script extraction → rough-storyboard visibility filtering → final-storyboard omission checks. Current code creates masters/variants from adopted event participants and locations. Director references identify objects in frame, and execution manifests resolve actual references.

Do not describe this as an implemented standalone rough-storyboard agent or a comprehensive semantic checker for all set-dressing objects. Objects omitted from event registration can still be missed, especially recurring background items without causal actions.

#### 9.2 Three layers

| Layer | Records | Change impact |
|---|---|---|
| master | Stable identity/form, anchors, freezeString, identityHash | Related variants and media |
| variant | Clothing, open/closed, damage, visible contents, claims/embedded | Tasks using that appearance and their strong dependencies |
| file | Actual file/path/URL/size/SHA-256 | Replacement must affect dependencies and cache validation |

Identity fingerprints include actual visual definitions, not merely names. Neutral identity references and state references are separate. Variants reuse equal claims hashes rather than generating another image for each event.

#### 9.3 Reference binding

References specify entity, role, phase, controlled fields, excludeInheritance, claims, file, and reviewEvidence. Roles include identity, environment, start_state, end_state, and detail.

Identity references preserve the same person/object without inheriting old backgrounds, poses, clothing, or held props automatically. Environment references control space without introducing props absent at this time. An end-state image cannot stand in for a before-state opening composition.

Reference review records evidence and responsibilities; this does not prove every reference was examined by a real vision model. Human/source evidence must remain explicit when real automated review is missing. Missing images block only tasks depending on them.

### 10. Direction, key approaches, and storyboards

#### 10.1 Creative order

The director first establishes viewer focus, emotion, shot groups, cut points, and sound; then blocking, acting, camera, lighting, composition, and shot information. `SceneDirection` holds scene-wide standards; `ShotContract` describes individual shots.

Each shot binds eventId, presentationId, eventPhase, dialogueIds, subjects, references, duration, action, sound, and producibility risk. The prompt compiler faithfully translates adopted direction. Generation must not secretly restore removed A dialogue or invent causal props.

#### 10.2 Key scenes

`key_scene_roles()` uses position and event-complexity heuristics: first scene for opening/introduction, last for climax, middle or special presentation for revelation, and many participants/changes for complex staging.

This reduces choices but is not mature semantic key-scene selection. Key scenes offer substantially different approaches; ordinary scenes can automatically adopt independently reviewed recommendations in the new workflow. Review whether heuristics miss real twists/emotional climaxes and whether ordinary-scene automatic adoption meets premium goals.

#### 10.3 Local changes

Selection supports nonadjacent and cross-scene shots with lock protection. Local revisions must cover exactly the selected editable shots, preserving IDs, current durations, scene-level lighting/blocking/palette/sound, and other shots. This supports precise editing but restricts local timing changes, splitting/merging, and rhythm redesign; larger changes need a clear whole-scene revision path.

Axis, screen direction, and character left/right have fields and some rules. Free-text blocking still requires review; comprehensive 3D spatial reasoning is not established.

### 11. Storyboards versus generation units

Shots express directing/editing intent; generation units are actual provider requests. Multiple continuous shots may form one video request, reducing mechanical per-shot costs and interrupted actions.

```text
Adopted shots
→ group by continuity and objective
→ ordered shots, total duration, prompts, real reference-image indices
→ deduplicate reference files while preserving responsibilities
→ bind adopted upstream video/end state
→ validate configured/CLI limits and chaining capabilities
→ persist generation_task/inputHash
→ dry-run/planHash → confirm execution
→ actual file → mark per-shot intervals and review
```

Units compile each shot using actual reference indices. External strong dependencies wait for upstream adoption and check file hash, adopted interval, and observed end state. frame_chain uses the adopted end-state frame; extension/ref_video uses the adopted interval.

Legacy single-shot render and generation-task paths coexist. Review consistency of caching, recovery, intervals, in-flight version changes, and cost rules.

Seedance limitations come from configuration and current Dreamina CLI capability handling, not hardcoded claims in this report. Defaults include `videoModel=seedance2.0fast` and `videoResolution=720p`; this does not mean provider=dreamina is enabled or the provider accepts every parameter.

### 12. Agent control: controller, specialists, and permissions

#### 12.1 Three meanings of agent

| Name | Current meaning | Tool autonomy |
|---|---|---|
| Project controller | Program state machine, services, scheduling, adoption validation | Controlled program paths |
| Author/reviewer agent | Model inference in separate roles/scopes/persistent CLI sessions | Text adapter disables tools and autonomous delegation |
| Media execution runner | Process executing an explicit TaskSpec or configured third-party runner | Tool whitelist, routing, qualification, and workspace restrictions |

There is no continuously paid model supervisor reading all history, and no default launch of many chat windows. Role sessions are created when needed; the user does not manage context manually.

#### 12.2 Session tree

```text
User: adoption, edits, cost confirmation
└─ Program controller: authoritative database versions determine tasks
   ├─ A project P_A
   │  ├─ Original: target node × level × phase × strategy
   │  │  └─ independent validator session
   │  ├─ novel-analysis:<sourceId>: explicit whole-book unit analysis
   │  ├─ novel:<sourceId>: selected adaptation, continuation, local repairs
   │  │  └─ review:novel:<sourceId>: source/event review
   │  └─ Other observation/scan roles: isolated by role and target
   │
   └─ B project P_B: adopted file imported, A author reasoning not inherited
      ├─ shooting:cinema
      │  └─ review:shooting:cinema
      ├─ shooting:series
      │  └─ review:shooting:series
      ├─ shooting:fast_drama
      │  └─ review:shooting:fast_drama
      ├─ shots:<mode>:<sceneId>: direction, shots, local edits
      │  └─ review:shots:<mode>:<sceneId>
      └─ Media execution/observation: TaskSpec or observation request
```

Project, role, scope, and connection identity together identify a session. B modes are instantiated only when requested. Session separation does not imply three independent production database branches.

#### 12.3 Where independent agents are needed

| Responsibility | Current implementation | Reason/recommendation |
|---|---|---|
| Original author vs reviewer | Author role and validator request/session separated | Avoid self-approval; necessary |
| Novel adaptation vs source review | structure/reviewer and separate scopes | Source, cause, state checks; necessary |
| Book analysis vs adaptation | Separate explicit scopes; analysis not mandatory | Different goals/outputs; analysis on demand |
| Three B presentation modes | treatment sessions separated by mode | Prevent short-drama preferences contaminating film; necessary |
| B adaptation vs review | treatment/reviewer separated | Protected facts and actual presentation differences; necessary |
| Scene directing | Continuation per mode/scene | Limit context and revision scope; reasonable default |
| Director vs storyboard review | shots/reviewer separated | Coverage, dialogue, states, axis; necessary |
| Asset extraction/program handling | Mainly event-based program extraction | No agent per prop; targeted omission review when needed |
| Rough vs final storyboard | Same directing responsibility currently | No separate rough-storyboard service; splitting must demonstrate benefit |
| Media review vs author | Gates/vision/detectors/human observations | Must inspect actual media, not author self-assessment |
| Experience organization | Mainly rule recording and application | Batch organization could use a specialist; complete automatic extraction not identified |
| Media execution | Trusted subprocess default; other runners qualified | Tool, cost, and recovery isolation |

Independence primarily means separate context, task, and judgment, not mandatory use of another vendor. Review sessions also continue and retain review history. They do not inherit author reasoning, but are not entirely history-free blind reviews each time. Evaluate anchoring from earlier verdicts.

#### 12.4 Decision boundaries

The program decides the next step, authoritative version, scope, applicable experiences, deduplication, caching, allowed tools, cost plans, adoption conditions, and invalidation.

Models decide creative expression, character motivation/causality, adaptation choices, direction, quality judgments, and evidence-based issues. They return candidate JSON, reports, or patches; they do not adopt content or freely order media.

The user chooses core story and shooting-script adoption, key approaches, protected-fact changes, paid batches, final media, and cross-work experience promotion.

### 13. Codex CLI sessions, incremental context, and models

#### 13.1 Connection identity

Text calls use `codex --no-daemon exec`; continuation explicitly uses `resume <threadId>`, never `--last` or the desktop development chat's ID. npm launchers resolve to the actual Node entry; argument arrays avoid shell interpolation.

The adapter reads the chosen CodexHome configuration to resolve defaults for model, reasoning, and credential storage, then executes with `--ignore-user-config` and controlled overrides. Selected settings are inherited; global coding instructions, plugins, and memories are not imported into screenplay tasks.

The preset supports `gpt-5.6-sol / high / timeout=600 / contextCharacters=96000`. A configured model string does not guarantee account availability; connection checks and real calls establish availability. API temperature/maxTokens/extraBody are not represented as effective CLI controls.

Session identity includes project, role, scope, protocol, command/login directory, model, and reasoning. Result cache identity additionally includes CLI runtime files/version and instruction identity. Compatible sessions can continue when prompt wording or runtime changes invalidate results; model or protocol changes may create a new session.

#### 13.2 Continued-session payloads

| Situation | Payload | Preservation |
|---|---|---|
| First role task | snapshot: rules/input/inputHash | Persistent session created |
| Same responsibility continues | delta: baseHash/inputHash/add/replace/remove | Same session and unchanged data |
| Immediate local repair | resultBinding when previousCandidate exactly equals the preceding output | Avoid resend of identical candidate |
| Large replacement | snapshot when shorter than delta | Same session |
| Maintenance checkpoint | 12 delta turns, or at least 4 with accumulated differences over twice full context | Next normal call synchronizes state, no extra summary call |
| Interrupted/lost context | needsResync → snapshot | Continue original session when possible; bounded resynchronization |
| Explicit reset | Clear session binding and rebuild later | Adopted authoritative data remains |

`studio-context-v1` includes deletions. Revoked experiences and removed references leave the current input, rather than being superseded only by another appended note. Hashes verify which input underlies a model response. Missing reconstructable context triggers bounded resynchronization, not guessed facts.

#### 13.3 Review context

Reviewers receive source, constraints, necessary prior context, candidate, and required checks. Author generation history, shapeExample, self-assessment, and random candidate markers are normally excluded; continuation/local revision retains relevant adopted fragments. Specific positions and evidence are mandatory.

Common checks: source_fidelity, cause_effect, dialogue, event_coverage, continuity, presentation. Malformed reports are repaired as reports without gratuitous candidate rewrites.

#### 13.4 Queue and cancellation

A/B share a cross-process FIFO queue through the same CodexHome, default concurrency one. Different client limits combine conservatively. Queue records contain process/lease metadata, not text or secrets.

Long-running live owners are not displaced merely for age; dead owners are reaped. Persistent ownerPid prevents simultaneous session continuation. Windows process-tree cleanup handles timeouts, cancellation, and parent exit. Cancellation while waiting is supported.

The queue does not control user-launched CLI processes, other desktop chats, or unrelated apps. It is not an account-wide quota manager.

#### 13.5 Three cache layers

1. Business candidate reuse directly returns an existing valid candidate for the request.
2. Platform result caching avoids starting CLI/media when the actual request fingerprint matches.
3. Provider prefix caching is decided by the provider; reported cached_input_tokens are recorded.

Continuation can reduce resending, but neither guarantees prefix hits nor makes calls free. Small historical samples establish some continuation/cache behavior, not a universal savings percentage.

### 14. Bounded review and invocation cost

Ordinary `generate_reviewed()` permits an initial draft plus two creative repairs. Repairing an existing failed draft allows two patch rounds. A bounded set of JSON Pointer add/replace/remove operations is merged into a copy and fully validated. Unchanged repair output stops with specific issues.

Each structurally valid candidate may require independent review, and each review report allows up to three format attempts. Therefore two repair rounds do not mean only two model calls in total: a worst case can involve three author calls and up to nine reviewer calls, plus possible resynchronization. A normal path should often be one draft and one review, with caching reducing actual calls.

Original multi-strategy/batch review has different call behavior. Review real run records for first-pass adoption, format failure, repair count, latency, and cancelled requests already submitted.

CLI usage uses reported counts and differences between cumulative session totals to avoid recounting history. Subscription usage is not fabricated into API dollar prices. Unknown prices remain unknown. API costs use configured ordinary/cache rates and mark estimates when usage is incomplete.

A retains its API inference project-budget mechanism. B removes legacy cumulative caps and confirms media batch plans. No new cumulative media budget cap is introduced. Reduce useless calls and paid rework without removing necessary review.

### 15. Caching, dependencies, and adoption impact

#### 15.1 Main fingerprints

| Object | Current key inputs | Review concern |
|---|---|---|
| LLM result | project/role/provider/model/system/user/schema/images/runtime | Experiences in user change lower-level cache |
| Novel analysis | sourceHash, range/unit content | Prior context and rule changes may require reevaluation |
| Shooting candidate | sourceHash/mode/instruction/target scenes/baseline/new-candidate intent | Business requestKey vs experience revision |
| Direction candidate | shootingHash/style/identities/existing shots/task parameters | creative_snapshot lacks explicit experience revision |
| Media | Actual prompt/profile/identity/variant/files/seed/dimensions/duration/strong dependencies | Actual request reuse separate from adoption |
| Generation unit | Compiled shots/reference roles/signatures/adoption/profile/focus/style | Interval/end-state change must affect dependency signature |
| Adoption binding | fileHash/interval/observedEndState | Actual evidence remains necessary |

File caches check existence and declared SHA-256. Keeping an unchanged URL does not make a replaced file the same reference.

#### 15.2 Invalidation

```text
Identity change → related variants → media using them
Shooting-scene change → that scene's direction/shots/media
Shot change → its media + strongly dependent successors
Upstream adopted video/interval/end state change
  → recursive frame_chain / extension / ref_video invalidation
  → affected generation units
Unrelated scenes/media remain
```

Freshness may be clean, opportunity, or broken. Invalidation does not delete historical files. Pins, locks, and arbitration protect adopted work; subsequent rework needs an impact explanation.

Not every invalidation is at the smallest field level. Some paths are scene/identity-wide and conservative. Complex dependencies need tests. New generation-unit execution recalculates inputHash after results return; the older single-shot path requires separate post-return consistency assessment.

#### 15.3 Static candidate-cache risk

Novel and shooting propose methods can return a passed candidate via a business-level requestKey that lacks explicit experience revision. Director snapshots/keys similarly omit it. Lower-level LLM requests contain experience guidance, but early business reuse bypasses that layer.

It is therefore unproven that changing/revoking experience always prevents related candidate reuse. Reproduce: generate a passed unadopted candidate → change/revoke guidance → regenerate/adopt the same target → inspect effective snapshot and invalidation. This is a static risk, not a targeted reproduction performed during documentation.

### 16. Media execution, recovery, and costs

#### 16.1 Provider versus Runner

Providers are generation services: demo, manual, Dreamina, OpenAI images, Generic HTTP, ComfyUI, and others. Runners execute compiled tasks: trusted subprocess by default; pi-agent/codex third-party runners are disabled by default and require current-profile qualification.

Persistent Codex text sessions and `runner=codex` execution agents are different paths. Third-party isolation explicitly declares docker or qualified host mode. A working directory alone is not a security sandbox.

#### 16.2 TaskSpec

Tasks declare taskId, renderKey, role, stage, task, objective, inputs, tools, workdir, acceptance, limits, and reportSchema. Allowed tools principally include render, ffmpeg, read_task, write_report; operator roles are limited to production/test stages.

Only authorized references are copied into task directories. Results require real files, size/extension acceptance, actual prompts, and reports. A changed prompt must preserve frozen identities; changed results receive actualKey/requestedKey redirection and a curator item.

#### 16.3 Dreamina recovery

```text
Confirmed cost plan
→ persist execution input/attempt workspace
→ record submitting before submission
→ persist reliable submit_id immediately after CLI response
→ query_result for the original task
→ download/register/hash → review

Timeout/download failure with ID: query/download original, no new submission
Possible submission without reliable ID: state_unknown → manual reconciliation
Local cancellation: stop local waiting; remote may still execute/charge
```

Local records, remote responses, and original files are retained. Recovery must check the original basis. A `runner-runs/{id}/recover` route exists; generic Jobs resume mainly restores text and must not blindly rerun paid media.

**Confirmed endpoint-wiring defect:** `recover_remote()` in production.py is nested inside `asset_render()`, rather than a ProductionService method. main.py calls `b.recover_remote(...)`. AST inspection confirms this nesting, so the endpoint cannot be reported as working end-to-end recovery. Low-level original-task querying exists; method ownership and route-level regression must be fixed.

This design cannot guarantee provider-side exactly-once execution. A disconnect after successful submission but before ID persistence requires an unknown state and reconciliation. Other providers may have different recovery semantics and require separate acceptance.

#### 16.4 Cost preview

dry-run returns tasks, actual references, duration, cache, known/unknown prices, blockers, and planHash. Execution validates the latest plan and each task's basis during generation. Consecutive failures can open a scene circuit that must be inspected and reset.

Estimates come from configuration, not necessarily live provider billing. Recovering downloads and submitting a new paid candidate must be distinguishable in the UI.

### 17. Actual media review, adoption, and production package

#### 17.1 Review layers

| Layer | Method | Limit |
|---|---|---|
| File/parameters | Decode, FFprobe/FFmpeg, dimensions, aspect, duration | File usability, not story correctness |
| Coarse image checks | Blank/uniform detection, brightness shifts, optional OpenCV face counts | Counts are not identity; brightness is not temporal proof |
| Specialist detectors | Configured identity/anatomy/text/temporal/audio plugins | Missing/unavailable detectors return unknown |
| Vision model | Actual sampled frames checked against informationPayload | Roughly up to five points, not full action/audio coverage |
| Human final review | Watch and record reasons, interval, end state | Still essential for premium delivery |

Checks use pass/fail/review/unknown. A fail rejects; review/unknown require review rather than invented automatic approval. `dialogue_audio` is separate: an audio track does not prove correct dialogue delivery.

The current vision invocation condition also requires model and baseUrl; a pure codex_cli vision configuration may be skipped by this legacy gate. An integration interface does not prove every vision configuration works.

#### 17.2 Video adoption

Adoption stores actual file SHA-256, duration, interval.in/out, decodable start/end evidence-frame times/hashes, observed end state, and evidence. The end frame comes from the adopted interval, not automatically from the original file's final frame.

Replacing upstream media or changing the interval invalidates strong dependencies. Evidence frames and human/detector state observations are distinct; an extracted frame does not prove every entity state.

#### 17.3 Package

The `ProductionPackage-v1` ZIP includes production-package.json, readable documents, adopted media and required references, shot order, dialogue/sound guidance, identity/variant mappings, source mappings, adopted intervals, versions, and missing items.

It is independently readable. A package with missing files is not automatically a complete finished-video delivery. External editing uses recorded intervals; final voice-over, subtitles, and editing remain external.

### 18. Feedback, experience, and continuous improvement

#### 18.1 Implemented mechanisms

Feedback anchors targets, selected text, timestamps, and versions. Categories are fact, preference, production, false_positive. Specific explicit feedback may immediately become project-local active guidance. Inferred preferences and vague negative comments remain candidates pending confirmation or clarification.

Experience records hold rule/action/exceptions/conditions/scope/feedbackIds/portableExample/revision/status/timestamps. Scopes are project/genre/global. Cross-work promotion uses confirm; project identities and prop facts do not default to general aesthetic rules.

Applicable rules use equality conditions and scope-priority truncation: default eight, maximum twenty. Generation saves experience_application. Validation results are resolved/recurred/misapplied/unknown. Misapplication, or recurrence caused by unclear rules/scope, may demote a rule to candidate.

#### 18.2 This is not automatic model training

```text
Feedback → concrete rule/pending suggestion → scoped selection → next task context
→ application record → observed validation → edit/narrow/suspend
```

It does not change weights or guarantee that a corrected mistake never recurs. Retrieval is equality matching plus sorting, not semantic retrieval; many rules may crowd out relevant guidance.

Adoption creates preference_signal rather than endorsing every detail. Signals exist, but a complete automatic signal-to-rule service, grouped preference suggestions, and automatic per-rule post-generation validation were not identified. validate mainly receives explicitly submitted observations. Fully autonomous self-improvement is not yet established.

#### 18.3 A/B experience exchange

`ExperiencePack-v1` exports active genre/global methods, examples, origin, portableKey, and fingerprints. Import saves local rules and a receipt, allowing reproduction without the external pack.

Explicit import/export is visible; an automatically synchronized local versioned experience library was not confirmed. Valid imported rules become active, so import confirmation and fact-leak boundaries need assessment. Changing or suspending a source rule does not establish that another platform's copy was updated.

#### 18.4 Effectiveness

Metrics use recorded applications/validations, recurrence, misapplication, and per-rule outcomes. unknown is neither success nor failure. Samples, denominator selection, target/version linkage, and failure-only feedback can bias metrics.

Review exact application/target linkage, rule selection records, conflicts, deletion synchronization in continued sessions, generated regression cases, reasonable exceptions, and cross-platform propagation. These provide stronger evidence than naming an additional learning agent.

### 19. Security, recovery, compatibility, and deployment limits

Local HTTP checks Host/Origin; writes require `X-Studio-Client: local-ui`. CSP applies to static resources, and paths remain within allowed data roots. This client marker is not public user authentication; the service is not ready for direct multi-tenant exposure.

Codex text sessions disable shell, browsing, media generation, apps/plugins, skill discovery, memories, and multi-agent delegation, with read-only sandbox and constrained JSON. Story content and experience are data and cannot expand tool permissions.

Settings may store API secrets and HTTP reads redact them; settings.json is not automatically an encrypted credential store. Runs may retain prompts/source context, and backups may contain text/call records. Review before sharing.

Store uses transactions, optimistic versions, and append-only audit. Jobs initialization marks queued/running work interrupted. Text recovery reuses stable identity/results. A data directory should not be served by multiple concurrent instances: a second instance may alter the first's job state.

Tests previously imported the default app and touched production Jobs. Test setup now configures temporary STUDIO_DATA before import. This illustrates why test counts cannot replace production isolation. Service-instance ownership still deserves a separate lock and acceptance test.

Compatibility covers old SceneExport versions, old/new B paths, historical candidates/media, and backup restore. Restores create a new project and remap IDs rather than overwrite originals. Future branches/libraries require versioned migrations and rollback scenarios.

### 20. Important interfaces and interaction contracts

The full AST-derived route catalogue appears in Part V.

| Platform | Interface family | Purpose |
|---|---|---|
| A | /api/novels, /projects/{p}/novel | Source import/update, coverage, candidates |
| A | /novel/analyze, /novel/propose, /novel/drafts/{id}/adopt | Deep reading, range adaptation, local repairs, adoption |
| A | /brainstorms, /generate, /structure, /candidates/* | Concepts, candidates, structure |
| A | /plan, /nodes/*, /branches/*, /canon, /scan | Impact, versions, canon, review |
| A/B | /workflow, /advance, /refine | Reader workflow and local revision |
| B | /import-scene-export, /shooting/* | Source history, adaptation, previews, adoption |
| B | /propose/{stage}, /proposals/* | Director proposals/legacy compatibility |
| B | /objects/{kind}/*, /scenes/*, /assets/* | Identity, variants, states, references |
| B | /generation-tasks/*, /render/* | Unit/single-shot planning, execution, imports, repair |
| B | /renders/*, /runner-runs/*/recover | Observations, adoption, remote recovery |
| B | /export/production-package | Independent production package |
| A/B | /feedback, /experiences/*, /experience-pack/* | Record, confirm, modify, validate, exchange experiences |
| A/B | /api/jobs/*, /api/events, /runs, /history | Jobs, cancel/resume, SSE, audit |
| A/B | /api/codex/status, /codex-sessions/* | CLI status and role sessions |

Most project interfaces are under `/api/projects/{p}`. Adoption/impact checks must preserve passed/source/baseline/lock/planHash checks. Exact payloads are defined in routes and services.

Job deduplication principally uses `(project,kind,operationId)`; different content under the same ID conflicts. Do not infer uniform idempotency/version validation across every synchronous write.

### 21. Known gaps and review priorities

These findings combine static inspection and evidence limits. They are not all reproduced bugs. Classify each as reproduced defect, static risk, missing product capability, or unverified outcome.

| ID | Current issue/boundary | Consequence | Acceptance |
|---|---|---|---|
| R01 | Candidate keys omit some experience/analysis revisions | Old candidate may survive revocation | Change/revoke guidance on passed unadopted candidates |
| R02 | One active shooting/production collection per B project | Saved scripts are not isolated production branches | Independent film/short-drama media survive repeated switches |
| R03 | Reviewed adaptations and dedicated analysis share coverage | Understanding depth may be overstated; isolate demo | Distinct loaded/reviewed/deep-read/synthesized statuses |
| R04 | Unit reuse insufficiently binds prior interpretation | Earlier changes can alter unchanged later text's meaning | Reevaluation after identity/revelation changes |
| R05 | 80k excerpt and character guards; repair context grows | Initial draft fits but review/repair fails | Whole-chain sizing/decomposition without dropping facts |
| R06 | Position/complexity key-scene heuristics | Important turns missed; premature automatic adoption | Compare against real creative key-scene labels |
| R07 | Assets derive from registered events/references | Set dressing and causal props may be omitted | Source/script/shot/reference omission review |
| R08 | Signals/rules/applications exist; automatic synthesis/validation incomplete | Learning needs manual maintenance | One correction used, checked, and validated next time |
| R09 | Manual experience-pack copies, no confirmed synchronization | Cross-platform edits/revocations diverge | sourceKey/revision/tombstone sync and offline snapshots |
| R10 | Single-shot and unit paths coexist | Recovery/cost/interval/version behavior diverges | Same changes/faults tested in both paths |
| R11 | VLM requires baseUrl | CLI vision role may be skipped | Real codex_cli image input and unknown cases |
| R12 | Sparse frames/human end state; incomplete temporal/audio checks | Actions, held props, dialogue missed | Actual video/audio evidence; unknown never passed |
| R13 | Multiple instances initialize Jobs on the same DB | Running work marked interrupted | Instance lock, death recovery, isolated tests |
| R14 | Native compaction/whole-book/multi-day stress incomplete | Long history/queue reliability unproven | Continuation, updates, compaction, cancellation/recovery |
| R15 | Historical documentation/manifest labels differ | Implemented/verified maturity overestimated | Bind generated status to code and evidence versions |
| R16 | Confirmed nested recover_remote; route expects class method | Recovery endpoint cannot reach querying | Fix ownership and add route-level ID recovery tests |

### 22. Acceptance scenarios and expected output

Assess quality, cost, reliability, and interaction together, comparing identical text/model configurations/ranges rather than agent counts alone.

#### 22.1 Required scenarios

- Import an approximately 800,000-character novel and select only the first five chapters: no hidden whole-book calls, truthful progress, complete candidate.
- Produce film and short-drama treatments from one adopted story: real pacing/presentation differences, protected facts, no branch contamination.
- Open/extract/transfer/container movement/clothing/injury/hidden/unknown/empty/destroyed cases: ledger, references, and media agree.
- Preview/flashback returns: physical time stays coherent and knowledge/dialogue delivery are not duplicated.
- Edit two nonadjacent shots: preserve others, propagate strong dependencies, support appropriate rhythm revision.
- Replace upstream video/change interval: invalidate actual dependents, preserve unrelated media, use adopted end state.
- One explicit rule, reasonable exception, revoked rule: applicable tasks change, other modes remain isolated, sessions continue.
- Timeout/crash/unknown submission/download failure: retain IDs, avoid blind submission/duplicate charges/fabricated approval.
- Desktop/narrow-screen reading, comparison, feedback, editing, batch confirmation, and independent package reading.

#### 22.2 Report outcomes separately

| Category | Evidence |
|---|---|
| Engineering | Reproduction input/version/state/expected/actual/tests |
| Text quality | Blind source/character/causality/adaptation assessment, adoption and rework |
| Actual media | Observed files/times/actions/states/identity/dialogue/failures |
| Learning | Selected rule/revision/implementation/recurrence/misuse/unknown/exceptions |
| Costs/experience | Real calls/usage/wait/cache/cost confirmation/necessary clicks |

Recommendations must specify evidence, changed data/API/agent responsibility, cache/migration impact, user interaction, call cost, compatibility, and acceptance. Part IV contains the complete review brief and reusable prompt.

### 23. Snapshot and use

The report derives from the September 29 code snapshot, manifests, and existing evidence, without copying private novel text, production databases, credentials, or secrets. Relative paths, line numbers, and hashes support matching external source review.

The HTML edition reads/searches/prints offline; Markdown can be uploaded to an external AI. Suggested improvements are review content, not automatic execution instructions. Documentation did not change business implementations or adopted works or initiate paid production.

## Part III: Concrete scenarios and task traces

These examples use fictional work. IDs, timing, and content are illustrative, not production records or complete importable protocol samples. Each distinguishes current behavior from required verification.

### 1. Import a whole book; adapt chapters 1–5 only

```text
Input: complete TXT, approximately 800,000 characters; first five original chapters
Program: save source/text/hash → index → verify units map to original chapters
Program: select character range and validate excerpt/full task guards
Session: A / structure / novel:<sourceId> → initial snapshot
Model: complete scenes, identities, props, initial states, events, source evidence
Program: references/range/replay/adopted-baseline checks
Session: A / reviewer / review:novel:<sourceId> → independent source/candidate review
Result: proposed draft + attempts → user reads/adopts
Next segment: same author/reviewer scopes; differences and necessary context only
```

Do not automatically deep-read hundreds of units. Unread later chapters remain unverified. The 80k excerpt guard, full-input guard, and unit splitting constrain larger ranges. Dedicated analysis uses novel-analysis; adaptation coverage is not dedicated book-analysis coverage.

### 2. Film and short-drama versions of one story

Protected story: a girl receives her missing father's box, finds an address, and chooses to go to an old warehouse. Identity, address provenance, disappearance, and choice are protected.

| Expression | Film tendency | Short-drama tendency |
|---|---|---|
| Entry | Establish her connection to the keepsake through sound/pauses | Quickly enter a conflict over possession |
| Explanation | Hands, an old letter, and conversational avoidance | Adversarial dialogue quickly reveals the box's value |
| Clue | Delay full address, show her reaction first | Reveal actionable information during conflict |
| Segment end | Emotional/spatial transition with room for silence | Fulfill the choice and introduce new action pressure |

Separate shooting:cinema/fast_drama sessions and reviewers share unchanged source. Every deletion/merge has mapping and reason. Shots read only the adopted B script.

Current code saves both drafts, but activeShootingId selects one. Complete acceptance requires separate shots/media/adoption pointers surviving switches; that branch isolation remains unfinished.

### 3. Open, extract, transfer, and move a container

```text
Initial:
  A and B at room
  box held_by A; lid=closed; contentsKnown=true
  key inside box; active=true
E1: A opens box → lid closed to open
E2: A extracts key → inside(box) to held_by(A)
E3: A gives key to B → held_by(A) to held_by(B)
E4: A leaves with box; B stays → A at(room) to at(corridor), declared movement
```

Reject extraction before E1, an unexplained return of the key to A after E3, or transfer to B in another location without transition. If the key remains inside the box, container relationships move it with the box; do not create a duplicate key.

Separate box identity, closed, open-with-key, and open-empty references. Generate only actually needed states lacking adequate references. An opening shot's before image must not already show the open box. Character identity references must not inherit old prop ownership.

Watch actual video to verify the extraction occurs; a valid written E2 does not prove it.

### 4. Preview, flashback, and dialogue coverage

```text
Actual: E1 receive box → E2 open → E3 warehouse → E4 danger
Playback: P1 preview(E4) → P2 main(E1) → P3 main(E2) → ...
```

Declare P1 as preview without making E4's end state E1's initial state. Dialogue redelivery needs explicit allocation, not undeclared repetition. The audience has seen danger while the character has not; track their knowledge separately.

Program checks declared plan/order/references; intentional misdirection still needs semantic review and creative intent.

### 5. Repair a failed candidate locally

Issue: E2 still uses from=held_by(A), but E1 already transferred the key to B.

```text
User: repair the identified issue
Program: repairDraftId → verify source/baseline/same range
Original author session: exact preceding output may use resultBinding
Model: patches locate E2 changes and all related errors
Program: apply to copy → complete replay/scope checks
Independent reviewer: revised candidate and source → renewed review
Persist: new candidate/repairedFrom; original failure remains in history
```

At most two repair rounds for this task. Stop on no progress. New entities/fields cannot conceal conflicts; protected-fact changes require story-version confirmation.

### 6. Adopted video interval and strong chaining

V1 lasts 12 seconds, but [2.0,8.5] is adopted. The final decodable evidence frame before 8.5 shows B holding the key and the box open.

```text
Adoption: fileHash, interval, endFrameTime, observedEndState, evidence
Downstream V2 frame_chain: adoption.endFrameTime actual frame
New cost plan: bind adoption signature and actual references, not V1's 12-second end
```

Changing the interval to [2.0,7.0] may precede transfer, so V2 requires renewed checking/invalidation. Unrelated room shots remain valid.

Confirming expected end state still requires observation evidence. A ledger statement cannot masquerade as actual video observation. Extracted frames are not complete action/audio verification.

### 7. Feedback learning and revocation

Feedback: this work's short-drama opening is too slow; introduce a concrete obstacle earlier.

```text
Explicit project feedback → active preference, presentationMode=fast_drama
Film task → condition mismatch, rule not injected
Short-drama task → select rule/revision → persist application
Review/user → specific resolved/recurred/misapplied/unknown evidence
Cross-work confirmation → genre/global method; remove project-specific facts
Revocation → suspended; next delta deletes guidance; related evidence/cache updated
```

Recording, matching, application, and validation endpoints exist. Automatic synthesis/per-rule checking is incomplete. High-level candidate reuse without experience revision is a risk; observing guidance in lower-level prompts alone does not prove revocation works.

### 8. Faults and recovery

| Fault | Expected action | Current check |
|---|---|---|
| Cancel while queued | Leave queue without submitting | Queue/cancel tests |
| Text timeout | Persist failure/resync need; continue responsibility | Real long-session stress |
| Media timeout with ID | Query original | Low-level support; platform nested-method defect |
| Successful media, failed download | Retain ID, download only | Provider response/file evidence |
| Possible submission without ID | Unknown, reconcile manually | No blind resubmission |
| Restart | Jobs interrupted; authoritative state persists | Instance ownership |
| Reference changes in flight | Retain old-basis candidate, do not present as current | Unit/legacy render consistency |

Each scenario requires structural correctness, observed content, costs, and necessary user actions. More tests or agent names alone do not establish acceptance.

## Part IV: External review brief

### 1. What to evaluate

Evaluate two local AI creation platforms: A handles original/novel story creation; B handles further screen adaptation, direction, storyboards, assets, generation, review, and packaging. Use this design and index as evidence, distinguishing implementation, static risk, missing capability, and unverified outcomes.

The user prioritizes premium quality balanced with cost, accepts iterative choices/edits, and wants proactive preparation without complicated operation. Support original premium work and acted/dialogue-based fast novel-promotion short dramas. Seedance 2.0 Fast is common, but fixed templates must not sacrifice quality.

### 2. Requirements to preserve

- Independent A/B runtime and storage; adopted story-file handoff.
- Complete B audiovisual adaptation before storyboards.
- Separate source route, presentation format, and aspect ratio.
- Whole-book import with first-chapter range processing; dedicated book analysis separately triggered.
- No compulsory fixed duration, shot count, or reversal cadence.
- Reading/comparison/adoption/natural-language feedback, with internal processing in the background.
- Candidates separate from adoption; no silent overwrites of adopted work/history.
- Independent author/reviewer contexts; versioned database authority.
- Role continuation, deltas, and platform/provider cache reuse without guaranteed hit claims.
- Paid-media preview/confirmation, no automatic paid retries or new cumulative cap.
- Unobserved media/unsupported detectors/insufficient action evidence remain unknown.
- Confirm cross-work learning; isolate short-drama preferences and project facts.

### 3. Questions that must be answered

#### Workflow and creative quality

1. Where are there too many choices or premature automatic adoptions? Improve without adding interactions.
2. Can selected adaptation preserve plot, motivation, props, and continuity? How is unread future uncertainty expressed?
3. How do film and fast drama demonstrate real viewing/pacing differences instead of labels/durations/wording?
4. Where do key-scene heuristics fail? Is semantic directing required or a simpler improvement sufficient?
5. How do dialogue cuts/merges, externalized thought, and scene reordering retain information and dramatic function?

#### Agent control and cost

6. Is program control sufficient? If adding a model supervisor, specify extra solved problems, context, cost, and failure surface.
7. Which roles require isolation, which should continue, and which should be programmatic? Provide an executable session tree.
8. How can persistent author/reviewer history contaminate or anchor decisions? Control it while preserving cache.
9. Are scopes, roles, models, formats, targets, checkpoints, and deletions appropriate?
10. Do creative repairs, report repairs, and resynchronization create excessive calls? Provide an evidenced budget.

#### Data, assets, and dependencies

11. Does SceneExport v4 adequately model facts, knowledge, misbelief, provenance, events, and playback? Identify ambiguous/missing fields.
12. How should historical formats become independent production branches? Which identity assets can be shared?
13. How are omitted props, lids, transfer, containment, clothing, and injury unified from text to video?
14. How do references control identity without inheriting old backgrounds, poses, or held objects?
15. How do candidate reuse, review/media caching, and adoption stay consistent? Are there revocation/update bypasses?
16. How do in-flight basis changes produce old-version candidates rather than falsely current outputs?

#### Recovery, media, and learning

17. How do route-level tests prevent the confirmed nested recovery defect and other disconnected endpoints?
18. How is a disconnect between submission and ID persistence reconciled without blind retries/duplicate charges?
19. What is missing from intervals, end states, sampling, action verification, and listening checks? What stays human?
20. How are feedback/signals converted into confirmed scoped rules, independently validated, revoked, and synchronized?
21. Is equality matching sufficient? How are conflicts and truncation handled?
22. How can affordable real trials prove repeated mistakes decrease rather than merely count stored rules?

### 4. Recommendation template

| Field | Requirement |
|---|---|
| ID/priority | P0 unauthorized charges/data contamination; P1 core flows/facts; P2 quality/cost/experience; P3 extensibility. Rate actual impact |
| Type | Reproduced bug/static risk/product gap/unverified outcome |
| Evidence | File/function/input/state; label document-only inference |
| Trigger/result | User action, actual control path, unmet goal |
| Solution | Specific controller/agent/data/API/UI changes |
| Adoption/cache | Changed fingerprints, preserved work, affected successors |
| Cost/interaction | Added/removed calls/choices, not merely smarter behavior |
| Migration/failure | Legacy work, interruption, unknowns, rollback, concurrency |
| Acceptance | Failure reproduction, corrected example, exception/unrelated case |

### 5. Required final proposal

1. Overall assessment, suitable operating scale, and evidenced maturity limits.
2. Target architecture, complete user flow, controller states, and role-session tree.
3. Every agent's inputs/outputs/authority/permissions/continuation/switch/review relationship.
4. Data/version models, real production branches, event/knowledge/reference/adoption dependencies.
5. Cache keys, revocation/invalidation matrix, and in-flight changes.
6. Learning loop, cross-platform synchronization, regression examples, outcome metrics.
7. Minimum-interaction desktop/narrow-screen reading experience.
8. Complete acceptance, real-trial cost, defect priorities, implementation dependencies.

Provide the complete target design rather than only a first-phase slogan. Implementation may have dependencies, but final scope must be explicit. More agents, more user clicks, or a universal giant prompt do not replace state/data governance.

### 6. Reusable external-AI prompt

```text
Act as an independent product and AI engineering architect. Thoroughly evaluate this A/B platform document.

A develops original premium stories or novel adaptations. B further adapts an adopted story into film, series, or fast short drama, then handles direction, shots, characters/props, image/video production, review, and packaging. Novel promotion also uses acted dialogue; Seedance 2.0 Fast is common. Quality, invocation cost, and low interaction all matter.

Distinguish actual code, product goals, and observed acceptance. Read the complete design, review requirements, implementation/API index, fingerprints, and scenarios. The index is not full source; mark anything requiring code or trials instead of inventing evidence.

Focus on:
1. Program control and author/adaptation/director/reviewer/media responsibility boundaries.
2. Persistent sessions, scopes, deletions, preceding-output bindings, checkpoints, cancellation/recovery, and shared-account queuing: balance reuse and independence.
3. Whole-book upload with selected early chapters, long text, continuation, preceding changes, and truthful understanding coverage.
4. Complete B adaptation, real film/short-drama differences, single activeShootingId versus actual branches.
5. Source-to-script-to-events-to-assets-to-shots-to-real-references-to-adoption continuity, especially props, lids, transfers, containment, clothing, and injuries.
6. Business-level candidate reuse bypassing changed experiences, revoked rules, or new analyses.
7. Confirmed nested recovery method, costs, unknown submissions, download recovery, and in-flight version changes.
8. Genuine learning closure: signal extraction, applicability/exceptions, independent validation, cross-platform sync, revocation.
9. Actual-media evidence versus structural tests; unavailable detectors and unobserved details remain unknown.

Deliver a complete target design: overall assessment, issue table, user workflow, session tree, controller states/permissions, each agent's input/output, versions/cache dependencies, media recovery, learning, minimal-operation UI, costs, and acceptance. Every improvement needs evidence, benefits, costs, migration, and counterexamples.

Do not assume more agents are better. Preserve B adaptation and independent review. Do not impose fixed duration/shot/reversal rules or manual clicks for all internal analysis. Do not automatically retry paid media or add a cumulative media budget cap. Do not claim demos/structural tests prove premium finished videos.
```

<!-- TECHNICAL APPENDICES -->

## Part V: Code, API, and evidence index

Snapshot: September 29, 2026. AST-derived metadata; no application import or production database access. Paths are relative to StorySystems. Line numbers locate the snapshot; hashes appear in Part VI.

### 1. Core files and responsibilities

| Platform | File | Responsibility |
|---|---|---|
| system-a | `system-a/app/call_queue.py` | Cross-process FIFO for one account |
| system-a | `system-a/app/codex_cli.py` | Persistent sessions, deltas, preceding-output binding, CLI permissions |
| system-a | `system-a/app/core.py` | Persistence, audit, jobs, idempotency, and caching |
| system-a | `system-a/app/creative_review.py` | Independent review, bounded generation, JSON Patch |
| system-a | `system-a/app/experience.py` | Feedback, scoped rules, applications, validation, and exchange |
| system-a | `system-a/app/http.py` | Local access guard, jobs, SSE, files, and backups |
| system-a | `system-a/app/ideation.py` | AI concept entry |
| system-a | `system-a/app/interchange.py` | SceneExport v4 export |
| system-a | `system-a/app/llm.py` | Model requests, usage, result cache, and concurrency |
| system-a | `system-a/app/main.py` | HTTP routes and service composition |
| system-a | `system-a/app/models.py` | Data and output models |
| system-a | `system-a/app/novel.py` | Indexing, selected adaptation, whole-book reading, continuation |
| system-a | `system-a/app/process_tree.py` | Windows process trees and liveness |
| system-a | `system-a/app/reading_export.py` | Readable exports |
| system-a | `system-a/app/settings.py` | Role configuration, prices, and runtime settings |
| system-a | `system-a/app/story.py` | Original story nodes and adoption |
| system-a | `system-a/app/story_contract.py` | Blocks, event replay, states, presentation, and coverage |
| system-a | `system-a/app/story_review.py` | Independent original-story review |
| system-b | `system-b/app/assembly.py` | Rough cuts and assembly |
| system-b | `system-b/app/call_queue.py` | Cross-process FIFO for one account |
| system-b | `system-b/app/cinema.py` | Shot rules, prompt compilation, and render keys |
| system-b | `system-b/app/codex_cli.py` | Persistent sessions, deltas, preceding-output binding, CLI permissions |
| system-b | `system-b/app/core.py` | Persistence, audit, jobs, idempotency, and caching |
| system-b | `system-b/app/creative_review.py` | Independent review, bounded generation, JSON Patch |
| system-b | `system-b/app/experience.py` | Feedback, scoped rules, applications, validation, and exchange |
| system-b | `system-b/app/gates.py` | Actual-file inspection and observations |
| system-b | `system-b/app/http.py` | Local access guard, jobs, SSE, files, and backups |
| system-b | `system-b/app/llm.py` | Model requests, usage, result cache, and concurrency |
| system-b | `system-b/app/main.py` | HTTP routes and service composition |
| system-b | `system-b/app/models.py` | Data and output models |
| system-b | `system-b/app/process_tree.py` | Windows process trees and liveness |
| system-b | `system-b/app/production.py` | Production objects, impact, single-shot media, legacy workflows |
| system-b | `system-b/app/qualification.py` | Third-party runner qualification |
| system-b | `system-b/app/reading_export.py` | Readable exports |
| system-b | `system-b/app/runner.py` | Task execution, isolation, qualification, output acceptance |
| system-b | `system-b/app/settings.py` | Role configuration, prices, and runtime settings |
| system-b | `system-b/app/shooting.py` | B adaptation, direction, assets, and generation units |
| system-b | `system-b/app/story_contract.py` | Blocks, event replay, states, presentation, and coverage |
| system-b | `system-b/app/workflow.py` | Legacy staged proposal compatibility |
| system-b | `system-b/tools/render.py` | Media providers and Dreamina submission/query |

### 2. Core method locations

| File | Symbol | Line |
|---|---|---|
| `system-a/app/call_queue.py` | `AccountQueue.acquire` | 51 |
| `system-a/app/codex_cli.py` | `prepare` | 106 |
| `system-a/app/codex_cli.py` | `packet` | 191 |
| `system-a/app/codex_cli.py` | `CodexSessions._claim` | 303 |
| `system-a/app/codex_cli.py` | `CodexSessions.request` | 329 |
| `system-a/app/codex_cli.py` | `CodexSessions._request` | 351 |
| `system-a/app/creative_review.py` | `review_candidate` | 9 |
| `system-a/app/creative_review.py` | `generate_reviewed` | 77 |
| `system-a/app/experience.py` | `ExperienceService.applicable` | 214 |
| `system-a/app/experience.py` | `ExperienceService.guidance` | 222 |
| `system-a/app/experience.py` | `ExperienceService.validate` | 263 |
| `system-a/app/experience.py` | `ExperienceService.export_pack` | 299 |
| `system-a/app/experience.py` | `ExperienceService.import_pack` | 312 |
| `system-a/app/ideation.py` | `IdeationService.generate` | 63 |
| `system-a/app/ideation.py` | `IdeationService.adopt` | 101 |
| `system-a/app/interchange.py` | `scene_export` | 7 |
| `system-a/app/llm.py` | `LLM.json` | 136 |
| `system-a/app/llm.py` | `LLM._request` | 291 |
| `system-a/app/main.py` | `create_app` | 20 |
| `system-a/app/main.py` | `create_app.advance` | 73 |
| `system-a/app/main.py` | `create_app.generate` | 88 |
| `system-a/app/main.py` | `create_app.adopt` | 96 |
| `system-a/app/novel.py` | `chapter_index` | 11 |
| `system-a/app/novel.py` | `NovelService.analyze_all` | 163 |
| `system-a/app/novel.py` | `NovelService.next_step` | 202 |
| `system-a/app/novel.py` | `NovelService.read` | 214 |
| `system-a/app/novel.py` | `NovelService.propose` | 227 |
| `system-a/app/novel.py` | `NovelService.propose.validate` | 266 |
| `system-a/app/novel.py` | `NovelService.adopt` | 329 |
| `system-a/app/settings.py` | `Settings.read` | 47 |
| `system-a/app/story.py` | `StoryService.context` | 164 |
| `system-a/app/story.py` | `StoryService.next_step` | 194 |
| `system-a/app/story.py` | `StoryService.advance` | 241 |
| `system-a/app/story.py` | `StoryService.generate` | 276 |
| `system-a/app/story.py` | `StoryService.adopt` | 503 |
| `system-a/app/story_contract.py` | `check_world` | 82 |
| `system-a/app/story_contract.py` | `replay` | 98 |
| `system-a/app/story_contract.py` | `validate_shot_coverage` | 224 |
| `system-a/app/story_review.py` | `review_candidates` | 35 |
| `system-b/app/call_queue.py` | `AccountQueue.acquire` | 51 |
| `system-b/app/codex_cli.py` | `prepare` | 106 |
| `system-b/app/codex_cli.py` | `packet` | 191 |
| `system-b/app/codex_cli.py` | `CodexSessions._claim` | 303 |
| `system-b/app/codex_cli.py` | `CodexSessions.request` | 329 |
| `system-b/app/codex_cli.py` | `CodexSessions._request` | 351 |
| `system-b/app/creative_review.py` | `review_candidate` | 9 |
| `system-b/app/creative_review.py` | `generate_reviewed` | 77 |
| `system-b/app/experience.py` | `ExperienceService.applicable` | 99 |
| `system-b/app/experience.py` | `ExperienceService.guidance` | 103 |
| `system-b/app/experience.py` | `ExperienceService.validate` | 120 |
| `system-b/app/experience.py` | `ExperienceService.export_pack` | 131 |
| `system-b/app/experience.py` | `ExperienceService.import_pack` | 136 |
| `system-b/app/gates.py` | `Gates.inspect` | 32 |
| `system-b/app/llm.py` | `LLM.json` | 136 |
| `system-b/app/llm.py` | `LLM._request` | 281 |
| `system-b/app/main.py` | `create_app` | 22 |
| `system-b/app/main.py` | `create_app.advance` | 67 |
| `system-b/app/main.py` | `create_app.propose` | 84 |
| `system-b/app/main.py` | `create_app.adopt` | 87 |
| `system-b/app/main.py` | `create_app.change_plan` | 101 |
| `system-b/app/main.py` | `create_app.render` | 140 |
| `system-b/app/production.py` | `ProductionService.change_plan` | 117 |
| `system-b/app/production.py` | `ProductionService.apply_impact` | 157 |
| `system-b/app/production.py` | `ProductionService.propose` | 183 |
| `system-b/app/production.py` | `ProductionService.render` | 460 |
| `system-b/app/production.py` | `ProductionService.select_render` | 518 |
| `system-b/app/production.py` | `ProductionService.asset_render.recover_remote` | 646 |
| `system-b/app/runner.py` | `RunnerRegistry.execute` | 44 |
| `system-b/app/settings.py` | `Settings.read` | 50 |
| `system-b/app/shooting.py` | `ShootingWorkflow.propose_shooting` | 151 |
| `system-b/app/shooting.py` | `ShootingWorkflow.propose_shooting.validate` | 165 |
| `system-b/app/shooting.py` | `ShootingWorkflow.shooting_adoption_plan` | 199 |
| `system-b/app/shooting.py` | `ShootingWorkflow.adopt_shooting` | 212 |
| `system-b/app/shooting.py` | `ShootingWorkflow.key_scene_roles` | 258 |
| `system-b/app/shooting.py` | `ShootingWorkflow.advance_creative` | 302 |
| `system-b/app/shooting.py` | `ShootingWorkflow.creative_snapshot` | 340 |
| `system-b/app/shooting.py` | `ShootingWorkflow.propose_director` | 348 |
| `system-b/app/shooting.py` | `ShootingWorkflow.propose_director.validate` | 395 |
| `system-b/app/shooting.py` | `ShootingWorkflow.prepare_event_assets` | 486 |
| `system-b/app/shooting.py` | `ShootingWorkflow.event_manifest` | 533 |
| `system-b/app/shooting.py` | `ShootingWorkflow.observed_adoption` | 603 |
| `system-b/app/shooting.py` | `ShootingWorkflow.plan_generation_tasks` | 672 |
| `system-b/app/shooting.py` | `ShootingWorkflow.generation_dry_run` | 725 |
| `system-b/app/shooting.py` | `ShootingWorkflow.execute_generation_tasks` | 752 |
| `system-b/app/story_contract.py` | `check_world` | 82 |
| `system-b/app/story_contract.py` | `replay` | 98 |
| `system-b/app/story_contract.py` | `validate_shot_coverage` | 224 |
| `system-b/app/workflow.py` | `ProposalWorkflow.next_step` | 52 |
| `system-b/app/workflow.py` | `ProposalWorkflow.advance` | 103 |
| `system-b/tools/render.py` | `dreamina_remote` | 100 |
| `system-b/tools/render.py` | `dreamina` | 111 |

### 3. Confirmed recovery endpoint defect

The production.py AST contains `ProductionService.asset_render.recover_remote`, not `ProductionService.recover_remote`. The route calls the latter. This confirms incorrect method ownership; no paid-media reproduction was initiated.

### 4. Complete API route catalogue

Each platform registers the common http.py endpoints. Both copies are listed. Endpoint existence does not establish end-to-end acceptance.

| Platform | Method | Path | File:line |
|---|---|---|---|
| system-a | GET | `/api/health` | `system-a/app/http.py:27` |
| system-a | GET | `/api/settings` | `system-a/app/http.py:29` |
| system-a | PUT | `/api/settings` | `system-a/app/http.py:31` |
| system-a | GET | `/api/codex/status` | `system-a/app/http.py:33` |
| system-a | GET | `/api/projects/{id}/codex-sessions` | `system-a/app/http.py:37` |
| system-a | POST | `/api/projects/{id}/codex-sessions/{session}/reset` | `system-a/app/http.py:41` |
| system-a | GET | `/api/jobs` | `system-a/app/http.py:45` |
| system-a | GET | `/api/jobs/{id}` | `system-a/app/http.py:47` |
| system-a | POST | `/api/jobs/{id}/cancel` | `system-a/app/http.py:49` |
| system-a | GET | `/api/events` | `system-a/app/http.py:51` |
| system-a | GET | `/api/projects/{id}/history` | `system-a/app/http.py:62` |
| system-a | GET | `/api/projects/{id}/runs` | `system-a/app/http.py:64` |
| system-a | POST | `/api/projects/{id}/upload` | `system-a/app/http.py:66` |
| system-a | GET | `/api/projects/{id}/files` | `system-a/app/http.py:78` |
| system-a | GET | `/api/projects/{id}/backup` | `system-a/app/http.py:80` |
| system-a | POST | `/api/backups/restore` | `system-a/app/http.py:92` |
| system-a | POST | `/api/projects/{id}/comments` | `system-a/app/http.py:138` |
| system-a | GET | `/api/projects/{id}/comments` | `system-a/app/http.py:141` |
| system-a | GET | `/` | `system-a/app/http.py:143` |
| system-a | GET | `/media/{relative:path}` | `system-a/app/http.py:146` |
| system-a | GET | `/api/files/{fileid}/download` | `system-a/app/http.py:154` |
| system-a | POST | `/api/jobs/{identifier}/resume` | `system-a/app/main.py:27` |
| system-a | POST | `/api/novels` | `system-a/app/main.py:34` |
| system-a | GET | `/api/projects/{p}/novel` | `system-a/app/main.py:36` |
| system-a | PUT | `/api/projects/{p}/novel` | `system-a/app/main.py:38` |
| system-a | POST | `/api/projects/{p}/novel/analyze` | `system-a/app/main.py:40` |
| system-a | POST | `/api/projects/{p}/novel/propose` | `system-a/app/main.py:43` |
| system-a | POST | `/api/projects/{p}/novel/drafts/{identifier}/adopt` | `system-a/app/main.py:47` |
| system-a | POST | `/api/projects/{p}/novel/drafts/{identifier}/reject` | `system-a/app/main.py:50` |
| system-a | GET | `/api/brainstorms` | `system-a/app/main.py:55` |
| system-a | POST | `/api/brainstorms` | `system-a/app/main.py:57` |
| system-a | POST | `/api/brainstorms/{batch_id}/ideas/{idea_id}/adopt` | `system-a/app/main.py:60` |
| system-a | GET | `/api/projects` | `system-a/app/main.py:64` |
| system-a | POST | `/api/projects` | `system-a/app/main.py:66` |
| system-a | GET | `/api/projects/{p}` | `system-a/app/main.py:68` |
| system-a | GET | `/api/projects/{p}/workflow` | `system-a/app/main.py:70` |
| system-a | POST | `/api/projects/{p}/advance` | `system-a/app/main.py:72` |
| system-a | POST | `/api/projects/{p}/refine` | `system-a/app/main.py:77` |
| system-a | PUT | `/api/projects/{p}` | `system-a/app/main.py:85` |
| system-a | POST | `/api/projects/{p}/generate` | `system-a/app/main.py:87` |
| system-a | POST | `/api/projects/{p}/plan` | `system-a/app/main.py:91` |
| system-a | POST | `/api/projects/{p}/structure` | `system-a/app/main.py:93` |
| system-a | POST | `/api/projects/{p}/candidates/{id}/adopt` | `system-a/app/main.py:95` |
| system-a | POST | `/api/projects/{p}/candidates/{id}/reject` | `system-a/app/main.py:98` |
| system-a | GET | `/api/projects/{p}/candidates/{id}/diff` | `system-a/app/main.py:102` |
| system-a | POST | `/api/projects/{p}/candidates/merge` | `system-a/app/main.py:106` |
| system-a | GET | `/api/projects/{p}/nodes/{id}/revisions` | `system-a/app/main.py:111` |
| system-a | POST | `/api/projects/{p}/nodes/{id}/restore` | `system-a/app/main.py:113` |
| system-a | POST | `/api/projects/{p}/undo` | `system-a/app/main.py:115` |
| system-a | PUT | `/api/projects/{p}/canon` | `system-a/app/main.py:131` |
| system-a | POST | `/api/projects/{p}/patches/{id}` | `system-a/app/main.py:133` |
| system-a | GET | `/api/projects/{p}/readthrough` | `system-a/app/main.py:135` |
| system-a | POST | `/api/projects/{p}/scan` | `system-a/app/main.py:137` |
| system-a | GET | `/api/projects/{p}/knowledge` | `system-a/app/main.py:139` |
| system-a | POST | `/api/projects/{p}/edges` | `system-a/app/main.py:141` |
| system-a | PUT | `/api/projects/{p}/edges/{id}` | `system-a/app/main.py:143` |
| system-a | POST | `/api/projects/{p}/probe` | `system-a/app/main.py:150` |
| system-a | PUT | `/api/projects/{p}/probe-specs` | `system-a/app/main.py:152` |
| system-a | POST | `/api/projects/{p}/experiments` | `system-a/app/main.py:158` |
| system-a | POST | `/api/projects/{p}/experiments/blind` | `system-a/app/main.py:161` |
| system-a | POST | `/api/projects/{p}/experiments/{id}/choose` | `system-a/app/main.py:172` |
| system-a | GET | `/api/projects/{p}/experiments` | `system-a/app/main.py:175` |
| system-a | POST | `/api/projects/{p}/branches` | `system-a/app/main.py:179` |
| system-a | GET | `/api/projects/{p}/branches/{id}/compare` | `system-a/app/main.py:181` |
| system-a | POST | `/api/projects/{p}/branches/{id}/adopt` | `system-a/app/main.py:183` |
| system-a | POST | `/api/projects/{p}/branches/{id}/abandon` | `system-a/app/main.py:185` |
| system-a | GET | `/api/projects/{p}/metrics` | `system-a/app/main.py:187` |
| system-a | POST | `/api/projects/{p}/intent` | `system-a/app/main.py:189` |
| system-a | POST | `/api/projects/{p}/voice-audit` | `system-a/app/main.py:197` |
| system-a | POST | `/api/projects/{p}/seed-vision` | `system-a/app/main.py:207` |
| system-a | GET | `/api/projects/{p}/experiences` | `system-a/app/main.py:214` |
| system-a | POST | `/api/projects/{p}/feedback` | `system-a/app/main.py:216` |
| system-a | POST | `/api/projects/{p}/experiences/{identifier}/confirm` | `system-a/app/main.py:218` |
| system-a | PUT | `/api/projects/{p}/experiences/{identifier}` | `system-a/app/main.py:220` |
| system-a | POST | `/api/projects/{p}/experiences/{identifier}/validate` | `system-a/app/main.py:222` |
| system-a | GET | `/api/projects/{p}/experience-pack` | `system-a/app/main.py:224` |
| system-a | POST | `/api/projects/{p}/experience-pack/import` | `system-a/app/main.py:226` |
| system-a | GET | `/api/projects/{p}/export/{format}` | `system-a/app/main.py:228` |
| system-a | GET | `/api/schemas` | `system-a/app/main.py:235` |
| system-b | GET | `/api/health` | `system-b/app/http.py:27` |
| system-b | GET | `/api/settings` | `system-b/app/http.py:29` |
| system-b | PUT | `/api/settings` | `system-b/app/http.py:31` |
| system-b | GET | `/api/codex/status` | `system-b/app/http.py:33` |
| system-b | GET | `/api/projects/{id}/codex-sessions` | `system-b/app/http.py:37` |
| system-b | POST | `/api/projects/{id}/codex-sessions/{session}/reset` | `system-b/app/http.py:41` |
| system-b | GET | `/api/jobs` | `system-b/app/http.py:45` |
| system-b | GET | `/api/jobs/{id}` | `system-b/app/http.py:47` |
| system-b | POST | `/api/jobs/{id}/cancel` | `system-b/app/http.py:49` |
| system-b | GET | `/api/events` | `system-b/app/http.py:51` |
| system-b | GET | `/api/projects/{id}/history` | `system-b/app/http.py:62` |
| system-b | GET | `/api/projects/{id}/runs` | `system-b/app/http.py:64` |
| system-b | POST | `/api/projects/{id}/upload` | `system-b/app/http.py:66` |
| system-b | GET | `/api/projects/{id}/files` | `system-b/app/http.py:78` |
| system-b | GET | `/api/projects/{id}/backup` | `system-b/app/http.py:80` |
| system-b | POST | `/api/backups/restore` | `system-b/app/http.py:92` |
| system-b | POST | `/api/projects/{id}/comments` | `system-b/app/http.py:138` |
| system-b | GET | `/api/projects/{id}/comments` | `system-b/app/http.py:141` |
| system-b | GET | `/` | `system-b/app/http.py:143` |
| system-b | GET | `/media/{relative:path}` | `system-b/app/http.py:146` |
| system-b | GET | `/api/files/{fileid}/download` | `system-b/app/http.py:154` |
| system-b | POST | `/api/jobs/{identifier}/resume` | `system-b/app/main.py:26` |
| system-b | GET | `/api/projects` | `system-b/app/main.py:35` |
| system-b | POST | `/api/projects` | `system-b/app/main.py:37` |
| system-b | GET | `/api/projects/{p}` | `system-b/app/main.py:39` |
| system-b | GET | `/api/projects/{p}/workflow` | `system-b/app/main.py:42` |
| system-b | POST | `/api/projects/{p}/shooting/propose` | `system-b/app/main.py:44` |
| system-b | POST | `/api/projects/{p}/shooting/{identifier}/adopt` | `system-b/app/main.py:46` |
| system-b | GET | `/api/projects/{p}/shooting/{identifier}/adoption-preview` | `system-b/app/main.py:49` |
| system-b | POST | `/api/projects/{p}/shooting/{identifier}/reject` | `system-b/app/main.py:51` |
| system-b | POST | `/api/projects/{p}/generation-tasks` | `system-b/app/main.py:56` |
| system-b | POST | `/api/projects/{p}/generation-tasks/dry-run` | `system-b/app/main.py:58` |
| system-b | POST | `/api/projects/{p}/generation-tasks/execute` | `system-b/app/main.py:60` |
| system-b | POST | `/api/projects/{p}/generation-tasks/{identifier}/import` | `system-b/app/main.py:62` |
| system-b | POST | `/api/projects/{p}/assets/{identifier}/review-reference` | `system-b/app/main.py:64` |
| system-b | POST | `/api/projects/{p}/advance` | `system-b/app/main.py:66` |
| system-b | POST | `/api/projects/{p}/refine` | `system-b/app/main.py:70` |
| system-b | PUT | `/api/projects/{p}` | `system-b/app/main.py:77` |
| system-b | POST | `/api/projects/{p}/propose/{stage}` | `system-b/app/main.py:83` |
| system-b | POST | `/api/projects/{p}/proposals/{id}/adopt` | `system-b/app/main.py:86` |
| system-b | GET | `/api/projects/{p}/proposals/{id}/adoption-preview` | `system-b/app/main.py:89` |
| system-b | POST | `/api/projects/{p}/proposals/{id}/reject` | `system-b/app/main.py:92` |
| system-b | PUT | `/api/projects/{p}/proposals/{id}` | `system-b/app/main.py:97` |
| system-b | POST | `/api/projects/{p}/objects/{kind}/plan` | `system-b/app/main.py:100` |
| system-b | POST | `/api/projects/{p}/objects/{kind}` | `system-b/app/main.py:102` |
| system-b | GET | `/api/projects/{p}/objects/{kind}/{id}/revisions` | `system-b/app/main.py:104` |
| system-b | POST | `/api/projects/{p}/objects/{kind}/{id}/restore` | `system-b/app/main.py:107` |
| system-b | POST | `/api/projects/{p}/objects/{kind}/{id}/finalize` | `system-b/app/main.py:110` |
| system-b | POST | `/api/projects/{p}/objects/{kind}/{id}/unlock` | `system-b/app/main.py:112` |
| system-b | POST | `/api/projects/{p}/objects/{kind}/{id}/archive` | `system-b/app/main.py:115` |
| system-b | POST | `/api/projects/{p}/objects/{kind}/{id}/resolve` | `system-b/app/main.py:118` |
| system-b | GET | `/api/projects/{p}/scenes/{id}/validate` | `system-b/app/main.py:121` |
| system-b | GET | `/api/projects/{p}/scenes/{id}/manifest` | `system-b/app/main.py:123` |
| system-b | POST | `/api/projects/{p}/assets/generate` | `system-b/app/main.py:125` |
| system-b | POST | `/api/projects/{p}/assets/dry-run` | `system-b/app/main.py:127` |
| system-b | POST | `/api/projects/{p}/assets/options/{id}/accept` | `system-b/app/main.py:129` |
| system-b | POST | `/api/projects/{p}/assets/{id}/reference` | `system-b/app/main.py:131` |
| system-b | POST | `/api/projects/{p}/render/preview` | `system-b/app/main.py:134` |
| system-b | POST | `/api/projects/{p}/render/dry-run` | `system-b/app/main.py:137` |
| system-b | POST | `/api/projects/{p}/render/execute` | `system-b/app/main.py:139` |
| system-b | POST | `/api/projects/{p}/render/retry-plan` | `system-b/app/main.py:141` |
| system-b | POST | `/api/projects/{p}/render/import` | `system-b/app/main.py:143` |
| system-b | POST | `/api/projects/{p}/renders/{id}/review` | `system-b/app/main.py:145` |
| system-b | GET | `/api/projects/{p}/renders/{id}/adoption-preview` | `system-b/app/main.py:147` |
| system-b | POST | `/api/projects/{p}/renders/{id}/gate` | `system-b/app/main.py:151` |
| system-b | POST | `/api/projects/{p}/renders/shortlist` | `system-b/app/main.py:154` |
| system-b | POST | `/api/projects/{p}/circuit/reset` | `system-b/app/main.py:161` |
| system-b | POST | `/api/projects/{p}/assembly/plan` | `system-b/app/main.py:164` |
| system-b | POST | `/api/projects/{p}/assembly/run` | `system-b/app/main.py:166` |
| system-b | POST | `/api/projects/{p}/assemblies/{id}/accept` | `system-b/app/main.py:168` |
| system-b | POST | `/api/projects/{p}/import-scene-export` | `system-b/app/main.py:171` |
| system-b | GET | `/api/projects/{p}/experiences` | `system-b/app/main.py:173` |
| system-b | POST | `/api/projects/{p}/feedback` | `system-b/app/main.py:175` |
| system-b | POST | `/api/projects/{p}/experiences/{identifier}/confirm` | `system-b/app/main.py:177` |
| system-b | PUT | `/api/projects/{p}/experiences/{identifier}` | `system-b/app/main.py:179` |
| system-b | POST | `/api/projects/{p}/experiences/{identifier}/validate` | `system-b/app/main.py:181` |
| system-b | GET | `/api/projects/{p}/experience-pack` | `system-b/app/main.py:183` |
| system-b | POST | `/api/projects/{p}/experience-pack/import` | `system-b/app/main.py:185` |
| system-b | GET | `/api/projects/{p}/export/{format}` | `system-b/app/main.py:187` |
| system-b | GET | `/api/runners` | `system-b/app/main.py:245` |
| system-b | POST | `/api/runners/{id}/qualify` | `system-b/app/main.py:247` |
| system-b | GET | `/api/runners/{id}/qualification` | `system-b/app/main.py:252` |
| system-b | GET | `/api/projects/{p}/runner-runs` | `system-b/app/main.py:254` |
| system-b | POST | `/api/projects/{p}/runner-runs/{identifier}/recover` | `system-b/app/main.py:256` |
| system-b | POST | `/api/projects/{p}/curator/{id}` | `system-b/app/main.py:259` |
| system-b | GET | `/api/schemas` | `system-b/app/main.py:262` |

### 5. Persistent document kinds

Extracted from literal Store.put(kind,...) calls. Dynamic kinds may be omitted; listing does not establish a formal schema.

#### system-a

`addressable_block`, `backup_provenance`, `book_analysis`, `book_unit_analysis`, `branch`, `candidate`, `canon_patch`, `chapter_analysis`, `codex_session`, `comment`, `creative_review`, `decision_batch`, `edge`, `experience`, `experience_application`, `experience_migration`, `experience_pack`, `experience_validation`, `experiment`, `feedback`, `file`, `generation_request`, `idea_batch`, `llm_hold`, `node`, `novel_draft`, `novel_source`, `novel_source_version`, `observation`, `preference_signal`, `probe_spec`, `project`, `revision`, `run`, `spike`

#### system-b

`assembly`, `asset_option`, `backup_provenance`, `codex_session`, `comment`, `creative_review`, `curator_item`, `direction`, `experience`, `experience_application`, `experience_migration`, `experience_pack`, `experience_validation`, `feedback`, `file`, `gate_report`, `generation_task`, `llm_hold`, `master`, `preference_signal`, `project`, `proposal`, `qualification`, `render`, `reservation`, `retry_request`, `revision`, `run`, `runner_run`, `scene`, `shooting_script`, `shot`, `story_source`, `style`, `transition`, `variant`

### 6. Tests and evidence

Current manifests record A:164 and B:218 tests. Older docs/pytest-result.txt reports contain 157 and 216 respectively; collaboration XML belongs to an earlier run. These are different historical versions, not a newly rerun full suite.

| Evidence | Available in original workspace |
|---|---|
| `system-a/docs/pytest-result.txt` | Yes |
| `system-b/docs/pytest-result.txt` | Yes |
| `.validation/collaboration-a-tests.xml` | Yes |
| `.validation/collaboration-b-tests.xml` | Yes |
| `.validation/upgrade-20260927/browser-result.json` | Yes |
| `.validation/upgrade-20260928/browser-result.json` | Yes |
| `.validation/reader-smoke-results.json` | Yes |
| `.validation/storyboard-copy/verification.json` | Yes |
| `.validation/codex-system-b-b1ab6274/verification.json` | Yes |
| `.validation/codex-result-binding-c2b6202d/verification.json` | Yes |
| `.validation/collaboration-real-a-5c254b88/verification.json` | Yes |
| `.validation/handoff-6c841e26c8784b57a62414bec6a3af18/result.json` | Yes |

#### Test-file entry points

##### system-a

- `system-a/tests/conftest.py`: 0 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/fixtures/codex_process.py`: 0 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/fixtures/queue_worker.py`: 0 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_call_queue.py`: 4 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_call_safety.py`: 18 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_codex_cli.py`: 21 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_common.py`: 14 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_creative_patches.py`: 4 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_experience_upgrade.py`: 2 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_ideation.py`: 7 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_model_protocols.py`: 5 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_novel_upgrade.py`: 15 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_reader_api.py`: 2 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_story.py`: 31 statically identified test functions; parametrized case counts can differ.
- `system-a/tests/test_story_collaboration.py`: 8 statically identified test functions; parametrized case counts can differ.

##### system-b

- `system-b/tests/conftest.py`: 0 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/fixtures/codex_process.py`: 0 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/fixtures/queue_worker.py`: 0 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_call_queue.py`: 4 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_call_safety.py`: 19 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_codex_cli.py`: 21 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_common.py`: 14 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_complete_plan.py`: 8 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_creative_patches.py`: 4 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_model_protocols.py`: 5 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_onboarding.py`: 7 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_production.py`: 26 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_reader_api.py`: 2 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_shooting_upgrade.py`: 30 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_storyboard_workflow.py`: 21 statically identified test functions; parametrized case counts can differ.
- `system-b/tests/test_upgrade_jobs.py`: 2 statically identified test functions; parametrized case counts can differ.

### 7. Snapshot scope

The index covers 103 app/static/tools/tests and release/configuration source files. It excludes data, login files, private text, production media, settings.json, and .env.

Source fingerprints, core symbols, lines, routes, and evidence locations support external source verification. Manifest labels are not automatically evidence of real paid-media acceptance.


## Part VI: Snapshot metadata and source fingerprints

Machine-index fingerprints, release metadata, the confirmed defect, and document checks are represented as readable tables. Core methods and complete endpoints appear in Part V without a repeated JSON dump.

### 1. Snapshot metadata

| Item | Value |
|---|---|
| Index format | `ABReviewSourceIndex-v1` |
| Snapshot date | 2026-09-29 |
| Original generation time (UTC) | 2026-09-29T14:06:25.934150+00:00 |
| Indexed files | 103 |
| Route records | 165 |
| Method | Static AST and file SHA-256; applications not imported; production data not read |

### 2. Release manifest records

| Platform | Release | Minimum Python | Tests | Complete paid-provider verification | Historical browser label |
|---|---|---|---|---|---|
| system-a | 2.0.0 | 3.11 | 164 | false | Windows Edge 1440px / 390px |
| system-b | 2.0.0 | 3.11 | 218 | false | Windows Edge 1440px / 390px |

These are original manifest values, not tests rerun during consolidation/translation. Older report counts remain historical evidence.

### 3. Confirmed recovery defect

| Field | Value |
|---|---|
| ID | R16 |
| File | `system-b/app/production.py` |
| AST symbol | `ProductionService.asset_render.recover_remote` |
| Evidence | recover_remote is nested inside asset_render, not a ProductionService method; the route calls b.recover_remote. |

### 4. Source-file SHA-256

Paths are relative to StorySystems. Hashes identify source content in the original review index, without including the code, secrets, or production data itself.

| File | Lines | SHA-256 |
|---|---|---|
| `system-a/app/__init__.py` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `system-a/app/call_queue.py` | 84 | `2e3d12032fa82985c416f8c79d63c119f989b031c00857fcd7893bae73bd2aa8` |
| `system-a/app/codex_cli.py` | 498 | `55dfc94e5579e12181735cb1b980fcb72be6b648ebcffa4949e4c9b615d5fc68` |
| `system-a/app/core.py` | 189 | `e9b0c4240fa5d1445301c6e624ca055709efb327a45025f0ad63ecf283f03fde` |
| `system-a/app/creative_review.py` | 125 | `7d730d304792150e3903efbc90e47e220ccf4b71d001338fcd8a865209035e6c` |
| `system-a/app/experience.py` | 334 | `cb7d6a18351285859d7fa39585e10f26281c85025df273b10f4d1b2b9b683213` |
| `system-a/app/http.py` | 158 | `f5740af9a3f7eec5e91a4b21bdce1f66634cc9949d80f2460648378ebec7475d` |
| `system-a/app/ideation.py` | 107 | `adc94165de87fb6ee65f11a114dd657f48908ee60e00e1c77f9614ab7c80f6a0` |
| `system-a/app/interchange.py` | 47 | `1c3b684f6fc41bfc959e930badf97759d0a64a783724595e3d2f012fff60b1cc` |
| `system-a/app/llm.py` | 339 | `53657d467ee8709bdab3000e5e1b7ca797d9ffcc5613e472d407c076d2451fac` |
| `system-a/app/main.py` | 239 | `258d3befad0c12819078b312c17e3386be5dae9fd3b5998d51828088788f58db` |
| `system-a/app/models.py` | 148 | `567d78658ab8ec3ce2c45d5b989832804177a714c69e8a64637e92961d5bab55` |
| `system-a/app/novel.py` | 372 | `83a4dd37cd5683d15115b94105cee1fde86f4af89bbf32c211376e2ce559a1f2` |
| `system-a/app/probe_media.py` | 27 | `4328fc9013171142b35a67f9d7a5a64190dcc8e9f87c9172534cbbad207846f4` |
| `system-a/app/process_tree.py` | 85 | `43c7be3274770e71699ed6b9c0f44abe049c98c6a10d9410389feffac82351e1` |
| `system-a/app/reading_export.py` | 66 | `8349f262fdc3dae3c76b21f72108e3b7aaa074892ba81bf677d6f502777fa969` |
| `system-a/app/settings.py` | 112 | `5339f9004f0576e81640a8e9598ed4f62b01fa227ab47bec64f1927b97a1e384` |
| `system-a/app/story.py` | 892 | `01340092e1af02eed815d9965f63b79c72cecd3167d4834e1637983a9b807634` |
| `system-a/app/story_contract.py` | 242 | `e7e7a1e497bc4c6bade7046d6db93dc6696397eb2ba8342a51c4829986445e3f` |
| `system-a/app/story_review.py` | 87 | `5c3b15404ded4e65967e995e66edf5121e7a20b2dd320d4463af425c7fd6cc25` |
| `system-a/static/app.js` | 69 | `346d1d665d240a0d1bcf38e718c2552fe77d84097137efdfb3f0e76efbb4c061` |
| `system-a/static/codex-ui.js` | 72 | `1a71990dffcff4f7a78dda1f1bbec72f3235660799388ac7809b746a8e50df2c` |
| `system-a/static/common.js` | 59 | `fab548b9e76061519ae24d19e3187523a30bce6966704bd44d37933c98e38742` |
| `system-a/static/ideation.css` | 1 | `4a0c496eab8d066b726b18de9f2dfeacccb725a0f7e29de307f906bd090d97c1` |
| `system-a/static/ideation.js` | 86 | `031e933f774a332a49a790ed8c2f7601d61cd84c3e66e1c72d96ad4910ad39a1` |
| `system-a/static/index.html` | 1 | `34e65fb6ed8ebd90551c0d563fe2660fd31b94f4b44e54ebb64901effe035e87` |
| `system-a/static/memory-ui.js` | 57 | `8799f12f5244e796e5635ce044ecf49336bba7a3487b0f186d4db0fe2e032ec2` |
| `system-a/static/reader.css` | 30 | `c4fb2ebcf416a0d8676e0a4b7721abdb437d05c569eaf5872b30d0ae861c2937` |
| `system-a/static/reader.js` | 86 | `bc41973d0d551b755c13ad7bfdcd74afb0fc14ecdb7ed051ff69340837c3d86c` |
| `system-a/static/studio-upgrade.css` | 5 | `9de0cb01cd0cf4f6de2d0cc8b38761fcf321e756fe4a2141eaf01cbd05e59ff3` |
| `system-a/static/studio-upgrade.js` | 146 | `e2370944ae49d50908f333b6d4b987ee3a1b679cf3f9ad289e7d55cf76d2e576` |
| `system-a/static/style.css` | 8 | `f049ab77b28927b13d6fe9af0ece42752e9947cc010a422dd7d50e6fa9e681d3` |
| `system-a/tools/probe_render.py` | 152 | `0a14d561cfb48f58cde9b59a6df7afe95153ada01050e3157a3a539cc5a7a21c` |
| `system-a/tests/conftest.py` | 21 | `345b53197457aebc3058a719d3be6ecd306d15a243b3bc91fe9ff73660bdcb58` |
| `system-a/tests/fixtures/codex_process.py` | 59 | `928eac630238d633b593bd7b16246275794594e8a25e4db379be3dfc164a9d31` |
| `system-a/tests/fixtures/queue_worker.py` | 24 | `52665e4aaf00ca7cc50997960b132c81e4bb8a9ada6a864e1c4928d4a8e01bcc` |
| `system-a/tests/test_call_queue.py` | 71 | `30f7c600e8885f09e2eaa8f9d74e102711c273ec742cb7ff2ec29f429b011487` |
| `system-a/tests/test_call_safety.py` | 238 | `c7c8428d99241d81f628b441c1cd2a4d3a5c6055d44b79689f3ea6afdc4f4a84` |
| `system-a/tests/test_codex_cli.py` | 302 | `ffa475b038224c5e54d9b578701eab54b647a05a2c76385d58222acf726b9226` |
| `system-a/tests/test_common.py` | 102 | `94113f24bb37a98418e73b380a8543d3035dee38ad11df90c7acdd4fc281fa6c` |
| `system-a/tests/test_creative_patches.py` | 63 | `0dbae324fd5062dbb2078d6ca8a59d5880e56423ee0b3113bf648acc542e6280` |
| `system-a/tests/test_experience_upgrade.py` | 39 | `892e14bef5b6c05262abc1a0c39f35615db243f397854fc84f82ad98036e2966` |
| `system-a/tests/test_ideation.py` | 107 | `cf7093eb2bde710e4c9b5534ff8f439757d2d140767415e9b4aae6e39ce060c4` |
| `system-a/tests/test_model_protocols.py` | 45 | `2c88d3eb9b71b6a6a5e632f43eda551e0caecd7e90bc83e3c3127561c1a76f4c` |
| `system-a/tests/test_novel_upgrade.py` | 217 | `039b2a19db1de6780939b217e0de207a7b46d92d4d8489fd60c221c4b38d23ba` |
| `system-a/tests/test_reader_api.py` | 44 | `79ce535eb93b088dd5c053b036560223eaf442b309b2c0179c85345f294da43b` |
| `system-a/tests/test_story.py` | 321 | `d9f0917798914b7f39e5223e32547b1980d86e6865d120f61e68b2b6bc85f0d9` |
| `system-a/tests/test_story_collaboration.py` | 149 | `5b49991786a5d4673ef64fff94e09f29de9d920b5e9acdedc5020b62afbfada2` |
| `system-a/requirements.txt` | 9 | `8918ae183d17ed788fb92cb184c9d50e7a1ea7a00914b69750b93377ac5c79b4` |
| `system-a/MANIFEST.json` | 102 | `c1e9cb30e5bf606493f4ce90fa5ba5e7b721aaad7d727ae9e97259498c3feaf8` |
| `system-b/app/__init__.py` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `system-b/app/assembly.py` | 107 | `34e5d86b3c71df29a1e0483f28eccdf3dc98c2573eac990812954f51698a09ba` |
| `system-b/app/call_queue.py` | 84 | `2e3d12032fa82985c416f8c79d63c119f989b031c00857fcd7893bae73bd2aa8` |
| `system-b/app/cinema.py` | 165 | `c5ea6e5bfc48a7c38230ff82370212e0f879ef4b0426db218c90e2296e0295b2` |
| `system-b/app/codex_cli.py` | 498 | `55dfc94e5579e12181735cb1b980fcb72be6b648ebcffa4949e4c9b615d5fc68` |
| `system-b/app/core.py` | 189 | `e9b0c4240fa5d1445301c6e624ca055709efb327a45025f0ad63ecf283f03fde` |
| `system-b/app/creative_review.py` | 121 | `384dc7622920d7cd38da4fd0c0fb8efc0a611910b04932b28ae8a9b9a0a8543c` |
| `system-b/app/experience.py` | 142 | `e3bc0953fcac6c7bdf8aec107d09ab0a4a1674a33f55c6d3f7be997686378502` |
| `system-b/app/gates.py` | 115 | `a6ad393de3825e543031f2bac973b72cba8f6ab37f65f2eac32e9faaabd299b0` |
| `system-b/app/http.py` | 158 | `f5740af9a3f7eec5e91a4b21bdce1f66634cc9949d80f2460648378ebec7475d` |
| `system-b/app/llm.py` | 329 | `d0f55ab6b07ab08f38e6145b1300d7fd644ae9fb42a9282ed5db17e25cb7b4a8` |
| `system-b/app/main.py` | 265 | `8b98fb09c5c2e5911aa5c873f3c7142f6791ef445e25185d6d380f38391f371f` |
| `system-b/app/models.py` | 101 | `6823abc589ad5028c1c69ecf6fafea5f487b6141f2e8d5fee79077063d0da261` |
| `system-b/app/process_tree.py` | 85 | `e6b7cd3e711871ff700f14ca885ab90100a5fe173bac7765a8bf64dac7f451b6` |
| `system-b/app/production.py` | 678 | `16d04272006efeb0559322648700f744f1d2b8966dc8c5daf692dc68e94b25c2` |
| `system-b/app/qualification.py` | 31 | `0ae8cf633db5836d1d47ececde4e6d4fbce8131e0da402786d8d4a6c48ed5678` |
| `system-b/app/reading_export.py` | 69 | `002656d1608bd30c5868b10bddfc43553b8afc50a0a4da8252b02a3040e7917d` |
| `system-b/app/runner.py` | 276 | `fd35095a01c77ddf58d1921ef7c687e833bdb9d2f29cc44d4a3c1ae7cad285c9` |
| `system-b/app/settings.py` | 134 | `c3e3847db19e488928d275071a2152dcdc4a70eb75c2558c2438cf50de5f87c1` |
| `system-b/app/shooting.py` | 786 | `6688a0fb51a8468c99770c9a02cdf894dca66eb5829c49f2bba4f6d87cb1a7cd` |
| `system-b/app/story_contract.py` | 242 | `e7e7a1e497bc4c6bade7046d6db93dc6696397eb2ba8342a51c4829986445e3f` |
| `system-b/app/workflow.py` | 110 | `58aaca214979b2239cc9b47d36b9e54e7ca69e1f6f5b475527b249e820da9d88` |
| `system-b/static/app.js` | 77 | `c30ab2d28b952734f6b59362eac315cd421ef3d611b2449e5752f0392c8994c3` |
| `system-b/static/codex-ui.js` | 72 | `82b2f7ee4fb02f56ae79664993055b2db8837c628ba27d39542ba3bf3f2b49d7` |
| `system-b/static/common.js` | 64 | `349a3bafe32c38f1ea6b708775d0ebe8a0e098fc91734edbeeece2b8324c91ca` |
| `system-b/static/index.html` | 1 | `863755f819080137a085cacc116793f2a72c835de524853dc66a41637758b4e7` |
| `system-b/static/memory-ui.js` | 57 | `8799f12f5244e796e5635ce044ecf49336bba7a3487b0f186d4db0fe2e032ec2` |
| `system-b/static/reader.css` | 33 | `6ceed6af0ab3f1a02cfaa56fadcbf611792e18efd86d12f320c417d59efa6130` |
| `system-b/static/reader.js` | 94 | `02f6c0bd4ea2b878018e696f0852ea5aa3ff3af9f216c8dd4f56a41035aa72f5` |
| `system-b/static/shot_text.js` | 51 | `63ca35450838e6ea98973e895131df285ec465a13ec13905fdba99603226e2d3` |
| `system-b/static/studio-upgrade.css` | 5 | `9de0cb01cd0cf4f6de2d0cc8b38761fcf321e756fe4a2141eaf01cbd05e59ff3` |
| `system-b/static/studio-upgrade.js` | 149 | `ebb40eb03ca456a79ca4f0d597c8e7be4aba451a5f32bafb7d442cf3e50c7f1b` |
| `system-b/static/style.css` | 8 | `f049ab77b28927b13d6fe9af0ece42752e9947cc010a422dd7d50e6fa9e681d3` |
| `system-b/tools/qualification_fixture.py` | 22 | `d50cceec0245bde3ecaafe63fba82a5f954c86ef94be45a4c1e8d9c235b042ef` |
| `system-b/tools/render.py` | 272 | `fad14f3a23421b8792669e273a6230be64ca378f2a98829203830a9dffcf4e33` |
| `system-b/tests/conftest.py` | 21 | `e0133e2fecf7e83e91d15d0fe9989947c8f21f6b15169697e53291e5ed3feed4` |
| `system-b/tests/fixtures/codex_process.py` | 59 | `928eac630238d633b593bd7b16246275794594e8a25e4db379be3dfc164a9d31` |
| `system-b/tests/fixtures/queue_worker.py` | 24 | `52665e4aaf00ca7cc50997960b132c81e4bb8a9ada6a864e1c4928d4a8e01bcc` |
| `system-b/tests/test_call_queue.py` | 71 | `30f7c600e8885f09e2eaa8f9d74e102711c273ec742cb7ff2ec29f429b011487` |
| `system-b/tests/test_call_safety.py` | 255 | `4051b34af381c7d1fa70f4ed14cf9ffe75ae405890c7f58bf14522143dafa7dc` |
| `system-b/tests/test_codex_cli.py` | 302 | `ffa475b038224c5e54d9b578701eab54b647a05a2c76385d58222acf726b9226` |
| `system-b/tests/test_common.py` | 102 | `5a74c91fb9ecffd8af4b492a6722afec515f0156b77e7e4693c107278965859a` |
| `system-b/tests/test_complete_plan.py` | 138 | `10f9a0c4589d4b914f6eac1c8a5fcde9649efeca2ecbea8c6d72465da2bdca5e` |
| `system-b/tests/test_creative_patches.py` | 63 | `0dbae324fd5062dbb2078d6ca8a59d5880e56423ee0b3113bf648acc542e6280` |
| `system-b/tests/test_model_protocols.py` | 45 | `8d511a4f8bb4cdebd8e8e46973a1d6907b5b05a8e77d0ed9ded451e454f5a532` |
| `system-b/tests/test_onboarding.py` | 94 | `ca5916db1f621eb05438dea918dfc688673b03e32300d9f5cea7bc1e30331914` |
| `system-b/tests/test_production.py` | 175 | `2b66559859ac2fb7ffa1a57464064338c2f944f240b20ff167d0b9f1785f136d` |
| `system-b/tests/test_reader_api.py` | 47 | `292de122a58a18ceb197b12cf5ac0cdd0a633a3baae74265a4eaae7b30271b7f` |
| `system-b/tests/test_shooting_upgrade.py` | 424 | `9468a77b34faf1d427ed6ae3ffb35ca6bece4045986ed570646c409b1bb5ec1d` |
| `system-b/tests/test_storyboard_workflow.py` | 266 | `2256fd7c28136e2aa755ee767cc2a62525baa921d007963227b08c25016e605a` |
| `system-b/tests/test_upgrade_jobs.py` | 41 | `9b3de9751df0abc7e6b4c7b5e03e46085a12db8f0efe614e9abf5e4eca23284c` |
| `system-b/requirements.txt` | 9 | `8918ae183d17ed788fb92cb184c9d50e7a1ea7a00914b69750b93377ac5c79b4` |
| `system-b/MANIFEST.json` | 108 | `5e8699e857eaf27bd14c291526e89cf3cde080f2408739cc3435996568d68ed3` |

### 5. Original document checks

| Check | Result |
|---|---|
| `balancedCodeFences` | Passed |
| `uniqueHtmlIds` | Passed |
| `internalAnchorsResolve` | Passed |
| `localLinksResolve` | Passed |
| `noExternalRuntimeAssets` | Passed |
| `confirmedRecoveryAstFinding` | Passed |
| `htmlJavaScriptSyntax` | Passed |

These checks concern document structure, links, and script syntax. They are not new business suites, screenshot inspections, or paid-media tests.

### 6. Source-material fingerprints

Original filenames are retained as provenance identifiers. This document is independently readable; opening those files is not required.

| Original material | SHA-256 |
|---|---|
| `01-评审包说明.md` | `1d007403b8f1108df878d8b0676972c687acedc95a7fe01672d2c5b3407f8a93` |
| `02-AB详细设计文档.md` | `f4480d79294f8154767dedafbfcf0e2d8fe08a5a01eb7417f26dde146c6f43d4` |
| `03-外部评估任务书.md` | `56e861fb4fac2c87928c58245caf94be9f8baaf6f936a18248eb606f9688af71` |
| `04-代码与接口索引.md` | `5fea581d8a5880e91232d4c30e4c10754ba60220237edd4ca27095a74c8c99f1` |
| `05-代码快照索引.json` | `9efd551817254fa06679979310f5fd1fd7062eb08efa88759c82e7ccda7714e3` |
| `06-关键场景与任务轨迹.md` | `04b97f9298f2043d7b8daf8bb20fd48b4949b583c9266e450d1d2c7c575bcecb` |
| `07-文档检查记录.json` | `491d710b386885a95400abf623fea9f4f3c5480146712a0120d4026331743920` |
