# Purpose

codebase-agent-setup manages the agent configuration of many repositories and of the machine they are worked on, including the half that git cannot hold. Its audience includes developers who use more than one agent tool, work across more than one repository, and move between machines.

It installs one tool-neutral guide with a thin pointer per assistant, seeds a repository-owned project guide it never overwrites, and maintains a handover document so work survives a change of tool or session. It captures user config, per-checkout local settings and known tool directories into portable capsules whose credentials are always removed, and it operates across a declared fleet of repositories with a per-repository publication policy.

It is not an agent client renderer: fanning instructions out to dozens of tools is `ruler`'s and `rulesync`'s job, and the intention is to emit their source format rather than duplicate it. It no longer installs or manages GitHub Spec Kit (removed 2026-09-30).

Token savings are an intended benefit of the optional knowledge backends to measure against real agent tasks, not an established performance claim. Current delivery belongs in [STATUS.md](STATUS.md), priorities in [ROADMAP.md](ROADMAP.md), and open actions in [TODO.md](TODO.md).

This project is not a compiler index engine, an autonomous agent coordinator, a replacement for project tests, or a guarantee that every assistant enforces Markdown guidance. It does not grant model access or publish customer code. Product packaging and knowledge-artifact publication have distinct contracts and authorization.
