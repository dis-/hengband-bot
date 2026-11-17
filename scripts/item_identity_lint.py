#!/usr/bin/env python3
"""Keep item identity in ``hengbot.item_identity`` (maintainability review S1).

Two shapes are rejected outside ``src/hengbot/item_identity.py``:

* a brace-stripping name reading: ``re.sub``/``re.subn`` with a ``\\{...\\}``
  pattern, a ``re.compile``'d ``\\{...\\}`` pattern whose ``.sub`` the module
  calls, or a ``partition``/``rpartition``/``split``/``rsplit`` on ``"{"``;
* a hand-built identity tuple holding both a name and a tval
  (``(item.name, item.tval, item.sval)``, ``(tval, sval, name)``, ...).

Call the named reading in ``item_identity`` instead (``display_signature``,
``sale_identity``, ``without_trailing_block``, ``without_any_block``, ...).
``ALLOWED`` lists the reviewed exceptions by file and enclosing function.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
HOME_MODULE = "item_identity.py"

# (file, enclosing function) -> why the tuple is not an item identity reading.
ALLOWED: dict[tuple[str, str], str] = {
    # Baseline at introduction (2026-11-18): the read binding records the exact
    # display name next to the letter it was read from, and checks that very
    # letter still shows that very name; it is a board-binding check, not an
    # item identity shared with other readers.
    ("policy_town.py", "_progress_only_restores_consumed_resource"):
        "read binding: exact (tval, sval, name) of the bound letter",
}

_SPLITTERS = frozenset({"partition", "rpartition", "split", "rsplit"})


def _is_brace_pattern(node: ast.AST | None) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and "\\{" in node.value and "\\}" in node.value)


def _re_call(node: ast.AST, names: frozenset[str]) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in names and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re")


def _is_name_part(node: ast.AST) -> bool:
    """``x.name``, or a reading of it such as ``shelf_item_name(x.name)``."""
    if isinstance(node, ast.Attribute):
        return node.attr == "name"
    if isinstance(node, ast.Call):
        return any(isinstance(arg, ast.Attribute) and arg.attr == "name" for arg in node.args)
    return False


def _is_kind_part(node: ast.AST, field: str) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == field
    return isinstance(node, ast.Name) and node.id == field


def _is_identity_tuple(node: ast.AST) -> bool:
    """A 2-3 element ``(x.name, tval[, sval])`` built from an item, any order.

    Wider tuples (a page fingerprint with the letter, count or price) and
    repacked locals (``(name, tval, sval)`` from an unpacked record) are not
    identity readings.
    """
    if not isinstance(node, ast.Tuple) or not isinstance(node.ctx, ast.Load)             or not 2 <= len(node.elts) <= 3:
        return False
    names = [elt for elt in node.elts if _is_name_part(elt)]
    tvals = [elt for elt in node.elts if _is_kind_part(elt, "tval")]
    svals = [elt for elt in node.elts if _is_kind_part(elt, "sval")]
    return len(names) == 1 and len(tvals) == 1 and len(names) + len(tvals) + len(svals) == len(node.elts)


def _functions(tree: ast.AST) -> dict[ast.AST, str]:
    owner: dict[ast.AST, str] = {}

    def visit(node: ast.AST, name: str) -> None:
        for child in ast.iter_child_nodes(node):
            child_name = (child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                          else name)
            owner[child] = child_name
            visit(child, child_name)

    visit(tree, "<module>")
    return owner


def analyze_source(source: str, filename: str = "<source>") -> list[str]:
    tree = ast.parse(source)
    owner = _functions(tree)
    findings: list[str] = []
    compiled: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _re_call(node.value, frozenset({"compile"})) \
                and node.value.args and _is_brace_pattern(node.value.args[0]):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    compiled[target.id] = node.lineno
    for node in ast.walk(tree):
        function = owner.get(node, "<module>")
        if (filename, function) in ALLOWED:
            continue
        if _re_call(node, frozenset({"sub", "subn"})) and node.args \
                and _is_brace_pattern(node.args[0]):
            findings.append(f"line {node.lineno}: {function} strips a {{...}} block with re.sub")
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in {"sub", "subn"} and isinstance(node.func.value, ast.Name)
              and node.func.value.id in compiled):
            findings.append(
                f"line {node.lineno}: {function} strips a {{...}} block with "
                f"{node.func.value.id}.sub (compiled at line {compiled[node.func.value.id]})"
            )
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in _SPLITTERS and node.args
              and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
              and "{" in node.args[0].value):
            findings.append(f"line {node.lineno}: {function} splits a name at a {{...}} block")
        elif _is_identity_tuple(node):
            findings.append(f"line {node.lineno}: {function} hand-builds a (name, tval) identity")
    return findings


def main() -> int:
    findings = [
        f"{path.name}: {finding}"
        for path in sorted(POLICY_ROOT.glob("*.py"))
        if path.name != HOME_MODULE
        for finding in analyze_source(path.read_text(encoding="utf-8"), path.name)
    ]
    for finding in findings:
        print(f"item-identity-lint: {finding}")
    print(f"item-identity-lint: {len(findings)} violation(s)")
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
