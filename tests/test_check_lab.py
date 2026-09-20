"""Real Git/worktree regressions for the student scope checker."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "tools" / "check_lab.py"


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q", "-b", "ch2-api")
        self.git("config", "user.name", "Scope test")
        self.git("config", "user.email", "scope@example.invalid")
        self.write("os/trap.c", 'void trap(void) { /* TODO(ch2-api) */ }\n')
        self.write("os/other.c", "int provided = 1;\n")
        self.write("tests/test.sh", "exit 0\n")
        self.write(".gitignore", "build/\nuser/\n.ai/course-tools/\n")
        self.manifest = {
            "schema_version": 1, "chapter": 2, "title": "Trap handling",
            "student_branch": "ch2-api", "reference_branch": "ch2-api-impl",
            "allowed_code_files": ["os/trap.c"],
            "functions": [{"file": "os/trap.c", "name": "trap"}],
            "test": {"base": 1},
        }
        self.write("lab.json", json.dumps(self.manifest))
        self.git("add", ".")
        self.git("commit", "-qm", "Skeleton")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/ch2-api", self.base)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              check=True, capture_output=True, text=True).stdout

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def check(self, code=0, *args, default=False):
        command = [sys.executable, str(CHECKER)]
        if not default:
            command += ["--base", self.base]
        result = subprocess.run(command + list(args), cwd=self.root,
                                capture_output=True, text=True)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, code, output)
        return output

    def test_skeleton_passes_but_completion_rejects_todo(self):
        self.check()
        self.assertIn("remaining TODO(ch2-api)", self.check(1, "--require-complete"))
        self.write("os/trap.c", "void trap(void) {}\n")
        self.check(0, "--require-complete")

    def test_allowed_committed_staged_and_unstaged_changes(self):
        self.write("os/trap.c", "void trap(void) {}\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Implementation")
        self.write("os/trap.c", "static int helper(void) { return 0; }\n")
        self.git("add", "os/trap.c")
        self.write("os/trap.c", "static int helper(void) { return 1; }\n")
        self.check()

    def test_forbidden_committed_change(self):
        self.write("os/other.c", "int provided = 0;\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Changed supporting code")
        self.assertIn("os/other.c", self.check(1))

    def test_forbidden_staged_change_and_test_modification(self):
        self.write("tests/test.sh", "echo fake success\n")
        self.git("add", "tests/test.sh")
        self.assertIn("tests/test.sh", self.check(1))

    def test_forbidden_unstaged_change(self):
        self.write("os/other.c", "int provided = 0;\n")
        self.assertIn("outside the allowed scope", self.check(1))

    def test_new_source_rejected_untracked_staged_and_committed(self):
        self.write("os/helper.c", "int helper;\n")
        self.assertIn("os/helper.c", self.check(1))
        self.git("add", "os/helper.c")
        self.check(1)
        self.git("commit", "-qm", "New source")
        self.check(1)

    def test_allowed_reports_and_course_records(self):
        for path in ("reports/ch2.md", "reports/ch2/gdb.txt", "reports/ch2/run.log",
                     ".ai/events/session.jsonl", ".ai/agent-sessions/codex/session.jsonl",
                     ".ai/submissions/attempt.jsonl"):
            self.write(path, "evidence\n")
        self.check()
        self.git("add", ".")
        self.git("commit", "-qm", "Reports")
        self.check()

    def test_invalid_report_and_record_extensions_rejected(self):
        self.write("reports/cheat.c", "int main;\n")
        self.write(".ai/events/payload.py", "print('no')\n")
        self.write(".ai/agent-sessions/session.jsonl", "{}\n")
        output = self.check(1)
        for path in ("reports/cheat.c", ".ai/events/payload.py",
                     ".ai/agent-sessions/session.jsonl"):
            self.assertIn(path, output)

    def test_deleting_allowed_file_rejected(self):
        (self.root / "os/trap.c").unlink()
        self.assertIn("os/trap.c: missing", self.check(1))
        self.git("add", "os/trap.c")
        self.git("commit", "-qm", "Delete target")
        self.check(1)

    def test_renaming_allowed_file_rejected(self):
        self.git("mv", "os/trap.c", "os/new.c")
        output = self.check(1)
        self.assertIn("os/trap.c: missing", output)
        self.assertIn("os/new.c", output)

    def test_target_symlink_rejected(self):
        target = self.root / "os/trap.c"
        target.unlink()
        target.symlink_to("other.c")
        self.assertIn("os/trap.c: symlink", self.check(1))

    def test_report_symlink_rejected(self):
        (self.root / "reports").mkdir()
        (self.root / "reports/result.md").symlink_to("../os/other.c")
        self.assertIn("reports/result.md: symlink", self.check(1))

    def test_symlink_parent_rejected(self):
        (self.root / "reports").symlink_to("os", target_is_directory=True)
        self.assertIn("symlink", self.check(1))

    def test_baseline_manifest_is_authoritative(self):
        self.manifest["allowed_code_files"].append("os/other.c")
        self.write("lab.json", json.dumps(self.manifest))
        self.write("os/other.c", "int provided = 0;\n")
        output = self.check(1)
        self.assertIn("lab.json", output)
        self.assertIn("os/other.c", output)

    def test_remote_default_preferred_over_local_branch(self):
        self.write("os/other.c", "int provided = 0;\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Local branch moved")
        output = self.check(1, default=True)
        self.assertIn("Baseline: " + self.base, output)

    def test_local_default_fallback_and_unknown_branch(self):
        self.git("update-ref", "-d", "refs/remotes/origin/ch2-api")
        self.check(default=True)
        self.git("checkout", "-qb", "work")
        self.assertIn("Pass --base", self.check(2, default=True))
        self.check()

    def test_explicit_remote_resolves_to_full_sha(self):
        output = self.check(0, "--base", "origin/ch2-api")
        self.assertIn("Baseline: " + self.base, output)

    def test_chapter_three_full_test_base_is_supported(self):
        self.git("checkout", "-qb", "ch3-api")
        self.manifest.update(chapter=3, student_branch="ch3-api",
                             reference_branch="ch3-api-impl", test={"base": 2})
        self.write("lab.json", json.dumps(self.manifest))
        self.write("os/trap.c", "void trap(void) { /* TODO(ch3-api) */ }\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Chapter three skeleton")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/ch3-api", self.base)
        self.check(default=True)
        self.assertIn("remaining TODO(ch3-api)", self.check(1, "--require-complete"))

    def test_git_ignored_generated_and_external_content_skipped(self):
        self.write("build/generated.c", "generated\n")
        self.write("user/test.c", "external test\n")
        self.write(".ai/course-tools/archive.py", "tool\n")
        (self.root / "build/link").symlink_to("generated.c")
        self.check()

    def test_assume_unchanged_does_not_hide_provided_code_edits(self):
        self.git("update-index", "--assume-unchanged", "os/other.c")
        self.write("os/other.c", "int provided = 0;\n")
        self.assertIn("os/other.c", self.check(1))

    def test_executable_mode_changes_rejected(self):
        os.chmod(self.root / "os/trap.c", 0o755)
        self.assertIn("executable mode changed", self.check(1))

    def test_checker_has_no_repository_side_effects(self):
        self.write("os/trap.c", "void trap(void) {}\n")
        self.git("add", "os/trap.c")
        before_index = (self.root / ".git/index").read_bytes()
        before_config = (self.root / ".git/config").read_bytes()
        before_tree = {str(path.relative_to(self.root)): path.read_bytes()
                       for path in self.root.rglob("*") if path.is_file()}
        self.check()
        self.assertEqual(before_index, (self.root / ".git/index").read_bytes())
        self.assertEqual(before_config, (self.root / ".git/config").read_bytes())
        self.assertEqual(before_tree, {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()})


if __name__ == "__main__":
    unittest.main()
