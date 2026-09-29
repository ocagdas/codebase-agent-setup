"""Install pinned default/alternate Spec Kit CLIs in isolated CI environments."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALTERNATE_COMMIT = "6906bc582230bb752776e23287ee97990c1af743"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / ".quality/toolchains")
    parser.add_argument("--github-env", action="store_true")
    args = parser.parse_args()
    pin = json.loads((ROOT / "upstream.lock.json").read_text(encoding="utf-8"))
    directory = args.directory.resolve()
    variables = {"CBSETUP_PACKAGE_TESTS": "1"}
    for name, commit in (("default", pin["upstream_commit"]), ("alternate", ALTERNATE_COMMIT)):
        environment = directory / name
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True, timeout=120)
        binary = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        requirement = f"specify-cli @ git+{pin['upstream_repository']}.git@{commit}"
        subprocess.run([str(python), "-m", "pip", "install", requirement], check=True, timeout=600)
        variables["SPECIFY_BIN" if name == "default" else "SPECIFY_ALTERNATE_BIN"] = str(
            binary / ("specify.exe" if os.name == "nt" else "specify")
        )
    record = directory / "alternate.json"
    record.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "requested_ref": "v1.0.3",
                "upstream_repository": pin["upstream_repository"],
                "upstream_commit": ALTERNATE_COMMIT,
                "specify_cli_version": "1.0.3",
                "package_version": pin["package_version"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    variables["SPECIFY_ALTERNATE_RECORD"] = str(record)
    (directory / "environment.json").write_text(json.dumps(variables, indent=2) + "\n", encoding="utf-8")
    if args.github_env:
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as handle:
            for key, value in variables.items():
                handle.write(f"{key}={value}\n")
    print(json.dumps(variables, indent=2))


if __name__ == "__main__":
    main()
