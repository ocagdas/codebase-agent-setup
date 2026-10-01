# Configuring CAS preferences

Use cbsetup configure --help for current options. The installed ai_workflow/settings.md is a small agent-facing
inspection reference; CAS administration belongs here rather than in every target's context.

```bash
cbsetup configure inspect --repo /path/to/repo
cbsetup configure configure --repo /path/to/repo          # preview
cbsetup configure configure --repo /path/to/repo --apply
cbsetup configure handover --repo /path/to/repo
```

Configuration creates a shared settings.json and canonical repository identity, without overwriting an existing
settings.json. In a default local-only installation these files stay ignored; explicitly review any intentional
sharing. Configuration does not upgrade installed scripts, waive project checks or execute indexers.

## Precedence

From lowest to highest: distribution defaults; user settings; bootstrap.json and project settings.json; user
projects[repository_id]; checkout-local settings.local.json; explicit invocation options. Mappings merge, lists
replace, null resets to defaults. Unknown keys are rejected. Inspect reports effective values and origins.

The user file is $XDG_CONFIG_HOME/codebase-agent-setup/config.json (or ~/.config/codebase-agent-setup/config.json)
on Linux, ~/Library/Application Support/codebase-agent-setup/config.json on macOS, and
%APPDATA%/codebase-agent-setup/config.json on Windows. --user-config PATH selects a different file.

Current setting families: tooling (mode, env_dir, conda_name), agent (integrations), handover (path), and knowledge
(mode, base_refs, cache_root, indexers, store, repository_id). Consult the installed settings.schema.json for the
exact contract. Spec Kit and bundled CGC/Sourcegraph settings are retired and rejected.

Keep machine-specific handover paths in user per-project settings or ignored settings.local.json. Repository
identity defaults to a normalized origin hash; without origin set an explicit knowledge.repository_id. Do not
assign the same identity to unrelated projects. No credential fields are supported; never embed secrets in names,
paths, command arguments, settings or guidance. Use external credential mechanisms and environment references.

See [templates](templates.md) for custom source installation and README for installation, fleet and capsule
operations. Use each command's --help; removed root launcher scripts are not supported interfaces.
