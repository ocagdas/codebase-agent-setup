"""Indexer-agnostic repository knowledge: declared commands, per-file content addressing, layered lookup.

CAS ships no indexer. Every test configures a real command and checks that the wrapper runs it, keys its output by
the content of each file, and refuses the unsafe cases. The property that matters most: editing one file must
re-index one file.
"""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "project/ai_workflow/tools"))
import knowledge

# A declared "indexer": mirrors each input path under {out} and records which files it was asked to index.
# Real indexers are wrapped by a script like this one.
INDEXER = (
    "import json,sys,pathlib;"
    "out=pathlib.Path(sys.argv[1]);"
    "log=pathlib.Path(sys.argv[2]);"
    "paths=sys.argv[3:];"
    "log.parent.mkdir(parents=True,exist_ok=True);"
    "log.open('a').write(json.dumps(sorted(paths))+chr(10));"
    "[ (out/p).parent.mkdir(parents=True,exist_ok=True) or (out/p).write_text(json.dumps({'file':p})) for p in paths ]"
)
# Same, but reads its file list from a response file, the way a real tool handles thousands of paths.
INDEXER_FROM_FILE = (
    "import json,sys,pathlib;"
    "out=pathlib.Path(sys.argv[1]);"
    "paths=pathlib.Path(sys.argv[2]).read_text().split(chr(10));"
    "paths=[p for p in paths if p];"
    "[ (out/p).parent.mkdir(parents=True,exist_ok=True) or (out/p).write_text(json.dumps({'file':p})) for p in paths ]"
)


class KnowledgeHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve() / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "docs").mkdir()
        for name in ("a", "b", "c"):
            (self.repo / f"src/{name}.py").write_text(f"def {name}(): pass\n", encoding="utf-8")
        (self.repo / "docs/guide.md").write_text("# guide\n", encoding="utf-8")
        # The installer gitignores the cache; mirror that so fixtures match a real repository.
        (self.repo / ".gitignore").write_text(".ai_cache/\n", encoding="utf-8")
        self.log = Path(self.temp.name) / "invocations.log"
        self.git("init", "-b", "main")
        # A shared store is addressed by repository identity, which must match across clones.
        self.git("remote", "add", "origin", "https://example.invalid/team/repo.git")
        self.git("add", ".")
        self.git("commit", "-m", "initial")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "T",
                "GIT_AUTHOR_EMAIL": "t@example.invalid",
                "GIT_COMMITTER_NAME": "T",
                "GIT_COMMITTER_EMAIL": "t@example.invalid",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            },
        ).stdout.strip()

    def indexer(self, **overrides):
        spec = {
            "id": "fake",
            "version": "1",
            "kind": "symbols",
            "granularity": "file",
            "paths": ["src"],
            "build_command": [sys.executable, "-c", INDEXER, "{out}", str(self.log), "{files}"],
            "query_command": [sys.executable, "-c", "import sys;print(sys.argv[1:])", "{artifacts}"],
        }
        spec.update(overrides)
        return spec

    def config(self, **overrides):
        settings = {
            "cache_root": ".ai_cache/knowledge",
            "base_refs": ["main"],
            "indexers": [self.indexer()],
            "store": None,
        }
        settings.update(overrides)
        return knowledge.Config.from_settings(self.repo, settings)

    def invocations(self, cfg=None):
        if not self.log.is_file():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]


