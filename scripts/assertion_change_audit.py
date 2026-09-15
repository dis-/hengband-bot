#!/usr/bin/env python3
"""Audit weakening or suspicious edits to existing tests."""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEAK = {"assertNotEqual", "assertIn", "assertTrue", "assertIsNotNone"}
FORBIDDEN = ("town-progress-invariant:defect:", "TOWN_PROGRESS_INVARIANT_DEFECT",
             "TOWN_LIVENESS_INVARIANT_DEFECT", "defect:=>")


@dataclass
class Function:
    assertions: list[tuple[str, str]]
    returns: list[str]
    expected_strings: list[str]
    comparisons: list[tuple[str, str]]


def source(node: ast.AST, text: str) -> str:
    return ast.get_source_segment(text, node) or ast.dump(node, include_attributes=False)


def functions(text: str) -> dict[str, Function]:
    try: tree = ast.parse(text)
    except SyntaxError: return {}
    result: dict[str, Function] = {}
    class Visitor(ast.NodeVisitor):
        scope: list[str] = []
        def visit_ClassDef(self, node):
            self.scope.append(node.name); self.generic_visit(node); self.scope.pop()
        def visit_FunctionDef(self, node):
            name = ".".join((*self.scope, node.name))
            assertions, returns, strings, comparisons = [], [], [], []
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr.startswith("assert"):
                    assertions.append((child.func.attr, source(child, text)))
                    for arg in child.args[1:]:
                        strings.extend(x.value for x in ast.walk(arg)
                                       if isinstance(x, ast.Constant) and isinstance(x.value, str))
                if isinstance(child, ast.Return) and child is not node:
                    returns.append(source(child, text))
                if isinstance(child, ast.Compare):
                    constants = [x for x in ast.walk(child) if isinstance(x, ast.Constant)]
                    if constants: comparisons.append((source(child, text), repr(tuple(x.value for x in constants))))
            result[name] = Function(assertions, returns, strings, comparisons)
    Visitor().visit(tree)
    return result


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, encoding="utf-8",
                          errors="replace", capture_output=True, check=check)


def test_paths(base: str, root: Path) -> list[str]:
    tracked = set(git("diff", "--name-only", base, "--", "tests", cwd=root).stdout.splitlines())
    untracked = set(git("ls-files", "--others", "--exclude-standard", "tests", cwd=root).stdout.splitlines())
    return sorted(path for path in tracked | untracked if path.endswith(".py"))


def audit(base: str, root: Path = ROOT) -> tuple[list[str], bool]:
    lines: list[str] = []
    fatal = False
    for rel in test_paths(base, root):
        old_run = git("show", f"{base}:{rel}", cwd=root, check=False)
        old_text = old_run.stdout if old_run.returncode == 0 else ""
        path = root / rel
        new_text = path.read_text(encoding="utf-8") if path.is_file() else ""
        old_funcs, new_funcs = functions(old_text), functions(new_text)
        for name in sorted(old_funcs.keys() & new_funcs.keys()):
            before, after = old_funcs[name], new_funcs[name]
            for index, assertion in enumerate(before.assertions):
                replacement = after.assertions[index] if index < len(after.assertions) else ("<removed>", "<removed>")
                if assertion != replacement:
                    lines.append(f"CHANGED {rel}:{name}\n  before: {assertion[1]}\n  after: {replacement[1]}")
                    if (len(before.assertions) == len(after.assertions)
                            and assertion[0] in {"assertEqual", "assertIs"}
                            and replacement[0] in WEAK):
                        lines.append(f"FATAL weakened-or-removed assertion: {assertion[0]} -> {replacement[0]}"); fatal = True
            if len(after.returns) > len(before.returns):
                for value in after.returns[len(before.returns):]:
                    lines.append(f"FATAL added early return {rel}:{name}: {value}"); fatal = True
            for value in after.expected_strings:
                if value not in before.expected_strings and any(marker in value for marker in FORBIDDEN):
                    lines.append(f"FATAL forbidden expected string {rel}:{name}: {value!r}"); fatal = True
            if Path(rel).name == "absorbing_state_catalog.py" and before.comparisons != after.comparisons:
                suspicious = any(any(marker in rendered for marker in FORBIDDEN)
                                 for _, rendered in after.comparisons)
                prefix = "FATAL" if suspicious else "CHANGED"
                lines.append(f"{prefix} replay identity constants changed {rel}:{name}\n  before: {before.comparisons}\n  after: {after.comparisons}")
                fatal |= suspicious
    if not lines: lines.append("No changed pre-existing assertions or forbidden test edits.")
    return lines, fatal


def travel_symbols() -> int:
    sys.path[:0] = [str(ROOT / "src")]
    from hengbot.policy_constants import TOWN_TRAVEL_STORE_SYMBOLS
    from hengbot import model
    for index, symbol in enumerate(TOWN_TRAVEL_STORE_SYMBOLS):
        names = sorted(name for name, value in vars(model).items()
                       if name.startswith("STORE_") and value == index)
        print(f"{index} {symbol!r} -> {names[0] if names else '<unknown>'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--travel-symbols", action="store_true")
    args = parser.parse_args(argv)
    if args.travel_symbols: return travel_symbols()
    if not args.base: parser.error("--base is required")
    lines, fatal = audit(args.base, args.root.resolve())
    print("\n".join(lines))
    return int(fatal)


if __name__ == "__main__":
    raise SystemExit(main())
