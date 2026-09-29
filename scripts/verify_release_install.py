"""Qualify a downloaded codebase-agent-setup wheel in an isolated environment."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from build_release import verify_manifest


def main():
    directory = Path(sys.argv[1]).resolve()
    verify_manifest(directory)
    wheel = next(directory.glob("*.whl"))
    provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        for suffix in ("project/AI_CONTEXT.md", "project/ai_workflow/settings.md"):
            if not any(name.endswith(suffix) for name in names):
                raise ValueError(f"Missing consumer resource: {suffix}")
    with tempfile.TemporaryDirectory(prefix="codebase-agent-setup-published-") as temp:
        env = Path(temp) / "env"
        subprocess.run([sys.executable, "-m", "venv", str(env)], check=True)
        binary = env / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        subprocess.run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], check=True)
        cli = binary / ("codebase-agent-setup.exe" if os.name == "nt" else "codebase-agent-setup")
        result = subprocess.check_output([str(cli), "--version"], cwd=temp, text=True, encoding="utf-8")
        if json.loads(result)["version"] != provenance["version"]:
            raise ValueError("Installed version differs from released version")
        subprocess.run(
            [str(cli), "configure", "inspect", "--user-config", str(Path(temp) / "absent.json")], cwd=temp, check=True
        )


if __name__ == "__main__":
    main()
