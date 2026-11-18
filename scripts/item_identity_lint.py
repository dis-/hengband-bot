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
import sys
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


# --------------------------------------------------------------------------
# Remembered items (owner 2026-11-18, review Q1 「印や割引だけ違えば同じ品」).
#
# Every state that remembers an item holds it by the memory reading
# (item_identity.memory_identity): the sets, maps and queues are
# MemorySignatures / MemorySignatureMap / MemorySignatureList, which apply the
# reading to what they hold and are asked about; a remembered single item
# (the pending take, a candidate) is compared by item_identity.same_memory.
# Rejected outside item_identity:
#
# * ``==`` / ``!=`` with a remembered single item (or a field of it);
# * a remembered single item looked up ``in`` a collection that does not
#   remember (a plain set or list answers by the display name);
# * set algebra whose receiver does not remember and whose operand does
#   (``plain.issubset(remembered)``, ``plain - remembered``, ...): the
#   plain receiver compares the display names;
# * a policy's own remembering attribute assigned anything but a remembering
#   container (the visit's and the holds' fields are read into theirs by
#   their forwarding properties).

sys.path.insert(0, str(ROOT / "src"))

from hengbot.policy_state import (  # noqa: E402
    REMEMBERED_POLICY_ATTRIBUTES, REMEMBERED_POLICY_VALUES,
)
from hengbot.town_visit import (  # noqa: E402
    FLOOR_HOLD_LEGACY_NAMES, HOLD_LEGACY_NAMES, LEGACY_NAMES, REMEMBERED_FIELDS,
)


def _remembered_containers() -> frozenset[str]:
    names = set(REMEMBERED_POLICY_ATTRIBUTES)
    for legacy_names in (LEGACY_NAMES, HOLD_LEGACY_NAMES, FLOOR_HOLD_LEGACY_NAMES):
        names.update(legacy for legacy, field in legacy_names.items()
                     if field in REMEMBERED_FIELDS)
    names.update(REMEMBERED_FIELDS)
    return frozenset(names)


REMEMBERED_CONTAINERS = _remembered_containers()
REMEMBERED_VALUES = REMEMBERED_POLICY_VALUES
_REMEMBERING_CONSTRUCTORS = frozenset({
    "MemorySignatures", "MemorySignatureMap", "MemorySignatureList",
    "remembered_set", "remembered_map", "remembered_list",
})
_SET_ALGEBRA = frozenset({
    "issubset", "issuperset", "isdisjoint", "intersection", "difference", "union",
    "symmetric_difference", "intersection_update", "difference_update",
    "symmetric_difference_update", "update",
})

# (file, enclosing function) -> why a remembered-item comparison stays as it is.
REMEMBERED_ALLOWED: dict[tuple[str, str], str] = {
}


def _attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _mentions_value(node: ast.AST) -> str | None:
    """A remembered single item, or a part of it (``pending[0]``)."""
    while isinstance(node, ast.Subscript):
        node = node.value
    name = _attribute_name(node)
    return name if name in REMEMBERED_VALUES else None


def _is_container(node: ast.AST, local: frozenset[str] = frozenset()) -> bool:
    """A remembered container: a remembering attribute, a remembering
    constructor call, or a local bound to either in the same function."""
    if isinstance(node, ast.Name):
        return node.id in local
    return _attribute_name(node) in REMEMBERED_CONTAINERS or (
        isinstance(node, ast.Call) and _is_remembering_value(node))


def _is_remembering_value(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else _attribute_name(func)
        return name in _REMEMBERING_CONSTRUCTORS
    return False


def analyze_remembered(source: str, filename: str = "<source>") -> list[str]:
    tree = ast.parse(source)
    owner = _functions(tree)
    findings: list[str] = []
    locals_by_function: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and _is_container(node.value)):
            locals_by_function.setdefault(owner.get(node, "<module>"), set()).add(
                node.targets[0].id)
    for node in ast.walk(tree):
        function = owner.get(node, "<module>")
        if (filename, function) in REMEMBERED_ALLOWED:
            continue
        local = frozenset(locals_by_function.get(function, ()))
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for position, op in enumerate(node.ops):
                left, right = operands[position], operands[position + 1]
                if isinstance(op, (ast.Eq, ast.NotEq)):
                    name = _mentions_value(left) or _mentions_value(right)
                    if name:
                        findings.append(
                            f"line {node.lineno}: {function} compares the remembered {name} "
                            "with ==/!=; use item_identity.same_memory")
                elif isinstance(op, (ast.In, ast.NotIn)):
                    name = _mentions_value(left)
                    if name and not _is_container(right, local):
                        findings.append(
                            f"line {node.lineno}: {function} looks the remembered {name} up "
                            "in a collection that does not remember items")
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in _SET_ALGEBRA and not _is_container(node.func.value, local)
              and any(_is_container(arg, local) for arg in node.args)):
            findings.append(
                f"line {node.lineno}: {function} reads a remembered set through a plain "
                f".{node.func.attr}")
        elif (isinstance(node, ast.BinOp)
              and isinstance(node.op, (ast.Sub, ast.BitAnd, ast.BitOr, ast.BitXor))
              and _is_container(node.right, local) and not _is_container(node.left, local)):
            findings.append(
                f"line {node.lineno}: {function} combines a plain set with a remembered set")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = _attribute_name(target)
                if name in REMEMBERED_POLICY_ATTRIBUTES and not _is_remembering_value(node.value):
                    findings.append(
                        f"line {node.lineno}: {function} assigns the remembered {name} "
                        "something that does not remember items")
    return findings


def _container_findings() -> list[str]:
    """Each remembering field of the visit and the holds is made remembering."""
    from dataclasses import fields as dataclass_fields

    from hengbot.item_identity import MemorySignatureList, MemorySignatureMap, MemorySignatures
    from hengbot.town_visit import FloorHolds, TownHolds, TownVisit

    remembering = (MemorySignatures, MemorySignatureMap, MemorySignatureList)
    findings = []
    for cls in (TownVisit, TownHolds, FloorHolds):
        for spec in dataclass_fields(cls):
            if spec.name in REMEMBERED_FIELDS and not isinstance(spec.default_factory(), remembering):
                findings.append(f"town_visit.py: {cls.__name__}.{spec.name} is not made remembering")
    return findings


def main() -> int:
    findings = [
        f"{path.name}: {finding}"
        for path in sorted(POLICY_ROOT.glob("*.py"))
        if path.name != HOME_MODULE
        for finding in analyze_source(path.read_text(encoding="utf-8"), path.name)
    ]
    findings += [
        f"{path.name}: {finding}"
        for path in sorted(POLICY_ROOT.glob("*.py"))
        if path.name != HOME_MODULE
        for finding in analyze_remembered(path.read_text(encoding="utf-8"), path.name)
    ]
    findings += _container_findings()
    for finding in findings:
        print(f"item-identity-lint: {finding}")
    print(f"item-identity-lint: {len(findings)} violation(s)")
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
