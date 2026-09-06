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
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

import verify_scope
from failure_headers import failure_sections

ROOT = Path(__file__).resolve().parents[1]
VERSION = "3.0"
DEFAULT_MODULE_TIMEOUT = 900.0
# Python's unified-diff generator joins edits separated by at most this many
# unchanged lines at the default context width (3 + 3 + two boundary lines).
ADJACENT_HUNK_GAP = 8


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
                and int(hunk["line_start"]) - int(groups[-1][-1]["line_end"]) <= ADJACENT_HUNK_GAP):
            groups[-1].append(hunk)
        else:
            groups.append([hunk])
    return groups


def prepare_tree(target: str) -> tuple[Path, Path]:
    temp = Path(tempfile.mkdtemp(prefix="hengbot-hunk-"))
    commit = "HEAD" if target == "WORKTREE" else target
    verify_scope.record_worktree_owner(temp)
    verify_scope.git(ROOT, "worktree", "add", "--detach", str(temp), commit)
    verify_scope._ACTIVE_WORKTREES.add(temp.resolve())
    if target == "WORKTREE":
        for area in ("src", "tests"):
            source = ROOT / area
            destination = temp / area
            if destination.exists(): shutil.rmtree(destination)
            shutil.copytree(source, destination)
    verify_scope.copy_runtime_artifacts(ROOT, temp)
    return temp, temp


def apply_patch(root: Path, patch: str, reverse: bool) -> None:
    command = ["git", "apply", "--unidiff-zero", "--whitespace=nowarn", "--ignore-space-change"]
    if reverse: command.append("--reverse")
    run = subprocess.run(command, cwd=root, input=patch, text=True, encoding="utf-8",
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run.returncode:
        raise RuntimeError(f"git apply failed: {run.stderr.strip()}")


def introduced_symbols(body: list[str]) -> set[str]:
    """Return identifiers defined or imported by the added side of a hunk."""
    import ast
    added = textwrap.dedent("\n".join(
        line[1:].rstrip("\r\n") for line in body
        if line.startswith("+") and not line.startswith("+++")))
    if not added.strip():
        return set()
    try:
        tree = ast.parse(added)
    except SyntaxError:
        # A zero-context hunk is often only part of a suite/function.  These
        # forms cover the names whose absence produces the structural errors
        # this discriminator is intended to reject.
        patterns = (
            r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_]\w*)",
            r"^\s*([A-Za-z_]\w*)\s*(?::[^=]+)?=",
            r"^\s*import\s+([A-Za-z_]\w*)",
            r"^\s*from\s+\S+\s+import\s+([A-Za-z_]\w*)",
        )
        return {match.group(1) for line in added.splitlines()
                for pattern in patterns if (match := re.search(pattern, line))}
    names: set[str] = set()
    def assigned_names(target: ast.expr) -> set[str]:
        if isinstance(target, ast.Name):
            return {target.id}
        if isinstance(target, ast.Attribute):
            return {target.attr}
        if isinstance(target, (ast.Tuple, ast.List)):
            return set().union(*(assigned_names(item) for item in target.elts))
        return set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(name for target in targets for name in assigned_names(target))
    return names


def _failure_sections(stderr: str) -> dict[str, str]:
    return failure_sections(stderr, test_names_only=True)


def _is_incoherent_revert(section: str, root: Path, reverted_file: str,
                          symbols: set[str]) -> bool:
    if not symbols or not section.startswith("ERROR:"):
        return False
    frames = re.findall(r'^\s*File "([^"]+)", line \d+', section, re.MULTILINE)
    if not frames:
        return False
    deepest = Path(frames[-1])
    expected = (root / reverted_file).resolve()
    try:
        if deepest.resolve() != expected:
            return False
    except OSError:
        return False
    messages = (
        re.search(r"(?:NameError|UnboundLocalError): name '([^']+)'", section),
        re.search(r"AttributeError: .* has no attribute '([^']+)'", section),
        re.search(r"(?:ImportError|ModuleNotFoundError): .*?(?:name |module named )['\"]?([A-Za-z_]\w*)", section),
    )
    return any(match and match.group(1) in symbols for match in messages)


@dataclass(frozen=True)
class CandidateResult:
    status: str
    failures: frozenset[str] = frozenset()


def _artifact_failure(stderr: str) -> bool:
    return bool(re.search(
        r"(?:FileNotFoundError|No such file or directory|could not find|missing (?:artifact|fixture))",
        stderr, re.IGNORECASE))


