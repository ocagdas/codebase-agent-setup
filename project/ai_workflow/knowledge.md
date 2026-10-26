# Optional repository knowledge

Indexing belongs to the separately installed Codebase Index Kit tool. Follow the project
guide's configuration and permission rules; installing CAS alone does not install an
indexer or mean an index exists. CAS keeps optional bridges and legacy settings handoff.
Check freshness, query relevant information, and verify against current source before
editing. Missing tools mean source fallback, not permission to install automatically.
Never publish/push an index unless asked. Git ignores do not stop cloud-agent reads.
Administration belongs in Codebase Index Kit documentation and its command help.

When configured, check `cbsetup knowledge --repo . status`; for structural maps use
`cbsetup repo-map status --repo .` and show only current maps. Direct Codebase Index Kit
commands are also available: use the configuration documented by the project guide.

Generation and pull may write/read sensitive data or contact external systems.
Follow project authorization before running them; a missing index does not authorize
network access or a rebuild. Report stale/missing coverage and read source as needed.
Do not inject a whole-repository map into every prompt or treat structural coverage
as compiler correctness. See `cbkit <command> --help` for administration.
