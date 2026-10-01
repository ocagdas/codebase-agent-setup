# Roadmap: portable project guidance and reusable code knowledge

Status: reconciled with the working tree on 8 September 2026. Configuration, version overrides and packaging are implemented; local retrieval and manual full-snapshot sharing are partial deliveries of the knowledge roadmap. STATUS.md and VALIDATION.md remain the sources for current readiness and executed checks.

See [repository knowledge](project/ai_workflow/knowledge.md) for the layer model and the agent-facing rules; TODO.md owns open actions.

## Aim

Give coding agents a consistent project baseline and reusable, revision-aware knowledge of large repositories. Share project information, goals, guidance, and generated knowledge across agents, sessions, clones, machines, and teams. Let individuals customise supported behaviour without changing shared defaults or this distribution.

Keep the knowledge engine usable independently of Spec Kit, with this package providing configuration and workflow integration. Spec Kit remains the owner of feature specifications and tasks; caches must not become a second task ledger.

## Existing foundation

The package supplies project configuration, engineering guidance, agent entry points, an upstream Spec Kit pin, and installation helpers. Bootstrap creates local file inventories, branch deltas, and worktree overlays. It checks basic semantic manifests but does not execute an indexing backend, compose semantic graphs, or publish/fetch shared artifacts.

Repository knowledge is indexer-agnostic as of 2026-09-30: the CGC and Sourcegraph adapters were retired and CAS ships no indexer. You declare a command; CAS runs it, caches each artifact under the content hash of the single file it describes, resolves worktree over branch over base, and shares artifacts through declared transport commands. Mixed-language repositories are supported — C/C++ and Python indexers coexist in one cache.

Current base selection picks the first configured reference that exists, then uses its merge-base with HEAD. It does not infer parent trunks. Large-repository performance and live agent token savings have not been established.

## Configuration hierarchy

The resolver uses JSON files. See [settings.md](project/ai_workflow/settings.md) for current fields, paths and configuration. Broader knowledge controls remain future work.

Implemented precedence, lowest to highest:

| Order | Scope | Purpose | Sharing |
| --- | --- | --- | --- |
| 1 | Distribution defaults | Supported baseline, including validated upstream pin | Distribution |
| 2 | User defaults | Preferences across projects | Personal |
| 3 | Shared project settings | Team defaults and project requirements | Project Git |
| 4 | User settings for this project | Personal overrides keyed by repository identity, reusable across clones | Personal |
| 5 | Checkout-local settings | Overrides for one clone/worktree | Ignored file |
| 6 | Explicit invocation settings | Temporary CLI/session choices | Not persisted |

This interprets the requested hierarchy as reading user defaults first, overlaying shared project settings, then personal project and checkout settings. To supersede a team default, set the preference in the personal project layer. Within user configuration, merge general settings before the matching project entry.

Implemented locations are an OS-appropriate user configuration directory containing `codebase-agent-setup/config.json` with general settings and project entries, committed `ai_workflow/settings.json`, and ignored `ai_workflow/settings.local.json`. Existing bootstrap.json navigation fields enter at shared-project precedence before settings.json. Project policy and commands remain in their existing files; configuration does not copy them into a second authority.

Recursively merge mappings; replace lists/scalars; reject unknown keys; define null/reset behaviour in the schema. Resolve relative paths against the declaring file. Provide effective-configuration inspection showing each setting's origin with secrets redacted. All commands must use the same resolver.

Separate personal preferences from mandatory project checks and runtime permissions. Overrides must not silently downgrade required checks or bypass execution permissions. Diagnose conflicting choices rather than silently changing behaviour.

### User-selectable behaviour

Current support includes retrieval mode, backend selection, integration selection and query limits supplied on the knowledge CLI. The origin/fetch/update policies, cache budgets, overlay exports and explanation preferences below are planned; unsupported settings are rejected. Auto mode reports when source fallback is needed; the adapter does not read source on the caller's behalf.

- Retrieval mode: `auto`, `index`, or `source`. Source mode bypasses graph/index queries while retaining project guidance. Index mode requires compatible knowledge for the requested scope or reports what is missing. Auto uses compatible knowledge and falls back to current source with visible coverage limits.
- Index origin: shared prebuilt artifacts, local generation, or both.
- Fetch policy: automatic, explicit-only, or offline.
- Update policy: automatic local incremental updates, explicit-only, or disabled.
- Limits: cache size, indexing time, retrieval output budget, and retention.
- Sharing: explicit committed-overlay export; dirty worktree data excluded unless deliberately selected.
- Agent preferences: explanation detail, preferred available integration, and supported workflow choices.

