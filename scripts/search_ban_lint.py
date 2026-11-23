#!/usr/bin/env python3
"""Every sender of the search key asks search_ban (no search on Angband 99F/100F).

Owner 2026-11-23 (verbatim): 「99F 100Fはサーチ禁止。必要なら感知すること。」  The one predicate is
``hengbot.search_ban.banned``; each place that sends the search command ('s',
src/io/input-key-processor.cpp -> do_cmd_search) checks it, asks ``search_ban.detect_key`` /
``search_ban.wait_key``, or both.  This lint reads ``src/hengbot`` and fails on

- a load of ``SEARCH_KEY`` or ``CHEST_SEARCH_KEY``, or a ``return "s"``, in a function that is
  not guarded by search_ban, unless the function is a row of ``READERS`` (it compares a key with
  the search key and sends nothing).  Guarded: an enclosing ``if`` (or ``elif``) whose test calls
  ``search_ban.<name>``, or an earlier statement of an enclosing block that is such an ``if``
  ending in ``return`` (the ban's early exit);
- such a load at module level outside ``READERS`` (an alias a sender could return);
- a ``READERS`` row the source no longer has.

A new sender: ask search_ban in it.  A new reader that sends nothing: add its row with the reason.

    python scripts/search_ban_lint.py      # exit 1 on a finding
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
NAMES = frozenset({"SEARCH_KEY", "CHEST_SEARCH_KEY"})
LITERAL = "s"
BAN_MODULE = "search_ban"
MODULE_LEVEL = "<module>"

# (module, function or <module>): why it may load the search key without asking search_ban.
READERS = {
    ("curse_cure", "rests_or_waits"): "reads a decided key (rest or wait); sends nothing",
    ("damaging_ground", MODULE_LEVEL): "STANDSTILLS: the keys that stand still; read, not sent",
    ("search_ban", "wait_key"): "the predicate's own answer",
}


def _asks(node) -> bool:
    """``node`` holds a call of ``search_ban.<name>``."""
    return any(isinstance(each, ast.Call) and isinstance(each.func, ast.Attribute)
               and isinstance(each.func.value, ast.Name) and each.func.value.id == BAN_MODULE
               for each in ast.walk(node))


def _early_exit(statement) -> bool:
    return (isinstance(statement, ast.If) and _asks(statement.test) and statement.body
            and isinstance(statement.body[-1], ast.Return))


def _sends(node) -> bool:
    if isinstance(node, ast.Name):
        return node.id in NAMES and isinstance(node.ctx, ast.Load)
    return (isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
            and node.value.value == LITERAL)


def _scope_sends(scope, body):
    """(line, guarded) of each send in ``body`` (nested functions apart)."""
    out = []

    def walk(node, guarded):
        for field, value in ast.iter_fields(node):
            children = value if isinstance(value, list) else [value]
            block_guard = guarded
            for child in children:
                if not isinstance(child, ast.AST):
                    continue
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                child_guard = block_guard
                if isinstance(node, ast.If) and field in ("body", "orelse") and _asks(node.test):
                    child_guard = True
                if _sends(child):
                    out.append((child.lineno, child_guard))
                walk(child, child_guard)
                if isinstance(value, list) and _early_exit(child):
                    block_guard = True

    walk(ast.Module(body=list(body), type_ignores=[]), False)
    return out


def findings(root: Path = POLICY_ROOT, readers=READERS) -> list[str]:
    found, seen = [], set()
    for path in sorted(root.glob("*.py")):
        module = path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        scopes = [(MODULE_LEVEL, tree.body)]
        scopes += [(node.name, node.body) for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for name, body in scopes:
            sends = _scope_sends(name, body)
            if not sends:
                continue
            if (module, name) in readers:
                seen.add((module, name))
                continue
            for line, guarded in sends:
                if guarded and name != MODULE_LEVEL:
                    continue
                found.append(f"src/hengbot/{path.name}:{line}: {name} sends the search key without "
                             f"the {BAN_MODULE} guard (owner 2026-11-23 「99F 100Fはサーチ禁止」)")
    for row in sorted(set(readers) - seen):
        found.append(f"READERS row {row} names no search key load in the source")
    return found


def main() -> int:
    found = findings()
    for line in found:
        print(line)
    if found:
        print(f"search_ban_lint: {len(found)} finding(s)")
        return 1
    print("search_ban_lint: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
