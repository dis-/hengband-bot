#!/usr/bin/env python3
"""Derive and run the verification scope for a Hengbot change."""

from __future__ import annotations

import argparse
import atexit
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
WORKTREE_OWNER_FILE = ".hengbot-gate-owner.json"
STALE_WORKTREE_AGE_SECONDS = 24 * 60 * 60
ALWAYS_MODULES = {"tests.test_policy", "tests.test_cli", "tests.test_absorbing_states"}
LINTS = ("scripts/sale_key_lint.py", "scripts/test_fakery_lint.py")
EXCLUDED_TESTS = {
    "test_cli.DecisionTimingTest": "known hang; exclusion required by SOL-TASK-verification-gates.md",
}
KNOWN_FAILURES = (
    {
        "module": "tests.test_shop_one_shot",
        "pattern": "evidence-sale-inflight-lines.jsonl",
        "count": 1,
        "reason": "pre-existing missing artifact",
        "date": "2026-08-18",
    },
    {
        "module": "tests.test_home_knowledge_scan",
        "pattern": "stalled-capture",
        "count": 1,
        "reason": "pre-existing missing artifact",
        "date": "2026-08-18",
    },
    {
        "module": "tests.test_home_visit",
        "pattern": "FileNotFoundError",
        "count": 4,
        "reason": "artifact-dependent; required incident-captures/ and evidence/ files were destroyed by the gate junction incident on 2026-08-18 and no backup exists",
        "date": "2026-08-18",
    },
    {
        "module": "tests.test_worldmap_key_hygiene",
        "pattern": "FileNotFoundError",
        "count": 1,
        "reason": "artifact-dependent; required incident-captures/ and evidence/ files were destroyed by the gate junction incident on 2026-08-18 and no backup exists",
        "date": "2026-08-18",
    },
    {
        "module": "tests.test_test_fakery_lint",
        "pattern": "test_tree_has_only_catalogued_undeclared_shapes",
        "count": 1,
        "reason": "same 9 undeclared shapes already count-exactly allowed for scripts/test_fakery_lint.py",
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

_ACTIVE_WORKTREES: set[Path] = set()


def is_reparse_point(path: Path) -> bool:
    """Return true for symlinks and Windows junctions without following them."""
    if path.is_symlink():
        return True
    try:
        return bool(path.lstat().st_file_attributes & 0x400)
    except (AttributeError, FileNotFoundError, OSError):
        return False


def refuse_reparse_points(root: Path) -> None:
    """Fail before recursive cleanup if any entry could escape *root*."""
    if not root.exists():
        return
    pending = [root]
    while pending:
        current = pending.pop()
        if current != root and is_reparse_point(current):
            raise RuntimeError(f"refusing recursive cleanup through reparse point: {current}")
        if current.is_dir():
            pending.extend(current.iterdir())


def prune_worktrees(root: Path = ROOT) -> None:
    git(root, "worktree", "prune", check=False)


def cleanup_stale_temp_worktrees(root: Path = ROOT) -> None:
    """Recover registered gate worktrees left behind by an uncatchable kill."""
    listing = git(root, "worktree", "list", "--porcelain", check=False)
    registered = {Path(value).resolve() for value in re.findall(r"^worktree (.+)$", listing, re.MULTILINE)}
    for path in registered:
        if path.name.startswith(("hengbot-verify-", "hengbot-hunk-")) and path != root:
            owner = read_worktree_owner(path)
            if owner is None or not owner_is_live(owner):
                cleanup_worktree(path, root)
    # A kill can land after directory creation but before `git worktree add`
    # registers it.  Reclaim only old, gate-named siblings whose owner is not
    # live; the age threshold deliberately favors leaks over racing a process.
    temp_root = Path(tempfile.gettempdir())
    now = time.time()
    for path in temp_root.iterdir():
        if (path.resolve() in registered or not path.is_dir()
                or not path.name.startswith(("hengbot-verify-", "hengbot-hunk-"))):
            continue
        owner = read_worktree_owner(path)
        try:
            started = float(owner["started"]) if owner else path.stat().st_mtime
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if now - started > STALE_WORKTREE_AGE_SECONDS and not (owner and owner_is_live(owner, now)):
            refuse_reparse_points(path)
            shutil.rmtree(path)
            worktree_owner_path(path).unlink(missing_ok=True)
    prune_worktrees(root)


def record_worktree_owner(path: Path) -> None:
    worktree_owner_path(path).write_text(json.dumps({
        "pid": os.getpid(), "started": time.time(),
    }), encoding="utf-8")


def worktree_owner_path(path: Path) -> Path:
    return path.with_name(path.name + WORKTREE_OWNER_FILE)


def read_worktree_owner(path: Path) -> dict[str, object] | None:
    try:
        return json.loads(worktree_owner_path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            exit_code = ctypes.c_ulong()
            queried = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            return bool(queried and exit_code.value == 259)  # STILL_ACTIVE
        # ERROR_INVALID_PARAMETER means there is no process with this PID.
        # Access denied is deliberately treated as live.
        return ctypes.get_last_error() != 87
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as error:
        # Windows reports ERROR_INVALID_PARAMETER for a PID that does not
        # exist; it is the os.kill(pid, 0) equivalent of ESRCH.
        return getattr(error, "winerror", None) != 87
    return True


def owner_is_live(owner: dict[str, object], now: float | None = None) -> bool:
    try:
        pid, started = int(owner["pid"]), float(owner["started"])
    except (KeyError, TypeError, ValueError):
        return False
    return process_is_running(pid)


def cleanup_worktree(path: Path, root: Path = ROOT) -> None:
    """Remove a detached worktree only after proving it contains no links."""
    path = path.resolve()
    if path.exists():
        refuse_reparse_points(path)
    # Unregister before deleting: a kill between these operations leaves an
    # unregistered directory that the startup sweep can safely reclaim.
    git(root, "worktree", "remove", "--force", str(path), check=False)
    if path.exists():
        shutil.rmtree(path)
    worktree_owner_path(path).unlink(missing_ok=True)
    prune_worktrees(root)
    _ACTIVE_WORKTREES.discard(path)


def cleanup_active_worktrees() -> None:
    for path in list(_ACTIVE_WORKTREES):
        try:
            cleanup_worktree(path)
        except Exception:
            # Never turn interpreter shutdown into an unsafe recursive retry.
            pass


atexit.register(cleanup_active_worktrees)


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


def test_paths_at(root: Path, target: str) -> list[str]:
    if target == "WORKTREE":
        return [str(path.relative_to(root)).replace("\\", "/")
                for path in sorted((root / "tests").glob("test_*.py"))]
    return [path for path in git(root, "ls-tree", "-r", "--name-only", target, "tests").splitlines()
            if re.fullmatch(r"tests/test_[^/]+\.py", path)]


def test_modules_referencing(root: Path, target: str, symbols: dict[str, list[str]]) -> set[str]:
    names = {name for values in symbols.values() for name in values if name != "<module>"}
    modules: set[str] = set()
    for relative in test_paths_at(root, target):
        text = source_at(root, target, relative)
        if any(re.search(rf"\b{re.escape(name)}\b", text) for name in names):
            modules.add(f"tests.{Path(relative).stem}")
    return modules


def derive_scope(root: Path, base: str, target: str) -> dict[str, object]:
    paths = changed_paths(root, base, target)
    symbols = changed_symbols(root, base, target, paths)
    modules = test_modules_referencing(root, target, symbols) | ALWAYS_MODULES
    target_tests = set(test_paths_at(root, target))
    for path in symbols:
        owner = root / "tests" / f"test_{Path(path).stem}.py"
        relative = str(owner.relative_to(root)).replace("\\", "/")
        if relative in target_tests:
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
    verbose = re.findall(
        r"^(test\S+) \(([^)]+)\)(?:\n(?![-=]{5})[^\n]+)?\n? \.\.\. (?:FAIL|ERROR)$",
        stderr, re.MULTILINE,
    )
    headers = re.findall(r"^(?:FAIL|ERROR): (test\S+) \(([^)]+)\)$", stderr, re.MULTILINE)
    return list(dict.fromkeys(qualified for _name, qualified in verbose + headers))


def parse_test_errors(stderr: str) -> list[str]:
    return list(dict.fromkeys(qualified for _name, qualified in re.findall(
        r"^ERROR: (test\S+) \(([^)]+)\)$", stderr, re.MULTILINE)))


def known_failure_matches(key: str, stderr: str, failure_ids: list[str]) -> list[dict[str, str]]:
    matches = [entry for entry in KNOWN_FAILURES if entry["module"] == key and entry["pattern"] in stderr]
    return matches if len(matches) == 1 and len(failure_ids) == matches[0]["count"] else []


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
        error_ids = parse_test_errors(output)
        failed_count = len(undeclared_lint_findings) if lint_allowance else (len(reported_failures) or len(lint_findings))
        return {"status": status, "failed": failed_count, "skipped": len(re.findall(r"\.\.\. skipped ", output)),
                "failing_test_ids": reported_failures, "errors": error_ids, "duration": round(time.monotonic() - started, 3),
                "stderr_path": stderr_label,
                "known_failures": known}
    except subprocess.TimeoutExpired:
        partial = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
        failures = parse_test_failures(partial)
        return {"status": "error", "failed": len(failures),
                "skipped": len(re.findall(r"\.\.\. skipped ", partial)),
                "failing_test_ids": failures, "errors": [f"timeout after {timeout}s", *parse_test_errors(partial)],
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
    """Copy ignored evidence into a worktree; never link, move, or touch source."""
    present = {}
    for name in ("incident-captures", "evidence"):
        src, dst = source / name, destination / name
        present[name] = src.is_dir()
        if src.is_dir():
            before = artifact_inventory(source)[name]
            shutil.copytree(src, dst, copy_function=shutil.copy2)
            if is_reparse_point(dst) or artifact_inventory(source)[name] != before:
                raise RuntimeError(f"unsafe or source-mutating artifact copy: {name}")
    return present


def allowlist_coverage(results: dict[str, dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    failure_entries = []
    for entry in KNOWN_FAILURES:
        if entry["module"] in results:
            matched = entry in results[entry["module"]].get("known_failures", [])
            failure_entries.append({**entry, "matched": matched})
    lint_entries = []
    for module, entry in KNOWN_LINT_FAILURES.items():
        if module in results:
            matched = entry in results[module].get("known_failures", [])
            lint_entries.append({"module": module, **entry, "matched": matched})
    return {"known_failures": failure_entries, "known_lint_failures": lint_entries}


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
    cleanup_stale_temp_worktrees(ROOT)
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
            record_worktree_owner(temp)
            git(ROOT, "worktree", "add", "--detach", str(temp), target)
            _ACTIVE_WORKTREES.add(temp.resolve())
            run_root = temp
            # Gate implementations are always the reviewed live scripts; the
            # selected commit supplies only the product and its tests.
            shutil.copytree(ROOT / "scripts", temp / "scripts", dirs_exist_ok=True)
            copy_runtime_artifacts(ROOT, temp)
        results = {} if args.derive_only else run_scope(run_root, scope, args.timeout, ROOT / "jsonlog" / "verify-scope")
        coverage = allowlist_coverage(results)
        dead_allowances = [entry for values in coverage.values() for entry in values if not entry["matched"]]
        evidence = {"tool": {"name": "verify_scope", "version": VERSION, "base_ref": base, "target": target,
                             "tree_fingerprint": tree_fingerprint(run_root)},
                    "runtime_artifacts": artifacts,
                    "derived": scope, "known_untested_paths": EXCLUDED_TESTS, "known_failure_list": KNOWN_FAILURES,
                    "allowlist_coverage": coverage, "modules": results}
        rendered = json.dumps(evidence, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        return int(bool(dead_allowances) or any(item["status"] in {"failed", "error"} for item in results.values()))
    finally:
        if temp:
            cleanup_worktree(temp, ROOT)
        after = tree_fingerprint(ROOT)
        if before != after:
            raise RuntimeError(f"live tree fingerprint changed: {before} != {after}")


if __name__ == "__main__":
    raise SystemExit(main())
