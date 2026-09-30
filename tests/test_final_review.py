"""Regressions for planning preconditions and platform-safe transactions."""

import os
import contextlib
import io
from types import SimpleNamespace
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from codebase_agent_setup import install_transaction as transaction
from codebase_agent_setup import install


class FinalReviewTests(unittest.TestCase):
    def test_installer_passes_planning_snapshot_to_transaction(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            target, stage, payload = base / "repo", base / "stage", base / "payload"
            target.mkdir()
            stage.mkdir()
            (payload / "project").mkdir(parents=True)
            (payload / "legacy_v6_files.json").write_text("{}")
            (target / "managed.txt").write_text("original")
            (stage / "managed.txt").write_text("original")
            apply = transaction.apply_writes

            def edit_before_write(repo, writes, **kwargs):
                (repo / "managed.txt").write_text("authored after planning")
                return apply(repo, writes, **kwargs)

            args = SimpleNamespace(repo=target, apply=True, integration=["codex"], specify=None, migrate_v6=False)
            with (
                patch.object(install, "ROOT", payload),
                patch.object(
                    install,
                    "resolve",
                    return_value={"settings": {"agent": {"integrations": ["codex"]}, "speckit": {"ref": None}}},
                ),
                patch.object(install.toolchains, "resolve_selection", return_value={}),
                patch.object(install.toolchains, "discover_cli", return_value=[]),
                patch.object(install.toolchains, "stage_package", return_value=(stage, {})),
                patch.object(transaction, "apply_writes", side_effect=edit_before_write),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                with self.assertRaisesRegex(RuntimeError, "after installation planning"):
                    install.install(args)
            self.assertEqual((target / "managed.txt").read_text(), "authored after planning")

    def test_changed_and_newly_created_destinations_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            source.write_text("incoming", encoding="utf-8")
            target = root / "repo"
            target.mkdir()
            for expected in (None, "0" * 64):
                (target / "authored").write_text("user edit", encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "after installation planning"):
                    transaction.apply_writes(
                        target, {"new": source, "authored": source}, expected={"authored": expected}
                    )
                self.assertEqual((target / "authored").read_text(), "user edit")
                self.assertFalse((target / "new").exists())
                self.assertFalse((target / transaction.JOURNAL).exists())

    def test_copy_flushes_a_writable_handle_and_preserves_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target = root / "source", root / "target"
            source.write_bytes(b"payload")
            real_sync = os.fsync

            def writable_sync(fd):
                os.write(fd, b"")  # A read-only descriptor fails on every platform.
                real_sync(fd)

            with patch.object(transaction.os, "fsync", side_effect=writable_sync):
                transaction.atomic_copy(source, target)
            self.assertEqual(target.read_bytes(), b"payload")

    def test_direct_version_script_ignores_unrelated_scripts_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "scripts/__init__.py").write_text("", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/version.py"), "current", "--plain"],
                cwd=root,
                env=os.environ | {"PYTHONPATH": str(root)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertRegex(result.stdout.strip(), r"^\d+\.\d+\.\d+$")


class AliasedRecoveryTests(unittest.TestCase):
    def test_recovery_faults_trigger_through_aliased_temp_directory(self):
        from test_review_fixes import ReviewFixTests, RecoveryProcessTests

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            actual = root / "actual"
            actual.mkdir()
            alias = root / "alias"
            try:
                alias.symlink_to(actual, target_is_directory=True)
            except OSError:
                # Windows commonly disallows symlinks; a lexical alias still exercises
                # normalization there. The normal platform suite covers native temp paths.
                alias = actual / ".." / "actual"
            tests = [
                ReviewFixTests(name)
                for name in (
                    "test_failed_multi_file_write_rolls_back_and_retry_succeeds",
                    "test_interrupted_transaction_requires_apply_and_recovers",
                    "test_completed_transaction_cleanup_does_not_restore_old_files",
                    "test_recovery_preserves_post_interruption_edits",
                    "test_recovery_checks_all_backups_before_changing_targets",
                    "test_recovery_refuses_live_owner",
                )
            ]
            tests.append(RecoveryProcessTests("test_real_process_death_releases_lock_and_restores_snapshot"))
            output = io.StringIO()
            with patch.object(tempfile, "tempdir", str(alias)):
                result = unittest.TextTestRunner(stream=output).run(unittest.TestSuite(tests))
            self.assertTrue(result.wasSuccessful(), output.getvalue())
