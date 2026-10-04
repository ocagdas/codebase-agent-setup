"""Real Git privacy/freshness/transfer tests; external worker replaced by a command fixture."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codebase_agent_setup import repo_map


class RepoMapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        (self.repo / "module.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.calls = 0
        self.real_run = subprocess.run

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, check=True).stdout

    def worker(self, argv, **kwargs):
        if len(argv) > 1 and str(argv[1]).endswith("aider_worker.py"):
            if argv[-1] == "--version":
                return subprocess.CompletedProcess(argv, 0, "fixture-1\n", "")
            self.calls += 1
            request = json.loads(Path(argv[-1]).read_text(encoding="utf-8"))
            self.assertEqual(request["files"], ["module.py"])
            self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
            self.assertEqual((Path(request["root"]) / "module.py").read_bytes(), (self.repo / "module.py").read_bytes())
            return subprocess.CompletedProcess(
                argv, 0, json.dumps({"version": "fixture-1", "map": "module.py:\n def hello()\n"}), ""
            )
        return self.real_run(argv, **kwargs)

    def build(self):
        with patch.object(repo_map.subprocess, "run", side_effect=self.worker):
            return repo_map.build(self.repo, sys.executable, ["."], 1024)

    def cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return repo_map.main([*args, "--repo", str(self.repo)])

    def test_build_private_unchanged_reuse_and_stale_refusal(self):
        before = self.git("status", "--porcelain")
        self.build()
        self.assertEqual(self.git("status", "--porcelain"), before)
        self.assertEqual(self.git("ls-files", "--", repo_map.CACHE), b"")
        self.assertEqual(self.cli("show"), 0)
        self.assertTrue(self.build()["reused"])
        self.assertEqual(self.calls, 1)
        (self.repo / "module.py").write_text("def goodbye(): pass\n", encoding="utf-8")
        self.assertEqual(self.cli("show"), 1)
        self.build()
        self.assertEqual(self.calls, 2)
        (self.repo / "module.py").unlink()
        self.assertEqual(self.cli("show"), 1)

    def test_export_restore_and_tamper_refusal(self):
        self.build()
        bundle = self.root / "backup.json"
        self.assertEqual(self.cli("export", "--out", str(bundle)), 0)
        self.assertEqual(self.cli("export", "--out", str(bundle)), 1)
        self.assertEqual(self.cli("restore", "--from", str(bundle)), 0)
        clone = self.root / "clone"
        self.real_run(["git", "clone", "-q", str(self.repo), str(clone)], check=True)
        self.assertEqual(repo_map.main(["restore", "--repo", str(clone), "--from", str(bundle)]), 0)
        altered = json.loads(bundle.read_text(encoding="utf-8"))
        altered["map"] += "tamper"
        bundle.write_text(json.dumps(altered), encoding="utf-8")
        self.assertEqual(self.cli("restore", "--from", str(bundle)), 1)

    def test_dry_run_never_creates_cache_or_exclude(self):
        exclude = self.repo / ".git/info/exclude"
        before = exclude.read_bytes()
        self.assertEqual(self.cli("build", "--dry-run"), 0)
        self.assertEqual(exclude.read_bytes(), before)
        self.assertFalse((self.repo / repo_map.CACHE).exists())

    def test_scope_and_ignored_files(self):
        (self.repo / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
        (self.repo / "secret.txt").write_text("private", encoding="utf-8")
        self.assertEqual(list(repo_map.inventory(self.repo, ["module.py"])), ["module.py"])
        self.assertNotIn("secret.txt", repo_map.inventory(self.repo, ["."]))
        with self.assertRaises(ValueError):
            repo_map.inventory(self.repo, ["../outside"])

    def test_tracked_cache_refused(self):
        target = self.repo / repo_map.CACHE / "current.json"
        target.parent.mkdir(parents=True)
        target.write_text("{}", encoding="utf-8")
        self.git("add", str(target.relative_to(self.repo)))
        with self.assertRaisesRegex(ValueError, "already tracked"):
            self.build()

    def test_export_redacts_and_refuses_repository_destination(self):
        self.build()
        path = self.repo / repo_map.CACHE / "current.json"
        data = repo_map.read(self.repo)
        data["map"] = "password = example-sensitive-value\n"
        data["map_sha256"] = repo_map.digest(data["map"].encode())
        repo_map.write(path, data)
        bundle = self.root / "redacted.json"
        self.assertEqual(self.cli("export", "--out", str(bundle)), 0)
        self.assertNotIn("example-sensitive-value", bundle.read_text(encoding="utf-8"))
        self.assertEqual(self.cli("export", "--out", str(self.repo / "leak.json")), 1)

    def test_failed_worker_writes_no_current_map(self):
        with patch.object(repo_map.subprocess, "run", side_effect=self.worker):
            with patch.object(repo_map, "inventory", side_effect=[{"module.py": "wrong"}]):
                with self.assertRaisesRegex(ValueError, "Source changed"):
                    repo_map.build(self.repo, sys.executable, ["."], 1024)
        self.assertFalse((self.repo / repo_map.CACHE / "current.json").exists())

    def test_restore_dry_run_and_source_mismatch(self):
        self.build()
        bundle = self.root / "backup.json"
        self.assertEqual(self.cli("export", "--out", str(bundle)), 0)
        before = (self.repo / repo_map.CACHE / "current.json").read_bytes()
        self.assertEqual(self.cli("restore", "--from", str(bundle), "--dry-run"), 0)
        self.assertEqual((self.repo / repo_map.CACHE / "current.json").read_bytes(), before)
        (self.repo / "new.py").write_text("def new(): pass\n", encoding="utf-8")
        self.assertEqual(self.cli("restore", "--from", str(bundle)), 1)
        self.assertEqual((self.repo / repo_map.CACHE / "current.json").read_bytes(), before)

    def test_budget_change_requires_regeneration(self):
        self.build()
        with patch.object(repo_map.subprocess, "run", side_effect=self.worker):
            repo_map.build(self.repo, sys.executable, ["."], 2048)
        self.assertEqual(self.calls, 2)

    def test_invalid_budget_and_missing_dependency(self):
        self.assertEqual(self.cli("build", "--budget", "0"), 1)
        self.assertEqual(self.cli("build", "--python", str(self.root / "missing-python")), 1)
        self.assertFalse((self.repo / repo_map.CACHE / "current.json").exists())
