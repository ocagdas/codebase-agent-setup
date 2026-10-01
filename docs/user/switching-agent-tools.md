# Switching agent tools and keeping handovers current

codebase-agent-setup gives every coding assistant the same instructions, so you can move a repository between
Claude Code, Codex, GitHub Copilot, Cursor and Gemini CLI (or any tool that reads `AGENTS.md`) without rewriting
guidance, and every tool keeps the same handover document up to date.

## What a seeded repository contains

| File | Owner | Role |
| --- | --- | --- |
| `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.cursor/rules/engineering.mdc` | installer | One-line pointers to `AI_CONTEXT.md` |
| `AI_CONTEXT.md` | installer | Tool-neutral loading order, working rules and handover rules |
| `ai_workflow/project_guide.md` | repository | Purpose, document owners, commands, policies, hazards. Preserved unless explicitly overridden |
| `ai_workflow/handover.md`, `ai_workflow/tools/validate_handover.py` | installer | Handover contract, template and validator |

Upgrades (the default behaviour) replace installer-owned files only when you have not edited them, and never touch
`project_guide.md`.

## Seed a repository

```bash
# Guide, pointers and handover contract
codebase-agent-setup install /path/to/repo
```

Add --dry-run to preview without writes. Use --behaviour preserve to add missing files only or --behaviour override
to replace supported CAS files, including the guide, with backups. CAS requires no external CLI and no longer
installs or manages Spec Kit.

### Repositories that already have agent files

Add `--adopt`. For each existing `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, Copilot or Cursor entry file that differs
from the standard pointer, the installer appends its text verbatim to `ai_workflow/project_guide.md` under
`## Imported from <file> (review)`, backs up the original under `.ai_migration_backup/`, and installs the pointer.
The preview lists `referenced_guidance`: documents those files point to (for example a master guidance file) that
you should fold into the project guide or link from it. `--adopt` refuses to run when `project_guide.md` already
exists. Then rewrite the imported sections into the guide's headings and remove the `cbsetup:unfilled` marker.

## Configure the handover location

The handover defaults to `HANDOVER.md` in the repository (deliberately not `HANDOFF.md`, which many repositories
use for an authored maintainer guide). To keep handovers outside the repository (for example in a private workspace
`docs/<repo>/HANDOVER.md`), set `handover.path` in your user settings for that project so the machine-specific path
is never committed:

```json
{
  "schema_version": "1.0",
  "projects": {
    "remote:<identity from cbsetup configure inspect>": {
      "handover": {"path": "/home/me/work/docs/my-repo/HANDOVER.md"}
    }
  }
}
```

The user file is `~/.config/codebase-agent-setup/config.json` on Linux (see
[settings](../../project/ai_workflow/settings.md) for other platforms). Get the identity with
`cbsetup configure inspect --repo /path/to/repo` (`repository_id`). A checkout-local
`ai_workflow/settings.local.json` can override it.

Any tool, or you, can then run inside the repository:

```bash
python3 ai_workflow/tools/settings.py handover --repo .     # where is it?
python3 ai_workflow/tools/validate_handover.py --repo .     # does it meet the contract?
```

`AI_CONTEXT.md` tells every assistant to read and verify the handover at the start of a session and to update and
validate it before ending any session that changed code, repository state or decisions.
