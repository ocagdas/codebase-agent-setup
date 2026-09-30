# AI context

This is the single, tool-independent guide for every coding assistant working in this repository. Tool-specific
entry files only point here. Runtime permissions and the current user's instructions always take precedence.
This file is managed by codebase-agent-setup; put repository-specific guidance in `ai_workflow/project_guide.md`.

## Loading order

1. `ai_workflow/project_guide.md`: purpose, document owners, commands, policies and hazards for this repository.
   Its rules apply on top of this file.
2. The handover document (see below). Read it before starting work.
3. Only when `.specify/memory/constitution.md` exists: that Spec Kit workflow, for the specification
   workflow.
4. Only the source, tests and documents relevant to the task. Conceptual discussion needs no further loading.

## Handover

The handover document carries state between sessions and between tools. Locate it with
`python3 ai_workflow/tools/settings.py handover --repo .`; the `path` it prints is authoritative, and it may lie
outside the repository. The contract is in `ai_workflow/handover.md`.

- At the start, read it and verify its claims against the current code and Git state before relying on them. Where it
  contradicts what you find, correct it as part of your change rather than working around it.
- Before ending any session that changed code, repository state or decisions, update it in place: replace stale
  content rather than appending a dated log, set the `As of` date, and record only evidence that actually ran.
- Then run `python3 ai_workflow/tools/validate_handover.py --repo .` and fix what it reports.
- If the handover lies outside the repository, never copy its private content into the repository.
- If it does not exist yet, create it from the template in `ai_workflow/handover.md`.

## Working rules

- Inspect Git status first and preserve unrelated or uncommitted work.
- Read current source and the configured build system; an inventory or index is a map, not proof. Expand analysis to
  affected callers, tests and configuration.
- Keep documentation, tests and behaviour aligned in the same change; update the document that owns each fact.
- Use the commands in `ai_workflow/project_guide.md`; never assume a tool is installed because its name is known.
- Report every requested item as completed, incomplete or untouched, with actual evidence. Do not claim a check
  passed unless it ran. A self review is not an independent review.
- Commits, pushes, merges, releases and other publication follow the project guide's policy and explicit user
  authorisation. Existing authorisation for the task counts; ask only for unresolved scope or actions outside it.
- On Windows use an available Python 3.11+ interpreter (`py -3` or `python`) in place of `python3`; inside a venv or
  Conda session use that environment's interpreter.

## Optional tooling

- When code work permits local cache writes, `python3 ai_workflow/tools/repo_bootstrap.py prepare --pretty`
  prepares inventories; follow `ai_workflow/bootstrap_analysis.md` when analysis is requested. Strictly read-only
  work must not write caches. Commands declared in bootstrap configuration are not executed by the utility.
- Repository index, when one is configured: `ai_workflow/knowledge.md`. Run
  `python3 ai_workflow/tools/knowledge.py status --repo .` to see whether this repository has one. It is a starting
  point that must be verified against source, never an authority for a change.
- Personal preferences: `ai_workflow/settings.md`. They never override project quality gates or runtime permissions.
