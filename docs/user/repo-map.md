# Optional repository maps

Map generation, storage, freshness and transfer now belong to the separately installed
Codebase Index Kit project. CAS retains `cbsetup repo-map` as an optional compatibility bridge.
It checks CLI contract 1, forwards literal arguments, and returns the tool's exit code.
Neither installation downloads the companion or Aider automatically.

Install Codebase Index Kit from its reviewed checkout into an isolated environment and expose
`cbkit` on PATH. Provision Aider using that project's map guide. Then:

```bash
cbsetup repo-map build --repo /path/to/repo --python /path/to/aider/bin/python --path src --dry-run
cbsetup repo-map status --repo /path/to/repo
cbkit repo-map --help
```

Direct `cbkit repo-map` works without CAS. Existing `.ai_cache/repo-map` snapshots
remain compatible; extraction does not migrate/delete caches. Follow project permission
and privacy rules before generation, transfer or cloud-agent reads. Maps are hints, not
semantic proof. Existing installed CAS copies are unchanged until explicitly upgraded.
