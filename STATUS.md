# Current readiness

codebase-agent-setup is ready for a project pilot. Package metadata remains the source of the current package version; official Spec Kit is pinned to v1.0.4. See [VALIDATION.md](VALIDATION.md) for executed checks and their revision, [TODO.md](TODO.md) for remaining actions and [ROADMAP.md](ROADMAP.md) for milestone priorities.

## Delivered capabilities

- Composable Spec Kit preset/extension with Codex, Cursor and Copilot integration, project instructions, domain guidance and completion validation.
- Hierarchical project/user/checkout/invocation settings, default-off CGC and Sourcegraph adapters, bounded retrieval and source-fallback reporting.
- Local Git inventories and file branch deltas, integrity-bound bootstrap requests, incremental record reuse and SHA-1/SHA-256 repository support.
- Checked full CGC snapshots and bundle transfer between matching clean revisions with clone-path rebasing. These are not semantic trunk-plus-branch overlays.
- Static/editable codebase-agent-setup installations, optional dependency profiles, native/venv/Conda/Docker setup paths and isolated official release/commit overrides.
- Conservative install/upgrade and unchanged v6 migration with authored-file preservation, recoverable transactions, OS-owned locks, deferred cleanup and bounded/cancellable tooling commands.
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