Index navigation does not remove the need to inspect relevant current source before edits. Read-only requests must not unexpectedly create caches or launch updates. Project requirements conflicting with personal modes must be reported clearly.

### Local Spec Kit overrides

Keep upstream.lock.json and requirements.txt consistent as the distribution's validated default. A user's override must not edit these files.

Allow the hierarchy above to select an alternative official release or commit. Resolve release names to immutable commits. Store the effective source identity, CLI version, package version, and compatibility results in a local resolved-toolchain record; support exporting it for reproduction elsewhere.

Setup and installation consume the same effective selection. Isolate tooling environments by resolved identity so one project's choice does not replace another's CLI. Before target mutation, validate CLI capabilities and preset/extension integration in disposable staging. Preserve existing target files.

Distinguish the distribution-tested default, an override passing local compatibility checks, and an unsupported combination. Do not claim an override is distribution-validated. Version changes require a reviewable upgrade preview and explicit apply; changing a preference does not silently regenerate installed project files.

## Knowledge architecture

Keep three types of knowledge distinct:

1. Reviewed baseline: purpose, goals, constraints, conventions, commands, authoritative architecture documents, and references to active Spec Kit work. Commit with the project.
2. Extracted facts: files, symbols, references, dependencies, and build targets, tied to source and build inputs.
3. Derived understanding: evidence-linked component summaries and explanations with coverage and invalidation rules. Generated interpretations do not become project policy.

Store generated artifacts outside ordinary source history. Give agents concise orientation and bounded queries, not entire graphs in context. Support definitions, references, dependencies, change impact, relevant tests/targets, and expandable evidence. Results identify revision, source locations, and coverage gaps.

Caching parsing saves computation; token savings additionally depend on retrieval quality and bounded output. Measure both separately.

## Trunk snapshots and branch overlays

Configure release, RC, main/development, and other long-lived trunks. Separate logical trunk association from immutable snapshot identity.

The checkout view combines a compatible shared snapshot, a committed branch overlay, and a worktree overlay. Deletions and replacements hide obsolete lower-layer facts and edges. Update affected dependencies: changed headers or build configuration can invalidate facts in otherwise unchanged files.

Initially choose the newest compatible published snapshot on the selected trunk's history that is also an ancestor of the checkout. Compute the complete delta from that exact snapshot to HEAD. Do not combine a newer trunk-tip graph with only fork-to-branch changes: it would retain trunk changes absent from the branch.

Retain historical snapshots. If no compatible ancestor snapshot exists, follow configured policy: local generation, source fallback, or report required knowledge unavailable. Defer non-ancestor snapshot transformations until removal and dependency semantics are proven.

Resolve trunk association through explicit override, still-valid recorded selection, configured branch rules or available PR target metadata, then ancestry inference. Explain selection evidence and ambiguity; history does not always reveal intent. Persist user resolutions and reconsider after switches, rebases, merges, or rewritten history. Handle detached HEAD, shallow history, and missing refs explicitly.

## Portability and sharing

Artifacts identify repository, source revision, exact base artifact for overlays, schema/generator versions, selection rules, relevant build inputs, checksums, provenance, and coverage. Use relative paths and repository identity independent of clone location and SSH/HTTPS remote spelling.

For C/C++, include target, compiler context, defines, and generated inputs: one commit may have multiple semantic views. Normalise machine paths without erasing meaningful differences. Record relevant submodule and external input identities.

Provide a machine-level immutable cache shared by clones, with mutable worktree state isolated per checkout. Use locking, atomic writes, and retention protecting active overlay dependencies.

Use one bundle contract for manual exchange and CI publication. Support compact overlays referencing a known base and self-contained bundles including required bases. Validate compatibility, integrity, and dependency availability before activation. Imports must not execute embedded commands; a publisher field alone does not authenticate an artifact.

Knowledge bundles do not automatically transfer code. Matching source is necessary to treat an imported overlay as current checkout knowledge; otherwise expose it as knowledge of another revision. Any patch transport must be explicit and separate from activation. Dirty worktree exports are opt-in.

CI generates configured trunk snapshots on selected events or schedules, validates them, and publishes immutable artifacts and a discoverable catalog. Publish atomically, retain useful history, and respect authentication and offline policies during fetching. Keep manual sharing independent of the hosting service.

## Delivery phases

### Phase 1 — Configuration and portable contracts

Status: Configuration foundation delivered. Pilot selection and the full artifact/overlay contract remain open.