def run_candidate(root: Path, module: str, timeout: float, stderr_path: Path,
                  reverted_file: str | None = None,
                  symbols: set[str] | None = None) -> CandidateResult:
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(root / "src"), str(root / "tests")))
    command = [sys.executable, "-c", verify_scope._test_code(module)]
    try:
        with stderr_path.open("w", encoding="utf-8") as err:
            run = subprocess.run(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=err,
                                 text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return CandidateResult("TIMEOUT")
    if run.returncode == 0:
        return CandidateResult("PASS")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    # Classify each reported failure independently.  A real test may quite
    # legitimately pin behavior by asserting that an exception is raised;
    # exception text elsewhere in the same module run must not erase it.
    # unittest's loader/collection failures are the structural non-pins.
    sections = _failure_sections(stderr)
    reported = set(verify_scope.parse_test_failures(stderr))
    artifact_failures = {test_id for test_id in reported
                         if _artifact_failure(sections.get(test_id, ""))}
    failures = {test_id for test_id in reported
            if not test_id.startswith("unittest.loader._FailedTest.")
            and "._FailedTest." not in test_id
            and test_id not in artifact_failures
            and not (reverted_file and _is_incoherent_revert(
                sections.get(test_id, ""), root, reverted_file, symbols or set()))}
    if not failures and (artifact_failures or _artifact_failure(stderr)):
        return CandidateResult("ARTIFACT-SKIPPED")
    return CandidateResult("FAIL" if failures else "ERROR", frozenset(failures))


def compiles(root: Path, relative: str) -> bool:
    run = subprocess.run([sys.executable, "-m", "py_compile", relative], cwd=root,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return run.returncode == 0


def hunk_symbols(root: Path, target: str, group: list[dict[str, object]]) -> set[str]:
    """Return changed names plus enclosing top-level definitions for a hunk."""
    import ast
    names = set().union(*(introduced_symbols(hunk["body"]) for hunk in group))
    for hunk in group:
        text = verify_scope.source_at(root, target, str(hunk["file"]))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        start, end = int(hunk["line_start"]), int(hunk["line_end"])
        enclosing = [node for node in ast.walk(tree)
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and node.lineno <= end and getattr(node, "end_lineno", node.lineno) >= start]
        if enclosing:
            smallest_span = min(getattr(node, "end_lineno", node.lineno) - node.lineno
                                for node in enclosing)
            names.update(node.name for node in enclosing
                         if getattr(node, "end_lineno", node.lineno) - node.lineno == smallest_span)
    return names


def modules_for_hunk(root: Path, target: str, group: list[dict[str, object]],
                     candidates: list[str]) -> list[str]:
    names = hunk_symbols(root, target, group)
    owners = {f"tests.test_{Path(str(h['file'])).stem}" for h in group}
    selected = []
    for module in candidates:
        relative = "tests/" + module.removeprefix("tests.") + ".py"
        source = verify_scope.source_at(root, target, relative)
        if module in owners or any(re.search(rf"\b{re.escape(name)}\b", source) for name in names):
            selected.append(module)
    return selected


def source_text_only_tests(root: Path, target: str, modules: list[str]) -> set[tuple[str, str]]:
    """Return lint-identified source-text-only tests, which cannot protect code."""
    try:
        import test_fakery_lint
    except ImportError:
        return set()
    result = set()
    for module in modules:
        relative = "tests/" + module.removeprefix("tests.") + ".py"
        source = verify_scope.source_at(root, target, relative)
        for finding in test_fakery_lint.analyze_source(source, Path(relative)):
            if finding.rule == "source-text-only-assertions":
                result.add((module, finding.test))
    return result


def cleanup_tree(path: Path) -> None:
    verify_scope.cleanup_worktree(path, ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=("UNPROTECTED means no protection among the candidate_modules listed in the verdict. "
                "REVERT-UNAPPLIABLE is indeterminate; verify by manual revert."))
    parser.add_argument("--base")
    parser.add_argument("--target", default="WORKTREE")
    parser.add_argument("--timeout", type=float, default=DEFAULT_MODULE_TIMEOUT,
                        help="per-module timeout (default: %(default)ss)")
    parser.add_argument("--budget-seconds", type=float,
                        help="total hunk-evaluation budget; remaining hunks are reported NOT-EVALUATED")
    parser.add_argument("--output")
    parser.add_argument("--wide", action="store_true", help="include the full derived module sweep")
    parser.add_argument("--hunk", type=int, action="append", help="limit to a one-based diff hunk (diagnostic reconstruction)")
    parser.add_argument("--interrupt-after-revert", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.budget_seconds is not None and args.budget_seconds < 0:
        parser.error("timeouts and budgets must be positive (a zero budget is allowed)")
    started = time.monotonic()
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
    groups = group_hunks(hunks)
    per_group_candidates = [modules_for_hunk(ROOT, target, group, candidates) for group in groups]
    candidates = list(dict.fromkeys(module for modules in per_group_candidates for module in modules))
    sandbox, _ = prepare_tree(target)
    run_log_dir = ROOT / "jsonlog" / "hunk-guard" / (
        f"run-{time.time_ns()}-{os.getpid()}")
    original = file_hashes(sandbox)
    original_bytes = {rel: (sandbox / rel).read_bytes() for rel in original}
    results = []
    try:
        baseline: dict[str, CandidateResult] = {}
        remaining = None if args.budget_seconds is None else args.budget_seconds - (time.monotonic() - started)
        baseline_timeout = args.timeout if remaining is None else max(0.001, min(args.timeout, remaining))
        baseline_candidates = candidates if remaining is None or remaining > 0 else []
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(run_candidate, sandbox, module, baseline_timeout,
                                run_log_dir / f"baseline-{module}.stderr.log"): module
                    for module in baseline_candidates}
            for job in as_completed(jobs):
                baseline[jobs[job]] = job.result()
        ineligible = source_text_only_tests(ROOT, target, candidates)
        for number, group in enumerate(groups, 1):
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
            hunk_candidates = per_group_candidates[number - 1]
            record["candidate_modules"] = hunk_candidates
            elapsed = time.monotonic() - started
            if args.budget_seconds is not None and elapsed >= args.budget_seconds:
                record.update(protecting_test_id=None, result="NOT-EVALUATED",
                              reason="BUDGET-EXHAUSTED")
                results.append(record); continue
            new_file = any(hunk["new_file"] for hunk in group)
            try:
                try:
                    for hunk in reversed(group):
                        relative = str(hunk["file"])
                        if hunk["new_file"]:
                            if (sandbox / relative).exists():
                                (sandbox / relative).unlink()
                        else:
                            apply_patch(sandbox, str(hunk["patch"]), reverse=True)
                except RuntimeError as error:
                    record.update(protecting_test_id=None, result="REVERT-UNAPPLIABLE",
                                  reason=str(error))
                    results.append(record); continue
                if args.interrupt_after_revert:
                    raise KeyboardInterrupt("simulated interrupt")
                protector = None
                outcomes = {}
                if not new_file and not all(compiles(sandbox, path) for path in files):
                    record.update(protecting_test_id=None, result="REVERT-UNAPPLIABLE",
                                  reason="reverse-patched source does not compile")
                elif not new_file:
                    symbols = set().union(*(introduced_symbols(hunk["body"]) for hunk in behavioral))
                    for module in hunk_candidates:
                        baseline_status = baseline.get(module, CandidateResult("NOT-EVALUATED")).status
                        if baseline_status not in {"PASS", "FAIL", "ERROR"}:
                            outcomes[module] = baseline_status
                            continue
                        remaining = None if args.budget_seconds is None else args.budget_seconds - (time.monotonic() - started)
                        if remaining is not None and remaining <= 0:
                            outcomes["budget"] = "NOT-EVALUATED"
                            break
                        timeout = args.timeout if remaining is None else min(args.timeout, remaining)
                        outcome = run_candidate(sandbox, module, timeout,
                            run_log_dir / f"hunk-{number}-{module}.stderr.log",
                            files[0] if len(files) == 1 else None, symbols)
                        outcomes[module] = outcome.status
                        new_failures = outcome.failures - baseline[module].failures
                        new_failures = {test_id for test_id in new_failures
                                        if not any(test_id.startswith(lint_module.removeprefix("tests.") + ".")
                                                   and test_id.endswith("." + method)
                                                   for lint_module, method in ineligible)}
                        if new_failures:
                            protector = sorted(new_failures)[0]; break
                    record["module_outcomes"] = outcomes
                    if protector:
                        record.update(protecting_test_id=protector, result="PROTECTED")
                    elif "TIMEOUT" in outcomes.values():
                        record.update(protecting_test_id=None, result="TIMEOUT")
                    elif "ARTIFACT-SKIPPED" in outcomes.values():
                        record.update(protecting_test_id=None, result="ARTIFACT-SKIPPED")
                    elif "NOT-EVALUATED" in outcomes.values():
                        record.update(protecting_test_id=None, result="NOT-EVALUATED",
                                      reason="BUDGET-EXHAUSTED")
                    else:
                        record.update(protecting_test_id=None, result="UNPROTECTED")
                else:
                    record.update(protecting_test_id=None, result="NEW-FILE-UNVERIFIED")
                results.append(record)
            finally:
                for rel, content in original_bytes.items():
                    (sandbox / rel).write_bytes(content)
                if file_hashes(sandbox) != original:
                    raise RuntimeError(f"sandbox tree hash mismatch after hunk {number}")
        payload = {"tool": {"name": "hunk_guard", "version": VERSION, "base_ref": base, "target": target,
                            "tree_fingerprint": verify_scope.tree_fingerprint(sandbox)},
                   "candidate_modules": candidates, "hunks": results,
                   "summary": {name.lower().replace("-", "_"): sum(r["result"] == name for r in results)
                               for name in ("PROTECTED", "UNPROTECTED", "REVERT-UNAPPLIABLE", "TIMEOUT",
                                            "ARTIFACT-SKIPPED", "NOT-EVALUATED", "NEW-FILE-UNVERIFIED", "SKIPPED")}}
        if not any(r["classification"] == "behavioral" for r in results):
            payload["warnings"] = ["NO-BEHAVIORAL-HUNKS"]
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        print(rendered)
        print("hunk_guard: " + ", ".join(f"{count} {name.upper().replace('_', '-')}"
              for name, count in payload["summary"].items()), file=sys.stderr)
        if args.output: Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        return int(any(r["result"] not in {"PROTECTED", "SKIPPED"} for r in results))
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
