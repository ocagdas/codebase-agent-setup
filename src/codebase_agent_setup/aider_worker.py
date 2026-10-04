"""Executed only by the explicitly selected external Aider Python interpreter.

Calls the upstream library; no upstream implementation is copied here.
"""

import contextlib
import importlib.metadata
import json
from pathlib import Path
import socket
import sys


def main():
    if sys.argv[1:] == ["--version"]:
        print(importlib.metadata.version("aider-chat"))
        return

    def refuse_network(*args, **kwargs):
        raise RuntimeError("Network access is disabled in the CAS map worker")

    socket.socket.connect = refuse_network
    socket.socket.connect_ex = refuse_network
    socket.create_connection = refuse_network
    from aider.repomap import RepoMap

    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    class Budget:
        def token_count(self, text):
            # Avoid remote tokenizer downloads; this is explicitly approximate.
            return max(1, len(text.encode("utf-8")) / 4)

    class IO:
        def read_text(self, filename):
            return Path(filename).read_text(encoding="utf-8")

        def tool_output(self, *args):
            print(*args, file=sys.stderr)

        tool_warning = tool_output
        tool_error = tool_output

    with contextlib.redirect_stdout(sys.stderr):
        mapper = RepoMap(
            map_tokens=request["budget"], root=request["root"], main_model=Budget(), io=IO(), refresh="always"
        )
        files = [str(Path(request["root"]) / name) for name in request["files"]]
        text = mapper.get_repo_map([], files) or ""
    if not text.strip():
        raise ValueError("Aider returned an empty map")
    # Worker intentionally has no CAS imports/dependencies.
    print(json.dumps({"version": importlib.metadata.version("aider-chat"), "map": text, "redactions": []}))


if __name__ == "__main__":
    main()
