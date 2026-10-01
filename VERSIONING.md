# Package versions and tags

codebase-agent-setup follows the common [repository contract](REPOSITORY_STRUCTURE.md). `pyproject.toml [project].version` is the sole package-version source; upstream.lock.json and Spec Kit provisioning were retired. The repository adapter points its version mirror field at pyproject.toml. Ordinary feature PRs preserve the trunk version; CI owns the subsequent qualifying patch bump and immutable tag.

## Commands and outputs

```bash
python scripts/version.py check
python scripts/version.py current --plain
python scripts/version.py current --json
python scripts/version.py minor --dry-run
python scripts/version.py minor
# Also: patch, major, set 2.1.0
python scripts/version.py tag --dry-run
python scripts/version.py check-pr --base-ref origin/main
python scripts/version.py classify-ci --merged --github-output
python scripts/version.py classify-release --tag v1.2.0 --github-output
```

Numeric MAJOR.MINOR.PATCH is required; leading zeros, prereleases, inconsistent mirrors and equal/decreasing requested values are rejected. `current` defaults to JSON. Classifiers do not mutate Git. `classify-ci` returns integer `schema_version: 1`, `mode: patch|tag|none`, target `version`, `tag` and `source_commit`. Supply `--merged` only after verifying merged-PR association; merge commits are also recognized from history. Classifiers describe a commit; the workflow restricts which branch may publish it.

`--github-output` explicitly writes step outputs. `classify-release` requires tag, HEAD and package version to agree and always returns `publish: false`. Public GitHub Release/PyPI publication remains disabled.

Local bump commands edit pyproject.toml but do not commit/push. Use a clean, current selected-trunk checkout for a maintainer version increase; review, commit and push through authorized maintainer procedures. `tag` requires a clean tree, creates an annotated tag, and never moves an existing tag. The same-commit tag is an idempotent no-op. Local tagging does not run CI.

## Trunk and automatic policy

codebase-agent-setup's selected release trunk defaults to `main`. `REPOSITORY_TRUNK` is the common override for intentional policy changes. Checks still cover all branches. Update the trunk's protection rules when changing the selection; configuration alone does not grant a bypass.

Ordinary PRs must leave package version values unchanged. The PR check compares against the merge base so a later trunk version bump does not invalidate an unchanged stale feature branch. After a qualifying trunk merge passes Quality gate, CI increments the patch and tags it. Maintainer-selected higher versions on a direct trunk push are tagged without a second bump. Direct code-only pushes run checks without a bump.

Automatic mutation requires `REPOSITORY_VERSIONING_ENABLED=true` and the configured App.
Disabled automation leaves ordinary CI active. `ci.yml` calls the reusable `version.yml` only after job success and `go == 'true'`, for a top-level CI push to the selected trunk at the same tested SHA. PR, manual, merge-queue and reusable release-check runs cannot mutate versions. PR detection is paginated and filters merged PRs to the selected trunk, supporting squash/rebase merges. Mutation is serialized per trunk.

The publisher requires a clean disposable checkout, matching HEAD/GITHUB_SHA and the exact remote trunk tip. It does not rebase onto newer untested code. An advanced tip returns `superseded`; rapid merges may coalesce into one patch. A later direct code-only push does not cause an automatic catch-up bump. Merge another PR or select a version explicitly if one is needed.

A version commit and tag are pushed together using `git push --atomic`, without force. A matching tag prevents repeat versioning, including the App-triggered CI run. Credentials/actor names and commit message text do not serve as a substitute for the quality gate or immutable tag identity.

## GitHub activation

