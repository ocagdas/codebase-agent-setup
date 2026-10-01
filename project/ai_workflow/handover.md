# Handover contract

A handover document lets any assistant or person resume work without the previous session's context. There is one
per repository. Its location is the `handover.path` setting (see `settings.md`); it defaults to `HANDOVER.md` in the
repository and may live outside it. Find it with `python3 ai_workflow/tools/settings.py handover --repo .`.

## Rules

- Read it at the start of a session and verify its claims before relying on them.
- Update it in place before ending a session that changed code, repository state or decisions. Replace stale
  statements; do not append dated logs. Move superseded material to an archive if it must be kept.
- Record only evidence that ran, with its scope (for example "unit tests on Linux", not "tests pass").
- Keep private material out of public repositories when the document lives outside the repository.
- Validate with `python3 ai_workflow/tools/validate_handover.py --repo .` (or pass a path).

## Required content

- A line containing `As of YYYY-MM-DD` within the first ten lines, ideally with the branch and commit verified.
- `## State`: branch, working tree, versions, what is deployed or published.
- `## Open issues`: verified defects and gaps, with evidence and status.
- `## Next actions`: ordered steps for the next session.

Recommended (the validator warns when missing): `## Tests and evidence` (commands run, results, scope) and
`## Risks`. Headings may be numbered (`## 4. Open issues`). The validator also accepts these established names:
`Outstanding…` or `Known issues` for Open issues; `Resuming work`, `Next steps` or `Roadmap` for Next actions;
`Tests`, `Validation` or `Evidence` for Tests and evidence; `SWOT` for Risks.

## Template

```markdown
# <repository> — handover

**As of YYYY-MM-DD.** Verified against `<branch>` at `<commit>`.

## State

## Open issues

| ID | Issue | Evidence | Severity | Status |
| --- | --- | --- | --- | --- |

## Tests and evidence

## Risks

## Next actions

1.
```
