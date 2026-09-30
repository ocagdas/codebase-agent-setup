# Security policy

codebase-agent-setup is currently maintained as a project pilot. Security fixes target the default branch and the current package version recorded in `upstream.lock.json`; older versions receive fixes only when a maintainer explicitly backports them. No response-time guarantee is offered.

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/ocagdas/codebase-agent-setup/security/advisories/new). Repository administrators must enable that feature. If it is unavailable, ask the maintainer through their publicly listed contact channel for a private reporting route; do not disclose exploit details in a public issue.

Include the affected version or commit, operating system, Python version, reproducer, impact and redacted logs. Use dummy credentials and disposable repositories. Never send real tokens, proprietary source, customer data or private graph bundles. Maintainers will assess reports, coordinate a fix and disclosure, and offer credit with the reporter's agreement.

Security-sensitive areas include installation and recovery writes, toolchain provenance, configuration paths, backend credentials, bundle import/export, and CI artifact publication. Local graph data can contain source code and absolute paths. Checksums detect changed bytes; they do not authenticate an untrusted publisher. Markdown workflow instructions are not a sandbox. See [VALIDATION.md](VALIDATION.md) for actual execution evidence and limits.
