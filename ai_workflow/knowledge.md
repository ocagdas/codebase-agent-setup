# Repository knowledge

Shared-store prefixes percent-encode the repository identity as one directory component, including colons and
slashes, so the same configuration works on Windows and POSIX. Older unescaped stores must be republished or moved
to the encoded prefix before pulling; the cache format and artifact keys are unchanged.

This repository may carry a prebuilt index of its own code, so you can answer structural questions without reading
every file. The index is a **starting point, not the truth**.

Check whether it is configured and current:

```bash
python3 ai_workflow/tools/knowledge.py status --repo .
```

If `configured` is `false`, there is no index here. Work normally from source and ignore the rest of this document.

## Rules

1. **Query before reading.** Use `knowledge.py query` to locate symbols and get outlines, then read only the files the
   answer does not settle. Reading is still correct — it is just more expensive than it needs to be.
   A repository may declare several indexers, typically one per language. `query` asks them all and labels each block
   with the indexer that answered, so `(no match)` from one is not an answer about the others. Narrow with
   `--indexer <id>` only when you already know which one owns the question.
2. **Verify before you rely on it.** Every result carries `file:line` and the commit it was built from. Before
   changing code, confirm the claim against the current file. Never treat an index entry as authoritative for an edit.
3. **Pull, do not rebuild.** If `status` reports files as `missing`, run `knowledge.py pull` first: someone else has
   probably already indexed that content. Only build what pull cannot supply.
4. **Build the cheap layer, not the expensive one.** `--layer worktree` covers your uncommitted edits.
   `--layer base` is the shared trunk index and is normally built by CI, not on a developer machine. `build` refuses
   any layer whose commit is not checked out, and names that commit: on a dev branch the base layer is not yours to
   build, so `pull` it instead.
5. **Never push unless you are asked to.** Publishing an index of this repository's code discloses that code. It
   requires `--apply`, and for a repository whose policy reserves publication for a human it also requires
   `--include-owner-only`. Ask first.
6. **Report a stale or wrong entry** in your summary rather than quietly working around it, and say which file
   disagreed with it. A `stale` layer is still useful: it lists exactly which files it no longer covers, so use the
   index for the rest and read those directly.

## Commands

```bash
python3 ai_workflow/tools/knowledge.py status --repo .
python3 ai_workflow/tools/knowledge.py build --layer worktree --apply --repo .
python3 ai_workflow/tools/knowledge.py query --repo . -- <indexer arguments>
python3 ai_workflow/tools/knowledge.py query --repo . --indexer <id> -- <indexer arguments>
python3 ai_workflow/tools/knowledge.py pull --repo .
```

`build` without `--apply` prints what it would index and runs nothing.

Indexers read the working tree, so a layer can only be built where its commit is `HEAD`. Building the base layer from
a branch checkout would file this branch's content under the trunk's hashes, and that error would travel to everyone
who pulled it — so it is refused rather than warned about.

## What the states mean

| State | Meaning |
| --- | --- |
| `current` | Every in-scope file is covered by an artifact built from exactly its current content |
| `partial` | Most files are covered; `missing` lists the ones that are not. Read those directly or build the layer |
| `missing` | Nothing is covered for that layer yet |
| `stale` | A whole-scope index exists but the content moved; `changed_since` lists the files it no longer describes |
| `unavailable` | The layer cannot be evaluated here, usually because the trunk reference is not fetched |

## How it stays correct

Artifacts are keyed by the content hash of the single file they describe, so editing one file invalidates one entry
and nothing else. The key also mixes in the indexer's id, kind and version, so several indexers may cover the same
file — or the same repository in different languages — without colliding. The same file content in another clone, on another branch, under another path, resolves to the same
artifact — which is why pulling usually beats rebuilding.
