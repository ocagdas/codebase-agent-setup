# Current readiness

codebase-agent-setup is ready for a project pilot. pyproject.toml is the sole package-version source. Spec Kit provisioning, Docker setup, v6 migration and backend-specific adapters are retired. See [VALIDATION.md](VALIDATION.md) for executed checks, [TODO.md](TODO.md) for remaining actions and [ROADMAP.md](ROADMAP.md) for milestone priorities.

## Delivered capabilities

- Optional external Aider scope maps through the Codebase Index Kit `repo-map` bridge: the companion provides
  scoped generation, ignored snapshot storage, freshness, reuse and explicit transfer across matching clones.
  See [usage and limits](docs/user/repo-map.md). This is not yet per-file delta composition or compiler semantics.

- Tool-neutral agent guide: one `AI_CONTEXT.md` with pointers for five assistants, a seeded repository-owned project guide, a handover contract with `handover.path` and a validator, and `--adopt` for existing agent files.
- Hierarchical project/user/checkout/invocation settings with a shared resolver contract.
- Optional Codebase Index Kit bridges for maps and knowledge. Indexing implementation/tests now
  live in the separate project; CAS resolves legacy settings and checks CLI contract 1.
- `tools list|show` catalogs exact entry/manual paths. Five user-maintained manuals are
  seeded once, preserved even during override, ignored by default and captured in setup capsules.
- `capsule` captures/applies selected settings, the authored project guide, manuals and ledger with the sanitizer
  always applied. It refuses conflicting guides, unsafe destination parents and ambiguous repository layers;
  it is not a full environment or checkpoint backup. `fleet status`/`fleet apply` operate across declared repos.
- Local Git inventories and file branch deltas, integrity-bound bootstrap requests, incremental record reuse and SHA-1/SHA-256 repository support.
- Static/editable codebase-agent-setup installations with native/venv/Conda setup paths. Zero runtime dependencies; the only extra is the maintainer toolchain.
- Conservative install/upgrade with authored-file preservation, recoverable transactions, OS-owned locks and opt-in archival of obsolete managed files.
- Local-only guidance by default: missing root-relative Git ignores are previewed and installed transactionally;
  `--track-guidance` opts out for intentional sharing without changing existing ignores or the Git index.
  `--no-gitignore` leaves the ignore file entirely untouched for a single or fleet install.
- Editable built-in templates: `template create`, single/fleet `--template` installation, validated source paths
  and content, source-change checks, and backed-up `--behaviour override`. Install/template/fleet write by default
  with `--dry-run` previews; `--behaviour preserve|upgrade|override` defaults to upgrade. Installed settings docs are slim;
  administration belongs in CAS user docs. Live-repo export and full-guidance capsule recovery remain future work.
- Community documentation and pinned CI for formatting, analysis, contract checks, unit/platform matrices, strict integration and wheel/source payload verification.
- Quality-gated package bump/tag automation, configurable release trunk, atomic publication and common version/gate interfaces. Public GitHub Release/PyPI publication remains disabled.

## Functional limits

A map-first/source-check pilot across eight investigation areas located useful candidates
but exposed clipped signatures/bodies, missing behavioral details and filename-only build
metadata. Structural path coverage is not semantic coverage. Compiler-backed source
navigation is the next proposed layer; binary/debug analysis is complementary for actual
built artifacts, not a replacement for current source. Neither layer is implemented by
the Aider adapter. Full-map injection is not recommended; bounded retrieval is still pending.

Semantic ancestor snapshots and branch composition, authenticated knowledge publication/fetching, automatic semantic refresh, general task migration, concurrent agent orchestration and cache retention remain incomplete. No measured large-repository token-saving claim is established. Markdown instructions alone do not enforce runtime behavior.

Consumer repositories must supply actual compiler/interpreter versions, build/test commands, hardware/data targets, authoritative documents and mandatory gates. CUSTOMISE placeholders cannot count as successful checks.

## Qualification

[VALIDATION.md](VALIDATION.md) owns current executed evidence and outstanding platform
checks. [CI.md](CI.md) owns qualification commands; [VERSIONING.md](VERSIONING.md) and
[GitHub setup](docs/development/github-policy-setup.md) own release activation.
Shared repository interfaces are described in [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md).
