# Supported tool files and user-maintained manuals

```bash
cbsetup tools list
cbsetup tools show codex
cbsetup tools show cursor --json
```

The catalog reports CAS-managed entry paths, selected official instruction patterns,
exact manual paths and upstream documentation. It is not installed-tool detection or
a complete inventory of vendor settings. File integration is not proof of live-client
instruction compliance. Patterns/locations follow the official documentation checked
on 2026-10-05; the OpenAI Docs skill informed the Codex mapping.

| Tool | CAS entry file | User manual |
| --- | --- | --- |
| Codex | AGENTS.md | ai_workflow/tools/codex_manual.md |
| Claude | CLAUDE.md | ai_workflow/tools/claude_manual.md |
| Copilot | .github/copilot-instructions.md | ai_workflow/tools/copilot_manual.md |
| Cursor | .cursor/rules/engineering.mdc | ai_workflow/tools/cursor_manual.md |
| Gemini | GEMINI.md | ai_workflow/tools/gemini_manual.md |

Sources: [Codex](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[Claude](https://code.claude.com/docs/en/memory),
[Copilot](https://docs.github.com/en/copilot/reference/custom-instructions-support),
[Cursor](https://cursor.com/docs/rules),
[Gemini](https://geminicli.com/docs/cli/gemini-md/).

`*_manual.md` is our convention, not a vendor-discovered filename. Entry files point to
`AI_CONTEXT.md`, which directs the active tool to its exact manual through
`ai_workflow/tool_registry.json`. The registry is data, not a native client feature:
the assistant follows the guide's instruction to read it. Do not load every manual, infer tool identity from
an entry filename or load another tool's manual. Several tools also discover AGENTS.md.
Unknown tools skip manuals. User instructions/runtime permissions/project gates retain
their precedence; a manual supplements rather than overrides shared project rules.

CAS seeds missing manuals and preserves existing bytes during preserve, upgrade AND
override. Edited templates seed new manuals but cannot replace existing user content.
Manuals are outside managed-file hashes and obsolete cleanup; missing ones are reseeded.
Non-files/symlinks fail rather than being overwritten. Installed manuals are Git-ignored
by default, included in setup capsules and redacted like other captured text. Avoid
credentials regardless of ignore rules. `--track-guidance` does not erase existing rules.
