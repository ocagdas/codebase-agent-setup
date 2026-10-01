# Settings during repository work

Read this only when you need to inspect effective preferences or locate the handover. Repository policies and
quality gates live in `project_guide.md` and the documents it names; settings never override them.

## Inspect without changing anything

```bash
python3 ai_workflow/tools/settings.py inspect --repo .
python3 ai_workflow/tools/settings.py handover --repo .
```

Use the repository's Python 3.11+ environment (on Windows, `python` or `py -3`). The handover command reports its
resolved path and whether it exists; follow [handover.md](handover.md) when maintaining it.

Preferences may come from distribution defaults, a user file, project configuration, user per-project overrides,
ignored checkout-local `ai_workflow/settings.local.json`, and explicit invocation options, in that order.
Inspection reports the effective values and their origins. Do not modify configuration merely to bypass a failing
check, change a project's publication policy, or enable paid/external actions.

Installed guidance and local configuration are local-only by default. Never put credentials in guidance or settings.
Git ignores do not stop cloud tools from reading files. Ask before changing shared configuration or publishing data.

For installation, configuration, templates, upgrades, fleet management and backup/restore, use the
[CAS documentation](https://github.com/ocagdas/codebase-agent-setup/blob/main/docs/user/index.md) and `cbsetup --help`.
For optional code-index use during a task, see [knowledge.md](knowledge.md) only when an index is configured.
