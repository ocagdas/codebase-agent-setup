# Repository Bootstrap Analysis

## Session requirement

At the beginning of a repository session, run:

```text
python3 ai_workflow/tools/repo_bootstrap.py prepare
```

All three commands (`prepare`, `complete`, `status`) use the target repository's `ai_workflow/bootstrap.json` by default, including through the installed `codebase-agent-setup bootstrap` command. `--config` overrides it; the bundled configuration is used only when the project has none. Invalid project configuration is an error, not a fallback.

Read the JSON result. Inspect semantic status before acting on `action_required`. If it is `none`, no prose analysis refresh is requested, but semantic refresh may still be needed. If it is `full_analysis` or `incremental_analysis`, complete the analysis request before relying on repository knowledge.

Inspect the returned `semantic_index` object:

1. When its mode is `disabled`, ignore semantic data and inspect source normally.
2. When `use_for_queries` is true, query the listed compatible layers using the configured adapter and the declared query precedence.
3. When `update_required` is true, update only the session writable overlay layers using the configured commands.
4. When `fallback_to_direct_source` is true, continue normally from current source for anything the semantic view cannot establish.
5. Never update the base layer from a branch session.

An instruction file can request this check, but only the executable utility, a session wrapper, a provider hook, or CI can enforce that it ran.

## Full analysis

Use the generated `analysis_request.json` and `candidate_file_index.json`. Create an initial structural map, then inspect task relevant components deeply to produce `repository_analysis.md` in the branch state directory.

Cover:

1. Product purpose and boundaries.
2. Directory and component structure.
3. Executables, libraries, firmware images, and build targets.
4. Important interfaces, data formats, protocols, and persistence.
5. Startup, shutdown, lifecycle, concurrency, interrupt, and ownership models.
6. Hardware abstractions, supported targets, and generated code.
7. Build, formatting, test, static analysis, packaging, and deployment paths.
8. Test organisation and component coverage.
9. Resource, timing, compatibility, safety, and security constraints.
10. Important uncertainties, parse gaps, and areas not inspected.

Every material statement should cite repository paths and symbols where practical. Separate observed facts from inference and generated summaries.

## Incremental analysis

Read the generated request, prior `repository_analysis.md`, `branch_delta.md`, and relevant changed files. Analyse changed files plus affected interfaces, includers, callers, tests, specifications, and build targets.

Update `repository_analysis.md` only where the durable repository understanding changed. Write the branch specific analysis to the exact file listed in `required_analysis_outputs`.

Apply worktree findings over the branch analysis and branch findings over the base analysis. A deletion in an overlay hides the corresponding lower layer information.

The delta analysis must cover:

1. Behavioural and architectural changes.
2. Changed interfaces and compatibility impact.
3. Header and dependency invalidation.
4. Concurrency, lifetime, error handling, timing, and resource impact.
5. Tests and documentation affected.
6. New risks, uncertainties, and unverified assumptions.
7. Items that did not change despite appearing in the textual diff.

## Completion

After writing every required output, run:

```text
python3 ai_workflow/tools/repo_bootstrap.py complete
```

The command refuses completion if the repository changed after the request was prepared. In that case run `prepare` again and analyse the updated request.

## Coverage and evidence

An initial full analysis means a fresh inventory and structural map, not proof that every function was understood. Record inspected components, unexplored areas, source revision and configuration. Expand analysis to callers, includers, configuration consumers and tests when dependencies are uncertain. Never rely on changed files alone for impact analysis.

Completion checks file presence and repository identity. It does not validate the truth or depth of prose, nor certify semantic artefacts. In required semantic mode, all necessary current layers must already exist before prepare succeeds. Run an explicitly configured adapter to refresh them and retry; a command declaration alone is insufficient.

## Repository knowledge

The bundled CGC and Sourcegraph adapters were retired on 2026-09-30, and with them `semantic_index.optional_backend`. Repository knowledge is now a separate, indexer-agnostic tool: see [knowledge.md](knowledge.md). Bootstrap neither launches nor consults it, and an index is a starting point to verify against the source, never authority for an edit.
