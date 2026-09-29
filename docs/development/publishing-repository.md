# Use this as your tooling repository

Extract the archive, open the codebase-agent-setup directory and push its contents as the root of a new repository. Keep project/, preset/, extension/, tests/, the installation files and documentation. Do not push .venv, caches or credentials; ignore rules are included.

Example initialisation, after substituting your actual Git remote:

```text
git init -b main
git add .
git commit -m "Add codebase-agent-setup"
git remote add origin YOUR_GIT_REMOTE
git push -u origin main
```

No remote has been created or pushed by this task. Choose a licence and ownership notice before publishing the custom material publicly. The included NOTICE.md identifies official upstream; the custom package is not an official GitHub product.

This tooling repository is distinct from your firmware, service or data science repository. Install it into those repositories with install.py. Commit the agreed generated project instructions there so every clone receives the same workflow version.

No .github/workflows/validate.yml is currently included. Run the local checks in CONTRIBUTING.md before publishing. Adding a regression workflow for the pinned Spec Kit CLI, platform tests and Docker checks is follow-up work; pushing this checkout alone will not run those checks. Record remote results in VALIDATION.md only after the jobs actually execute.

Keep upstream.lock.json and requirements.txt in agreement. Retest a new official Spec Kit version before changing the pin. The preset and extension compatibility requirements must change in the same review. Installation verifies the selected CLI version and stages compatibility checks. Personal release/commit overrides leave the distribution pin unchanged; see docs/user/toolchain-versions.md.

Retain existing project commands and authored documents when upgrading. Initial installation rejects conflicting files. For installations with an engineering-install.json ledger, install.py --upgrade previews updates to unchanged managed files while preserving authored differences; --apply performs the reviewed update. Older installations without that ledger require manual reconciliation. See docs/user/toolchain-versions.md.
