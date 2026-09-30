# Current readiness

codebase-agent-setup is ready for a project pilot. pyproject.toml is the sole package-version source. Spec Kit provisioning, Docker setup, v6 migration and backend-specific adapters are retired. See [VALIDATION.md](VALIDATION.md) for executed checks, [TODO.md](TODO.md) for remaining actions and [ROADMAP.md](ROADMAP.md) for milestone priorities.

## Delivered capabilities

- Tool-neutral agent guide: one `AI_CONTEXT.md` with pointers for five assistants, a seeded repository-owned project guide, a handover contract with `handover.path` and a validator, and `--adopt` for existing agent files.
- Hierarchical project/user/checkout/invocation settings with a shared resolver contract.
- Repository knowledge: declared indexers, artifacts cached per file content, worktree/branch/base resolution, and sharing through declared transport commands. CAS ships no indexer.
- `capsule` (always-redacted backup, restore and clone of a setup) and `fleet status`/`fleet apply` across many repositories.
- Local Git inventories and file branch deltas, integrity-bound bootstrap requests, incremental record reuse and SHA-1/SHA-256 repository support.
- Static/editable codebase-agent-setup installations with native/venv/Conda setup paths. Zero runtime dependencies; the only extra is the maintainer toolchain.
- Conservative install/upgrade with authored-file preservation, recoverable transactions, OS-owned locks and opt-in archival of obsolete managed files.
- Community documentation and pinned CI for formatting, analysis, contract checks, unit/platform matrices, strict integration and wheel/source payload verification.
- Quality-gated package bump/tag automation, configurable release trunk, atomic publication and common version/gate interfaces. Public GitHub Release/PyPI publication remains disabled.

## Functional limits

Semantic ancestor snapshots and branch composition, authenticated knowledge publication/fetching, automatic semantic refresh, general task migration, concurrent agent orchestration and cache retention remain incomplete. No measured large-repository token-saving claim is established. Markdown instructions alone do not enforce runtime behavior.

Consumer repositories must supply actual compiler/interpreter versions, build/test commands, hardware/data targets, authoritative documents and mandatory gates. CUSTOMISE placeholders cannot count as successful checks.

## Qualification

[VALIDATION.md](VALIDATION.md) owns current executed evidence and outstanding platform
checks. [CI.md](CI.md) owns qualification commands; [VERSIONING.md](VERSIONING.md) and
[GitHub setup](docs/development/github-policy-setup.md) own release activation.
Shared repository interfaces are described in [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md).
