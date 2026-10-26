# Purpose

codebase-agent-setup writes supported instruction files into a checkout, records their ownership, preserves local
edits on upgrade, and captures selected setup files that the owner deliberately keeps outside Git. Its audience
includes developers using several coding clients, repositories or machines.

It installs a shared guide with a pointer per assistant and seeds a repository-owned project guide, preserved
unless the owner explicitly requests override. It installs a handover contract and validator; sessions still write
and maintain the actual handover. Capsules capture selected user/tool settings, checkout-local settings, the
authored project guide, manuals and ledger with known credential patterns redacted. They do not back up a running
harness, its database, model weights or arbitrary external handovers. Fleet operations apply the setup to declared
repositories under their publication policy.

It is not an agent client renderer: fanning instructions out to dozens of tools is `ruler`'s and `rulesync`'s job, and the intention is to emit their source format rather than duplicate it. It no longer installs or manages GitHub Spec Kit (removed 2026-09-30).

Token savings are an intended benefit of the optional knowledge backends to measure against real agent tasks, not an established performance claim. Current delivery belongs in [STATUS.md](STATUS.md), priorities in [ROADMAP.md](ROADMAP.md), and open actions in [TODO.md](TODO.md).

This project is not a compiler index engine, an autonomous agent coordinator, a replacement for project tests, or a guarantee that every assistant enforces Markdown guidance. It does not grant model access or publish customer code. Product packaging and knowledge-artifact publication have distinct contracts and authorization.
