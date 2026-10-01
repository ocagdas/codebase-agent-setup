# Maintaining codebase-agent-setup safely

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