Earlier audit 2026-10-01: main CI [run 36847270196](https://github.com/ocagdas/codebase-agent-setup/actions/runs/36847270196)
passed its Quality gate, but Version and tag trunk was skipped. REPOSITORY_VERSIONING_ENABLED is false;
CBSETUP_VERSIONING_APP_ID and CBSETUP_VERSIONING_APP_PRIVATE_KEY are not configured at repository scope.
Active main/v* rulesets currently permit administrator bypass only, not a versioning App. No tags exist.
Complete the App configuration/bypass below before enabling mutation. Branch names do not select package versions:
starting from 1.1.0, a qualifying ordinary PR merge increments to 1.1.1, regardless of its dev branch suffix.

Latest audit 2026-10-01: the owner enabled REPOSITORY_VERSIONING_ENABLED=true. Repository-scoped App ID/key
settings are still absent. Feature push/PR runs cannot publish versions regardless of this flag; complete App
configuration and protection permissions before the qualifying trunk merge. Changing the flag alone does not
prove a version/tag was published. PR #13's initial CI failed distribution validation; its correction requires a new run.

1. Install a repository-scoped GitHub App with Contents read/write permission.
2. Keep existing variable `CBSETUP_VERSIONING_APP_ID` and secret `CBSETUP_VERSIONING_APP_PRIVATE_KEY` (PEM key). No credential names changed during standardization. The reusable workflow passes the same secret through its internal `versioning-private-key` argument.
3. Set `CBSETUP_VERSIONING_ACTOR` to the App bot login for commit identity; its default remains `codebase-agent-setup-versioning[bot]`. Loop prevention now relies on the exact existing tag, rather than the former `[skip ci-version]` message/actor guard. Existing tagged commits remain no-ops; no message migration is needed.
4. Require the stable **Quality gate** check on contributor PRs. Allow only the dedicated App to make the necessary version commit/new tag under the selected trunk and `v*` rules. Keep force-push/tag-update/deletion restrictions. Explicit maintainer version commits require authorized repository rules.
5. Run a real trunk PR merge and inspect the version workflow and tag-triggered Release readiness. Missing App settings fail visibly when an action is needed. Hosted activation tasks remain in [TODO.md](TODO.md).

The App token allows pushed tags to trigger subsequent workflows; default GITHUB_TOKEN push events ordinarily do not. See [GitHub workflow triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow). CI/release callers allow contents/read and pull-requests/read; write credentials are created only inside the already-gated version job.

## Recovery and distribution boundary

The CI helper interface is:

```bash
python scripts/publish_version.py --source SHA --trunk BRANCH --merged --github-output
```

It emits integer schema version 1, `status: published|unchanged|superseded`, and `source_commit`; published results include `version`, `tag` and `version_commit`. A fabricated local flag does not grant publication authority. Use this helper only in an authorized disposable checkout with configured credentials.

Conflicting tags are errors, never overwritten. On branch-rule rejection, network failure or concurrent updates, resolve the underlying issue and rerun in a fresh checkout. Atomic publication avoids intentionally publishing half the operation; if the push succeeded but its response was lost, a fresh run sees the tag/advanced tip. Do not reuse the locally mutated failed checkout or delete tags as recovery.

Tags trigger full release-readiness checks and validated wheel/source artifacts. Source CI success is not proof that a subsequent tag build or public publication succeeded. [CI.md](CI.md) owns quality evidence; [VALIDATION.md](VALIDATION.md) records executed scope.

## Shared implementation and published verification

[REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) links the authoritative shared
interfaces and conformance suite. codebase-agent-setup keeps its mirror/build adapter and leaves
public publication disabled. The standard design owns cross-repository semantics;
this document owns codebase-agent-setup's operational settings and recovery commands.

`verify-release.yml` is dormant by default. For an existing published release, set
`CBSETUP_VERIFY_PUBLISHED_RELEASES=true` and dispatch with its tag. It verifies the
downloaded wheel, CLI and consumer resources; it does not enable a publisher or replace
assets. See [CI.md](CI.md) for build qualification and [VALIDATION.md](VALIDATION.md)
for actual evidence. Hosted setup/state belongs to the [setup guide](docs/development/github-policy-setup.md).
