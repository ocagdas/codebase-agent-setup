# Maintaining codebase-agent-setup safely

## Parked external-map work (2026-10-02)

Current local branch dev/aider-repo-maps is based on main 1cf8650/v1.1.1. The optional
Aider adapter and tests remain uncommitted, with new files intent-to-add rather than
staged contents. Preserve existing owner edits; a main clone or staged-only patch does
not carry the implementation. [STATUS.md](STATUS.md), [VALIDATION.md](VALIDATION.md),
[TODO.md](TODO.md) and [map usage](docs/user/repo-map.md) own public capability/evidence.
Private session continuity and consumer findings are held separately in the owner's
workspace handover; do not put private paths, source excerpts or maps in this repository.
Recreate CAS and external Aider environments on another machine. No new publication or
version bump is authorized by this handoff; fresh hosted/client qualification is pending.

Read [README.md](README.md), [STATUS.md](STATUS.md), [CONTRIBUTING.md](CONTRIBUTING.md),
[TODO.md](TODO.md) and [VALIDATION.md](VALIDATION.md). Inspect Git status and preserve
unrelated changes before editing. [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md)
identifies policy owners; update them rather than copying policy into this handoff.

`project/` is the installed consumer payload. Its AI_CONTEXT.md and AGENTS.md do not
instruct work on this tooling distribution. Runtime code lives in `src/codebase_agent_setup/`;
[architecture](docs/architecture.md) explains source, editable and wheel resources.
Preserve consumer-authored files and test installation/upgrade recovery when changing
those paths. Root AI_CONTEXT.md and ai_workflow/project_guide.md govern this checkout.
pyproject.toml is the sole package-version source; Spec Kit and its pin files are retired.

Use the current Python interpreter and UTF-8 I/O. Follow [CI.md](CI.md) for required
checks and record actual scope in VALIDATION.md; do not infer unexecuted platform or
live-agent results. [VERSIONING.md](VERSIONING.md) owns version/pin maintenance and
release operations. Local maintenance does not authorize publishing or hosted rule changes.

Keep TODO as the open-task ledger and ROADMAP at milestone level. Preserve approved
legal notices and reporting procedures. Do not import sibling repositories at runtime.
