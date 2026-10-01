# Open work

This is the tooling distribution's actionable backlog. Consumer feature work still uses Spec Kit's own tasks.md. Milestones and acceptance belong in [ROADMAP.md](ROADMAP.md); capabilities and evidence belong in [STATUS.md](STATUS.md) and [VALIDATION.md](VALIDATION.md).

## Priority now (P1 stabilization)

- Qualify dev/mvp_0.30 on hosted CI, including Windows and the strict packaging profile. Spec Kit provisioning and its toolchain gates are retired.

- Configure the versioning App variables/secret and narrowly scoped App bypass described in VERSIONING.md; branch/tag rules are active. Enable REPOSITORY_VERSIONING_ENABLED only after App setup.
- Run hosted CI and tag-triggered release readiness; prove the active Quality gate rule blocks failing PRs and verify commit/run evidence and App publication on the selected trunk.
- Execute the declared macOS/Windows matrix and record results. Broaden native installation, real backend and live-agent evidence only through actual runs.
- Verify the real private security-reporting feature/contact route before advertising it as enabled; maintain the existing SECURITY.md procedure without inventing contacts.

## Next (P2 pilot execution and contract hardening)

- Select a representative repository, languages, build variants, release/RC trunks and real agent clients for a repeatable pilot.
- Measure source-only versus assisted correctness, cold generation, warm startup, incremental refresh, retrieval accuracy, storage and actual agent token use; agree numerical targets from that baseline.
- Extend artifact identity with build inputs, generator compatibility, coverage, provenance, exact overlay bases and partial-extraction behavior. Specify replacement/tombstone and dependency invalidation semantics.
- Measure the delivered multi-indexer query fan-out and `--indexer` narrowing on real mixed-language tasks.
- Connect semantic refresh/query status to bootstrap through validated operations and effective source/index/auto, origin and update/fetch policies. Preserve read-only/source fallback behavior.
- Implement dirty-worktree semantic updates, rename/deletion/reversion handling and isolated concurrent worktrees. Compare results with a fresh index.

## Later (P2 portability and team distribution)

- Implement explicit logical trunk selection and branch override, with ancestry inference, ambiguity reporting and shallow/missing-ref/detached-HEAD handling.
- Select compatible ancestor snapshots independently of logical trunk association; compose overlays from the exact base to HEAD and then worktree changes. Revalidate after switches, merges, rebases and rewrites.
- Add immutable caches shared across clones with locks and retention protecting referenced bases; test separate release and RC histories without leaking absent trunk changes.
- Extend manual bundles to compact overlays and self-contained bases, build-context compatibility and explicit dirty content. Reject unsafe/corrupt archives and never execute embedded commands.
- Validate actual two-machine transfer, different clone paths, missing bases and unavailable source. Current local clone tests do not establish cross-machine behavior.
- Select a knowledge artifact host, authentication model, cadence and retention budget before implementing publication.
- Implement immutable trunk publication/catalogs, authenticated discovery/fetch, interrupted-download recovery, offline reuse and historical-base retention using the same manual bundle contract.
- Run a hosted knowledge publication/second-developer consumption pilot before marking team distribution delivered.
- Prioritize additional languages, summary reuse, cache retention, deduplication and non-ancestor reuse only from measured bottlenecks.

Public GitHub Release/PyPI publication remains disabled. Any future publication policy requires an explicit owner decision and qualification of downloaded assets; standardization does not authorize it.
