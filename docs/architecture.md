# Architecture and ownership

codebase-agent-setup manages repository agent configuration, handovers, portable capsules and fleets. Runtime code lives in src/codebase_agent_setup/. The single cbsetup command or python -m codebase_agent_setup works in an installed environment; source runs can use PYTHONPATH=src. Spec Kit provisioning, Docker setup and root launchers are retired.

| Component | Responsibility and data ownership |
| --- | --- |
| src/codebase_agent_setup/cli.py | Installed command dispatch and static/editable resource reporting |
| project/ai_workflow/tools/settings.py | Shared configuration hierarchy, scope/origin resolution and project settings |
| pyproject.toml | Sole package-version source and development dependency pins |
| src/codebase_agent_setup/install.py, src/codebase_agent_setup/install_transaction.py | Staging, authored-file preservation, managed upgrade ledger, recoverable atomic installation |
| src/codebase_agent_setup/templates.py | Editable baseline export, supported-path/content validation and source fingerprint verification; no live-repo state export |
| src/codebase_agent_setup/ | The one command surface: template, install, capsule, fleet, handover, configure, knowledge, bootstrap |
| project/ | Consumer-installed instructions, defaults, schemas, handover and bootstrap utilities |
| project/ai_workflow/tools/knowledge.py | Runs declared indexers, caches output per file content, resolves worktree → branch → base, and pushes/pulls through declared transport commands |
| scripts/, .github/workflows/ | Distribution validation, numeric versions, atomic package tags and release artifacts |
| tests/, project/ai_workflow/tools/test_*.py | Distribution and installed-utility regression evidence |

Consumer state, index caches, credentials, local overrides and install journals are not shared release source.
Installed guidance is local-only by default: install/upgrade adds root-relative ignores alongside transactional
payload writes. `--track-guidance` skips adding those guidance rules for teams intentionally sharing reviewed
content; it leaves existing ignore rules and the Git index untouched. State/backups/local settings stay ignored.
Reusable `project/` templates remain package source. Git ignores neither erase history nor stop cloud-agent reads;
credentials must not go in guidance. Index artifacts live under the configured `knowledge.cache_root` and are shared,
if at all, through a declared transport — CAS holds no credential of its own. See the installed
[knowledge guide](../project/ai_workflow/knowledge.md).

Package build artifacts are disposable under .quality/ or an explicit output directory. Release CI owns commit/run-bound gate evidence and wheel/source validation. Package tag automation does not publish knowledge snapshots or public package releases. Proposed graph/base/overlay ownership is described in [repository knowledge](../project/ai_workflow/knowledge.md).

Runtime code and CI are self-contained in this repository. Sibling projects inform shared conventions; none is imported at runtime.

Install, template create and fleet apply write by default; --dry-run validates/plans without target writes.
Install/fleet --behaviour defaults to upgrade (update unchanged managed files, preserve edits/guide).
Preserve adds missing files only; override replaces supported CAS files including the guide with transactional
backups. Unknown files without ledger ownership are preserved by upgrade. Local settings and unrelated paths are
outside override. Unsafe paths/non-files always fail. Other command families retain their existing write controls.

## Packaging resources

Setuptools discovers the tooling package under `src/`. `src/build_support.py` copies
only declared payload patterns into the wheel; `MANIFEST.in` includes the authored
inputs for rebuilding from an sdist. Tests, local settings and bytecode are excluded
from wheel payload data. Source/editable imports extend the package search path to
its own checkout for the standalone `project` namespace. Installed wheels resolve
all code and resources internally. `codebase-agent-setup --version` reports `code_path` and
`resource_path` separately. No sibling checkout or generated source copy is required.
