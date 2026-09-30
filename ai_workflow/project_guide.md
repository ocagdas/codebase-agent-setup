# Project guide — codebase-agent-setup

Repository-specific guidance for every coding assistant. `AI_CONTEXT.md` loads this file first. This file belongs
to the repository: codebase-agent-setup installs it once and never overwrites it. Replace each prompt below with
facts, delete sections that do not apply, and remove the `cbsetup:unfilled` marker on the first line when done.

## Purpose

CAS manages tool-neutral agent guides, handovers, settings, redacted portable capsules, fleet operations and
repository knowledge through declared indexers. CAS ships no indexer and no runtime dependencies.

## Document owners

STATUS.md owns capabilities; TODO.md owns actions; ROADMAP.md owns milestones; VALIDATION.md owns evidence;
CI.md owns checks; VERSIONING.md and BRANCHING.md own release/Git policy. Read README.md, CONTRIBUTING.md
and HANDOFF.md before changes. REPOSITORY_STRUCTURE.md owns shared interfaces; docs/architecture.md owns layout.

## Commands

Use Python 3.11+ (development on 3.12): `python -m pip install -e '.[dev]'`, then `python scripts/check.py`.
Full profile: `CBSETUP_PACKAGE_TESTS=1 python scripts/check.py --full`; it builds/installs packages and rejects skips.
Format with `python -m ruff format .`; build with `python scripts/build_release.py --candidate`.
Use the environment's Python on every platform. No Spec Kit binary or optional backend dependency is needed.

## Policies

Trunk is main. Work on dev/<topic> and merge reviewed squash PRs after Quality gate passes.
Ordinary PRs preserve the package version; qualifying trunk CI bumps/tags atomically. Do not tag incidental work.
Preserve authored target files, test install/upgrade/recovery, use UTF-8 and record only executed evidence.
Payload tools must use the standard library. No sibling runtime imports or private content in this public MIT repo.
aiplane owns MCP server definitions; CAS consumes its JSON export for client configuration. This remains planned.
Publication and hosted rule changes require task authorization.

## Hazards

project/ is the payload source. Root ai_workflow/ and tool pointers are CAS's installed copy: refresh through
`cbsetup install . --upgrade --apply` after payload changes. The filled project guide belongs to the repository.
The ledger is .cbsetup/install.json. Preserve dirty worktrees before branch cleanup.

## Imported from AGENTS.md (review)

# Working on this tooling distribution

Read README.md, STATUS.md, CONTRIBUTING.md and HANDOFF.md. TODO.md owns open actions; REPOSITORY_STRUCTURE.md owns shared automation interfaces. `project/` is the payload installed into consumer repositories; do not interpret `project/AI_CONTEXT.md` as the workflow for editing this tooling repository.

The core has no runtime dependencies and invokes no external CLI. Spec Kit is no longer installed or managed here (removed 2026-09-30); the payload only points at it when a consumer repository already has it. Payload tools under `project/ai_workflow/tools/` use the standard library only, and a test enforces it.

Preserve existing target files during installation. Use the current Python interpreter in tests and UTF-8 for text I/O. Do not claim a platform or live agent was tested unless it actually ran. Consult VALIDATION.md for current evidence.
