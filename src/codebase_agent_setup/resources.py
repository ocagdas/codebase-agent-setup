"""Resolve authored checkout resources or the self-contained wheel payload."""

from pathlib import Path
import tomllib


def resource_root(package_root):
    package_root = Path(package_root).resolve()
    # Bundled resources take precedence regardless of the install directory name.
    if (package_root / "upstream.lock.json").is_file():
        return package_root
    checkout = package_root.parents[1]
    if package_root.parent.name == "src":
        try:
            config = tomllib.loads((checkout / "pyproject.toml").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            config = {}
        project = config.get("project")
        if (
            isinstance(project, dict)
            and project.get("name") == "codebase-agent-setup"
            and (checkout / "upstream.lock.json").is_file()
            and (checkout / "project/ai_workflow/tools/settings.py").is_file()
        ):
            return checkout
    raise RuntimeError("codebase-agent-setup resource payload is missing; reinstall the distribution")


PACKAGE_ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = resource_root(PACKAGE_ROOT)
