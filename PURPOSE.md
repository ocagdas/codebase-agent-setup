# Purpose

codebase-agent-setup gives LLM coding assistants a reusable baseline for local software projects: project guidance, goals, working conventions and revision-aware knowledge. Its audience includes developers working across large repositories, long-lived release trunks, feature branches, clones and teams.

It composes a preset, extension and consumer project payload around official GitHub Spec Kit. The upstream remains unmodified. Installation preserves authored project files; shared defaults can be refined by user, project, checkout and invocation settings. Source access remains available when optional knowledge backends are disabled or unsuitable.

The longer-term aim is to reuse compatible trunk knowledge with exact-base branch overlays, portable bundles and optional team publication. Token savings are an intended benefit to measure against real agent tasks, not an established performance claim. Current delivery belongs in [STATUS.md](STATUS.md), priorities in [ROADMAP.md](ROADMAP.md), and open actions in [TODO.md](TODO.md).

This project is not a compiler index engine, an autonomous agent coordinator, a replacement for project tests, or a guarantee that every assistant enforces Markdown guidance. It does not grant model access or publish customer code. Product packaging and knowledge-artifact publication have distinct contracts and authorization.
