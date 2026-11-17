"""The return-to-town latch and its trigger written outside hengbot.return_start.

Whole-bot maintainability review 2026-11-17 (N6): a return to town started as the hand-written
three lines ``_note_return_start(trigger)`` / ``_returning_to_town = True`` /
``_last_return_trigger = trigger`` at about fifty sites.  They now go through
``return_start.start`` / ``relatch`` / ``set_trigger``; this lint fails on

- a write of ``_returning_to_town`` other than ``False`` (a reset) outside ``return_start``,
- a write of ``_last_return_trigger`` other than ``None`` (a reset) outside ``return_start``,
- a call of ``_note_return_start`` outside ``return_start`` and the sites listed in
  ``NOTE_ALLOWED`` (each with why it notes without latching).

A new start of a return: call ``return_start.start(policy, trigger)`` instead.

    python scripts/return_start_lint.py      # exit 1 on a finding
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

POLICY_ROOT = Path(__file__).resolve().parents[1] / "src" / "hengbot"
OWNER_MODULE = "return_start"
LATCH = "_returning_to_town"
TRIGGER = "_last_return_trigger"
NOTE = "_note_return_start"
# The value a reset writes: the latch released, the trigger cleared.
RESET = {LATCH: False, TRIGGER: None}

# (module, function) -> (count, why the site notes a return start without latching one).
NOTE_ALLOWED = {
    ("policy_town", "_return_to_town_key"): (
        1, "the stuck return's Recall escape: inside the latched return (a no-op note kept as is)"),
}


class _Sites(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.stack: list[str] = []
        self.writes: list[tuple[str, str, int, str]] = []
        self.notes: list[tuple[str, str, int]] = []

    def _scope(self, node, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node) -> None:
        self._scope(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _where(self) -> str:
        return self.stack[-1] if self.stack else "<module>"

    def _target(self, target, value) -> None:
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._target(element, None)
            return
        if isinstance(target, ast.Attribute) and target.attr in RESET:
            reset = (isinstance(value, ast.Constant) and value.value is RESET[target.attr])
            if not reset:
                self.writes.append((self.module, self._where(), target.lineno, target.attr))

    def visit_Assign(self, node) -> None:
        for target in node.targets:
            self._target(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node) -> None:
        if node.value is not None:
            self._target(node.target, node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node) -> None:
        self._target(node.target, None)
        self.generic_visit(node)

    def visit_Call(self, node) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == NOTE:
            self.notes.append((self.module, self._where(), node.lineno))
        if (isinstance(func, ast.Name) and func.id == "setattr" and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant) and node.args[1].value in RESET):
            value = node.args[2] if len(node.args) > 2 else None
            reset = isinstance(value, ast.Constant) and value.value is RESET[node.args[1].value]
            if not reset:
                self.writes.append((self.module, self._where(), node.lineno, node.args[1].value))
        self.generic_visit(node)


def sites(root: Path = POLICY_ROOT):
    """(writes, notes) outside the owner module."""
    writes, notes = [], []
    for path in sorted(root.glob("*.py")):
        module = path.stem
        if module == OWNER_MODULE:
            continue
        visitor = _Sites(module)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        writes.extend(visitor.writes)
        notes.extend(visitor.notes)
    return writes, notes


def findings(root: Path = POLICY_ROOT) -> list[str]:
    writes, notes = sites(root)
    lines = [f"{module}.py:{line} ({function}) writes {attr}: start a return with "
             f"return_start.start / relatch / set_trigger, or reset it to {RESET[attr]}"
             for module, function, line, attr in writes]
    counted = Counter((module, function) for module, function, _line in notes)
    for (module, function), count in sorted(counted.items()):
        allowed, _why = NOTE_ALLOWED.get((module, function), (0, ""))
        if count > allowed:
            where = ", ".join(str(line) for m, f, line in notes if (m, f) == (module, function))
            lines.append(f"{module}.py:{function} calls {NOTE} {count}x (listed {allowed}; "
                         f"lines {where}): call return_start.start instead, or list the site")
    for (module, function), (allowed, _why) in sorted(NOTE_ALLOWED.items()):
        if counted.get((module, function), 0) < allowed:
            lines.append(f"{module}.py:{function} is listed for {allowed} {NOTE} calls but has "
                         f"{counted.get((module, function), 0)}: shrink NOTE_ALLOWED")
    return lines


def main() -> int:
    lines = findings()
    for line in lines:
        print(line)
    print(f"return_start_lint: {len(lines)} finding(s)")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
