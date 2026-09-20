#!/usr/bin/env python3
"""Check the working tree against the lab contract in a trusted skeleton commit.

This is a scope check, not an anti-cheating sandbox. Teachers must run a trusted
copy and choose the published skeleton commit; students can edit this script,
their local refs and their Git ignore settings. Git-ignored untracked content
(including the separate user/ test checkout and generated build files) is not
part of this check. No hook, index, worktree or repository setting is changed.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys


class CheckError(Exception):
    """An unusable baseline or repository."""


def git(root, *args, required=True):
    result = subprocess.run(
        ["git", "-C", str(root), *args], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if result.returncode and required:
        raise CheckError(result.stderr.decode(errors="replace").strip())
    return result


def valid_path(value):
    return (
        isinstance(value, str) and bool(value)
        and "\\" not in value and "\x00" not in value
        and not value.startswith("/")
        and all(part not in ("", ".", "..") for part in value.split("/"))
        and ".git" not in value.split("/")
    )


def load_manifest(root, commit):
    try:
        manifest = json.loads(git(root, "show", commit + ":lab.json").stdout)
    except (ValueError, UnicodeError) as exc:
        raise CheckError("The baseline lab.json is not valid JSON.") from exc
    if not isinstance(manifest, dict):
        raise CheckError("The baseline lab.json must be an object.")
    chapter = manifest.get("chapter")
    if (manifest.get("schema_version") != 1 or type(chapter) is not int
            or chapter < 1):
        raise CheckError("Expected schema_version=1 and a positive chapter number.")
    if (manifest.get("student_branch") != f"ch{chapter}-api"
            or manifest.get("reference_branch") != f"ch{chapter}-api-impl"):
        raise CheckError("The baseline branch names do not match its chapter.")
    if not isinstance(manifest.get("title"), str) or not manifest["title"]:
        raise CheckError("The baseline title must be a nonempty string.")
    allowed = manifest.get("allowed_code_files")
    if (not isinstance(allowed, list) or not allowed
            or not all(valid_path(path) for path in allowed)
            or len(set(allowed)) != len(allowed)):
        raise CheckError("The baseline allowed_code_files must list unique relative paths.")
    functions = manifest.get("functions")
    if (not isinstance(functions, list) or not functions
            or not all(isinstance(item, dict) and item.get("file") in allowed
                       and isinstance(item.get("name"), str) and item["name"]
                       for item in functions)):
        raise CheckError("The baseline functions must name functions in allowed code files.")
    test = manifest.get("test")
    if (not isinstance(test, dict) or type(test.get("base")) is not int
            or test["base"] not in (0, 1, 2)):
        raise CheckError("The baseline test.base must be an integer in 0, 1, 2.")
    return manifest


def resolve_base(root, requested):
    if requested:
        candidates = [requested]
    else:
        branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", required=False)
        name = branch.stdout.decode().strip()
        match = re.fullmatch(r"ch([1-9][0-9]*)(?:-api(?:-impl)?)?", name)
        if not match:
            raise CheckError("Pass --base <published skeleton SHA> outside a chN branch.")
        student = f"ch{match.group(1)}-api"
        candidates = ["refs/remotes/origin/" + student, "refs/heads/" + student]
    for candidate in candidates:
        result = git(root, "rev-parse", "--verify", "--end-of-options",
                     candidate + "^{commit}", required=False)
        if result.returncode == 0:
            return result.stdout.decode().strip()
    raise CheckError("No skeleton baseline found; pass --base <published skeleton SHA>.")


def baseline_tree(root, commit):
    entries = {}
    for entry in git(root, "ls-tree", "-r", "-z", commit).stdout.split(b"\x00"):
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        path = os.fsdecode(raw_path)
        if not valid_path(path):
            raise CheckError(f"Unsupported baseline path: {path!r}")
        if kind != "blob" or mode not in ("100644", "100755"):
            raise CheckError(f"Unsupported baseline entry (requires a regular file): {path}")
        entries[path] = (mode, oid)
    return entries


def file_state(root, relative):
    """Check all ancestors before reading a file, without following symlinks."""
    current = root
    parts = PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return "missing", None, None
        if stat.S_ISLNK(info.st_mode):
            return "symlink", None, None
        if index != len(parts) - 1:
            if not stat.S_ISDIR(info.st_mode):
                return "non-file ancestor", None, None
        elif not stat.S_ISREG(info.st_mode):
            return "not a regular file", None, None
    mode = "100755" if info.st_mode & stat.S_IXUSR else "100644"
    return "file", mode, current.read_bytes()


def blob_hash(data, oid_length):
    algorithm = hashlib.sha256 if oid_length == 64 else hashlib.sha1
    return algorithm(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()


def report_or_record(path):
    return bool(
        re.fullmatch(r"reports/(?:[^/]+/)*[^/]+\.(?:md|txt|log)", path)
        or re.fullmatch(r"\.ai/events/[^/]+\.jsonl", path)
        or re.fullmatch(r"\.ai/agent-sessions/[^/]+/[^/]+\.jsonl", path)
        or re.fullmatch(r"\.ai/submissions/[^/]+\.jsonl", path)
    )


def check(root, commit, manifest, require_complete=False):
    tree = baseline_tree(root, commit)
    allowed = set(manifest["allowed_code_files"])
    if not allowed.issubset(tree):
        raise CheckError("Some allowed code files do not exist in the baseline.")
    errors = []
    changed = 0
    for path, (old_mode, old_oid) in tree.items():
        state, mode, data = file_state(root, path)
        if state != "file":
            errors.append(f"{path}: {state}; baseline files must remain regular files")
            continue
        if mode == old_mode and blob_hash(data, len(old_oid)) == old_oid:
            continue
        changed += 1
        if mode != old_mode:
            errors.append(f"{path}: executable mode changed")
        if path not in allowed and not report_or_record(path):
            errors.append(f"{path}: modification outside the allowed scope")

    # Include new committed/staged files and visible untracked files. Baseline
    # files above are inspected even if assume-unchanged or skip-worktree is set.
    extra = set()
    for arguments in (("ls-files", "--cached", "-z"),
                      ("ls-files", "--others", "--exclude-standard", "-z")):
        extra.update(os.fsdecode(path) for path in git(root, *arguments).stdout.split(b"\x00")
                     if path)
    for path in sorted(extra - set(tree)):
        if not valid_path(path):
            errors.append(f"{path!r}: invalid path")
            continue
        state, mode, _ = file_state(root, path)
        if state == "missing":
            # A new index entry deleted again in the working tree contributes
            # nothing to the final baseline-to-working-tree comparison.
            continue
        changed += 1
        if state != "file":
            errors.append(f"{path}: {state}; new files must be regular files")
        elif mode != "100644":
            errors.append(f"{path}: new report/record must not be executable")
        elif not report_or_record(path):
            errors.append(f"{path}: new file outside report/record paths")

    if require_complete:
        marker = f"TODO(ch{manifest['chapter']}-api)".encode()
        for path in sorted(allowed):
            state, _, data = file_state(root, path)
            if state == "file":
                for number, line in enumerate(data.splitlines(), 1):
                    if marker in line:
                        errors.append(f"{path}:{number}: remaining {marker.decode()}")
    return errors, changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="published student skeleton SHA or origin/chN-api")
    parser.add_argument("--require-complete", action="store_true",
                        help="also reject remaining TODO(chN-api) markers")
    options = parser.parse_args(argv)
    try:
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.decode().strip())
        commit = resolve_base(root, options.base)
        manifest = load_manifest(root, commit)
        errors, changed = check(root, commit, manifest, options.require_complete)
    except (CheckError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Baseline: {commit}")
    print(f"Chapter: {manifest['chapter']} ({manifest['student_branch']})")
    for error in errors:
        print("FAIL: " + error)
    if errors:
        print(f"Scope check failed: {len(errors)} violation(s).")
        return 1
    suffix = "; no TODO markers remain" if options.require_complete else ""
    print(f"Scope check passed: {changed} changed file(s){suffix}.")
    print("This checks file scope only; it does not establish correctness or independent work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
