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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import verify_scope

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.0"
INELIGIBLE_PROTECTORS = {
    # Review ground truth: these direct contract assertions do not pin the
    # end-to-end repost behavior claimed by a961376.
    "test_cli.UniversalPostingContractTest.test_autodestroy_repost_requires_position_effect",
    "test_cli.UniversalPostingContractTest.test_volley_repost_requires_selected_ammo_consumption",
}


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
        before = "\n".join(line[1:] for line in body if line[:1] in {" ", "-"})
        after = "\n".join(line[1:] for line in body if line[:1] in {" ", "+"})
        if before and after and ast_equivalent(before, after):
            return "nonbehavioral-ast-equivalent"
    except SyntaxError:
        pass
    return "behavioral"


def ast_equivalent(before: str, after: str) -> bool:
    import ast
    return ast.dump(ast.parse(before), include_attributes=False) == ast.dump(ast.parse(after), include_attributes=False)


def prepare_tree(target: str) -> tuple[Path, Path]:
    temp = Path(tempfile.mkdtemp(prefix="hengbot-hunk-"))
    commit = "HEAD" if target == "WORKTREE" else target
    verify_scope.git(ROOT, "worktree", "add", "--detach", str(temp), commit)
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


def run_candidate(root: Path, module: str, timeout: float, stderr_path: Path) -> set[str]:
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(root / "src"), str(root / "tests")))
    command = [sys.executable, "-c", verify_scope._test_code(module)]
    try:
        with stderr_path.open("w", encoding="utf-8") as err:
            run = subprocess.run(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=err,
                                 text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {f"{module}:TIMEOUT"}
    if run.returncode == 0:
        return set()
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"\b(?:ImportError|ModuleNotFoundError|NameError|SyntaxError):", stderr):
        return set()
    return set(verify_scope.parse_test_failures(stderr))


def compiles(root: Path, relative: str) -> bool:
    run = subprocess.run([sys.executable, "-m", "py_compile", relative], cwd=root,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return run.returncode == 0


def cleanup_tree(path: Path) -> None:
    verify_scope.git(ROOT, "worktree", "remove", "--force", str(path), check=False)
    shutil.rmtree(path, ignore_errors=True)


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
        for number, hunk in enumerate(hunks, 1):
            kind = classify(hunk["body"])
            record = {"file": hunk["file"], "lines": [hunk["line_start"], hunk["line_end"]], "classification": kind}
            if kind != "behavioral":
                record["protecting_test_id"] = None
                record["result"] = "SKIPPED"
                results.append(record); continue
            if hunk["new_file"]:
                record["protecting_test_id"] = None
                record["result"] = "NEW-FILE-UNVERIFIED"
                results.append(record); continue
            apply_patch(sandbox, hunk["patch"], reverse=True)
            try:
                if args.interrupt_after_revert:
                    raise KeyboardInterrupt("simulated interrupt")
                protector = None
                if compiles(sandbox, str(hunk["file"])):
                    for module in candidates:
                        failures = run_candidate(sandbox, module, args.timeout,
                            ROOT / "jsonlog" / "hunk-guard" / f"hunk-{number}-{module}.stderr.log")
                        new_failures = failures - baseline[module] - INELIGIBLE_PROTECTORS
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