class ScopeTests(KnowledgeHarness):
    def test_the_scope_lists_one_content_hash_per_file_from_git(self):
        cfg = self.config()
        files = knowledge.scope_files(self.repo, cfg.indexers[0], "base", cfg)
        self.assertEqual(sorted(files), ["src/a.py", "src/b.py", "src/c.py"])
        self.assertEqual(files["src/a.py"], self.git("rev-parse", "HEAD:src/a.py"))

    def test_paths_outside_the_configured_scope_are_not_listed(self):
        self.assertNotIn(
            "docs/guide.md", knowledge.scope_files(self.repo, self.config().indexers[0], "base", self.config())
        )

    def test_an_uncommitted_edit_changes_only_that_file_and_only_in_the_worktree_layer(self):
        cfg = self.config()
        base = knowledge.scope_files(self.repo, cfg.indexers[0], "base", cfg)
        (self.repo / "src/a.py").write_text("def a(): return 1\n", encoding="utf-8")
        worktree = knowledge.scope_files(self.repo, cfg.indexers[0], "worktree", cfg)
        self.assertEqual(knowledge.scope_files(self.repo, cfg.indexers[0], "base", cfg), base)
        self.assertNotEqual(worktree["src/a.py"], base["src/a.py"])
        self.assertEqual(worktree["src/b.py"], base["src/b.py"])

    def test_an_untracked_file_is_seen_by_the_worktree_layer(self):
        cfg = self.config()
        (self.repo / "src/new.py").write_text("def n(): pass\n", encoding="utf-8")
        self.assertIn("src/new.py", knowledge.scope_files(self.repo, cfg.indexers[0], "worktree", cfg))
        self.assertNotIn("src/new.py", knowledge.scope_files(self.repo, cfg.indexers[0], "base", cfg))

    def test_a_deleted_file_is_absent_from_the_worktree_layer(self):
        cfg = self.config()
        (self.repo / "src/b.py").unlink()
        self.assertNotIn("src/b.py", knowledge.scope_files(self.repo, cfg.indexers[0], "worktree", cfg))

    def test_a_missing_configured_path_is_an_error_not_a_silent_empty_scope(self):
        cfg = self.config(indexers=[self.indexer(paths=["does-not-exist"])])
        with self.assertRaisesRegex(knowledge.KnowledgeError, "does-not-exist"):
            knowledge.scope_files(self.repo, cfg.indexers[0], "base", cfg)


class KeyTests(KnowledgeHarness):
    def test_the_same_content_yields_the_same_key_in_a_different_clone_and_path(self):
        """The property the design rests on: clones share artifacts with no rebasing."""
        cfg = self.config()
        mine = knowledge.scope_files(self.repo, cfg.indexers[0], "base", cfg)
        clone = Path(self.temp.name) / "a totally different path"
        subprocess.run(["git", "clone", "-q", str(self.repo), str(clone)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(clone), "remote", "set-url", "origin", "https://example.invalid/team/repo.git"],
            check=True,
            capture_output=True,
        )
        other = knowledge.Config.from_settings(clone, cfg.raw)
        theirs = knowledge.scope_files(clone, other.indexers[0], "base", other)
        self.assertEqual(
            knowledge.file_key(cfg.indexers[0], mine["src/a.py"]),
            knowledge.file_key(other.indexers[0], theirs["src/a.py"]),
        )

    def test_a_new_indexer_version_invalidates_every_key(self):
        cfg = self.config()
        blob = knowledge.scope_files(self.repo, cfg.indexers[0], "base", cfg)["src/a.py"]
        bumped = self.config(indexers=[self.indexer(version="2")])
        self.assertNotEqual(knowledge.file_key(bumped.indexers[0], blob), knowledge.file_key(cfg.indexers[0], blob))

    def test_different_files_get_different_keys_and_identical_content_shares_one(self):
        cfg = self.config()
        (self.repo / "src/twin.py").write_text((self.repo / "src/a.py").read_text(encoding="utf-8"), encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "twin")
        files = knowledge.scope_files(self.repo, cfg.indexers[0], "base", cfg)
        key = lambda path: knowledge.file_key(cfg.indexers[0], files[path])  # noqa: E731
        self.assertNotEqual(key("src/a.py"), key("src/b.py"))
        self.assertEqual(key("src/a.py"), key("src/twin.py"))


