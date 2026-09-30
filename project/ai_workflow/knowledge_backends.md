# Optional code knowledge backends

CodeGraphContext (CGC) and Sourcegraph (SG) are selectable retrieval adapters. The default is `knowledge.backend: "off"`: no optional package import, backend process, indexing or network request occurs. File inventories from repo_bootstrap.py remain available independently.

## Configure and query

Add to the existing `settings` object in tracked `ai_workflow/settings.json`, or ignored `ai_workflow/settings.local.json` for this checkout:

```json
{
  "schema_version": "1.0",
  "settings": {
    "knowledge": {"backend": "cgc", "mode": "auto"}
  }
}
```

The normal precedence applies: distribution, user defaults, shared project, user's project-specific settings, checkout-local settings, invocation. `backend` accepts `off`, `cgc`, `sourcegraph`; the CLI also accepts `sg`. `knowledge.mode: "source"` disables retrieval regardless of the selected backend. An invocation override changes only that command, not files or subsequent commands.

From an installed consumer repository:

```bash
python ai_workflow/tools/knowledge_backend.py status
python ai_workflow/tools/knowledge_backend.py query --backend cgc --query greet --limit 10
python ai_workflow/tools/knowledge_backend.py query --backend sg --query greeting
python ai_workflow/tools/knowledge_backend.py query --backend off --query greeting
```

From the tooling distribution, use `python knowledge.py` with the same arguments plus `--repo /path/to/consumer`. `--set section.key=JSON_VALUE` and `--user-config` work on this entry point too. For example, `--set 'cgc.executable="/path/to/env/bin/cgc"'` selects an isolated CGC installation. Sourcegraph uses the Python interpreter running the adapter and does not need CGC.

`status` is local and does not probe a remote service. Queries emit JSON with revision, fallback and truncation information. Defaults are 20 matches and 12,000 output characters; `--limit` and `--max-chars` change those budgets. CGC results are flattened to avoid returning its duplicate result categories. The character budget bounds returned context, not backend memory use or a model-specific token count. Always check current source before editing or treating graph edges as authoritative.

## CGC installation and storage

In a dedicated environment, install the tested pilot versions:

```bash
python -m pip install codegraphcontext==0.6.13 kuzu==0.11.3 mcp==1.30.0
```

From the distribution, `python -m pip install -r requirements-knowledge.txt` is equivalent. Use an activated venv or Conda environment normally; no `conda run` is needed. These are optional dependencies and do not change Spec Kit's pinned requirements. A container can install the same optional requirements and mount the checkout; it must retain or export the cache to reuse it.

This adapter deliberately selects embedded Kuzu, passing both CGC's explicit database path and runtime overrides. Parsed data lives at `<repo>/.ai_cache/code_knowledge/cgc/kuzudb`, with a codebase-agent-setup revision record alongside it. `cgc.data_dir` overrides the containing directory; relative paths resolve against the declaring settings file. Use a private directory per checkout/snapshot. Do not point two different clones at the same mutable database. A lock prevents concurrent access through this wrapper; stop direct upstream CGC processes before operating on it.

CGC used directly has its own global/local/named context selection, including data under `~/.codegraphcontext`. It may also write configuration and logs there even when the graph database is redirected. Running bare `cgc` is therefore not equivalent to using this wrapper.

Create/rebuild a snapshot explicitly:

```bash
python ai_workflow/tools/knowledge_backend.py index --backend cgc
```

Use a clean Git checkout. CGC can generate `.cgcignore` on first indexing; review and commit that exclusion policy, then retry if the adapter reports a changed checkout. Ensure `.ai_cache/` is ignored (the installer does this). Exclude generated code, dependencies and unwanted files in the parsing policy. Do not commit database files.

The snapshot is tied to the local path and HEAD. Rebuilding invalidates its old record first; an interrupted rebuild cannot retain a current record. Checkout changes and dirty worktrees make it unavailable. This initial adapter performs a full explicit rebuild, not a branch graph delta. It does not certify C/C++ compiler configurations or precise SCIP coverage.

## Sharing CGC snapshots between clones and people

Track project guidance, shared settings, repository identity and `.cgcignore`. Share graphs separately as `.cgc` artifacts plus the generated `.cgc.json` sidecar:

