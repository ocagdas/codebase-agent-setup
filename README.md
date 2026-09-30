# codebase-agent-setup

**Set up your AI coding agents once. Use them in every repository, keep them in step, and carry the whole setup to
another machine in one command.**

`cbsetup` manages the agent configuration of *many* repositories and of the machine you work on — including the half
that git cannot hold. It writes one tool-neutral guide that Claude Code, Codex, Copilot, Cursor and Gemini CLI all
read, keeps a handover document current as work moves between them, and captures your whole setup into a portable
**capsule** that always has its credentials stripped out.

Python 3.11+. **No runtime dependencies** — standard library only.

> **Status: pre-release.** Working and used daily on a four-repository fleet, but not yet on PyPI, and the command
> surface may still change. See [what is not done yet](#what-is-not-done-yet).

---

## Why this exists

Every agent tool wants its own instruction file. Point five tools at five files and they drift; the rules you wrote
for one are missing from the next. And when you switch tools — or machines — everything you configured that *isn't*
in git goes with it: your user config, per-checkout local settings, the tool directories in your home folder, the
handover notes you keep outside the repository.

`cbsetup` treats that as one thing to manage, not a dozen files to remember.

| | |
| --- | --- |
| **One guide, every tool** | `AI_CONTEXT.md` holds the rules; each tool gets a one-line pointer to it. Switching tools changes nothing. |
| **Session continuity** | A handover contract every tool reads at the start, verifies against the code, and updates before it stops. |
| **Portable capture** | `capsule` packs the ungittable half of your setup into a reviewable archive. Apply it elsewhere and you have a clone. |
| **A fleet, not a repo** | `fleet status` tells you in one table which of your repositories has drifted. `fleet apply` fixes them together. |
| **Nothing clobbered** | A ledger records what the tool owns. Files you edited are preserved and reported, never silently overwritten. |
| **Secrets never travel** | Redaction is unconditional. Every removal is printed on capture *and* on apply, so you know exactly what to put back. |

---

## Install

Not on PyPI yet, so install from the repository:

```bash
# Try it without installing anything permanently
uvx --from git+https://github.com/ocagdas/codebase-agent-setup cbsetup --help

# Or install it for real
pipx install git+https://github.com/ocagdas/codebase-agent-setup
```

From a clone, for development:

```bash
git clone https://github.com/ocagdas/codebase-agent-setup && cd codebase-agent-setup
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/cbsetup --help
```

Every example below uses `cbsetup`. `python -m codebase_agent_setup` is the same program if you prefer not to install
a script.

---

## Quickstart

### 1. One repository

```bash
cd ~/code/my-app
cbsetup install .            # previews; writes nothing
cbsetup install . --apply
```

You now have:

```text
AI_CONTEXT.md                      the guide every tool reads (managed by cbsetup)
AGENTS.md  CLAUDE.md  GEMINI.md    one-line pointers to it
.github/copilot-instructions.md
.cursor/rules/engineering.mdc
ai_workflow/project_guide.md       YOUR rules — seeded once, never overwritten again
ai_workflow/handover.md            the handover contract
ai_workflow/settings.*             settings schema and reference
ai_workflow/tools/                 stdlib-only helpers the guide refers to
.cbsetup/install.json              the ledger: what cbsetup owns here
```

That is 22 managed files in total, plus the install-once authored project guide.
`cbsetup install` prints the exact list before it writes anything.

**The one manual step:** fill in `ai_workflow/project_guide.md` — what this repository is, which commands to run,
what an agent must never do. It ships as a template and `cbsetup` never touches it again, so put real rules there
rather than in the managed files. Asking your agent to fill it in from the codebase works well.

Then tell `cbsetup` where the handover document lives and check it:

```bash
cbsetup handover --repo .                      # validate it against the contract
```

The handover may live **outside** the repository — useful when it holds notes you do not want committed. Set that per
project in your user config (`~/.config/codebase-agent-setup/config.json`):

```json
{
  "schema_version": "1.0",
  "projects": {
    "remote:<the repository id from `cbsetup configure inspect --repo .`>": {
      "handover": {"path": "~/notes/my-app/HANDOVER.md"}
    }
  }
}
```

### Already have agent files?

`--adopt` moves your authored `AGENTS.md` / `CLAUDE.md` / Copilot / Cursor text into `project_guide.md` for review,
backs the originals up under `.ai_migration_backup/`, installs the standard pointers, and tells you which other
guidance documents those files referenced so nothing gets lost:

```bash
cbsetup install . --adopt --apply
```

Without `--adopt`, an existing `AGENTS.md` is a hard collision and nothing is written. That is deliberate.

### Keeping a repository up to date

```bash
cbsetup install . --upgrade --apply
```

Refreshes managed files you have not touched, **preserves** the ones you edited and lists them as
`preserve_authored`. Add `--remove-obsolete` to retire managed files a newer version no longer ships; they are
archived to `.ai_migration_backup/` first, and anything you edited is always kept.

### 2. Many repositories

Write a `fleet.json` — relative paths resolve against the file, so it is portable:

```json
{
  "schema_version": "1.0",
  "repositories": [
    {"path": "~/code/my-app"},
    {"path": "~/code/shared-lib"},
    {"path": "~/code/client-work", "publication": "owner-only"}
  ]
}
```

```bash
cbsetup fleet status
```

```text
repository   policy      managed  drift  missing  guide
-----------  ----------  -------  -----  -------  --------
my-app       open        24       -      -        filled
shared-lib   open        24       1      -        UNFILLED
client-work  owner-only  24       -      1        -
```

At a glance: `shared-lib` has one managed file someone edited by hand, `client-work` has one missing, and
`shared-lib`'s project guide is still the unfilled template. Then bring them all into line:

```bash
cbsetup fleet apply --upgrade            # previews every repository
cbsetup fleet apply --upgrade --apply
```

**`publication: "owner-only"`** marks a repository where a human makes the changes. `fleet apply` skips it unless you
pass `--include-owner-only`. If one repository fails — a collision, a missing directory — it is reported and the rest
of the fleet still completes.

### 3. Backup, restore and clone — outside the repository

This is the part no other tool does. Your repositories are in git; your *setup* is not. `capsule` captures what git
cannot:

- your user config (`~/.config/codebase-agent-setup/config.json`)
- the tool directories `cbsetup` knows: `~/.claude/`, `~/.codex/`, `~/.cursor/`, `~/.gemini/`
- per-checkout local settings (`ai_workflow/settings.local.json`) and the ledger, for each repository you name

**Back up:**

```bash
cbsetup capsule create --out ~/backups/setup.zip \
    --repo ~/code/my-app --repo ~/code/shared-lib
```

```text
Redacted 2 secret value(s) during capture. Restore these yourself:
  tool-global/claude/settings.json: env.ANTHROPIC_API_KEY  (key name 'ANTHROPIC_API_KEY')
  tool-global/codex/config.toml: line 2  (assignment to 'github_token')
A capsule never carries credentials. Re-enter them by hand, or ask your agent to, after applying.
```

**Read that message.** Redaction is not a setting and there is no flag to turn it off. The capsule contains
`<redacted-by-cbsetup>` where each secret was, and the list above is your restore checklist. Values that merely
*point* at a secret — `token_env`, `${OPENAI_API_KEY}` — are kept, because that is how a setup is supposed to carry
a credential, so a setup built that way needs no manual step at all.

Use `--out-dir ./setup/` instead of `--out` for a plain folder you can read, diff, rsync or commit. Zip is the
default because it behaves identically on Linux, macOS and Windows, and carries no POSIX mode bits or symlinks.

**Inspect before you trust it:**

```bash
cbsetup capsule show ~/backups/setup.zip
```

The manifest — not the archive — is the source of truth. It names every file, where it came from, its digest, and
every redaction, so you can review a capsule before sending it anywhere.

**Restore, or clone onto a new machine:**

```bash
cbsetup capsule apply ~/backups/setup.zip --repo ~/code/my-app            # previews
cbsetup capsule apply ~/backups/setup.zip --repo ~/code/my-app --apply
```

Every file's digest is verified against the manifest before a single byte is written. Target paths are **recomputed**
for the receiving machine rather than carried literally, so a capsule made on Linux applies correctly on Windows or
macOS. A file that already exists with different content is a collision; pass `--overwrite` to replace it. The
redaction list is printed again on apply, so the last thing you see is what you still have to restore.

Applying to a *different* repository and a *different* home directory is a clone:

```bash
git clone git@github.com:me/my-app.git ~/code/my-app     # the gittable half
cbsetup capsule apply setup.zip --repo ~/code/my-app --apply   # the other half
```

Use `--machine-only` to restore just the machine layer and leave repositories alone, and `--include PATH` for one-off
extra files. `--include` takes individual files: a directory or a glob is refused, and a whole-home sweep is refused
outright, not hidden behind a flag.

---

## How it compares

[`ruler`](https://github.com/intellectronica/ruler) and [`rulesync`](https://github.com/dyoshikawa/rulesync) fan one
instruction source out to 30–50 agent clients. They are good at it, with communities that absorb per-client format
change.

**`cbsetup` is not competing with them.** They distribute instruction text inside one repository, statelessly,
regenerating and overwriting. `cbsetup` manages a whole setup across many repositories and the machine, keeps state
about what it owns, and carries the parts that are not instruction text at all.

| | ruler / rulesync | cbsetup |
| --- | --- | --- |
| Scope | One repository | **Many repositories, plus the machine** |
| State | Stateless: regenerate and overwrite | **A ledger**: knows what it owns and what you edited |
| Unit of work | Instruction text → client files | **The whole setup**: guide, config, standards, handover |
| Across sessions | No concept of it | **A handover contract** read, validated and updated by every tool |
| The ungittable half | Not addressed | **Capsules**: capture, review, apply, clone |
| Agent clients supported | 30+ / 50+ | 5 — and growing this number is *not* the plan |

The intent is to emit ruler's own source format so it fans out to its 30–50 targets, rather than maintaining a
per-client renderer table here. Use both: ruler for reach, `cbsetup` for continuity, portability and fleet.

---

## Commands

```text
cbsetup install <repo>        Seed or upgrade a repository's tool-neutral agent guide
cbsetup fleet status|apply    Status and mass apply across many repositories
cbsetup capsule create|show|apply
                             Capture, inspect and replay a setup; always redacted
cbsetup handover             Locate and validate a repository's handover document
cbsetup configure            Inspect and change settings
cbsetup knowledge            Optional retrieval backends (off by default)
cbsetup bootstrap            Optional local inventories
```

Every command that writes **previews by default**. Nothing happens without `--apply`.

---

## Design commitments

These are the rules the code is held to, not aspirations:

1. **Preview by default.** Every mutating command prints its plan and exits unless you pass `--apply`.
2. **Your files are yours.** A managed file you edited is preserved and reported. A file seeded once
   (`project_guide.md`) is never replaced. Collisions stop the whole operation rather than resolving themselves.
3. **Writes are transactional.** A journal is written before target writes, with a per-checkout lock and rollback.
   An interrupted install recovers and refuses to overwrite anything you changed afterwards.
4. **Secrets never travel, ever.** No flag, no config key, no environment variable enables it. Every redaction is
   printed twice — on capture and on apply.
5. **No home-directory sweep.** Not behind a flag, not with confirmation.
6. **No runtime dependencies, no network, no external CLI.** Standard library only.
7. **`cbsetup` never runs git for you.** No commits, no pushes, no tags. It edits files; you review and commit them.

---

## What is not done yet

Honest list, so nobody is surprised:

- **Not on PyPI.** Install from git.
- **5 agent clients**, not 30. The ruler-format emitter that fixes this is designed but not built.
- **No `cbsetup detect`.** Seeding a repository means writing `project_guide.md` yourself; there is no command yet
  that proposes one from your Makefile, `pyproject.toml` or CI config. This is the biggest adoption cost.
- **No MCP distribution.** Planned, consuming an external export rather than defining servers here.
- **`capsule diff`** (capsule versus this machine) is designed but not built.
- **Handover staleness is not yet a gate** — `handover` validates structure and date, but nothing fails a build when
  the document falls behind the branch.
- **No hosted CI yet** on this work. The quality gate runs locally: 180 unit plus 32 integration tests, ruff clean.
- **Spec Kit support was removed** from the core on purpose. `cbsetup` no longer installs or manages
  [Spec Kit](https://github.com/github/spec-kit); if a repository has it, the guide points at it and otherwise stays
  out of the way. Run `specify init` yourself if you want it.

Roughly in that order, that is also the roadmap.

---

## Contributing

`CONTRIBUTING.md` has the details. In short: `make check` must print `Quality gate: GO`, behaviour changes land with
tests that failed before the fix, and the payload tools under `project/ai_workflow/tools/` stay standard-library only
(a test enforces it).

```bash
make check PYTHON=.venv/bin/python
make format PYTHON=.venv/bin/python
```

MIT licensed — see `LICENSE` and `NOTICE.md`. Not an official product of GitHub, Anthropic, OpenAI, Google or Cursor.
