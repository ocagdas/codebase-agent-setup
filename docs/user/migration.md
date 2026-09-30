# Migration ownership map

| Previous file or capability | Spec Kit destination | Migration rule |
| --- | --- | --- |
| AI_CONTEXT.md | AI_CONTEXT.md | Replace with Spec Kit navigation after preserving custom instructions |
| project_philosophy.md | .specify/memory/constitution.md | Merge authored principles once; remove the old duplicate |
| task YAML and task schema | Feature spec.md, plan.md and tasks.md | Preserve IDs through a documented mapping; do not maintain both ledgers |
| actions.yaml and action contracts | Official commands plus engineering extension | Use action_map.md for natural language routing |
| workflow.yaml | Official implementation and convergence workflow | Engineering lifecycle augments upstream commands |
| C and C++ rules | Domain guidance and preset | Preserve actual compiler, target and coding standard choices |
| Python and data science rules | Domain guidance and preset | Preserve environment, dataset and evaluation requirements |
| commands.yaml and quality gates | Project engineering configuration | Merge actual configured commands; never replace them with CUSTOMISE |
| bootstrap and branch deltas | Project bootstrap utility and configuration | Keep local caches separate; refresh when configuration changes |
| completion report | Derived completion.json in the feature directory | Map canonical tasks and AC numbered acceptance criteria |
| legacy provider agents and skills | Upstream generated integrations | Retire duplicate discovery paths after preserving customised procedures |

The automated migration path accepts unchanged v6 template files only. Hashes are bundled in legacy_v6_files.json. For customised repositories, install into an empty sibling directory first, compare the generated files and apply the ownership mapping manually. Keep existing specifications and real project configuration authoritative while merging. Do not overwrite an authored constitution during an upgrade.

The current package supports initial installation and recognised baseline migration. General migration of arbitrary active task formats, preset upgrades and merging an existing .specify installation need deliberate review. Keep backups until the new workflow has completed a representative task.

A preserved legacy backup is excluded from Git by the installer. It is for recovery and must not be loaded as current agent guidance.

## Renamed from repo_pilot

This distribution was previously published as `repo_pilot` / `repo-pilot`, and earlier as
`spec_kit_engineering`. GitHub redirects the old repository URL.

| Before | Now | Compatibility |
| --- | --- | --- |
| `repo-pilot` command | `codebase-agent-setup`, short alias `cbsetup` | Reinstall; the old command is removed |
| `import repo_pilot` | `import codebase_agent_setup` | None; update imports |
| `<user config>/repo-pilot/config.json` | `<user config>/codebase-agent-setup/config.json` | The old file is still read until the new one exists; move it when convenient |
| CGC state `repo-pilot.json` | `codebase-agent-setup.json` | The old marker is read; the next index rebuild replaces it |
| `.repo-pilot-toolchain.json` | `.codebase-agent-setup-toolchain.json` | Rerun setup, or pass an exported record with `--toolchain-record` |
| `REPO_PILOT_*` environment variables | `CBSETUP_*` | Timeout variables accept the old names; test and CI variables do not |
| Conda default `spec_kit_engineering` | `codebase-agent-setup` | Existing environments keep working with `--conda-name spec_kit_engineering` |

The Spec Kit extension ID `speckit.engineering` and its skills keep their names, so already-seeded projects are unaffected.