```bash
# Producer: clean checkout, already indexed; write outside the checkout.
python ai_workflow/tools/knowledge_backend.py export --backend cgc --bundle /tmp/project-release.cgc

# Transfer BOTH files to the consumer through your chosen artifact store or manually.
# Consumer: same project and commit, different clone path, no existing CGC data_dir.
python ai_workflow/tools/knowledge_backend.py import --backend cgc --bundle /tmp/project-release.cgc
python ai_workflow/tools/knowledge_backend.py query --backend cgc --query greet
```

Both operations require the pinned CGC package in the Python environment running the wrapper. Export refuses to overwrite an artifact. Import checks the format, backend version, repository identity, exact commit and SHA-256 checksum before loading. It stages a fresh database using CGC's bundle API, records the imported graph root (which includes CGC's bundle-name suffix), and maps query paths to actual files in the destination clone. This adapter accounts for that behavior in pinned CGC 0.6.13; the logical imported source root under data_dir is not a source checkout. Existing databases are preserved; use a fresh `cgc.data_dir` to import another snapshot. The same canonical origin or a committed `repository_id` identifies clones; local filesystem remotes alone cannot establish that identity.

Only import artifacts from trusted project/team sources. The sidecar checksum detects corruption; it does not authenticate a publisher or prove semantic correctness. Bundles contain code information and should have the same access controls as the repository. Do not copy a live embedded database between machines or treat an import from a different commit as current.

## Sourcegraph installation and storage

Install `mcp==1.30.0` into the Python environment running this adapter. Configure:

```json
{
  "schema_version": "1.0",
  "settings": {
    "knowledge": {"backend": "sourcegraph", "mode": "auto"},
    "sourcegraph": {
      "url": "https://sourcegraph.example.com",
      "repository": "github.com/your-team/your-repo",
      "token_env": "SOURCEGRAPH_TOKEN"
    }
  }
}
```

Set `SOURCEGRAPH_TOKEN` in your shell or secret manager. The configuration stores the environment variable's name, never the token. The URL is the deployment base URL, not its MCP endpoint; the adapter appends `/.api/mcp`. HTTPS is required and redirects are disabled. The deployment must support and enable MCP, and the user must have access to the repository. Sourcegraph documents MCP as an Enterprise feature; confirm availability for your deployment.

Parsed/indexed data stays on the Sourcegraph deployment, managed by its administrators. All clones and authorized team members reuse that service: share its URL and repository name, and use separate user credentials. The adapter issues literal keyword searches scoped to the configured repository and local HEAD commit. The server must have that commit; unpublished branches and dirty local edits are unavailable through this adapter. Errors request source fallback rather than silently querying the default branch.

codebase-agent-setup does not download or export Sourcegraph's internal graph as a CGC bundle. Sourcegraph provisioning, repository synchronization and precise code-intelligence uploads remain server/CI responsibilities. This adapter currently exposes keyword retrieval over MCP; it does not expose all Sourcegraph navigation tools.

## Trunks, CI and local deltas

For release, RC and development trunks, CI can run CGC indexing/export at each exact commit and publish the bundle plus sidecar under `<repository-id>/<trunk>/<commit>/cgc-0.6.13/`. Use immutable commit artifacts and an optional latest pointer. A teammate imports a matching snapshot instead of reparsing. For Sourcegraph, synchronize those refs into the shared server and query the requested revision.

A feature branch at a different commit cannot yet compose a trunk CGC snapshot with local semantic deltas. It needs its own full snapshot or source inspection. Existing bootstrap file inventories/deltas are useful inputs for future composition, but are not semantic graph overlays. Automated parent-trunk detection, dependency invalidation, authenticated fetch/publish, signed manifests and token/accuracy benchmarks remain roadmap work.

Bootstrap reports `semantic_index.optional_backend` and includes backend settings in its freshness fingerprint. `--knowledge-backend` overrides that bootstrap invocation. Run this adapter's `status` and bounded `query` explicitly with the same override; bootstrap does not launch a service. Its legacy `semantic_index` manifests/commands remain a separate advanced integration. Legacy `knowledge.mode: "index"` still requires complete semantic layers during bootstrap; use `auto` for this retrieval pilot.

Sources: [CGC CLI reference](https://github.com/CodeGraphContext/CodeGraphContext/blob/main/docs/CLI_COMPLETE_REFERENCE.md), [CGC bundles](https://github.com/CodeGraphContext/CodeGraphContext/blob/main/docs/BUNDLES.md), [Sourcegraph MCP](https://sourcegraph.com/docs/api/mcp), [Sourcegraph token authentication](https://sourcegraph.com/docs/api/mcp/authentication). The executable pilot pins PyPI CGC 0.6.13; upstream main documentation can describe a different revision.
