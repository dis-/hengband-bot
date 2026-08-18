#!/usr/bin/env python3
"""Derive and run the verification scope for a Hengbot change."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0"
ALWAYS_MODULES = {"tests.test_policy", "tests.test_cli", "tests.test_absorbing_states"}
LINTS = ("scripts/sale_key_lint.py", "scripts/test_fakery_lint.py")
EXCLUDED_TESTS = {
    "test_cli.DecisionTimingTest": "known hang; exclusion required by SOL-TASK-verification-gates.md",
}
KNOWN_FAILURES = (
    {
        "module": "tests.test_shop_one_shot",
        "pattern": "evidence-sale-inflight-lines.jsonl",
        "reason": "pre-existing missing artifact",
        "date": "2026-08-18",
    },
    {
        "module": "tests.test_home_knowledge_scan",
        "pattern": "stalled_capture",
        "reason": "pre-existing missing artifact",
        "date": "2026-08-18",
    },
)
KNOWN_LINT_FAILURES = {
    "scripts/test_fakery_lint.py": {
        "count": 9,
        "reason": "pre-existing undeclared test-fakery findings; additions remain blocking",
        "date": "2026-08-18",
    },
}


def git(root: Path, *args: str, check: bool = True) -> str:
    run = subprocess.run(["git", *args], cwd=root, text=True, encoding="utf-8",
                         errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and run.returncode:
        raise RuntimeError(run.stderr.strip() or "git command failed")
    return run.stdout


def resolve_base(root: Path, base: str | None, target: str) -> str:
    if base:
        return git(root, "rev-parse", base).strip()
    if target != "WORKTREE":
        return git(root, "rev-parse", f"{target}^").strip()
    return git(root, "rev-parse", "HEAD").strip()


def changed_paths(root: Path, base: str, target: str) -> list[str]:
    end = None if target == "WORKTREE" else target
    args = ["diff", "--name-only", base]
    if end:
        args.append(end)
    return [line for line in git(root, *args).splitlines() if line]


def source_at(root: Path, ref: str, path: str) -> str:
    if ref == "WORKTREE":
        file = root / path
        return file.read_text(encoding="utf-8") if file.exists() else ""
    return git(root, "show", f"{ref}:{path}", check=False)


def top_level_symbols(source: str) -> dict[str, str]:
    if not source:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"<module>": source}
    result: dict[str, str] = {}
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [n.id for target in targets for n in ast.walk(target) if isinstance(n, ast.Name)]
        for name in names:
            result[name] = ast.dump(node, include_attributes=False)
    return result


def changed_symbols(root: Path, base: str, target: str, paths: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for path in paths:
        if not re.fullmatch(r"src/hengbot/[^/]+\.py", path):
            continue
        before = top_level_symbols(source_at(root, base, path))
        after = top_level_symbols(source_at(root, target, path))
        names = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        result[path] = names or ["<module>"]
    return result


def test_modules_referencing(root: Path, symbols: dict[str, list[str]]) -> set[str]:
    names = {name for values in symbols.values() for name in values if name != "<module>"}
    modules: set[str] = set()
    for path in sorted((root / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        if any(re.search(rf"\b{re.escape(name)}\b", text) for name in names):
            modules.add(f"tests.{path.stem}")
    return modules


def derive_scope(root: Path, base: str, target: str) -> dict[str, object]:
    paths = changed_paths(root, base, target)
    symbols = changed_symbols(root, base, target, paths)
    modules = test_modules_referencing(root, symbols) | ALWAYS_MODULES
    for path in symbols:
        owner = root / "tests" / f"test_{Path(path).stem}.py"
        if owner.exists():
            modules.add(f"tests.{owner.stem}")
    for path in paths:
        if re.fullmatch(r"tests/test_[^/]+\.py", path):
            modules.add(f"tests.{Path(path).stem}")
    return {"paths": paths, "symbols": symbols, "modules": sorted(modules), "lints": list(LINTS)}


def tree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    # The gate mutates tracked source only.  Hash every tracked byte; unrelated
    # untracked operator artifacts are intentionally outside its tree model.
    for rel in sorted(git(root, "ls-files").splitlines()):
        path = root / rel
        if path.is_file():
            digest.update(rel.encode()); digest.update(b"\0"); digest.update(path.read_bytes()); digest.update(b"\0")
    return digest.hexdigest()


def _test_code(module: str) -> str:
    bare = module.removeprefix("tests.")
    return f"""import sys
import unittest
s = unittest.defaultTestLoader.loadTestsFromName({bare!r})
def filtered(suite):
    result = unittest.TestSuite()
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            result.addTests(filtered(test))
        elif not any(test.id().startswith(prefix + '.') for prefix in {tuple(EXCLUDED_TESTS)!r}):
            result.addTest(test)
    return result
