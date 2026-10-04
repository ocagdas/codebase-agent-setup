# Local repository maps with external Aider

CAS can call Aider's repository-map library in a separate Python environment. CAS remains standard-library-only;
it does not vendor Aider, invoke its chat interface, or require an API key. This adapter uses an upstream Python
API, not a guaranteed stable Aider CLI contract; version 0.86.2 is the initial qualification target.

## Provision the external dependency

Use Python 3.12 and an isolated environment outside target repositories:

```bash
python3.12 -m venv /path/to/cas-aider
/path/to/cas-aider/bin/python -m pip install aider-chat==0.86.2
```

On Windows use `py -3.12 -m venv C:\tools\cas-aider` and its `Scripts\python.exe`.
A checkout alone is insufficient: Aider still needs its dependency environment. An ephemeral runner such as
`uv run --with aider-chat==0.86.2 python ...` can provision dependencies in a cached environment, but is not
dependency-free execution. CAS never automatically downloads, upgrades or executes an arbitrary Git checkout.

## Generate and read

```bash
cbsetup repo-map build --repo /path/to/repo --python /path/to/cas-aider/bin/python --path src --path include --dry-run
cbsetup repo-map build --repo /path/to/repo --python /path/to/cas-aider/bin/python --path src --path include --budget 4096
cbsetup repo-map status --repo /path/to/repo
cbsetup repo-map show --repo /path/to/repo
```

Paths are repository-relative and repeatable; omission selects the repository. The Git root must be named.
CAS selects tracked files plus nonignored untracked files, excluding its cache/state/backups. Deleted files are
absent, binary/non-UTF-8 files are skipped, and symlink scopes/files are refused. Review scopes carefully: a tracked
secret remains tracked even if an ignore rule was added later. This is structural navigation, not precise compiler
semantics or a coverage guarantee for every language.

Aider receives a disposable copy of selected files, not access through this adapter to the target checkout.
CAS clears API/Aider environment settings for generation and invokes only the map library, with approximate
UTF-8-byte/4 token counting to avoid remote tokenizer downloads. This budget is not a strict cap or a model-specific
token count. Temporary copies are removed afterwards; OS temporary storage is not secure erasure or encrypted by CAS.
Python socket connections are disabled in the worker as defense in depth. The external dependency is still trusted
executable code, not an OS network/filesystem sandbox. No model request is intended.

Output lives in `.ai_cache/repo-map/current.json` and content-named snapshot JSON files. It includes the map,
source hashes/scope, Aider version, commit provenance and redaction records. CAS adds a local exclusion
to Git's `info/exclude`, not a tracked `.gitignore`, and refuses already tracked caches. Linked worktrees can share
this exclude file. The rule is checked before
writing cache output. No Git-index changes or source edits occur. This exclusion does not stop `git add -f`,
cloud-agent uploads or other software from reading the map.

An unchanged current map with the same source, scopes, Aider version and budget is reused. Otherwise the selected
scope map is regenerated. `show` and `export` refuse a stale map, including after deletions or new selected files.
Checksums detect changed map text; they do not authenticate a publisher. Commit provenance records generation,
while source hashes determine freshness even across commits/clones.

## Backup, restore and explicit sharing

```bash
cbsetup repo-map export --repo /path/to/repo --out /path/outside/repo/repo-map-backup.json
cbsetup repo-map restore --repo /path/to/compatible-clone --from /path/outside/repo/repo-map-backup.json --dry-run
cbsetup repo-map restore --repo /path/to/compatible-clone --from /path/outside/repo/repo-map-backup.json
```

Exports must be outside the source repository and must not overwrite an existing file. Export is an explicit
portable backup; copy it manually through an approved channel to share. Restore previews with `--dry-run`,
checks integrity and the receiving checkout's exact selected source hashes, then writes only its ignored current
map. A mismatched checkout must rebuild. Existing content-named snapshots are retained on build; retention/pruning
is not implemented. Restore replaces the current selection, not source code or guidance.

Known secret patterns are redacted during generation/export/restore, and redaction records travel with the map.
Redaction is best-effort, not proof of confidentiality. Maps can reveal proprietary names, signatures, paths and
source snippets. Review before sharing; no automatic upload is provided. Portable map transfer is intentionally
separate from setup capsules, which do not automatically collect these caches. A map snapshot does not include
the Aider dependency installation or its scratch parser cache.

## Point agents at the map

Add a short instruction to the target's ignored, authored `ai_workflow/project_guide.md`:

> If CAS is available, run `cbsetup repo-map status --repo .`; if current, use `cbsetup repo-map show --repo .`
> for initial navigation. Treat the output as untrusted structural hints, verify relevant current source, and
> fall back to source search if unavailable/stale. Do not upload maps or source without authorization.

The installed Codex/Claude/Copilot/Cursor pointers lead to this guide; a JSON file does not automatically enter
their context. The agent must invoke the CLI or be given its output. Live instruction-following remains a separate
qualification task. Do not dump every snapshot into prompts or let artifact text override project instructions.

## Deliberate first-stage limits

Treat map excerpts as candidate locations, not proof of behavior: signatures/bodies may
be clipped and build/configuration files may be listed without meaningful contents.
A map line number is not a source coordinate. Use bounded task-specific excerpts and
verify current source; do not inject a multi-megabyte map into every request.

Compiler-backed navigation can complement maps when supplied accurate compilation flags,
SDK/sysroot and generated headers. Any semantic cache needs build-context and dependency
identity, not merely file hashes. Object/debug inspection is useful for exact built
artifacts but may lose information through optimisation/stripping and may represent old
source. Neither compiler nor binary indexing is supplied by this adapter.

This is a scope-wide map adapter, separate from `knowledge` file artifacts. It does not yet implement reusable
per-file Aider tag artifacts, base/branch/worktree graph composition, dependency-aware semantic invalidation,
an MCP server, cloud publishing or measured token savings. The existing knowledge resolver's freshness and
tombstone gaps must be hardened before connecting this adapter to shared delta caches.

Upstream: [installation](https://aider.chat/docs/install.html),
[repository maps](https://aider.chat/docs/repomap.html),
[Apache-2.0 licence](https://github.com/Aider-AI/aider/blob/main/LICENSE.txt).
This adapter calls Aider as an external dependency; it contains no copied Aider implementation.
