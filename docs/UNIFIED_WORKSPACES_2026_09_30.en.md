# A/B Studio: implementation and design addendum

September 30, 2026. This updates the September 29 external review package, which remains a historical pre-change snapshot. At the user's request, no tests were run for this refactor.

## Ownership and user flow

One local application hosts two workspaces on one database, job pool and account call queue.

```text
Application controller
├─ A: original writing / segmented novel understanding and adaptation
│  ├─ Full film, series and fast-drama script versions and comparisons
│  ├─ Independent story review and local revisions
│  └─ User adoption → ScriptPackage-v1
└─ B: direction and production from the adopted A script
   ├─ Event requirements → key staging choices → recommended shots
   ├─ Visible assets → base references / necessary appearance variants
   ├─ Generation units and cost previews
   ├─ Actual clip intervals → continuous narrative review → group adoption
   ├─ Observed end states → downstream continuity / production package
   └─ Story change request → new A candidate and user adoption
```

A owns all presentation conversion and comparison. B no longer writes another treatment. Creation route, audiovisual format and aspect ratio are independent. A retains separate adopted pointers per format; B retains separate production branches. An independently reviewed and adopted novel draft already in its target format can be published without rewriting it again. Users chiefly read, compare, adopt, give feedback and approve paid batches. They can select a small number of key scenes for alternative staging; ordinary scenes follow independently reviewed recommendations.

## Agents, sessions and authority

The program owns official facts, schedules, dependencies, costs and user choices. Models handle creative and review judgments within assigned tasks; they cannot grant themselves tool permission or purchase media.

| Responsibility | Session context |
| --- | --- |
| A original writing | Reuse structure, story and script roles |
| A novel work | Reuse segmented analysis, excerpt adaptation and range caches |
| A format writing | `presentation`, scoped to `script:<format>` |
| Independent written review | Separate reviewer session; source, candidate and evidence, without author reasoning |
| B scene direction | `shots`, scoped to `shots:<format>:<sceneId>` |
| B sequence review | `vision`, scoped to `sequence-review:<format>:<sceneId>` |
| Media execution | Program-issued fixed requests, persistent remote IDs, actual files and recovery records |

Separate agents mean separate responsibilities and context, not a new chat for every call. CodexSessions, account queue, settings, task persistence and process control now have shared implementations. Existing session IDs and checkpoints remain. Continuing work synchronizes changes, retractions, applicable experience and a few examples incrementally. The relevant `shortdrama-director` asset card is loaded with a fingerprint as reference data rather than resending the entire skill or treating it as tool authority.

## Adopted versions and handoff contract

A stores `script_version` with the format, complete prose, event states, source mapping, independent review, approved protected-story changes, experience revision and source snapshot. `ScriptPackage-v1 / schemaVersion: 1` carries adopted IDs, source project, mode, `scenes`, `storyDocument`, stable body/dialogue IDs, initial/event states, playback order, mapping, fingerprint, demo marker and review basis. It retains SceneExport v4 reading coverage, facts, audience knowledge, dramatic functions and evidence.

B stores `adopted_script` and `activeScriptId` tied to A's `sourceScriptVersionId`. Earlier `shooting_script` versions and media remain readable. A branch update previews changed/preserved scenes and affected shots/media, then checks the preview basis at adoption. Scene signatures include related identities, event states, holding/containment and playback order, excluding unrelated world state.

Full-book indexing and background analysis progress remain source evidence. They are not repeatedly sent to the format agent or used alone to expire an adopted excerpt. A change to adopted prose or relevant facts changes the creative basis. Legacy SceneExport versions 1–4 remain readable; the unified entry returns legacy scripts to A for presentation and continuity completion, rather than claiming missing states are complete.

## “Clean” base images and state variants

“Clean” means a normal base reference with neutral expression. Declared costume, injury and dirt remain intact.

| Asset | Base reference | Additional image when needed |
| --- | --- | --- |
| Character | Same identity and baseline costume, neutral expression, stable pose, empty hands; 2×2 head front/side and body front/back | Visible significant costume, hair, injury or similar appearance change needs an anchor |
| Prop | Independent front/side/back/overhead views, without owner or hands | Necessary structure, material or damage change |
| Location | Empty high-angle 16:9 environment, fixed architecture and furniture | Necessary layout or environmental appearance change |

Expression, pose, position, handoff, containment, opening/closing and visibility remain event states and normally reuse the base image. A state record does not imply a newly generated image. Significant prop opening, damage or contents can receive an optional state reference after a cost preview; its prompt describes the physical change without owner or position. Child images edit the actual direct parent with the relevant differences. References record actual files, identity hashes, responsibilities, controlled attributes, inheritance exclusions and human observation. Identity images do not prove that an action finished. Missing references block only tasks that use them. These prompts and checks cannot guarantee model obedience.

## Sequence review, media and cost

Written review checks events, scenes and adjacent shot groups for causality, audience knowledge, prop states and information delivery. Individual clips retain decoding, aspect-ratio and duration checks. Shots can declare `eventPhase` and `endEventPhase`; within an event, a cut must connect the previous end to the next start. A setup or reaction shot cannot claim the whole action already completed. Substantive intermediate states must be subdivided in A.

A generation unit may contain consecutive shots. Internal continuity is handled by one request; external strong dependencies wait for actual upstream adoption. Platform duration, image-count and capability limits come from configuration, never assumed Seedance limits. Paid batches still show known cost and cache status before submission.

Returned source files are retained. Users mark actual per-shot intervals. Sequence review samples real times within those intervals and records frame IDs, timestamps, hashes, planned states and adjacent narrative context. This is sampled visual review: missing evidence, unavailable models, unheard audio and unobserved complete actions remain unknown. It does not replace human viewing of complete picture and sound.

Group adoption requires a person to inspect the full unit and provide evidence, confirming each cut's required end state or entering a different observed state. Records commit together; replacing a pinned clip needs explicit permission. Downstream continuity uses the adopted interval's evidence frame and observed state, never the raw file's final frame. Replacing a clip or interval invalidates real strong dependencies while retaining unaffected results and source files. Unchanged effective media requests remain cacheable. The production package includes adopted script, playback order, assets, real media, intervals and a version manifest.

## UI, APIs, data and verification boundary

Unified routes are `/a/` and `/b/`. Root `POST /api/handoff` handles A→B. A adds script proposal, comparison, publication, adoption and packaging. B adds script import/preview, change requests, scene sequence review and generation-unit group adoption. A emphasizes full scripts and comparisons; B emphasizes adopted scripts, shots, visible assets and generation units. A story suggestion from B creates an A candidate for the user's review, not an immediate production rewrite.

Pre-change backup: `.maintenance-backups/unified-workspaces-20260929-231235`. Default startup transactionally imports old records into root `data/studio.sqlite3`, merging settings in root `data/settings.json` and leaving original databases/media intact. Active legacy jobs or conflicting IDs stop import.

Only Python/JavaScript syntax and static structure/interface inspection were performed. No project tests, application startup/migration, browser walkthrough, real text model calls, image or video generation were performed. Neither runtime correctness nor real creative/media quality is claimed as validated; historical test evidence applies only to the earlier version.
