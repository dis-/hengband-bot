"""Direction and target keys appended to a command key outside the input entry.

Whole-bot maintainability review 2026-11-23 K4, (a)-3: the easy_open fix (6bef1941c0) made
'o'/'c'/'D' + direction release the direction only at the observed direction question, but an
item command with a suffix (``reserved_item_command(..., suffix=...)``: a wand, a rod, a throw or
a shot + direction or ``*t5\\x1b``) is still sent whole by ``observed_input.compile_observed_input``;
when the expected question does not appear, the trailing direction becomes the next command (a
move).  Each such composer is listed in ``observed_input`` so the set is known; this lint fails on

- a ``reserved_item_command(..., suffix=...)`` call in a function ``COMPOSED_SUFFIX_SITES`` does
  not list, or a listed count that differs from the source,
- ``KEY + direction`` (a key literal or a ``*_KEY`` name followed by ``direction``/``dir`` or a
  ``_direction_key``/``_direction``/``beam_direction``/``_cursor_delta_keys`` call) in a function
  ``COMPOSED_APPEND_SITES`` does not list, or a listed count that differs,
- a target-mode literal (``*t...`` / ``*p...`` / one holding ``t5\\x1b``) in a function that is in
  neither table (target walks belong to a listed composer),
- a listed site the source no longer has, or a suffix kind the table does not define,
- an aimed item command (``observed_input.AIMED_ITEM_COMMANDS``: wand, rod, fire, throw) whose
  direction or target walk the entry would send with the command instead of at the observed
  question (owner answer (b)-5, 2026-11-23 「問いが出た時だけ方向を送る」).

A new composer: list it in ``hengbot/observed_input.py`` (and say what the suffix answers).

    python scripts/composed_key_lint.py      # exit 1 on a finding
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
sys.path.insert(0, str(ROOT / "src"))

ENTRY_MODULE = "observed_input"
COMPOSER = "reserved_item_command"
DIRECTION_NAMES = frozenset({"direction", "dir"})
DIRECTION_CALLS = frozenset({"_direction_key", "_direction", "beam_direction", "_cursor_delta_keys"})
SUFFIX_KINDS = frozenset({"direction", "target-cursor", "item-target", "floor-item",
                          "dungeon-choice"})
APPEND_SENDS = frozenset({"observed", "passthrough"})
TARGET_TAIL = "t5\x1b"


def _call_name(node) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


def _is_direction(node) -> bool:
    if isinstance(node, ast.Name):
        return node.id in DIRECTION_NAMES
    return isinstance(node, ast.Call) and _call_name(node) in DIRECTION_CALLS


def _is_command(node) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.Name):
        return node.id.endswith("_KEY")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_command(node.left) or _is_command(node.right)
    return False


def _is_target_literal(node) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and (node.value.startswith(("*t", "*p")) or TARGET_TAIL in node.value))


class _Sites(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.stack: list[str] = []
        self.suffix: list[tuple[str, int]] = []
        self.append: list[tuple[str, int]] = []
        self.target: list[tuple[str, int]] = []

    def visit_FunctionDef(self, node) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _where(self) -> str:
        return self.stack[-1] if self.stack else "<module>"

    def visit_Call(self, node) -> None:
        if _call_name(node) == COMPOSER and any(k.arg == "suffix" for k in node.keywords):
            self.suffix.append((self._where(), node.lineno))
        self.generic_visit(node)

    def visit_BinOp(self, node) -> None:
        if isinstance(node.op, ast.Add) and _is_direction(node.right) and _is_command(node.left):
            self.append.append((self._where(), node.lineno))
        self.generic_visit(node)

    def visit_Constant(self, node) -> None:
        if _is_target_literal(node):
            self.target.append((self._where(), node.lineno))


def sites(sources: Mapping[str, str]):
    """(suffix calls, appends, target literals) as (module, function, line), outside the entry."""
    suffix, append, target = [], [], []
    for module, text in sorted(sources.items()):
        if module == ENTRY_MODULE:
            continue
        visitor = _Sites(module)
        visitor.visit(ast.parse(text, filename=f"{module}.py"))
        suffix.extend((module, f, line) for f, line in visitor.suffix)
        append.extend((module, f, line) for f, line in visitor.append)
        target.extend((module, f, line) for f, line in visitor.target)
    return suffix, append, target


def _counted(found, listed, label, table) -> list[str]:
    lines = []
    counted = Counter((module, function) for module, function, _line in found)
    for site, count in sorted(counted.items()):
        expected = listed.get(site, (0,))[0]
        if count != expected:
            where = ", ".join(str(line) for m, f, line in found if (m, f) == site)
            lines.append(f"{site[0]}.py:{site[1]} has {count} {label} (listed {expected}; lines "
                         f"{where}): list it in observed_input.{table}")
    for site, entry in sorted(listed.items()):
        if site not in counted:
            lines.append(f"{site[0]}.py:{site[1]} is listed in observed_input.{table} "
                         f"({entry[0]}) but has no {label}: remove the row")
    return lines


def findings(sources: Mapping[str, str], suffix_sites: Mapping, append_sites: Mapping) -> list[str]:
    suffix, append, target = sites(sources)
    lines = _counted(suffix, suffix_sites, f"{COMPOSER}(suffix=) call(s)", "COMPOSED_SUFFIX_SITES")
    lines += _counted(append, append_sites, "KEY + direction append(s)", "COMPOSED_APPEND_SITES")
    for module, function, line in target:
        if (module, function) not in suffix_sites and (module, function) not in append_sites:
            lines.append(f"{module}.py:{line} ({function}) writes a target-mode literal outside "
                         "a listed composer: list it in observed_input.COMPOSED_SUFFIX_SITES")
    for site, (_count, kinds) in sorted(suffix_sites.items()):
        if not kinds or not set(kinds) <= SUFFIX_KINDS:
            lines.append(f"{site[0]}.py:{site[1]} lists suffix kinds {sorted(kinds)}: use "
                         f"{sorted(SUFFIX_KINDS)}")
    for site, (_count, send) in sorted(append_sites.items()):
        if send not in APPEND_SENDS:
            lines.append(f"{site[0]}.py:{site[1]} lists send {send!r}: use {sorted(APPEND_SENDS)}")
    return lines


# Owner answer (b)-5 (2026-11-23 「問いが出た時だけ方向を送る」): the aimed item commands'
# direction and target walks are released only at the observed question.  One sample suffix per
# kind (the shapes the listed composers write).
AIMED_SAMPLES = {"direction": ("6",), "target-cursor": ("*t5\x1b", "*p966t5\x1b")}


def gate_findings(compile_observed_input, commands: str, screen_kinds) -> list[str]:
    """A sample aimed key that ``compile_observed_input`` still sends whole (or with the
    suffix inside its first segment) on the command screen, or with no screen."""
    lines = []
    for command in commands:
        for kind in screen_kinds:
            for suffix_kind, samples in sorted(AIMED_SAMPLES.items()):
                for suffix in samples:
                    key = command + "b" + suffix
                    prefix, steps = compile_observed_input(key, kind, None, "lint:aimed", [])
                    released = "".join(step.keys for step in steps)
                    if prefix not in (key[:1], key[:2]) or not released.endswith(suffix):
                        lines.append(f"{key!r} ({suffix_kind}, screen {kind}) is sent as "
                                     f"{prefix!r} + {released!r}: observed_input must release the "
                                     "suffix only at its observed question (owner answer (b)-5)")
    return lines


def main() -> int:
    from hengbot.input_executor import ScreenKind
    from hengbot.observed_input import (
        AIMED_ITEM_COMMANDS, COMPOSED_APPEND_SITES, COMPOSED_SUFFIX_SITES, compile_observed_input,
    )

    sources = {path.stem: path.read_text(encoding="utf-8")
               for path in sorted(POLICY_ROOT.glob("*.py"))}
    lines = findings(sources, COMPOSED_SUFFIX_SITES, COMPOSED_APPEND_SITES)
    lines += gate_findings(compile_observed_input, AIMED_ITEM_COMMANDS,
                           (ScreenKind.COMMAND, None))
    for line in lines:
        print(line)
    print(f"composed_key_lint: {len(lines)} finding(s)")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
