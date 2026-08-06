#!/usr/bin/env python3
"""Find behavioural tests which manufacture the result they claim to prove."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, replace
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
ALLOW_MARKER = "TEST_FAKERY_LINT_ALLOW:"
_ALLOW_RE = re.compile(
    r"#\s*" + re.escape(ALLOW_MARKER) + r"\s*([a-z][a-z0-9-]*):\s*(\S.*)$"
)
_PUBLIC_METHODS = frozenset({"choose_key", "_decide"})
_PATH_METHODS = frozenset({"_decide", "_shop", "_observe"})


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    rule: str
    message: str
    test: str
    allowed_reason: str | None = None

    def render(self) -> str:
        suffix = f" [DECLARED: {self.allowed_reason}]" if self.allowed_reason else ""
        return f"{self.path.as_posix()}:{self.line}: {self.rule}: {self.message}{suffix}"


def _call_name(node: ast.AST) -> str | None:
    func = node.func if isinstance(node, ast.Call) else node
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


def _string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _receiver(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _replacement(call: ast.Call) -> tuple[str | None, str | None]:
    """Return receiver/member for patch.object, patch('...'), and setattr."""
    if (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "object"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "patch"
        and len(call.args) >= 2
    ):
        return _receiver(call.args[0]), _string(call.args[1])
    if _call_name(call) == "patch" and call.args:
        target = _string(call.args[0])
        if target and "." in target:
            return target.rsplit(".", 2)[-2], target.rsplit(".", 1)[-1]
    if _call_name(call) == "setattr" and len(call.args) >= 2:
        return _receiver(call.args[0]), _string(call.args[1])
    return None, None


def _assignments(function: ast.AST) -> list[tuple[int, str | None, str]]:
    result = []
    for node in ast.walk(function):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute):
                result.append((target.lineno, _receiver(target.value), target.attr))
        if isinstance(node, ast.Call):
            receiver, name = _replacement(node)
            if _call_name(node) == "setattr" and name:
                result.append((node.lineno, receiver, name))
    return result


def _callable_assignments(function: ast.AST) -> list[tuple[int, str | None, str]]:
    result = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, (ast.Lambda, ast.Name, ast.Attribute)):
            continue
        for target in node.targets:
            if isinstance(target, ast.Attribute):
                result.append((target.lineno, _receiver(target.value), target.attr))
    return result


def _fabricates_best_loadout(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg != "best":
            continue
        if any(
            nested.arg == "loadout"
            for node in ast.walk(keyword.value)
            if isinstance(node, ast.Call)
            for nested in node.keywords
        ):
            return True
    return False


def _loop_count(loop: ast.AST) -> int | None:
    if not isinstance(loop, (ast.For, ast.AsyncFor)) or not isinstance(loop.iter, ast.Call):
        return None
    if _call_name(loop.iter) != "range" or not loop.iter.args:
        return None
    values = [arg.value for arg in loop.iter.args if isinstance(arg, ast.Constant) and isinstance(arg.value, int)]
    if len(values) != len(loop.iter.args):
        return None
    if len(values) == 1:
        return values[0]
    if len(values) >= 2:
        step = values[2] if len(values) == 3 else 1
        return max(0, (values[1] - values[0] + step - 1) // step) if step > 0 else None
    return None


def _frozen_argument(argument: ast.AST) -> bool:
    if isinstance(argument, ast.Name):
        return True
    if isinstance(argument, ast.Call) and _call_name(argument) == "replace":
        # Advancing time is not applying the returned movement to player/grids.
        return bool(argument.args) and all(kw.arg in {"turn", "energy"} for kw in argument.keywords)
    return False


def _markers(lines: list[str]) -> dict[int, tuple[str, str]]:
    result = {}
    for lineno, line in enumerate(lines, 1):
        match = _ALLOW_RE.search(line)
        if match:
            result[lineno] = (match.group(1), match.group(2).strip())
    return result


def analyze_source(source: str, path: Path = Path("fixture.py")) -> list[Finding]:
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines()
    markers = _markers(lines)
    findings: list[Finding] = []

    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for function in functions:
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
        public_calls = [call for call in calls if _call_name(call) in _PUBLIC_METHODS]
        assignments = _assignments(function)
        replacements = []
        for call in calls:
            receiver, name = _replacement(call)
            if name and name.startswith("_"):
                replacements.append((call.lineno, receiver, name))
        # Direct method assignment matters for public-path tests (including the
        # historical 13-method wrapper), but ordinary private units commonly
        # construct state with similarly named attributes.
        if public_calls:
            replacements.extend((line, receiver, name) for line, receiver, name in _callable_assignments(function) if name.startswith("_"))

        def add(line: int, rule: str, message: str) -> None:
            findings.append(Finding(path, line, rule, message, function.name))

        for call in calls:
            name = _call_name(call) or ""
            consumers = {"_dungeon_entry_allowed", "_equipment_departure_ready", "_departure_ready"}
            if (name.startswith("set_completed_") or (name.startswith("_mark_") and name.endswith("_complete"))) and any(
                _call_name(candidate) in consumers for candidate in calls
            ):
                add(call.lineno, "subject-precompleted", f"{function.name} pre-completes the subject under test")

        if public_calls:
            for line, _receiver_name, name in replacements:
                if name in _PATH_METHODS:
                    add(line, "public-path-replaced", f"{function.name} calls a public decision path after replacing {name}")

        asserted_attrs = {
            node.attr for node in ast.walk(function)
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
        }
        for line, _receiver_name, name in assignments:
            if any(token in name for token in ("_pages", "_catalog", "_input_key", "_inflight")) and (
                name in asserted_attrs or public_calls or name == "_home_address_pages"
            ):
                add(line, "private-state-injected", f"{function.name} assigns derived state {name} before its effect is asserted")

        for node in ast.walk(function):
            if isinstance(node, ast.Call) and _fabricates_best_loadout(node):
                add(node.lineno, "pipeline-result-injected", f"{function.name} constructs a stand-in best/loadout pipeline result")
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "loadout":
                        add(target.lineno, "pipeline-result-injected", f"{function.name} hand-assigns a best/loadout pipeline result")

        if "incomplete_optimizer_blocks" in function.name.lower():
            for line, _receiver_name, name in assignments:
                if name == "_fundraising_mode":
                    add(line, "invariant-input-overwritten", f"{function.name} directly selects the mode in its invariant")

        aliases: dict[str, str] = {}
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = aliases.get(node.value.id, node.value.id)
        by_receiver: dict[str | None, set[str]] = {}
        for _line, receiver_name, name in replacements:
            if name not in _PATH_METHODS:
                receiver_name = aliases.get(receiver_name or "", receiver_name)
                by_receiver.setdefault(receiver_name, set()).add(name)
        for receiver_name, names in by_receiver.items():
            if len(names) >= 4:
                line = min(line for line, rec, name in replacements if aliases.get(rec or "", rec) == receiver_name and name in names)
                add(line, "collaborator-wall", f"{function.name} replaces {len(names)} collaborators of one object: " + ", ".join(sorted(names)))

        choose_collections = set()
        choose_results = set()
        constants: dict[str, str] = {}
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                constants.update({target.id: node.value.value for target in node.targets if isinstance(target, ast.Name)})
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and _call_name(node.value) == "choose_key":
                choose_results.update(target.id for target in node.targets if isinstance(target, ast.Name))
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.ListComp, ast.SetComp)):
                if any(isinstance(child, ast.Call) and _call_name(child) == "choose_key" for child in ast.walk(node.value)):
                    choose_collections.update(target.id for target in node.targets if isinstance(target, ast.Name))
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and _call_name(node) == "count" and node.args and _string(node.args[0]) is not None:
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id in choose_collections:
                    add(node.lineno, "literal-success-predicate", f"{function.name} judges a public drive by a literal returned key")
            if isinstance(node, ast.Compare):
                parts = (node.left, *node.comparators)
                names = {part.id for part in parts if isinstance(part, ast.Name)}
                has_literal = any(_string(part) is not None or (isinstance(part, ast.Name) and part.id in constants) for part in parts)
                if has_literal and names & choose_results:
                    add(node.lineno, "literal-success-predicate", f"{function.name} judges a public drive by a literal returned key")

        for loop in [node for node in ast.walk(function) if isinstance(node, (ast.For, ast.AsyncFor, ast.While))]:
            for call in [node for node in ast.walk(loop) if isinstance(node, ast.Call) and _call_name(node) == "choose_key"]:
                if call.args and _frozen_argument(call.args[0]):
                    count = _loop_count(loop)
                    direct_long_drive = isinstance(call.args[0], ast.Name) and (
                        isinstance(loop, ast.While) or (count is not None and count >= 99)
                    )
                    turn_only_replay = isinstance(call.args[0], ast.Call)
                    if direct_long_drive or turn_only_replay:
                        add(call.lineno, "frozen-drive-state", f"{function.name} repeatedly drives choose_key without applying returned movement")

    # A declaration is valid only on the finding line or immediately above it,
    # and only for that one rule. It therefore cannot widen when a test changes.
    used_markers = set()
    qualified = []
    for finding in findings:
        allowance = None
        for marker_line in range(finding.line, max(0, finding.line - 6), -1):
            marker = markers.get(marker_line)
            if marker and marker[0] == finding.rule:
                allowance = marker[1]
                used_markers.add(marker_line)
                break
            if marker_line < finding.line and lines[marker_line - 1].strip() and not lines[marker_line - 1].lstrip().startswith("#"):
                break
        qualified.append(replace(finding, allowed_reason=allowance) if allowance else finding)
    stale = sorted(set(markers) - used_markers)
    for line in stale:
        rule, _reason = markers[line]
        qualified.append(Finding(path, line, "stale-allowance", f"inline allowance for {rule} matches no finding", "<marker>"))
    return qualified


def scan_tests(tests: Path = TESTS) -> list[Finding]:
    findings = []
    for path in sorted(tests.rglob("test*.py")):
        relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        findings.extend(analyze_source(path.read_text(encoding="utf-8"), relative))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=TESTS)
    args = parser.parse_args()
    findings = scan_tests(args.path) if args.path.is_dir() else analyze_source(args.path.read_text(encoding="utf-8"), args.path)
    for finding in findings:
        print(finding.render())
    undeclared = [finding for finding in findings if not finding.allowed_reason]
    declared = [finding for finding in findings if finding.allowed_reason]
    print(f"test-fakery-lint: {len(undeclared)} violation(s), {len(declared)} declared finding(s) in {len({f.test for f in declared})} test(s)")
    return bool(undeclared)


if __name__ == "__main__":
    raise SystemExit(main())
