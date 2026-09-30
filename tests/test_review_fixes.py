"""Failure and reuse regressions for the structural review fixes."""

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from codebase_agent_setup import cli
from codebase_agent_setup import install_transaction as transaction
from codebase_agent_setup import toolchains
from project.ai_workflow.tools import knowledge_backend as kb
from project.ai_workflow.tools import repo_bootstrap as bootstrap


class ReviewFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.source = self.root / "source"
        self.source.write_text("new content", encoding="utf-8")

    def test_failed_atomic_copy_preserves_original_and_cleans_temp(self):
        target = self.repo / "file"
        target.write_text("authored", encoding="utf-8")

        def fail(source, temporary):
            temporary.write(b"partial")
            raise OSError("disk full")

        with patch.object(transaction.shutil, "copyfileobj", side_effect=fail):
            with self.assertRaises(OSError):
                transaction.atomic_copy(self.source, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "authored")
        self.assertEqual(list(self.repo.iterdir()), [target])

    def test_failed_multi_file_write_rolls_back_and_retry_succeeds(self):
        target = self.repo / "existing"
        target.write_text("old content", encoding="utf-8")
        target.chmod(0o755)
        original_mode = stat.S_IMODE(target.stat().st_mode)
        original = transaction.atomic_copy

        def fail(source, destination):
            if destination == self.repo / "new":
                raise OSError("disk full")
            return original(source, destination)

        writes = {"existing": self.source, "new": self.source}
        with patch.object(transaction, "atomic_copy", side_effect=fail):
            with self.assertRaises(OSError):
                transaction.apply_writes(self.repo, writes)
        self.assertEqual(target.read_text(encoding="utf-8"), "old content")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), original_mode)
        self.assertFalse((self.repo / "new").exists())
        self.assertFalse((self.repo / transaction.JOURNAL).exists())
        transaction.apply_writes(self.repo, writes)
        self.assertEqual(target.read_text(encoding="utf-8"), "new content")

    def interrupt_transaction(self):
        (self.repo / "existing").write_text("old", encoding="utf-8")
        original = transaction.atomic_copy

        def interrupt(source, destination):
            if destination == self.repo / "new":
                raise KeyboardInterrupt()
            return original(source, destination)

        with patch.object(transaction, "atomic_copy", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                transaction.apply_writes(self.repo, {"existing": self.source, "new": self.source})

    def test_interrupted_transaction_requires_apply_and_recovers(self):
        self.interrupt_transaction()
        with self.assertRaisesRegex(RuntimeError, "--apply"):
            transaction.recover(self.repo)
        with patch.object(transaction.os, "kill", side_effect=AssertionError("PID probing forbidden")):
            transaction.recover(self.repo, apply=True)
        self.assertEqual((self.repo / "existing").read_text(encoding="utf-8"), "old")
        self.assertFalse((self.repo / transaction.JOURNAL).exists())

    def test_recovery_preserves_post_interruption_edits(self):
        self.interrupt_transaction()
        target = self.repo / "existing"
        target.write_text("authored after interruption", encoding="utf-8")
        with patch.object(transaction.os, "kill", side_effect=AssertionError("PID probing forbidden")):
            with self.assertRaisesRegex(RuntimeError, "edited file"):
                transaction.recover(self.repo, apply=True)
        self.assertEqual(target.read_text(encoding="utf-8"), "authored after interruption")
        self.assertTrue((self.repo / transaction.JOURNAL).exists())

    def test_recovery_refuses_live_owner(self):
        self.interrupt_transaction()
        with transaction.installation_lock(self.repo):
            with self.assertRaisesRegex(RuntimeError, "Another installer"):
                transaction.recover(self.repo, apply=True)

    def test_completed_transaction_cleanup_does_not_restore_old_files(self):
        self.interrupt_transaction()
        journal = self.repo / transaction.JOURNAL
        manifest = json.loads((journal / "manifest.json").read_text(encoding="utf-8"))
        transaction.write_manifest(journal, manifest["entries"], "committed")
        (journal / "0.original").unlink()
        with patch.object(transaction.os, "kill", side_effect=AssertionError("PID probing forbidden")):
            transaction.recover(self.repo, apply=True)
        self.assertEqual((self.repo / "existing").read_text(encoding="utf-8"), "new content")
        self.assertFalse(journal.exists())

    def test_toolchain_timeout_terminates_real_probe(self):
        with patch.dict(os.environ, {"CBSETUP_PROBE_TIMEOUT": "0.1"}):
            with self.assertRaisesRegex(toolchains.ToolchainError, "timed out"):
                toolchains.run([sys.executable, "-c", "import time; time.sleep(30)"], probe=True)

    def test_invalid_timeout_values_rejected(self):
        for value in ("0", "-1", "nan", "inf", "invalid"):
            with self.subTest(value=value), patch.dict(os.environ, {"CBSETUP_COMMAND_TIMEOUT": value}):
                with self.assertRaises(toolchains.ToolchainError):
                    toolchains.command_timeout()

    def test_callable_cli_leaves_process_state_unchanged(self):
        before = (list(sys.argv), list(sys.path), dict(os.environ))
        with contextlib.redirect_stdout(io.StringIO()):
            for command in ("configure", "knowledge", "bootstrap", "install"):
                with self.assertRaises(SystemExit) as result:
                    cli.main([command, "--help"])
                self.assertEqual(result.exception.code, 0)
        self.assertEqual(before, (list(sys.argv), list(sys.path), dict(os.environ)))

    def test_bootstrap_config_validation_reports_file_and_field(self):
        baseline = json.loads((ROOT / "project/ai_workflow/bootstrap.json").read_text(encoding="utf-8"))
        cases = [([], "bootstrap"), ({"schema_version": "1.0"}, "state_directory")]
        for section, key, value in [
            ("analysis", "file_index_file", "../escape"),
            ("semantic_index", "create_when_missing", "yes"),
            ("branch_selection", "include_regex", ["["]),
            ("semantic_index", "base_remote_namespace", "{unknown}"),
        ]:
            config = json.loads(json.dumps(baseline))
            config[section][key] = value
            cases.append((config, section + "." + key))
        path = self.repo / "bootstrap.json"
        for value, field in cases:
            with self.subTest(field=field):
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(bootstrap.BootstrapError) as result:
                    bootstrap.load_config(path)
                self.assertIn(str(path), str(result.exception))
                self.assertIn(field, str(result.exception))

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True, encoding="utf-8"
        ).stdout.strip()

    def test_incremental_reads_only_changed_and_previously_dirty_files(self):
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        for number in range(100):
            (self.repo / f"{number}.py").write_text("old", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        config = bootstrap.load_config(ROOT / "project/ai_workflow/bootstrap.json")
        head = self.git("rev-parse", "HEAD")
        previous = bootstrap.build_candidate_index(self.repo, config, "full_analysis", None, [], head, "first")
        (self.repo / "1.py").write_text("dirty", encoding="utf-8")
        with patch.object(bootstrap, "file_record", wraps=bootstrap.file_record) as read:
            changed = bootstrap.build_candidate_index(
                self.repo, config, "incremental_analysis", previous, [{"path": "1.py", "status": "M"}], head, "second"
            )
        self.assertEqual(read.call_count, 1)
        self.git("restore", "1.py")
        with patch.object(bootstrap, "file_record", wraps=bootstrap.file_record) as read:
            restored = bootstrap.build_candidate_index(
                self.repo, config, "incremental_analysis", changed, [], head, "third"
            )
        self.assertEqual(read.call_count, 1)
        self.assertEqual(restored["files"], previous["files"])
        del previous["dirty_paths"]
        with patch.object(bootstrap, "file_record", wraps=bootstrap.file_record) as read:
            bootstrap.build_candidate_index(self.repo, config, "incremental_analysis", previous, [], head, "fourth")
        self.assertEqual(read.call_count, 100)

    def test_incremental_rename_deletion_and_symlink_match_full_inventory(self):
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        (self.repo / "old.py").write_text("original", encoding="utf-8")
        (self.repo / "deleted.py").write_text("delete me", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        config = bootstrap.load_config(ROOT / "project/ai_workflow/bootstrap.json")
        head = self.git("rev-parse", "HEAD")
        previous = bootstrap.build_candidate_index(self.repo, config, "full_analysis", None, [], head, "first")
        self.git("mv", "old.py", "renamed.py")
        self.git("rm", "deleted.py")
        self.git("commit", "-m", "rename and delete")
        if os.name == "posix":
            (self.repo / "link.py").symlink_to("renamed.py")
        changes = bootstrap.committed_changes(self.repo, head)
        head = self.git("rev-parse", "HEAD")
        incremental = bootstrap.build_candidate_index(
            self.repo, config, "incremental_analysis", previous, changes, head, "current"
        )
        full = bootstrap.build_candidate_index(self.repo, config, "full_analysis", None, [], head, "current")
        self.assertEqual(incremental, full)
        paths = {item["path"] for item in incremental["files"]}
        self.assertNotIn("old.py", paths)
        self.assertNotIn("deleted.py", paths)
        self.assertIn("renamed.py", paths)

    def test_discovery_continues_after_timed_out_candidate(self):
        settings = {"tooling": {"env_dir": str(self.root), "mode": "venv"}}
        first = self.root / "first"
        second = self.root / "second"
        first.touch()
        second.touch()
        with (
            patch.object(toolchains, "environment_path", return_value=self.root),
            patch.object(toolchains, "cli_in", return_value=first),
            patch.object(toolchains.sysconfig, "get_path", return_value=str(self.root)),
            patch.object(toolchains.os, "get_exec_path", return_value=[str(self.root)]),
            patch.object(toolchains.shutil, "which", return_value=str(second)),
            patch.object(toolchains, "probe_cli", side_effect=[toolchains.ToolchainError("timed out"), "verified"]),
        ):
            self.assertEqual(toolchains.discover_cli(settings, {}), str(second))

    def test_recovery_checks_all_backups_before_changing_targets(self):
        self.interrupt_transaction()
        journal = self.repo / transaction.JOURNAL
        (journal / "0.original").write_text("corrupt", encoding="utf-8")
        with patch.object(transaction.os, "kill", side_effect=AssertionError("PID probing forbidden")):
            with self.assertRaisesRegex(RuntimeError, "Damaged installation backup"):
                transaction.recover(self.repo, apply=True)
        self.assertEqual((self.repo / "existing").read_text(encoding="utf-8"), "new content")

    def test_backend_state_and_internal_errors_have_actionable_safe_diagnostics(self):
        (self.repo / "codebase-agent-setup.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(kb.SettingsError, "codebase-agent-setup.json: invalid CGC state"):
            kb.state({"data_dir": str(self.repo)})
        output = io.StringIO()
        with (
            patch.object(kb, "context", side_effect=AttributeError("private token")),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(kb.main(["status"]), 2)
        self.assertIn("status failed unexpectedly (AttributeError)", output.getvalue())
        self.assertNotIn("private token", output.getvalue())


class RecoveryProcessTests(unittest.TestCase):
    setUp = ReviewFixTests.setUp

    def test_real_process_death_releases_lock_and_restores_snapshot(self):
        target = self.repo / "existing"
        target.write_text("old", encoding="utf-8")
        program = """
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))
from codebase_agent_setup import install_transaction as t
root, source = (Path(value).resolve() for value in sys.argv[1:])
original = t.atomic_copy
def pause(source, destination):
    original(source, destination)
    if destination == root / 'existing':
        print('written', flush=True)
        time.sleep(30)
t.atomic_copy = pause
t.apply_writes(root, {'existing': source})
"""
        child = subprocess.Popen(
            [sys.executable, "-u", "-c", program, str(self.repo), str(self.source)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            self.assertEqual(child.stdout.readline().strip(), "written")
            with self.assertRaisesRegex(RuntimeError, "Another installer"):
                transaction.recover(self.repo, apply=True)
            child.kill()
            child.communicate(timeout=5)
            transaction.recover(self.repo, apply=True)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)

    def test_partial_retired_cleanup_does_not_block_next_install(self):
        real = transaction.shutil.rmtree

        def fail(path):
            if Path(path).name.startswith("engineering-retired-"):
                (Path(path) / "manifest.json").unlink(missing_ok=True)
                raise OSError("cleanup interrupted")
            return real(path)

        with patch.object(transaction.shutil, "rmtree", side_effect=fail), contextlib.redirect_stderr(io.StringIO()):
            transaction.apply_writes(self.repo, {"existing": self.source})
        self.assertFalse((self.repo / transaction.JOURNAL).exists())
        transaction.apply_writes(self.repo, {"new": self.source})
        self.assertEqual(list((self.repo / ".specify").glob("engineering-retired-*")), [])
        self.assertTrue((self.repo / "new").exists())

    def test_windows_lock_uses_byte_locking_without_process_signals(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        locking = Mock()
        module = SimpleNamespace(locking=locking, LK_NBLCK=2, LK_UNLCK=0)
        with (
            patch.dict(sys.modules, {"msvcrt": module}),
            patch.object(transaction.os, "kill", side_effect=AssertionError),
        ):
            lock, unlock = transaction.lock_functions(SimpleNamespace(fileno=lambda: 7), windows=True)
            lock()
            unlock()
        self.assertEqual([call.args for call in locking.call_args_list], [(7, 2, 1), (7, 0, 1)])


class CommandCancellationTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX signal/session behavior")
    def test_ctrl_c_stops_command_and_descendant_before_returning(self):
        import signal
        import time

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ready = root / "ready"
            done = root / "done"
            worker = (
                "import time; from pathlib import Path; Path("
                + repr(str(ready))
                + ").touch(); time.sleep(1.5); Path("
                + repr(str(done))
                + ").touch()"
            )
            command = (
                "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
                + repr(worker)
                + "]); time.sleep(30)"
            )
            parent = (
                "import sys; from pathlib import Path; sys.path.insert(0, str(Path.cwd() / 'src')); from codebase_agent_setup import toolchains\ntry: toolchains.run([sys.executable,'-c',"
                + repr(command)
                + "])\nexcept KeyboardInterrupt: print('cancelled',flush=True)"
            )
            process = subprocess.Popen(
                [sys.executable, "-u", "-c", parent],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                process.send_signal(signal.SIGINT)
                output, error = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, error)
                self.assertIn("cancelled", output)
                time.sleep(1.7)
                self.assertFalse(done.exists(), "descendant continued writing after cancellation")
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_keyboard_interrupt_cleanup_precedes_propagation(self):
        from unittest.mock import Mock

        process = Mock()
        process.__enter__ = Mock(return_value=process)
        process.__exit__ = Mock(return_value=False)
        process.communicate.side_effect = KeyboardInterrupt()
        with (
            patch.object(toolchains.subprocess, "Popen", return_value=process),
            patch.object(toolchains, "stop_process") as stop,
        ):
            with self.assertRaises(KeyboardInterrupt):
                toolchains.run(["fixture"])
        stop.assert_called_once_with(process)

    def test_local_revision_formats_do_not_relax_upstream_pin_validation(self):
        from project.ai_workflow.tools.knowledge_state import valid_revision

        self.assertTrue(valid_revision("a" * 40, "sha1"))
        self.assertTrue(valid_revision("b" * 64, "sha256"))
        self.assertFalse(valid_revision("b" * 64, "sha1"))
        self.assertFalse(valid_revision("a" * 40, "sha256"))
        self.assertFalse(valid_revision("g" * 64, "sha256"))
        with self.assertRaises(toolchains.ToolchainError):
            toolchains.validate_ref("b" * 64)
