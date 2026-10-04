# Open work

This is the tooling distribution's actionable backlog. Consumer feature work still uses Spec Kit's own tasks.md. Milestones and acceptance belong in [ROADMAP.md](ROADMAP.md); capabilities and evidence belong in [STATUS.md](STATUS.md) and [VALIDATION.md](VALIDATION.md).

## Priority now (P1 stabilization)

- PR #13 is merged and its Linux/macOS/Windows matrix, strict integration and Quality gate passed.
  App configuration is active: the successful rerun published version 1.1.1 and tag v1.1.1 atomically.
  Tag-triggered Release readiness and version-commit CI passed. Prove protection enforcement
  separately: a green workflow alone does not prove failing PRs are blocked.
- Run the local-only private C++ repository pilot: installation/privacy/idempotence, authored-guide preservation,
  declared-indexer generation, local transport/reuse and incremental regeneration in disposable fixtures.
  Select a real C++ indexer and validate its compiler/build context before claiming semantic correctness.
- Qualify guidance discovery and instruction following in fresh Codex, Claude, Copilot and Cursor sessions.
  CLI availability and pointer-file tests are not live-client evidence. Obtain explicit approval before sending
  private source or guidance to cloud services.
- Broaden native installation, real backend and live-agent evidence only through actual runs.
- Verify the real private security-reporting feature/contact route before advertising it as enabled; maintain the existing SECURITY.md procedure without inventing contacts.

## Next (P2 pilot execution and contract hardening)

- Work parked on local dev/aider-repo-maps at main 1cf8650/v1.1.1: preserve uncommitted
  code/tests/docs and intent-to-add files when transferring machines; recreate environments.
- Validate compilation-database source paths AND compiler/SDK/sysroot/macros/generated
  headers on representative translation units. Qualify clangd/LSP or portable scip-clang
  artifacts before claiming semantic precision. Cache identity must include build context
  and dependency invalidation, not just source hashes. Binary/debug indexing is optional
  artifact-specific evidence; no binary execution is implied.
- Add bounded path/symbol-ranked retrieval and source coordinates; repeat eight map/source
  investigations against a source-only baseline with correctness, latency and actual tokens.

- Extend the initial external Aider scope-map adapter to safe per-file artifact reuse/base-delta composition only
  after knowledge freshness/tombstone contracts are hardened. Qualify real private-repository coverage and all
  four agent clients; synthetic map output is not live-agent or token-saving evidence.

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
