# Three-repository documentation and GitHub audit

Comparison date: 10 September 2026. Scope: maintained root documentation, docs/ trees
and .github/ in codebase-agent-setup, aiplane and AI_Content_Factory. Generated directories,
private strategy notes, production media and installed consumer payloads are excluded.

| Area | Result | Intentional differences |
| --- | --- | --- |
| Root community documents | Same names: LICENSE, NOTICE.md, CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md, SUPPORT.md | codebase-agent-setup/aiplane MIT; ACF proprietary. Notices, support windows and reporting routes retain actual project policies. |
| Root maintenance documents | README.md, PURPOSE.md, STATUS.md, VALIDATION.md, ROADMAP.md, TODO.md, HANDOFF.md, AGENTS.md, CI.md, VERSIONING.md, REPOSITORY_STRUCTURE.md present in all three | Product commands, evidence, architecture, backlog and agent restrictions are project-owned. |
| Navigation | docs/index.md, docs/user/index.md, docs/development/index.md and docs/architecture.md present in all three | Topic guides reflect product functionality. aiplane additionally needs docs/project/index.md. |
| Common GitHub files | CODEOWNERS, dependabot.yml, PULL_REQUEST_TEMPLATE.md and ISSUE_TEMPLATE/{bug_report.yml,feature_request.yml,config.yml} byte-identical | Ownership and Python ecosystem match these three repositories; new adopters must review those assumptions. |
| Conduct and support | CODE_OF_CONDUCT.md byte-identical; SUPPORT.md same structure and common reporting text | Getting-started links differ; ACF explicitly limits support to authorized collaborators. |
| Workflows | workflows/{ci.yml,version.yml,release.yml,verify-release.yml} in all three | Job implementations, App settings and release policy remain adapters. All have published artifact qualification; platforms and publication policy differ. |
| Agent integration | Preserved | aiplane .github/copilot-instructions.md serves its agent integration. codebase-agent-setup's consumer integration files belong in project/, not the tooling root. |
| Release notes and installation guides | Preserved where consumed | aiplane CHANGELOG.md is release-note input; its user/README.md has product contract coverage. codebase-agent-setup folded QUICKSTART.md and INSTALLATION.md into README.md (2026-09-30). |

The former aiplane Markdown issue templates were removed after replacing them with
shared YAML forms. Its contributor guide moved from docs/development/README.md to
setup.md, and project navigation from README.md to index.md; affected links and
contract tests were updated. Added its missing HANDOFF.md, NOTICE.md and SUPPORT.md.
ACF gained development navigation and community files without changing media workflows.

The source bundle tracks common GitHub files and conduct text with SHA-256 digests.
The portable conformance runner compares managed GitHub content and rejects the old
duplicate Markdown issue forms. Workflow filenames are checked, while product gates
retain their actual tests; making whole workflows identical would discard requirements.

Completed shared implementation and remaining hosted qualification are specified in the replaced parent
REPOSITORY_STANDARDIZATION_HANDOFF.md. Local parity does not certify
hosted branch protection, App publication or a public community launch.
