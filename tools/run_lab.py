#!/usr/bin/env python3
"""Build and execute the pinned uCore API lab tests, retaining all raw evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import socket
import subprocess
import sys
import time

TEST_COMMIT = "1733f460c596b013b1c509ad42afa428640783b0"
TEST_URL = "https://github.com/LearningOS/uCore-Tutorial-Test.git"
PREVIOUS_PATCH = "46196b323286a4bcb6d4be6619727fb80c3245db3f5fccdf2c470eec31f3ddfa"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def capture(args, cwd):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def prepare(repo, source, patch):
    user = repo / "user"
    if not user.exists():
        subprocess.run(["git", "clone", source, str(user)], check=True)
        subprocess.run(["git", "checkout", "--detach", TEST_COMMIT], cwd=user, check=True)
    if capture(["git", "rev-parse", "HEAD"], user) != TEST_COMMIT:
        raise RuntimeError("user/ is not the pinned test revision; preserve it and move it aside first")
    if capture(["git", "diff", "--cached", "--name-only"], user):
        raise RuntimeError("user/ has staged edits; refusing to overwrite them")
    if capture(["git", "ls-files", "--others", "--exclude-standard"], user):
        raise RuntimeError("user/ has untracked source files; preserve them and move them aside first")
    diff = subprocess.check_output(["git", "diff", "--binary"], cwd=user)
    expected = patch.read_bytes()
    if diff != expected and hashlib.sha256(diff).hexdigest() == PREVIOUS_PATCH:
        # Upgrade only the exact earlier generated compatibility patch, never
        # arbitrary local edits. Keep the original public test commit intact.
        subprocess.run(["git", "apply", "--reverse", "-"], cwd=user, input=diff, check=True)
        diff = b""
    if not diff:
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=user, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=user, check=True)
        diff = subprocess.check_output(["git", "diff", "--binary"], cwd=user)
    if diff != expected:
        raise RuntimeError("user/ contains edits other than the documented test compatibility patch")
    return user


def logged(command, cwd, path, timeout=240):
    with path.open("w") as log:
        log.write("$ " + " ".join(map(str, command)) + "\n")
        log.flush()
        result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}); see {path}")


def qemu_command(repo, chapter, bios):
    command = ["qemu-system-riscv64", "-nographic", "-machine", "virt", "-m", "128M", "-smp", "1",
               "-bios", bios, "-kernel", "build/kernel"]
    if chapter >= 6:
        command += ["-drive", "file=nfs/fs-copy.img,if=none,format=raw,id=x0",
                    "-device", "virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0"]
    return command


def execute(command, repo, path, timeout, stop_marker):
    started = time.monotonic()
    output = bytearray()
    completed = False
    completion_deadline = None
    with path.open("wb") as log:
        process = subprocess.Popen(command, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            while time.monotonic() - started < timeout:
                ready, _, _ = select.select([process.stdout], [], [], 0.1)
                if ready:
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if chunk:
                        log.write(chunk)
                        log.flush()
                        output.extend(chunk)
                    elif process.poll() is not None:
                        break
                if (stop_marker and not completed
                        and stop_marker in ANSI.sub("", output.decode(errors="replace"))):
                    completed = True
                    # Let the kernel finish its final diagnostic and shutdown.
                    # Immediate termination can split an expected completion
                    # panic into a partial line that looks like a real failure.
                    completion_deadline = time.monotonic() + 1.0
                if completion_deadline is not None and time.monotonic() >= completion_deadline:
                    break
                if process.poll() is not None:
                    break
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            rest = process.stdout.read()
            output.extend(rest)
            log.write(rest)
    return ANSI.sub("", output.decode(errors="replace")), process.returncode, completed


def verify_positive(text, chapter, user):
    errors = []
    # Expected end-of-batch panic is the historical loader completion mechanism.
    for line in text.splitlines():
        if re.search(r"assert(?:ion)?[^\n]*(?:fail|panic)|unknown syscall|Unimplemented|TODO\(ch|invalid opcode", line, re.I):
            errors.append(line)
        if re.search(r"\[PANIC\b|panicked at", line, re.I) and not any(end in line for end in ("all apps over", "all app are over!", "ALL DONE")):
            errors.append(line)
    if chapter == 1:
        if "ALL DONE" not in text or "hello wrold!" not in text:
            errors.append("missing chapter 1 completion")
    elif chapter <= 4:
        if chapter == 2:
            exits = re.findall(r"sysexit\((-?\d+)\)", text)
            marker = "ALL DONE"
        else:
            exits = re.findall(r"proc \d+ exit with (-?\d+)", text)
            marker = "all apps over"
        expected_count = len(list((user / "target/bin").iterdir()))
        if len(exits) != expected_count:
            errors.append(f"exit count {len(exits)} does not match {expected_count} selected apps")
        # ch2b_exit intentionally exits with MAGIC=1234. It is packed first;
        # other base applications and trace must exit with zero.
        apps = sorted(path.name for path in (user / "target/bin").iterdir())
        if chapter == 2:
            expected_exits = [1234 if name == "ch2b_exit" else 0 for name in apps]
            if list(map(int, exits)) != expected_exits:
                errors.append(f"application exits {exits} differ from {expected_exits}")
        else:
            observed = [(int(pid), int(code)) for pid, code in re.findall(r"proc (\d+) exit with (-?\d+)", text)]
            expected_exits = [(index + 1, 1234 if name == "ch2b_exit" else 0) for index, name in enumerate(apps)]
            if sorted(observed) != expected_exits:
                errors.append(f"PID/exit pairs {observed} differ from {expected_exits}")
        if marker not in text:
            errors.append(f"missing {marker!r}")
    else:
        source = (user / f"src/ch{chapter}b_usertest.c").read_text()
        array = re.search(r"TESTS\[\]\s*=\s*\{(.*?)\};", source, re.S).group(1)
        expected = [name.replace(r"\0", "") for name in re.findall(r'"([^"\n]+)"', array)]
        started = re.findall(r"Usertests: Running (\S+)", text)
        results = re.findall(r"Usertests: Test (\S+) in Process \d+ exited with code (-?\d+)", text)
        if started != expected:
            errors.append(f"test start order differs: expected={expected}, observed={started}")
        if [name for name, _ in results] != expected:
            errors.append("missing, duplicate, or unexpected individual test results")
        if any(int(code) != 0 for _, code in results):
            errors.append(f"failing individual results: {results}")
        if f"ch{chapter}b Usertests passed!" not in text:
            errors.append("missing suite completion")
    if errors:
        raise RuntimeError("; ".join(errors[:12]))


def gdb_smoke(command, repo, log, function):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (log.parent / "gdb-qemu.log").open("w") as qlog:
        qemu = subprocess.Popen(command + ["-S", "-gdb", f"tcp:127.0.0.1:{port}"], cwd=repo,
                                stdout=qlog, stderr=subprocess.STDOUT)
        try:
            # GDB's connection retry avoids a fixed startup sleep.
            script = ["set pagination off", "set confirm off", "set tcp auto-retry on",
                      "set tcp connect-timeout 10", f"target remote 127.0.0.1:{port}",
                      f"break {function}", "continue", "printf \"API_GDB_HIT\\n\"",
                      "x/i $pc", "info registers pc sp", "bt", "detach", "quit"]
            args = ["gdb-multiarch", "-q", "-batch", "build/kernel"]
            for instruction in script:
                args += ["-ex", instruction]
            logged(args, repo, log, 45)
            text = log.read_text()
            if "API_GDB_HIT" not in text or not re.search(r"Breakpoint \d+,", text):
                raise RuntimeError("GDB did not stop at the requested API function")
        finally:
            qemu.terminate()
            qemu.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--chapter", type=int)
    parser.add_argument("--mode", choices=["positive", "negative", "gdb"], default="positive")
    parser.add_argument("--test-source", default=TEST_URL)
    parser.add_argument("--bios", default="default", help="QEMU firmware, default: packaged OpenSBI")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    manifest = json.loads((repo / "lab.json").read_text()) if (repo / "lab.json").exists() else {}
    chapter = args.chapter or manifest.get("chapter")
    if chapter not in range(1, 9):
        parser.error("lab.json or --chapter must specify a chapter between 1 and 8")
    out = repo / "artifacts" / f"ch{chapter}-{args.mode}"
    out.mkdir(parents=True, exist_ok=True)
    report = {"chapter": chapter, "mode": args.mode, "test_commit": TEST_COMMIT,
              "bios": args.bios, "status": "FAIL"}
    try:
        report["kernel_commit"] = capture(["git", "rev-parse", "HEAD"], repo)
        patch = Path(__file__).with_name("tests-upstream.patch").resolve()
        report["test_patch_sha256"] = hashlib.sha256(patch.read_bytes()).hexdigest()
        user = prepare(repo, args.test_source, patch) if chapter > 1 else None
        if args.prepare_only:
            report["status"] = "PREPARED"
            return 0
        required = ["riscv64-unknown-elf-gcc", "riscv64-unknown-elf-ld", "riscv64-unknown-elf-objcopy", "cmake", "make", "qemu-system-riscv64"]
        if args.mode == "gdb":
            required.append("gdb-multiarch")
        missing = [tool for tool in required if not shutil.which(tool)]
        if missing:
            raise RuntimeError("missing tools: " + ", ".join(missing))
        for tool in ("riscv64-unknown-elf-gcc", "qemu-system-riscv64"):
            report[tool] = capture([tool, "--version"], repo).splitlines()[0]
        if user:
            base = manifest.get("test", {}).get("base", 2 if chapter == 3 else 1)
            report["base"] = base
            logged(["make", "clean"], user, out / "user-clean.log")
            logged(["make", f"CHAPTER={chapter}", f"BASE={base}", "TOOLPREFIX=riscv64-unknown-elf-"], user, out / "user-build.log")
        # These are generated products, never tracked student source files.
        shutil.rmtree(repo / "build", ignore_errors=True)
        for name in ("os/link_app.S", "os/kernel_app.ld", "os/initproc.S", "nfs/fs.img", "nfs/fs-copy.img"):
            path = repo / name
            if path.exists():
                if capture(["git", "ls-files", "--", name], repo):
                    raise RuntimeError(f"refusing to delete tracked product {name}")
                path.unlink()
        init = f"ch{chapter}b_usertest"
        command = ["make", "build", "LOG=debug" if chapter <= 2 else "LOG=info", f"CHAPTER={chapter}", f"INIT_PROC={init}"]
        logged(command, repo, out / "kernel-build.log")
        if chapter >= 6:
            logged(["make", "nfs/fs-copy.img"], repo, out / "fs-build.log")
        report["kernel_sha256"] = hashlib.sha256((repo / "build/kernel").read_bytes()).hexdigest()
        if args.build_only:
            report["status"] = "BUILT"
            return 0
        command = qemu_command(repo, chapter, args.bios)
        report["qemu_command"] = command
        if args.mode == "gdb":
            function = manifest.get("functions", [{"name": "main"}])[0]["name"]
            gdb_smoke(command, repo, out / "gdb.log", function)
        else:
            marker = f"ch{chapter}b Usertests passed!" if chapter >= 5 and args.mode == "positive" else None
            text, rc, stopped = execute(command, repo, out / "qemu.log", args.timeout, marker)
            report.update(qemu_exit=rc, stopped_after_suite=stopped)
            if args.mode == "negative":
                if not re.search(rf"Unimplemented ch{chapter} API|TODO\(ch{chapter}-api\)|TODO ch{chapter}-api", text):
                    raise RuntimeError("skeleton did not produce its expected TODO failure marker")
                if "Usertests passed!" in text or "all apps over" in text:
                    raise RuntimeError("skeleton unexpectedly completed tests")
            else:
                verify_positive(text, chapter, user)
                if chapter <= 4 and rc != 0:
                    raise RuntimeError(f"batch reached expected output but QEMU did not shut down cleanly: {rc}")
        report["status"] = "PASS"
        print(f"PASS ch{chapter} {args.mode}; evidence: {out}")
        return 0
    except (RuntimeError, subprocess.SubprocessError, OSError) as error:
        report["error"] = str(error)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    finally:
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