Deliver schema/resolver, precedence, provenance inspection, personal scopes, repository identity, and artifact/overlay contracts. Plan migration without overwriting customised files. Explain incompatible settings and expose effective configuration fingerprints.

Exit: verify merge rules and two-clone personal project reuse with isolated checkout overrides. Preserve current defaults. Select a representative pilot and record languages, size, build variants, and trunk structure.

### Phase 2 — Reproducible Spec Kit overrides

Retired 2026-09-30: Spec Kit toolchain selection left the core along with Spec Kit itself.

Deliver version resolution, isolated environments, local toolchain records, staging compatibility checks, and upgrade previews while leaving the distribution pin unchanged.

Exit: exercise the default and at least one selected alternative using actual CLI installations; reject incompatibility before target mutation; preserve existing files. Report only platforms and integrations actually exercised.

### Phase 3 — Useful local indexing and retrieval

Status: Partial. Phase 1 of the indexer-agnostic design is implemented and proven on mixed C and Python: declared indexers, per-file content addressing, three layers, declared transports, and a guard refusing any layer whose commit is not checked out. Open: `query` consults only the first configured indexer (a silent wrong answer, not merely a gap), a real indexer choice, and the measured agent comparison. No token-saving claim may ship before that measurement.

Select one backend using the pilot's language/build needs. Deliver bounded fact queries, source fallback, branch/worktree updates, and evidence-linked summaries where useful.

Exit: validate results against source/build evidence, including deletions, renames, header/configuration changes, and dirty reversions. Compare identical source-only and index-assisted tasks. Measure cold generation, unchanged-session startup, incremental refresh, retrieval accuracy, and actual agent tokens. Set numerical targets from pilot evidence rather than assuming savings.

### Phase 4 — Multiple trunks and portable reuse

Status: Partial. Content addressing gives clone-independent reuse by construction — the same file content resolves to the same artifact in any clone, on any branch, under any path — and `push`/`pull` move artifacts through declared commands. Open: trunk inference, a configured shared store (Azure, deliberately left open), retention and `gc`, and two-machine validation.

Deliver trunk inference with overrides, ancestor snapshot selection, exact-base overlays, shared local cache, and bundle export/import.

Exit: demonstrate release/RC feature branches across two clones and two machines. Exercise advancing trunks, rebases, missing bases, build-context mismatches, and unavailable source. Compare composed query results against a fresh index of the same checkout and build configuration.

### Phase 5 — CI publication and team consumption

Status: Planned. Repository regression CI, release-readiness workflows and selected-trunk package version/tag automation are implemented separately; see CI.md and TODO.md. Hosted execution/enforcement still needs confirmation.

Deliver scheduled/event-driven generation, immutable publication, discovery, authenticated fetching, integrity checks, and historical retention.

Exit: run an actual remote pipeline; a second developer consumes a snapshot and computes the needed local overlay. Demonstrate offline reuse, interrupted-download recovery, invalid-artifact rejection, and retention protecting active bases.

### Phase 6 — Scale and broader coverage

Status: Planned, dependent on pilot correctness and performance evidence.

Improve incremental CI builds, cross-trunk deduplication, dependency invalidation, summary reuse, retention, additional language adapters, and optional agent hooks. Consider non-ancestor reuse only if evidence justifies its complexity.

Exit: publish repeatable large-repository results for time, storage, network transfer, tokens, and correctness. Validate live integration behaviour separately from generated instruction files.

## Decisions to settle

- Pilot repository, dominant languages, build variants, and actual trunk naming/history.
- Any future changes to the implemented settings precedence and supported preference fields.
- Backend suitability for portable queries and correct incremental updates.
- Initial artifact host, credentials, publication cadence, and retention budget.
- Which workflow settings are personal preferences versus mandatory project requirements.

Phases 1–2 establish reproducible settings/tooling. Phases 3–4 prove knowledge quality and reuse before central publication in phase 5. Update STATUS.md and VALIDATION.md as implementation and evidence arrive; this document does not change readiness claims.

## Knowledge pilot update

The CGC and Sourcegraph adapters were retired on 2026-09-30 and replaced by a wrapper model: CAS ships no indexer and
runs whichever one a repository declares. What is proven is the caching and sharing substrate, not a value claim — the
only number so far is a size ratio (skeletons are 19 % of source bytes), which is neither tokens nor task success. The
open pilot questions are which indexer to adopt first (ctags to prove the plumbing, tree-sitter as the first useful
one, scip-clang for C/C++ cross-translation-unit resolution) and then running the measurement that would justify any
of it.
