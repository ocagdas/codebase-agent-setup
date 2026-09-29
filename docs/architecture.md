# Architecture and ownership

codebase-agent-setup is a tooling distribution around official Spec Kit. Runtime code lives in `src/codebase_agent_setup/`. Root launchers keep source-checkout commands usable before installation; machine and Docker setup remain separate entry points.

| Component | Responsibility and data ownership |
| --- | --- |
| src/codebase_agent_setup/cli.py, setup_tooling.py | Installed entry point and static/editable dependency-profile setup |
| configure.py, project/ai_workflow/tools/settings.py | Shared configuration hierarchy, scope/origin resolution and project settings |
| src/codebase_agent_setup/toolchains.py, upstream.lock.json, requirements.txt | Immutable official-tool selection and compatibility; package_version is a separate mirror |
| src/codebase_agent_setup/install.py, src/codebase_agent_setup/install_transaction.py | Staging, authored-file preservation, managed upgrade ledger, recoverable atomic installation |
| preset/, extension/ | Composable upstream additions and engineering commands |
| project/ | Consumer-installed instructions, defaults, schemas and bootstrap/completion utilities |
| knowledge.py | Optional CGC/Sourcegraph adapter commands, bounded retrieval and checked full-snapshot transfer |
| scripts/, .github/workflows/ | Distribution validation, numeric versions, atomic package tags and release artifacts |
| tests/, project/ai_workflow/tools/test_*.py | Distribution and installed-utility regression evidence |

Consumer state, graph caches, credentials, local overrides and install journals are not shared release source. Authored project guidance can be committed in the consumer repository; generated machine/checkout data uses documented ignored locations. Sourcegraph state is service-owned; CGC indexing/bundles use configured local storage. See the installed [backend guide](../project/ai_workflow/knowledge_backends.md).

Package build artifacts are disposable under .quality/ or an explicit output directory. Release CI owns commit/run-bound gate evidence and wheel/source validation. Package tag automation does not publish knowledge snapshots or public package releases. Proposed graph/base/overlay ownership is described in [knowledge design](development/knowledge-design.md).

Runtime code and CI are self-contained in this repository. Sibling projects inform shared conventions; none is imported at runtime.

## Packaging resources

Setuptools discovers the tooling package under `src/`. `src/build_support.py` copies
only declared payload patterns into the wheel; `MANIFEST.in` includes the authored
inputs for rebuilding from an sdist. Tests, local settings and bytecode are excluded
from wheel payload data. Source/editable imports extend the package search path to
its own checkout for the standalone `project` namespace. Installed wheels resolve
all code and resources internally. `codebase-agent-setup --version` reports `code_path` and
`resource_path` separately. No sibling checkout or generated source copy is required.