class BuildTests(KnowledgeHarness):
    def test_preview_runs_nothing_and_writes_nothing(self):
        cfg = self.config()
        plan = knowledge.build(self.repo, cfg, "base", apply=False)
        self.assertFalse(plan["apply"])
        self.assertEqual(plan["indexers"][0]["to_index"], ["src/a.py", "src/b.py", "src/c.py"])
        self.assertFalse((self.repo / ".ai_cache").exists())

    def test_apply_indexes_every_file_and_stores_one_artifact_each(self):
        cfg = self.config()
        result = knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(result["indexers"][0]["indexed"], ["src/a.py", "src/b.py", "src/c.py"])
        manifest = knowledge.layer_manifest(self.repo, cfg, cfg.indexers[0], "base")
        self.assertEqual(sorted(manifest), ["src/a.py", "src/b.py", "src/c.py"])
        for path, key in manifest.items():
            stored = knowledge.artifact_path(self.repo, cfg, key) / path
            self.assertTrue(stored.is_file(), path)
            self.assertEqual(json.loads(stored.read_text(encoding="utf-8"))["file"], path)

    def test_editing_one_file_reindexes_exactly_that_file(self):
        """The whole point. A single change must not invalidate the cache."""
        cfg = self.config()
        knowledge.build(self.repo, cfg, "base", apply=True)
        (self.repo / "src/b.py").write_text("def b(): return 99\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "one file")
        result = knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(result["indexers"][0]["indexed"], ["src/b.py"])
        self.assertEqual(sorted(result["indexers"][0]["reused"]), ["src/a.py", "src/c.py"])
        self.assertEqual(self.invocations(cfg)[-1], ["src/b.py"])

    def test_rebuilding_unchanged_content_runs_the_indexer_not_at_all(self):
        cfg = self.config()
        knowledge.build(self.repo, cfg, "base", apply=True)
        before = len(self.invocations(cfg))
        again = knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(again["indexers"][0]["indexed"], [])
        self.assertEqual(len(self.invocations(cfg)), before)

    def test_a_trunk_merge_only_reindexes_the_files_it_actually_changed(self):
        cfg = self.config()
        knowledge.build(self.repo, cfg, "base", apply=True)
        self.git("checkout", "-q", "-b", "feature")
        (self.repo / "src/c.py").write_text("def c(): return 'feature'\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "feature work")
        result = knowledge.build(self.repo, cfg, "branch", apply=True)
        self.assertEqual(result["indexers"][0]["indexed"], ["src/c.py"])
        self.assertEqual(sorted(result["indexers"][0]["reused"]), ["src/a.py", "src/b.py"])

    def test_the_manifest_records_provenance_for_every_artifact(self):
        cfg = self.config()
        knowledge.build(self.repo, cfg, "base", apply=True)
        entry = knowledge.read_manifest(self.repo, cfg)["artifacts"]
        one = next(iter(entry.values()))
        for field in ("indexer", "indexer_version", "kind", "path", "blob", "created"):
            self.assertIn(field, one)

    def test_a_failing_indexer_is_reported_and_stores_no_artifact(self):
        cfg = self.config(indexers=[self.indexer(build_command=[sys.executable, "-c", "import sys;sys.exit(3)"])])
        result = knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertTrue(result["failed"])
        self.assertIn("exit 3", result["failed"][0]["error"])
        self.assertEqual(knowledge.read_manifest(self.repo, cfg)["artifacts"], {})

    def test_a_file_the_indexer_skipped_is_reported_rather_than_recorded_as_done(self):
        skipping = (
            "import json,sys,pathlib;out=pathlib.Path(sys.argv[1]);"
            "paths=[p for p in sys.argv[2:] if 'b.py' not in p];"
            "[ (out/p).parent.mkdir(parents=True,exist_ok=True) or (out/p).write_text('{}') for p in paths ]"
        )
        cfg = self.config(indexers=[self.indexer(build_command=[sys.executable, "-c", skipping, "{out}", "{files}"])])
        result = knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(result["indexers"][0]["no_output"], ["src/b.py"])
        self.assertNotIn("src/b.py", knowledge.layer_manifest(self.repo, cfg, cfg.indexers[0], "base"))

    def test_a_response_file_carries_the_path_list_for_large_scopes(self):
        cfg = self.config(
            indexers=[self.indexer(build_command=[sys.executable, "-c", INDEXER_FROM_FILE, "{out}", "{files_from}"])]
        )
        result = knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(result["indexers"][0]["indexed"], ["src/a.py", "src/b.py", "src/c.py"])

    def test_a_command_is_a_list_never_a_shell_string(self):
        with self.assertRaisesRegex(knowledge.KnowledgeError, "list"):
            self.config(indexers=[self.indexer(build_command="ctags -R src")])

    def test_a_path_with_shell_metacharacters_stays_a_literal_argument(self):
        (self.repo / "src/; rm -rf x.py").write_text("def h(): pass\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "awkward name")
        cfg = self.config()
        result = knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(result["failed"], [])
        self.assertIn("src/; rm -rf x.py", result["indexers"][0]["indexed"])
        self.assertTrue((self.repo / "src/; rm -rf x.py").is_file())

    def test_the_base_layer_refuses_to_build_when_no_base_ref_resolves(self):
        cfg = self.config(base_refs=["origin/nope"])
        with self.assertRaisesRegex(knowledge.KnowledgeError, "base"):
            knowledge.build(self.repo, cfg, "base", apply=True)

    def on_a_dev_branch(self):
        """A developer checkout: HEAD has moved past the trunk, so the base layer's commit is not HEAD."""
        self.git("checkout", "-b", "dev/feature")
        (self.repo / "src/a.py").write_text("def a(): return 1\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "on the branch")

    def test_building_a_layer_whose_commit_is_not_head_is_refused_not_silently_wrong(self):
        """The indexers read the working tree, so off-HEAD content would be keyed to blobs the tree does not hold."""
        self.on_a_dev_branch()
        cfg = self.config()
        with self.assertRaisesRegex(knowledge.KnowledgeError, "not checked out"):
            knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(self.invocations(), [])

    def test_the_refusal_names_the_commit_and_how_to_get_it(self):
        self.on_a_dev_branch()
        merge_base = self.git("merge-base", "main", "HEAD")
        with self.assertRaises(knowledge.KnowledgeError) as caught:
            knowledge.build(self.repo, self.config(), "base", apply=True)
        message = str(caught.exception)
        self.assertIn(merge_base[:12], message)
        self.assertIn("base", message)

    def test_a_dry_run_is_refused_too_because_its_plan_would_be_wrong(self):
        self.on_a_dev_branch()
        with self.assertRaisesRegex(knowledge.KnowledgeError, "not checked out"):
            knowledge.build(self.repo, self.config(), "base", apply=False)

    def test_the_branch_and_worktree_layers_still_build_on_a_dev_branch(self):
        """Those layers are measured against HEAD by definition, so the guard must not touch them."""
        self.on_a_dev_branch()
        cfg = self.config()
        for layer in ("branch", "worktree"):
            result = knowledge.build(self.repo, cfg, layer, apply=True)
            self.assertEqual(result["failed"], [])

    def test_the_base_layer_builds_where_its_commit_is_head_which_is_what_ci_does(self):
        """CI checks out the trunk commit itself; there HEAD is the base commit and the build is correct."""
        self.on_a_dev_branch()
        self.git("checkout", "main")
        result = knowledge.build(self.repo, self.config(), "base", apply=True)
        self.assertEqual(result["failed"], [])
        self.assertIn("src/a.py", result["indexers"][0]["indexed"])


class ScopeGranularityTests(KnowledgeHarness):
    """An indexer that must see the whole project keys one artifact, and reports its delta rather than dying."""

    def scoped(self, **overrides):
        return self.indexer(
            granularity="scope",
            kind="scope",
            build_command=[sys.executable, "-c", INDEXER, "{out}", str(self.log), "{paths}"],
            **overrides,
        )

    def test_a_scope_indexer_produces_one_artifact_for_the_whole_scope(self):
        cfg = self.config(indexers=[self.scoped()])
        result = knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(result["indexers"][0]["granularity"], "scope")
        self.assertEqual(len(result["indexers"][0]["indexed"]), 1)

    def test_a_stale_scope_artifact_is_reported_with_the_files_that_moved_not_discarded(self):
        cfg = self.config(indexers=[self.scoped()])
        knowledge.build(self.repo, cfg, "base", apply=True)
        (self.repo / "src/a.py").write_text("def a(): return 1\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "moved")
        row = knowledge.status(self.repo, cfg)["layers"]["base"][0]
        self.assertEqual(row["state"], "stale")
        self.assertEqual(row["changed_since"], ["src/a.py"])
        self.assertTrue(row["artifact"])

    def test_a_file_granularity_indexer_never_reports_a_whole_layer_as_stale(self):
        cfg = self.config()
        knowledge.build(self.repo, cfg, "base", apply=True)
        (self.repo / "src/a.py").write_text("def a(): return 1\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "moved")
        row = knowledge.status(self.repo, cfg)["layers"]["base"][0]
        self.assertEqual(row["state"], "partial")
        self.assertEqual(row["missing"], ["src/a.py"])
        self.assertEqual(row["current"], 2)


class StatusTests(KnowledgeHarness):
    def test_status_reports_what_is_missing_without_running_an_indexer(self):
        cfg = self.config(indexers=[self.indexer(build_command=[sys.executable, "-c", "raise SystemExit(9)"])])
        report = knowledge.status(self.repo, cfg)
        self.assertEqual(report["layers"]["base"][0]["state"], "missing")
        self.assertFalse((self.repo / ".ai_cache").exists())

    def test_status_reports_current_after_a_build(self):
        cfg = self.config()
        knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(knowledge.status(self.repo, cfg)["layers"]["base"][0]["state"], "current")

    def test_status_without_configured_indexers_says_so_rather_than_failing(self):
        self.assertFalse(knowledge.status(self.repo, self.config(indexers=[]))["configured"])


class QueryTests(KnowledgeHarness):
    def test_query_delegates_to_the_declared_command_with_the_resolved_artifacts(self):
        cfg = self.config()
        knowledge.build(self.repo, cfg, "base", apply=True)
        output = knowledge.query(self.repo, cfg, [])
        self.assertIn(".ai_cache", output["stdout"])

    def test_query_resolves_worktree_over_base_for_an_edited_file(self):
        cfg = self.config()
        knowledge.build(self.repo, cfg, "base", apply=True)
        base_key = knowledge.layer_manifest(self.repo, cfg, cfg.indexers[0], "base")["src/a.py"]
        (self.repo / "src/a.py").write_text("def a(): return 1\n", encoding="utf-8")
        knowledge.build(self.repo, cfg, "worktree", apply=True)
        resolved = knowledge.resolve(self.repo, cfg, cfg.indexers[0])
        self.assertNotEqual(resolved["src/a.py"]["key"], base_key)
        self.assertEqual(resolved["src/a.py"]["layer"], "worktree")
        self.assertEqual(resolved["src/b.py"]["layer"], "base")

    def test_query_before_a_build_says_what_to_run_instead_of_failing_obscurely(self):
        with self.assertRaisesRegex(knowledge.KnowledgeError, "build"):
            knowledge.query(self.repo, self.config(), [])


class MultiIndexerQueryTests(KnowledgeHarness):
    """A mixed-language repository must be answerable in every language it declares an indexer for."""

    def setUp(self):
        super().setUp()
        (self.repo / "native").mkdir()
        (self.repo / "native/engine.c").write_text("int engine_init(void) { return 0; }\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "add native sources")
        self.c_log = Path(self.temp.name) / "c-invocations.log"

    def mixed(self):
        """Two indexers over disjoint paths, each reporting which artifact directories it was handed."""
        report = (
            "import sys;print(sys.argv[1] + ' saw ' + str(len([a for a in sys.argv[2].split() if a])) + ' artifacts')"
        )
        python = self.indexer(
            id="py-symbols",
            paths=["src"],
            query_command=[sys.executable, "-c", report, "python", "{artifacts}"],
        )
        native = self.indexer(
            id="c-symbols",
            paths=["native"],
            build_command=[sys.executable, "-c", INDEXER, "{out}", str(self.c_log), "{files}"],
            query_command=[sys.executable, "-c", report, "c", "{artifacts}"],
        )
        self.specs = [python, native]
        return self.config(indexers=[python, native])

    def test_every_configured_indexer_is_consulted_not_only_the_first(self):
        cfg = self.mixed()
        knowledge.build(self.repo, cfg, "base", apply=True)
        result = knowledge.query(self.repo, cfg, [])
        self.assertEqual([r["indexer"] for r in result["results"]], ["py-symbols", "c-symbols"])
        self.assertIn("python saw", result["stdout"])
        self.assertIn("c saw", result["stdout"])

    def test_reversing_the_configured_order_does_not_change_what_is_findable(self):
        """The bug this replaces: whichever indexer was listed first was the only one that could answer."""
        cfg = self.mixed()
        knowledge.build(self.repo, cfg, "base", apply=True)
        forward = knowledge.query(self.repo, cfg, [])
        reversed_cfg = self.config(indexers=list(reversed(self.specs)))
        knowledge.build(self.repo, reversed_cfg, "base", apply=True)
        backward = knowledge.query(self.repo, reversed_cfg, [])
        self.assertEqual(
            sorted(r["indexer"] for r in forward["results"]),
            sorted(r["indexer"] for r in backward["results"]),
        )

    def test_one_indexer_can_be_selected_by_id(self):
        cfg = self.mixed()
        knowledge.build(self.repo, cfg, "base", apply=True)
        result = knowledge.query(self.repo, cfg, [], indexer="c-symbols")
        self.assertEqual([r["indexer"] for r in result["results"]], ["c-symbols"])
        self.assertNotIn("python saw", result["stdout"])

    def test_an_unknown_indexer_id_lists_the_ones_that_exist(self):
        cfg = self.mixed()
        with self.assertRaisesRegex(knowledge.KnowledgeError, "py-symbols"):
            knowledge.query(self.repo, cfg, [], indexer="nope")

    def test_a_failing_indexer_does_not_suppress_the_others(self):
        cfg = self.mixed()
        cfg.indexers[0].query_command = [sys.executable, "-c", "import sys;sys.exit(3)"]
        knowledge.build(self.repo, cfg, "base", apply=True)
        result = knowledge.query(self.repo, cfg, [])
        codes = {r["indexer"]: r["returncode"] for r in result["results"]}
        self.assertEqual(codes["py-symbols"], 3)
        self.assertEqual(codes["c-symbols"], 0)
        self.assertIn("c saw", result["stdout"])
        self.assertEqual(result["returncode"], 3, "a nonzero result must still be reported to the caller")

    def test_an_indexer_with_no_artifacts_is_reported_as_skipped_not_fatal(self):
        cfg = self.mixed()
        # Build only the Python indexer's artifacts; the C indexer has nothing to answer from.
        knowledge.build(self.repo, self.config(indexers=[self.specs[0]]), "base", apply=True)
        result = knowledge.query(self.repo, cfg, [])
        self.assertEqual([r["indexer"] for r in result["results"]], ["py-symbols"])
        self.assertEqual([s["indexer"] for s in result["skipped"]], ["c-symbols"])

    def test_query_fails_only_when_no_indexer_can_answer(self):
        with self.assertRaisesRegex(knowledge.KnowledgeError, "build"):
            knowledge.query(self.repo, self.mixed(), [])

    def test_the_argument_separator_is_not_passed_through_to_the_indexer(self):
        """`query -- foo` must send the indexer `foo`, not `--` and then `foo`."""
        cfg = self.mixed()
        knowledge.build(self.repo, cfg, "base", apply=True)
        seen = self.repo / "seen.txt"
        cfg.indexers[0].query_command = [
            sys.executable,
            "-c",
            "import sys,pathlib;pathlib.Path(sys.argv[1]).write_text(repr(sys.argv[3:]))",
            str(seen),
            "{artifacts}",
        ]
        knowledge.query(self.repo, cfg, ["--", "greet"], indexer="py-symbols")
        self.assertEqual(seen.read_text(encoding="utf-8"), repr(["greet"]))


class TransportTests(KnowledgeHarness):
    def test_store_prefix_encodes_identity_for_portable_directory_names(self):
        cfg = self.config(store={"prefix": "{repository_id}/{key}"})
        self.assertEqual(knowledge.transport_prefix(cfg, "remote:abc", "key"), "remote%3Aabc/key")
        self.assertEqual(knowledge.transport_prefix(cfg, "team/monorepo", "key"), "team%2Fmonorepo/key")

    def store(self, destination):
        copy = "import shutil,sys,pathlib;pathlib.Path(sys.argv[2]).parent.mkdir(parents=True,exist_ok=True);shutil.copytree(sys.argv[1],sys.argv[2],dirs_exist_ok=True)"
        return {
            "push_command": [sys.executable, "-c", copy, "{local}", str(destination) + "/{prefix}"],
            "pull_command": [sys.executable, "-c", copy, str(destination) + "/{prefix}", "{local}"],
            "prefix": "{repository_id}/{key}",
        }

    def test_push_requires_apply(self):
        remote = Path(self.temp.name) / "remote"
        cfg = self.config(store=self.store(remote))
        knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertFalse(knowledge.push(self.repo, cfg, apply=False)["apply"])
        self.assertFalse(remote.exists())

    def test_push_then_pull_into_a_fresh_clone_reuses_every_artifact(self):
        remote = Path(self.temp.name) / "remote"
        cfg = self.config(store=self.store(remote))
        knowledge.build(self.repo, cfg, "base", apply=True)
        knowledge.push(self.repo, cfg, apply=True)
        clone = Path(self.temp.name) / "clone"
        subprocess.run(["git", "clone", "-q", str(self.repo), str(clone)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(clone), "remote", "set-url", "origin", "https://example.invalid/team/repo.git"],
            check=True,
            capture_output=True,
        )
        other = knowledge.Config.from_settings(clone, cfg.raw)
        self.assertEqual(knowledge.status(clone, other)["layers"]["base"][0]["state"], "missing")
        knowledge.pull(clone, other, apply=True)
        self.assertEqual(knowledge.status(clone, other)["layers"]["base"][0]["state"], "current")

    def test_pull_fetches_only_the_artifacts_this_checkout_lacks(self):
        remote = Path(self.temp.name) / "remote"
        cfg = self.config(store=self.store(remote))
        knowledge.build(self.repo, cfg, "base", apply=True)
        knowledge.push(self.repo, cfg, apply=True)
        plan = knowledge.pull(self.repo, cfg, apply=True)
        self.assertEqual(plan["fetched"], [])

    def test_push_refuses_a_dirty_checkout_because_a_published_artifact_must_match_a_commit(self):
        remote = Path(self.temp.name) / "remote"
        cfg = self.config(store=self.store(remote))
        knowledge.build(self.repo, cfg, "base", apply=True)
        (self.repo / "src/a.py").write_text("uncommitted\n", encoding="utf-8")
        with self.assertRaisesRegex(knowledge.KnowledgeError, "clean"):
            knowledge.push(self.repo, cfg, apply=True)

    def test_push_refuses_an_owner_only_repository_unless_told_explicitly(self):
        remote = Path(self.temp.name) / "remote"
        cfg = self.config(store=self.store(remote), publication="owner-only")
        knowledge.build(self.repo, cfg, "base", apply=True)
        with self.assertRaisesRegex(knowledge.KnowledgeError, "owner-only"):
            knowledge.push(self.repo, cfg, apply=True)
        self.assertTrue(knowledge.push(self.repo, cfg, apply=True, include_owner_only=True)["pushed"])

    def test_sharing_refuses_a_checkout_with_no_stable_identity(self):
        """An index addressed by a per-clone identity could never be reused, so say so instead."""
        remote = Path(self.temp.name) / "remote"
        cfg = self.config(store=self.store(remote))
        knowledge.build(self.repo, cfg, "base", apply=True)
        self.git("remote", "remove", "origin")
        with self.assertRaisesRegex(knowledge.KnowledgeError, "origin remote"):
            knowledge.push(self.repo, cfg, apply=True)

    def test_an_explicit_repository_id_lets_a_repository_without_a_remote_share(self):
        remote = Path(self.temp.name) / "remote"
        cfg = self.config(store=self.store(remote), repository_id="team/monorepo")
        knowledge.build(self.repo, cfg, "base", apply=True)
        self.git("remote", "remove", "origin")
        self.assertTrue(knowledge.push(self.repo, cfg, apply=True)["pushed"])
        self.assertTrue((remote / "team%2Fmonorepo").is_dir())

    def test_push_without_a_configured_store_explains_rather_than_crashing(self):
        cfg = self.config()
        knowledge.build(self.repo, cfg, "base", apply=True)
        with self.assertRaisesRegex(knowledge.KnowledgeError, "store"):
            knowledge.push(self.repo, cfg, apply=True)


class SafetyTests(KnowledgeHarness):
    def test_an_artifact_key_may_not_escape_the_cache_root(self):
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.artifact_path(self.repo, self.config(), "../../escaped")

    def test_a_cache_root_outside_the_repository_is_refused(self):
        with self.assertRaisesRegex(knowledge.KnowledgeError, "cache_root"):
            self.config(cache_root="../outside")

    def test_an_unknown_artifact_kind_is_refused_at_configuration_time(self):
        with self.assertRaisesRegex(knowledge.KnowledgeError, "kind"):
            self.config(indexers=[self.indexer(kind="telepathy")])

    def test_an_unknown_granularity_is_refused_at_configuration_time(self):
        with self.assertRaisesRegex(knowledge.KnowledgeError, "granularity"):
            self.config(indexers=[self.indexer(granularity="vibes")])

    def test_duplicate_indexer_ids_are_refused(self):
        with self.assertRaisesRegex(knowledge.KnowledgeError, "twice"):
            self.config(indexers=[self.indexer(), self.indexer()])

    def test_an_indexer_that_writes_outside_its_output_directory_is_refused(self):
        escaping = (
            "import sys,pathlib;out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True);"
            "(out.parent/'escaped.json').write_text('{}')"
        )
        cfg = self.config(indexers=[self.indexer(build_command=[sys.executable, "-c", escaping, "{out}", "{files}"])])
        result = knowledge.build(self.repo, cfg, "base", apply=True)
        self.assertEqual(result["indexers"][0]["indexed"], [])
        self.assertFalse((knowledge.cache_root(self.repo, cfg) / "escaped.json").exists())

    def test_the_module_uses_only_the_standard_library(self):
        tree = ast.parse((ROOT / "project/ai_workflow/tools/knowledge.py").read_text(encoding="utf-8"))
        local = {path.stem for path in (ROOT / "project/ai_workflow/tools").glob("*.py")}
        allowed = set(sys.stdlib_module_names) | local | {"__future__"}
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                self.assertIn(name.split(".")[0], allowed)


class CommandSurfaceTests(unittest.TestCase):
    """The tool is worthless if the documented command does not reach it."""

    def help_text(self):
        import contextlib
        import io

        sys.path.insert(0, str(ROOT / "src"))
        from codebase_agent_setup import cli

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertRaises(SystemExit) as result:
            cli.main(["knowledge", "--help"])
        self.assertEqual(result.exception.code, 0)
        return buffer.getvalue()

    def test_the_knowledge_command_reaches_the_layered_index_not_the_retired_backend(self):
        text = self.help_text()
        for verb in ("status", "build", "query", "push", "pull"):
            self.assertIn(verb, text)

    def test_the_command_surface_documents_the_layer_option(self):
        self.assertIn("--repo", self.help_text())


if __name__ == "__main__":
    unittest.main()
