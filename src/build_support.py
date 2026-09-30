"""Build wheels from the single authored consumer payload at repository root."""

from pathlib import Path
import shutil
import tomllib
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        root = Path(__file__).resolve().parents[1]
        destination = Path(self.build_lib) / "codebase_agent_setup"
        if destination.resolve().is_relative_to(root / "src"):
            raise ValueError("Build output must not overwrite source files")
        if destination.exists():
            shutil.rmtree(destination)  # Rebuild only generated package output; omit stale payloads.
        super().run()
        config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]
        excluded = {
            path for pattern in config["exclude-package-data"]["codebase_agent_setup"] for path in root.glob(pattern)
        }
        for pattern in config["package-data"]["codebase_agent_setup"]:
            for source in root.glob(pattern):
                if source.is_file() and source not in excluded:
                    target = destination / source.relative_to(root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
