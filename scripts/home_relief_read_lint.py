#!/usr/bin/env python3
"""The full-Home relief is read only through ``home_full_relief.relief_of``.

Maintainability review 2026-11-23 (a)-9: the relief (``HomeMixin._home_full_relief``, a
``home_full_relief.HomeFullRelief`` or None) was read as ``policy._home_full_relief`` and as
``getattr(policy, "_home_full_relief", None)`` in ten modules.  Every read now goes through
``relief_of(policy)``; this rejects any other read of the attribute:

* an attribute read ``<x>._home_full_relief`` (an assignment or ``del`` writes it and is allowed);
* the attribute's name as a string (``getattr``, ``__dict__[...]``), outside the container's own
  module and the files that name the attribute as data (the checkpoint registry and the
  telemetry observer's list of copied objects);
* the relief read as the dict it was (``relief["mode"]``, ``relief.get("mode")``, ``"mode" in
  relief``): the bot reads the fields.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
ATTRIBUTE = "_home_full_relief"
# The container's module (it defines relief_of and the attribute's descriptor).
CONTAINER = "home_full_relief.py"
# The files that name the attribute as data, never to read the relief.
NAMED_AS_DATA = {
    "state_registry.py": "the checkpoint registry's row",
    "cli.py": "the telemetry observer's copied memo objects (_OBSERVER_COPIED_MEMO_OBJECTS)",
}
DICT_METHODS = {"get", "pop", "setdefault", "update", "keys", "items", "values"}


def _relief_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "relief"


def analyze_source(source: str, filename: str = "mutant.py") -> list[str]:
    if filename == CONTAINER:
        return []
    findings: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Attribute) and node.attr == ATTRIBUTE
                and isinstance(node.ctx, ast.Load)):
            findings.append(f"line {node.lineno}: reads .{ATTRIBUTE}; read it with relief_of(policy)")
        elif (isinstance(node, ast.Constant) and node.value == ATTRIBUTE
                and filename not in NAMED_AS_DATA):
            findings.append(f"line {node.lineno}: names {ATTRIBUTE!r}; read the relief with relief_of(policy)")
        elif (isinstance(node, ast.Subscript) and _relief_name(node.value)
                and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)):
            findings.append(f"line {node.lineno}: reads the relief as a dict; read its field")
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and _relief_name(node.func.value) and node.func.attr in DICT_METHODS):
            findings.append(f"line {node.lineno}: reads the relief as a dict (.{node.func.attr}); read its field")
        elif (isinstance(node, ast.Compare) and len(node.ops) == 1
                and isinstance(node.ops[0], (ast.In, ast.NotIn))
                and _relief_name(node.comparators[0])
                and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)):
            findings.append(f"line {node.lineno}: tests a relief key; read its field")
    return findings


def main() -> int:
    findings = [
        f"{path.relative_to(POLICY_ROOT).as_posix()}: {finding}"
        for path in sorted(POLICY_ROOT.rglob("*.py"))
        for finding in analyze_source(path.read_text(encoding="utf-8"), path.name)
    ]
    for finding in findings:
        print(f"home-relief-read-lint: {finding}")
    print(f"home-relief-read-lint: {len(findings)} violation(s)")
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
