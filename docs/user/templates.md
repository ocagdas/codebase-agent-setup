# Editable templates

Export a neutral baseline, edit it locally, then install it into one or several repositories. This is not capsule
backup/restore: no machine configuration, target ledger, cache, backup or credentials are exported.

```bash
cbsetup template create /path/to/team-template --dry-run # preview; no writes
cbsetup template create /path/to/team-template           # new or empty directory only
# Edit the template's AI_CONTEXT.md and ai_workflow/project_guide.md, etc.
cbsetup install /path/to/repo --template /path/to/team-template --dry-run
cbsetup install /path/to/repo --template /path/to/team-template
```

The directory mirrors target-relative paths and includes template.json (schema 1.0 with a files list). Edit file
contents, not the supported inventory. Extra/missing files, unsupported paths, traversal, symlinks, malformed JSON
or Python, and recognized credential-shaped content are rejected. This detection is not proof that no secret is
present: never store credentials in a template. Test scripts are not exported. The template must be outside every
target directory, and export must not overlap the packaged project/ source. Custom Python helpers are executable
content: use only trusted/reviewed templates. Import validates syntax but never executes their scripts.

## Existing repositories

```bash
cbsetup install /path/to/repo --template /path/to/team-template
```

Unchanged managed files update; authored changes are preserved and reported. Existing project guides are always
preserved by default, even on a first install. To intentionally replace one with the edited template guide:

```bash
cbsetup install /path/to/repo --template /path/to/team-template --behaviour override
```

Changed originals are archived under ignored .ai_migration_backup/. Override cannot be combined with --adopt.
It works with the built-in payload too (without --template). Guide content remains repository-owned, not managed by future ordinary upgrades.
--adopt is still available on first installations to migrate authored entry files when no project guide exists.

Install and fleet apply accept --behaviour preserve|upgrade|override:

- preserve adds missing files and keeps all existing regular files.
- upgrade (default) updates unchanged managed files and keeps authored edits and the project guide.
- override replaces supported CAS files, including the guide, backing up changed originals.

Without a ledger, upgrade seeds missing files and preserves unknown existing files. Local settings, credentials,
unrelated files and obsolete files are not overridden. Use --remove-obsolete with upgrade for unchanged retired
managed files. Install, template create and fleet apply write by default; --dry-run validates/previews without writes.
The positional install target and --template value are directory paths, relative to the current directory or absolute.
Old --apply/--upgrade/--replace-guide flags remain hidden compatibility aliases; prefer the new options.

Templates are snapshotted when planning and checked again before target writes; a source edit during planning
fails the operation. Payload, ignores, backups and the fresh target-specific ledger use the existing recoverable
transaction. template.json is not installed and another checkout's ledger is never imported.

## Fleet

```json
{"schema_version":"1.0","repositories":[
  {"path":"./repo-one","publication":"open"},
  {"path":"./repo-two","publication":"owner-only"}
]}
```

Paths in fleet.json are relative to that file. Template CLI paths are relative to the current directory.

```bash
cbsetup fleet --file /path/to/fleet.json apply --template /path/to/team-template --dry-run
cbsetup fleet --file /path/to/fleet.json apply --template /path/to/team-template
```

Owner-only targets are skipped unless --include-owner-only is explicit. --behaviour override is also available for
deliberate fleet-wide guide replacement; preview each target first. Failures are reported per target and return
a nonzero exit; a fleet is not one atomic cross-repository transaction. No Git publication occurs.

Installed guidance remains ignored by default. --track-guidance skips adding guidance ignores; it never removes
existing ignores or changes tracking. State and local settings stay ignored. Keep editable templates outside Git
unless explicitly reviewed for intentional sharing.

## Limits

Export currently starts from the built-in baseline, not a live repository. Supported paths are tied to the current
payload; regenerate/review a template after a CAS payload-layout change. JSON syntax is checked, not arbitrary
custom schema semantics. Existing capsule repo snapshots still contain only local settings and the ledger, not
the full installed guidance tree. Full-guidance recovery and explicit export from a live repo remain separate work.
