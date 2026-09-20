"""Regression transcripts for the actual positive-run oracle (no emulator)."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_lab", ROOT / "tools/run_lab.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class PositiveOracleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.user = Path(self.temp.name) / "user"
        (self.user / "src").mkdir(parents=True)
        (self.user / "target/bin").mkdir(parents=True)
        self.apps = ["ch2b_exit", "ch2b_hello_world", "ch2b_power"]
        for app in self.apps:
            (self.user / "target/bin" / app).write_bytes(b"fixture")
        self.suite = ["ch2b_hello_world", "ch6b_filetest_simple", "ch6b_exec"]
        entries = ",\n".join('    "' + name + r'\0"' for name in self.suite)
        (self.user / "src/ch6b_usertest.c").write_text(
            "const char *TESTS[] = {\n" + entries + "\n};\n")

    def verify(self, text, chapter=6):
        RUNNER.verify_positive(text, chapter, self.user)

    def reject(self, text, chapter=6):
        with self.assertRaises(RuntimeError):
            self.verify(text, chapter)

    def suite_log(self, names=None, codes=None):
        names = self.suite if names is None else names
        codes = [0] * len(names) if codes is None else codes
        lines = []
        for index, (name, code) in enumerate(zip(names, codes), 2):
            lines += [f"Usertests: Running {name}",
                      f"Usertests: Test {name} in Process {index} exited with code {code}"]
        return "\n".join(lines + ["ch6b Usertests passed!", ""])

    def test_real_result_format_passes(self):
        self.verify(self.suite_log())

    def test_panic_program_filename_in_listing_is_not_a_failure(self):
        self.verify("app list:\nch6b_panic\nch6b_filetest_simple\n" + self.suite_log())

    def test_real_kernel_panic_is_rejected_even_after_complete_results(self):
        for diagnostic in ("[PANIC] fileopen: corrupt inode",
                           "thread panicked at 'unexpected failure'"):
            with self.subTest(diagnostic=diagnostic):
                self.reject(self.suite_log() + diagnostic + "\n")

    def test_middle_nonzero_exit_cannot_be_hidden_by_passed_footer(self):
        for code in (-1, 1, 1234):
            with self.subTest(code=code):
                self.reject(self.suite_log(codes=[0, code, 0]))

    def test_missing_test_cannot_be_hidden_by_passed_footer(self):
        self.reject(self.suite_log(names=[self.suite[0], self.suite[2]]))

    def test_started_but_missing_result_is_rejected(self):
        text = self.suite_log()
        text = "\n".join(line for line in text.splitlines()
                         if not line.startswith("Usertests: Test " + self.suite[1]))
        self.reject(text)

    def test_start_order_is_checked_separately_from_result_order(self):
        text = self.suite_log()
        first = "Usertests: Running " + self.suite[0]
        second = "Usertests: Running " + self.suite[1]
        text = text.replace(first, "SWAP").replace(second, first).replace("SWAP", second)
        self.reject(text)

    def test_result_order_is_checked_separately_from_start_order(self):
        lines = self.suite_log().splitlines()
        lines[1], lines[3] = lines[3], lines[1]
        self.reject("\n".join(lines))

    def test_duplicate_result_is_rejected(self):
        self.reject(self.suite_log() +
                    "Usertests: Test ch6b_exec in Process 9 exited with code 0\n")

    def test_completion_footer_is_required(self):
        self.reject(self.suite_log().replace("ch6b Usertests passed!", ""))

    def test_chapter_two_allows_1234_only_for_the_exit_application(self):
        self.verify("sysexit(1234)\nsysexit(0)\nsysexit(0)\nALL DONE\n", 2)
        for exits in ((0, 1234, 0), (1234, 1234, 0), (1234, 0, 42), (0, 0, 0)):
            with self.subTest(exits=exits):
                text = "".join(f"sysexit({code})\n" for code in exits) + "ALL DONE\n"
                self.reject(text, 2)

    def test_chapter_two_missing_exit_is_rejected(self):
        self.reject("sysexit(1234)\nsysexit(0)\nALL DONE\n", 2)

    def test_chapter_three_accepts_scheduler_order_but_matches_pid_to_status(self):
        # PIDs follow sorted packed applications, while scheduling may finish
        # them in a different order. Only PID 1 runs ch2b_exit in this fixture.
        self.verify("proc 3 exit with 0\nproc 1 exit with 1234\n"
                    "proc 2 exit with 0\n[PANIC] all apps over\n", 3)
        for pairs in (((1, 0), (2, 1234), (3, 0)),
                      ((1, 1234), (2, 1234), (3, 0)),
                      ((1, 1234), (2, 0), (3, -2))):
            with self.subTest(pairs=pairs):
                text = "".join(f"proc {pid} exit with {code}\n" for pid, code in pairs)
                self.reject(text + "[PANIC] all apps over\n", 3)

    def test_chapter_three_duplicate_pid_cannot_replace_missing_pid(self):
        self.reject("proc 1 exit with 1234\nproc 2 exit with 0\n"
                    "proc 2 exit with 0\n[PANIC] all apps over\n", 3)

    def test_chapter_one_requires_startup_and_completion(self):
        self.verify("hello wrold!\n[PANIC] ALL DONE\n", 1)
        self.reject("[PANIC] ALL DONE\n", 1)
        self.reject("hello wrold!\n", 1)

    def test_incomplete_api_marker_is_not_success(self):
        self.reject(self.suite_log() + "[PANIC] TODO(ch6-api): filealloc\n")


if __name__ == "__main__":
    unittest.main()
