"""Version policy and real Git publication in disposable local repositories."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class PublishVersionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "work"
        self.repo.mkdir()
        self.env = os.environ | {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_ACTOR": "maintainer",
            "CBSETUP_ASSOCIATED_PR": "true",
        }
        self.env.pop("GITHUB_OUTPUT", None)
        (self.repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        (self.repo / "scripts").mkdir()
        for name in ("version.py", "publish_version.py", "repository_release.py"):
            shutil.copyfile(ROOT / "scripts" / name, self.repo / "scripts" / name)
        (self.repo / "pyproject.toml").write_text('[project]\nname = "fixture"\nversion = "1.1.0"\n', encoding="utf-8")
        shutil.copyfile(ROOT / "upstream.lock.json", self.repo / "upstream.lock.json")
        pin = json.loads((self.repo / "upstream.lock.json").read_text(encoding="utf-8"))
        pin["package_version"] = "1.1.0"
        (self.repo / "upstream.lock.json").write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
        self.git("init", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.base = self.git("rev-parse", "HEAD")
        (self.repo / "README.md").write_text("A merged change\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "squashed PR")
        self.source = self.git("rev-parse", "HEAD")
        self.env["GITHUB_SHA"] = self.source
        self.remote = self.root / "remote.git"
        self.git("init", "--bare", str(self.remote))
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "origin", "main")

    def command(self, *args, good=True):
        result = subprocess.run(
            args, cwd=self.repo, env=self.env, text=True, encoding="utf-8", capture_output=True, timeout=30
        )
        if good:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return (result.stdout + (result.stderr if not good else "")).strip()

    def git(self, *args):
        return self.command("git", *args)

    def script(self, *args, good=True):
        return self.command(sys.executable, "scripts/version.py", *args, good=good)

    def publish(self, good=True):
        return self.command(
            sys.executable,
            "scripts/publish_version.py",
            "--source",
            self.source,
            "--trunk",
            "main",
            *(["--merged"] if self.env["CBSETUP_ASSOCIATED_PR"] == "true" else []),
            good=good,
        )

    def test_patch_atomic_publication_and_rerun(self):
        old = json.loads((self.repo / "upstream.lock.json").read_text(encoding="utf-8"))
        self.assertIn('"status": "published"', self.publish())
        self.assertEqual(self.git("rev-parse", "v1.1.1^{}"), self.git("rev-parse", "HEAD"))
        self.assertEqual(self.git("cat-file", "-t", "v1.1.1"), "tag")
        new = json.loads((self.repo / "upstream.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(new, old | {"package_version": "1.1.1"})
        self.assertEqual(self.git("rev-parse", "HEAD^"), self.source)
        self.assertIn(self.git("rev-parse", "HEAD"), self.git("ls-remote", "origin", "refs/heads/main"))
        self.git("checkout", "--detach", self.source)
        self.assertIn('"status": "superseded"', self.publish())

    def test_superseded_run_does_not_version_new_code(self):
        self.git("commit", "--allow-empty", "-m", "newer untested change")
        newer = self.git("rev-parse", "HEAD")
        self.git("push", "origin", "main")
        self.git("checkout", "--detach", self.source)
        self.assertIn('"status": "superseded"', self.publish())
        self.assertEqual(self.git("tag", "--list"), "")
        self.assertIn(newer, self.git("ls-remote", "origin", "main"))

    def test_tag_collision_cannot_partially_push_version_commit(self):
        self.git("tag", "v1.1.1", self.base)
        self.git("push", "origin", "v1.1.1")
        self.assertIn("already belongs", self.publish(good=False))
        self.assertIn(self.source, self.git("ls-remote", "origin", "main"))
        self.assertEqual(self.git("rev-parse", "v1.1.1"), self.base)

    def test_rejected_tag_push_does_not_update_remote_branch(self):
        # Git executes update hooks with its shell, including Git for Windows.
        hook = self.remote / "hooks" / "update"
        hook.write_text('#!/bin/sh\ncase "$1" in refs/tags/*) exit 1 ;; esac\nexit 0\n', encoding="utf-8")
        hook.chmod(0o755)
        self.assertIn("hook declined", self.publish(good=False))
        self.assertIn(self.source, self.git("ls-remote", "origin", "main"))
        self.assertEqual(self.git("ls-remote", "origin", "refs/tags/v1.1.1"), "")

    def test_manual_version_dry_run_monotonicity_and_pr_guard(self):
        self.script("minor", "--dry-run")
        self.assertEqual(self.script("current", "--plain"), "1.1.0")
        self.script("set", "1.0.0", good=False)
        self.script("minor")
        self.script("tag", good=False)
        self.script("check-pr", "--base-ref", self.base, good=False)
        self.git("add", ".")
        self.git("commit", "-m", "select minor release")
        self.source = self.git("rev-parse", "HEAD")
        self.env.update(GITHUB_SHA=self.source, CBSETUP_ASSOCIATED_PR="false")
        self.git("push", "origin", "main")
        self.publish()
        self.assertEqual(self.git("rev-parse", "HEAD"), self.source)
        self.assertEqual(self.git("rev-parse", "v1.2.0^{}"), self.source)
        self.script("tag")  # idempotent

    def test_wrong_source_and_unsynchronized_metadata_fail(self):
        self.env["GITHUB_SHA"] = self.base
        self.publish(good=False)
        (self.repo / "pyproject.toml").write_text('[project]\nversion = "1.2.0"\n', encoding="utf-8")
        self.script("check", good=False)

    def test_pr_comparison_uses_merge_base_not_newer_main_version(self):
        self.git("checkout", "-b", "feature", self.source)
        self.git("checkout", "main")
        self.script("patch")
        self.git("add", ".")
        self.git("commit", "-m", "main version advance")
        self.git("checkout", "feature")
        self.script("check-pr", "--base-ref", "main")

    def test_non_main_trunk_and_publisher_json(self):
        self.git("branch", "-m", "release/next")
        self.git("push", "origin", "release/next")
        output = self.command(
            sys.executable, "scripts/publish_version.py", "--source", self.source, "--trunk", "release/next", "--merged"
        )
        result = json.loads(output)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["source_commit"], self.source)
        self.assertIn(result["version_commit"], self.git("ls-remote", "origin", "refs/heads/release/next"))
        self.assertIn(self.source, self.git("ls-remote", "origin", "refs/heads/main"))

    def test_release_identity_and_disabled_publication(self):
        self.publish()
        result = json.loads(self.script("classify-release", "--tag", "v1.1.1"))
        self.assertIs(result["publish"], False)
        self.assertEqual(result["schema_version"], 1)
        self.script("classify-release", "--tag", "v9.0.0", good=False)
        self.git("checkout", "--detach", self.source)
        self.script("classify-release", "--tag", "v1.1.1", good=False)

    def test_classifier_and_current_json_outputs(self):
        result = json.loads(self.script("classify-ci", "--merged"))
        self.assertEqual(result["mode"], "patch")
        self.assertEqual(result["version"], "1.1.1")
        self.assertEqual(result["tag"], "v1.1.1")
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["source_commit"], self.source)
        self.assertEqual(json.loads(self.script("current", "--json")), {"version": "1.1.0"})
        output = self.root / "outputs"
        self.env["GITHUB_OUTPUT"] = str(output)
        self.script("classify-ci", "--merged")
        self.assertFalse(output.exists())
        self.script("classify-ci", "--merged", "--github-output")
        self.assertIn("mode=patch", output.read_text(encoding="utf-8"))
