#!/usr/bin/env python3
"""Verify that independently reverting every behavioral source hunk breaks a test."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import verify_scope

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.0"


def file_hashes(root: Path) -> dict[str, str]:
    result = {}
    for rel in verify_scope.git(root, "ls-files", "src").splitlines():
        path = root / rel
        result[rel.replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def parse_hunks(diff: str) -> list[dict[str, object]]:
    hunks: list[dict[str, object]] = []
    header: list[str] = []
    current_path = ""
    lines = diff.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git "):
            header = [line]
            index += 1
            while index < len(lines) and not lines[index].startswith("@@ ") and not lines[index].startswith("diff --git "):
                header.append(lines[index]); index += 1
            match = re.search(r" b/(.+?)(?:\r?\n)?$", header[0])
            current_path = match.group(1) if match else ""
            continue
        if line.startswith("@@ "):
            body = [line]; index += 1
            while index < len(lines) and not lines[index].startswith(("@@ ", "diff --git ")):
                body.append(lines[index]); index += 1
            range_match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            start = int(range_match.group(1)) if range_match else 0
            count = int(range_match.group(2) or "1") if range_match else 0
            is_new = any(line.startswith("new file mode ") or line.startswith("--- /dev/null") for line in header)
            hunks.append({"file": current_path, "line_start": start, "line_end": start + max(count - 1, 0), "new_file": is_new,
                          "patch": "".join(header + body), "body": body[1:]})
            continue
        index += 1
    return hunks


def classify(body: list[str]) -> str:
    changed = [line[1:].rstrip("\r\n") for line in body if line[:1] in {"+", "-"} and not line.startswith(("+++", "---"))]
    if changed and all(not line.strip() or line.lstrip().startswith("#") for line in changed):
        return "nonbehavioral-comment-or-blank"
    removed = [re.sub(r"\s+", "", line[1:]) for line in body if line.startswith("-") and not line.startswith("---")]
    added = [re.sub(r"\s+", "", line[1:]) for line in body if line.startswith("+") and not line.startswith("+++")]
    if removed and added and removed == added:
        return "nonbehavioral-format-only"
    try:
        before = textwrap.dedent("\n".join(line[1:] for line in body if line[:1] in {" ", "-"}))
        after = textwrap.dedent("\n".join(line[1:] for line in body if line[:1] in {" ", "+"}))
        if before and after and ast_equivalent(before, after):
            return "nonbehavioral-ast-equivalent"
    except SyntaxError:
        # A zero-context diff inside a multiline docstring contains prose but
        # not the unchanged quote delimiters.  Recognise only plain prose
        # fragments; punctuation used by executable Python keeps the hunk
        # behavioral.
        if changed and all(re.fullmatch(r"[A-Za-z0-9 `_'.,;:()-]+", line.strip()) for line in changed):
            return "nonbehavioral-docstring-prose"
    return "behavioral"


def ast_equivalent(before: str, after: str) -> bool:
    import ast
    before_tree, after_tree = ast.parse(before), ast.parse(after)
    if all(isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
           for node in before_tree.body + after_tree.body):
        return True
    return ast.dump(before_tree, include_attributes=False) == ast.dump(after_tree, include_attributes=False)


def group_hunks(hunks: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    """Revert adjacent hunks as semantic units.

    Isolated zero-context reverts manufacture import failures when one hunk
    defines a name consumed by another.  Nearby edits are grouped while
    distant, independently testable changes retain separate verdicts.
    """
    groups: list[list[dict[str, object]]] = []
    for hunk in hunks:
        if (groups and groups[-1][-1]["file"] == hunk["file"]
                and int(hunk["line_start"]) - int(groups[-1][-1]["line_end"]) <= 8):
            groups[-1].append(hunk)
        else:
            groups.append([hunk])
    # A newly introduced module and the consumer hunks that name it form one
    # cross-file unit: deleting only the module manufactures an import error,
    # while reverting only its consumers leaves dead new code behind.
    for new_group in list(groups):
        if not any(bool(h.get("new_file")) for h in new_group):
            continue
        stems = {Path(str(h["file"])).stem for h in new_group}
        direct = [group for group in groups if group is not new_group and any(
            any(stem in "".join(str(line) for line in h.get("body", [])) for stem in stems)
            for h in group)]
        dependent_files = {str(h["file"]) for group in direct for h in group}
        dependents = [group for group in groups if group is not new_group
                      and any(str(h["file"]) in dependent_files for h in group)]
        for group in dependents:
            new_group[:0] = group
            groups.remove(group)
    return groups


def prepare_tree(target: str) -> tuple[Path, Path]:
    temp = Path(tempfile.mkdtemp(prefix="hengbot-hunk-"))
    commit = "HEAD" if target == "WORKTREE" else target
    verify_scope.git(ROOT, "worktree", "add", "--detach", str(temp), commit)
    verify_scope._ACTIVE_WORKTREES.add(temp.resolve())
    if target == "WORKTREE":
        for area in ("src", "tests"):
            source = ROOT / area
            destination = temp / area
            if destination.exists(): shutil.rmtree(destination)
            shutil.copytree(source, destination)
    return temp, temp


def apply_patch(root: Path, patch: str, reverse: bool) -> None:
    command = ["git", "apply", "--unidiff-zero", "--whitespace=nowarn", "--ignore-space-change"]
    if reverse: command.append("--reverse")
    run = subprocess.run(command, cwd=root, input=patch, text=True, encoding="utf-8",
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run.returncode:
        raise RuntimeError(f"git apply failed: {run.stderr.strip()}")


def run_candidate(root: Path, module: str, timeout: float, stderr_path: Path, *, structural: bool = False) -> set[str]:
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(root / "src"), str(root / "tests")))
    command = [sys.executable, "-c", verify_scope._test_code(module)]
    try:
        with stderr_path.open("w", encoding="utf-8") as err:
            run = subprocess.run(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=err,
                                 text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return set()
    if run.returncode == 0:
        return set()
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    if not structural and re.search(r"\b(?:ImportError|ModuleNotFoundError|NameError|SyntaxError|AttributeError|TypeError|IndentationError|TabError):", stderr):
        return set()
    return {test_id for test_id in verify_scope.parse_test_failures(stderr)
            if structural or (not test_id.startswith("unittest.loader._FailedTest.") and "._FailedTest." not in test_id)}


def compiles(root: Path, relative: str) -> bool:
    run = subprocess.run([sys.executable, "-m", "py_compile", relative], cwd=root,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return run.returncode == 0


def cleanup_tree(path: Path) -> None:
    verify_scope.cleanup_worktree(path, ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--target", default="WORKTREE")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output")
    parser.add_argument("--wide", action="store_true", help="include the full derived module sweep")
    parser.add_argument("--hunk", type=int, action="append", help="limit to a one-based diff hunk (diagnostic reconstruction)")
    parser.add_argument("--interrupt-after-revert", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    live_before = verify_scope.tree_fingerprint(ROOT)
    base = verify_scope.resolve_base(ROOT, args.base, args.target)
    target = args.target if args.target == "WORKTREE" else verify_scope.git(ROOT, "rev-parse", args.target).strip()
    verify_scope.cleanup_stale_temp_worktrees(ROOT)
    diff_args = ["diff", "--unified=0", "--no-ext-diff", base]
    if target != "WORKTREE": diff_args.append(target)
    diff_args.extend(["--", "src/hengbot"])
    hunks = parse_hunks(verify_scope.git(ROOT, *diff_args))
    if args.hunk:
        selected = set(args.hunk)
        hunks = [hunk for number, hunk in enumerate(hunks, 1) if number in selected]
    scope = verify_scope.derive_scope(ROOT, base, target)
    preferred = []
    for path in scope["paths"]:
        if re.fullmatch(r"tests/test_[^/]+\.py", path):
            preferred.append(f"tests.{Path(path).stem}")
    for path in scope["symbols"]:
        preferred.append(f"tests.test_{Path(path).stem}")
    preferred = list(dict.fromkeys(m for m in preferred if m in scope["modules"]))
    candidates = preferred + ([m for m in scope["modules"] if m not in preferred] if args.wide else [])
    sandbox, _ = prepare_tree(target)
    original = file_hashes(sandbox)
    original_bytes = {rel: (sandbox / rel).read_bytes() for rel in original}
    results = []
    try:
        baseline: dict[str, set[str]] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(run_candidate, sandbox, module, args.timeout,
                                ROOT / "jsonlog" / "hunk-guard" / f"baseline-{module}.stderr.log"): module
                    for module in candidates}
            for job in as_completed(jobs):
                baseline[jobs[job]] = job.result()
        for number, group in enumerate(group_hunks(hunks), 1):
            kinds = [classify(hunk["body"]) for hunk in group]
            behavioral = [hunk for hunk, kind in zip(group, kinds) if kind == "behavioral"]
            files = list(dict.fromkeys(str(h["file"]) for h in group))
            record = {"file": files[0] if len(files) == 1 else files,
                      "lines": [min(int(h["line_start"]) for h in group), max(int(h["line_end"]) for h in group)],
                      "grouped_hunks": len(group),
                      "classification": "behavioral" if behavioral else kinds[0]}
            if not behavioral:
                record["protecting_test_id"] = None
                record["result"] = "SKIPPED"
                results.append(record); continue
            new_file = any(hunk["new_file"] for hunk in group)
            for hunk in reversed(group):
                relative = str(hunk["file"])
                if hunk["new_file"]:
                    if (sandbox / relative).exists():
                        (sandbox / relative).unlink()
                else:
                    apply_patch(sandbox, str(hunk["patch"]), reverse=True)
            try:
                if args.interrupt_after_revert:
                    raise KeyboardInterrupt("simulated interrupt")
                protector = None
                if new_file or all(compiles(sandbox, path) for path in files):
                    for module in candidates:
                        failures = run_candidate(sandbox, module, args.timeout,
                            ROOT / "jsonlog" / "hunk-guard" / f"hunk-{number}-{module}.stderr.log", structural=new_file)
                        new_failures = failures - baseline[module]
                        if new_failures:
                            protector = sorted(new_failures)[0]; break
                record["protecting_test_id"] = protector
                record["result"] = "PROTECTED" if protector else "UNPROTECTED"
                results.append(record)
            finally:
                for rel, content in original_bytes.items():
                    (sandbox / rel).write_bytes(content)
                if file_hashes(sandbox) != original:
                    raise RuntimeError(f"sandbox tree hash mismatch after hunk {number}")
        payload = {"tool": {"name": "hunk_guard", "version": VERSION, "base_ref": base, "target": target,
                            "tree_fingerprint": verify_scope.tree_fingerprint(sandbox)},
                   "candidate_modules": candidates, "hunks": results,
                   "summary": {"protected": sum(r["result"] == "PROTECTED" for r in results),
                               "unprotected": sum(r["result"] == "UNPROTECTED" for r in results),
                               "new_file_unverified": sum(r["result"] == "NEW-FILE-UNVERIFIED" for r in results),
                               "skipped": sum(r["result"] == "SKIPPED" for r in results)}}
        if not any(r["classification"] == "behavioral" for r in results):
            payload["warnings"] = ["NO-BEHAVIORAL-HUNKS"]
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        print(rendered)
        print(f"hunk_guard: {payload['summary']['protected']} protected, {payload['summary']['unprotected']} UNPROTECTED, {payload['summary']['skipped']} explicitly skipped", file=sys.stderr)
        if args.output: Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        return int(payload["summary"]["unprotected"] > 0 or payload["summary"]["new_file_unverified"] > 0)
    finally:
        for rel, content in original_bytes.items():
            (sandbox / rel).write_bytes(content)
        if file_hashes(sandbox) != original:
            raise RuntimeError("sandbox tree hash mismatch during final restoration")
        cleanup_tree(sandbox)
        verify_scope.git(ROOT, "worktree", "prune", check=False)
        if verify_scope.tree_fingerprint(ROOT) != live_before:
            raise RuntimeError("live tree fingerprint changed")


if __name__ == "__main__":
    raise SystemExit(main())