x = unittest.TextTestRunner(verbosity=2).run(filtered(s))
sys.exit(not x.wasSuccessful())
"""


def parse_test_failures(stderr: str) -> list[str]:
    """Return unittest ids, including verbose failures followed by docstrings."""
    pattern = r"^(test\S+) \(([^)]+)\)(?:\n[^\n]+)?\n? \.\.\. (?:FAIL|ERROR)$"
    return [qualified for _name, qualified in re.findall(pattern, stderr, re.MULTILINE)]


def known_failure_matches(key: str, stderr: str, failure_ids: list[str]) -> list[dict[str, str]]:
    matches = [entry for entry in KNOWN_FAILURES if entry["module"] == key and entry["pattern"] in stderr]
    return matches if len(failure_ids) == 1 and len(matches) == 1 else []


def run_item(root: Path, key: str, command: list[str], timeout: float, stderr_dir: Path) -> dict[str, object]:
    stderr_dir.mkdir(parents=True, exist_ok=True)
    stderr_path = stderr_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".stderr.log")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(root / "src"), str(root / "tests")))
    started = time.monotonic()
    try:
        stderr_label = str(stderr_path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        stderr_label = str(stderr_path)
    try:
        with stderr_path.open("w", encoding="utf-8") as err:
            run = subprocess.run(command, cwd=root, env=env, text=True, encoding="utf-8",
                                 errors="replace", stdout=subprocess.PIPE, stderr=err, timeout=timeout)
        stderr = stderr_path.read_text(encoding="utf-8")
        output = stderr + "\n" + run.stdout
        reported_failures = parse_test_failures(output)
        known = known_failure_matches(key, output, reported_failures)
        lint_allowance = KNOWN_LINT_FAILURES.get(key)
        lint_findings = [line for line in output.splitlines() if re.match(r"^tests/.+?:\d+: ", line)]
        undeclared_lint_findings = [line for line in lint_findings if "[DECLARED:" not in line]
        if lint_allowance and len(undeclared_lint_findings) == lint_allowance["count"]:
            known = [lint_allowance]
        status = "ran" if run.returncode == 0 else ("failed_known" if known else "failed")
        return {"status": status, "failed": len(reported_failures) or len(lint_findings), "skipped": stderr.count(" ... skipped "),
                "failing_test_ids": reported_failures, "errors": [], "duration": round(time.monotonic() - started, 3),
                "stderr_path": stderr_label,
                "known_failures": known}
    except subprocess.TimeoutExpired:
        return {"status": "error", "failed": 0, "skipped": 0, "errors": [f"timeout after {timeout}s"],
                "duration": round(time.monotonic() - started, 3), "stderr_path": stderr_label}


def run_scope(root: Path, scope: dict[str, object], timeout: float, stderr_dir: Path) -> dict[str, dict[str, object]]:
    work = [(module, [sys.executable, "-c", _test_code(module)]) for module in scope["modules"]]
    work += [(lint, [sys.executable, lint]) for lint in scope["lints"]]
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run_item, root, key, command, timeout, stderr_dir): key for key, command in work}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def copy_runtime_artifacts(source: Path, destination: Path) -> dict[str, bool]:
    """Link ignored evidence into commit worktrees so both modes see identical bytes."""
    present = {}
    for name in ("incident-captures", "evidence"):
        src, dst = source / name, destination / name
        present[name] = src.is_dir()
        if src.is_dir():
            try:
                os.symlink(src, dst, target_is_directory=True)
            except OSError:
                # Windows directory junctions do not require symlink privilege.
                run = subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if run.returncode:
                    raise RuntimeError(f"cannot expose runtime artifact {name}: {run.stderr.strip()}")
    return present


def artifact_inventory(root: Path) -> dict[str, list[str]]:
    return {
        name: sorted(str(path.relative_to(root / name)).replace("\\", "/")
                     for path in (root / name).rglob("*") if path.is_file())
        if (root / name).is_dir() else []
        for name in ("incident-captures", "evidence")
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--target", default="WORKTREE")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output")
    parser.add_argument("--derive-only", action="store_true")
    args = parser.parse_args(argv)
    before = tree_fingerprint(ROOT)
    base = resolve_base(ROOT, args.base, args.target)
    target = args.target if args.target == "WORKTREE" else git(ROOT, "rev-parse", args.target).strip()
    scope = derive_scope(ROOT, base, target)
    run_root = ROOT
    temp = None
    artifacts = artifact_inventory(ROOT)
    try:
        if target != "WORKTREE":
            temp = Path(tempfile.mkdtemp(prefix="hengbot-verify-"))
            git(ROOT, "worktree", "add", "--detach", str(temp), target)
            run_root = temp
            copy_runtime_artifacts(ROOT, temp)
        results = {} if args.derive_only else run_scope(run_root, scope, args.timeout, ROOT / "jsonlog" / "verify-scope")
        evidence = {"tool": {"name": "verify_scope", "version": VERSION, "base_ref": base, "target": target,
                             "tree_fingerprint": tree_fingerprint(run_root)},
                    "runtime_artifacts": artifacts,
                    "derived": scope, "known_untested_paths": EXCLUDED_TESTS, "known_failure_list": KNOWN_FAILURES,
                    "modules": results}
        rendered = json.dumps(evidence, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        return int(any(item["status"] in {"failed", "error"} for item in results.values()))
    finally:
        if temp:
            git(ROOT, "worktree", "remove", "--force", str(temp), check=False)
            shutil.rmtree(temp, ignore_errors=True)
            git(ROOT, "worktree", "prune", check=False)
        after = tree_fingerprint(ROOT)
        if before != after:
            raise RuntimeError(f"live tree fingerprint changed: {before} != {after}")


if __name__ == "__main__":
    raise SystemExit(main())
