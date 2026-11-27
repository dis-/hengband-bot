#!/usr/bin/env python3
"""No new branch on a literal race / class / personality id or on an instance name.

MAINTAINABILITY.md rule 1 (2026-11-27): judge from the board's facts, not from the race or
class number.  A class difference that has to stay goes through a predicate of
``class_roles.py`` (``plays_as_warrior``, ``casts_realm_spells``, ...); an instance (n1-a ...)
differs only through ``strategy-profile.json`` (``strategy_profile.py``).

From the AST of ``src/hengbot/*.py`` this finds:

* ``<who>-literal``: a comparison (``==``, ``!=``, ``in``, ``not in``, ``<`` ...) of the player's
  class / race / personality id (``class_id``, ``personality_id``, ``player.race_id``,
  ``getattr(player, "class_id")`` ...) with an int literal or a collection of int literals
  (``class_id == 0``, ``class_id in (0, 16)``);
* ``<who>-constant``: a comparison that names a class / race / personality constant
  (``PLAYER_CLASS_*``, ``PLAYER_RACE_*``, ``RACE_*``, ``PERSONALITY_*``) on either side;
* ``constant-definition``: ``PLAYER_CLASS_* = <int>`` (and the race / personality ones) defined
  outside the modules allowed to define them (a second copy of a class number);
* ``instance-name``: a string that is an instance name (``"n1-a"``, ``"n1-b/"``), or a string
  compared with something or used as a dict key that names one; prose that mentions an instance
  (``"n1-c life-209: ..."`` in a description) is not a branch and is not a finding.

Ordering comparisons (``class_id >= 0``: the id has been read) and the unknown sentinel
(``-1``) are not branches on a class.

The modules that define or parse the ids (``ALLOWED_MODULES``) are not checked for the first
three kinds.  The findings of 2026-11-27 are recorded in
``scripts/class_literal_lint_baseline.json`` (lint_baseline: keys are
``<file>:<function>: <kind>: <expression>`` with counts, never line numbers); only a finding
beyond that baseline fails, and a baseline entry that disappeared is reported so the file can
shrink (``--write-baseline``).  The ``PLAYER_CLASS_MAGIC_EATER`` checks are legitimate today
(the absorbed-power rules) and stay baselined; their count is printed so it stays visible.

``--list`` prints every finding with its line.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import re
import sys
from typing import NamedTuple

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import lint_baseline  # noqa: E402

POLICY_ROOT = SCRIPTS.parent / 'src' / 'hengbot'
LINT = 'class_literal_lint'
LABEL = 'class-literal-lint'

# The modules that define the ids, read them from the game, or map the class keys of the
# strategy data (rule 1: the places a class difference is allowed to live).
ALLOWED_MODULES = frozenset({
    'class_roles.py',               # the class predicates
    'equipment_class_profile.py',   # the class-table numbers (blows, shots)
    'policy_constants.py',          # definitions
    'quest_strategies.py',          # strategy/quests ``*_by_class`` rows
    'quest_entry_requirements.py',  # strategy/quests class keys
    'strategy_profile.py',          # the per-instance profile
    'model.py',                     # the board's parsing
    'protocol.py',                  # the protocol's parsing
})
# The instance profile is the one place an instance may be named.
INSTANCE_ALLOWED_MODULES = frozenset({'strategy_profile.py'})

CONSTANT_NAME = re.compile(r'^(?:PLAYER_CLASS|PLAYER_RACE|PLAYER_PERSONALITY|PERSONALITY)_[A-Z0-9_]+$')
# Names of tables keyed by an id are not ids (PERSONALITY_TO_M_CHANCE is the game's table).
TABLE_NAME = re.compile(r'_(?:TO|BY|OF)_|_(?:TABLE|ROWS|MAP|NAMES|PROFILES)$')
INSTANCE_NAME = re.compile(r'(?<![\w-])n1-[abc](?![\w])')
# A string that is an instance name (``"n1-a"``, ``"n1-b/"``), not prose that mentions one.
INSTANCE_TOKEN = re.compile(r'^\s*n1-[abc](?:[^\w\s]\S*)?\s*$')
# Ordering comparisons (``class_id >= 0``: the id is known) and the unknown sentinel are no branch.
_ORDERING = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
_SENTINELS = frozenset({-1})
_ID_ATTRS = {'class_id': 'class', 'personality_id': 'personality', 'race_id': 'race'}
_ID_NAMES = {
    'class_id': 'class', 'player_class': 'class', 'player_class_id': 'class', 'pclass': 'class',
    'personality_id': 'personality', 'player_personality': 'personality',
    'player_race': 'race', 'player_race_id': 'race', 'prace': 'race',
}
_PLAYERISH = ('player', 'character', 'sheet')


class Finding(NamedTuple):
    file: str
    line: int
    function: str
    kind: str
    expression: str
    constants: tuple = ()


def _constant_who(name: str) -> str | None:
    if not CONSTANT_NAME.match(name) or TABLE_NAME.search(name):
        return None
    if name.startswith('PERSONALITY'):
        return 'personality'
    if 'RACE' in name.split('_')[:2]:
        return 'race'
    return 'class'


def _name_of(node) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _chain_names(node) -> list[str]:
    out = []
    while isinstance(node, ast.Attribute):
        out.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        out.append(node.id)
    return out


def identity_who(node) -> str | None:
    """``class`` / ``race`` / ``personality`` when ``node`` reads the player's id."""
    if isinstance(node, ast.Call) and _name_of(node.func) == 'getattr' and len(node.args) >= 2:
        key = node.args[1]
        if isinstance(key, ast.Constant) and key.value in _ID_ATTRS:
            who = _ID_ATTRS[key.value]
            if who != 'race' or any(p in name for name in _chain_names(node.args[0]) for p in _PLAYERISH):
                return who
        return None
    if isinstance(node, ast.Attribute) and node.attr in _ID_ATTRS:
        who = _ID_ATTRS[node.attr]
        if who == 'race':
            # Monsters have a race_id too: only the player's counts.
            owners = _chain_names(node.value)
            return who if any(p in name for name in owners for p in _PLAYERISH) else None
        return who
    if isinstance(node, ast.Name):
        return _ID_NAMES.get(node.id)
    return None


def _int_literal(node) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int


def _elements(node):
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return node.elts
    if (isinstance(node, ast.Call) and _name_of(node.func) in ('frozenset', 'set', 'tuple')
            and len(node.args) == 1 and isinstance(node.args[0], (ast.Tuple, ast.List, ast.Set))):
        return node.args[0].elts
    return None


def _int_value(node):
    if _int_literal(node):
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
            and _int_literal(node.operand)):
        return -node.operand.value
    return None


def literal_side(node) -> bool:
    """An int literal or a collection of them, the unknown sentinel (-1) excepted."""
    value = _int_value(node)
    if value is not None:
        return value not in _SENTINELS
    elements = _elements(node)
    return bool(elements) and all(_int_value(element) is not None for element in elements)


def constants_named(node) -> list[tuple[str, str]]:
    """(constant, who) for the id constants ``node`` names (itself or as elements)."""
    elements = _elements(node)
    out = []
    for item in (elements if elements is not None else [node]):
        name = _name_of(item) if isinstance(item, (ast.Name, ast.Attribute)) else None
        who = _constant_who(name) if name else None
        if who:
            out.append((name, who))
    return out


def _docstrings(tree) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            for statement in node.body:
                if (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
                        and isinstance(statement.value.value, str)):
                    out.add(id(statement.value))
    return out


def _functions(tree) -> dict[int, str]:
    """node id -> the qualified name of the innermost function around it."""
    enclosing: dict[int, str] = {}

    def visit(node, prefix, function):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f'{prefix}{child.name}'
                inner = function if isinstance(child, ast.ClassDef) else name
                enclosing[id(child)] = function
                visit(child, name + '.', inner)
            else:
                enclosing[id(child)] = function
                visit(child, prefix, function)

    visit(tree, '', '<module>')
    return enclosing


def findings_in(source: str, filename: str) -> list[Finding]:
    tree = ast.parse(source)
    where = _functions(tree)
    docstrings = _docstrings(tree)
    allowed = filename in ALLOWED_MODULES
    # Strings compared or looked up (``name == "n1-a"``, ``{"n1-a": ...}``) name an instance
    # even inside longer text.
    compared = {id(child) for node in ast.walk(tree)
                for part in ([node] if isinstance(node, ast.Compare)
                             else [key for key in node.keys if key is not None] if isinstance(node, ast.Dict)
                             else [])
                for child in ast.walk(part) if isinstance(child, ast.Constant)}
    found: list[Finding] = []
    for node in ast.walk(tree):
        function = where.get(id(node), '<module>')
        if isinstance(node, ast.Compare) and not allowed:
            sides = [node.left, *node.comparators]
            named = [pair for side in sides for pair in constants_named(side)]
            whos = {who for side in sides for who in [identity_who(side)] if who}
            expression = ast.unparse(node)
            if named:
                who = named[0][1]
                found.append(Finding(filename, node.lineno, function, f'{who}-constant', expression,
                                     tuple(sorted({name for name, _ in named}))))
            elif (whos and any(literal_side(side) for side in sides)
                  and not any(isinstance(op, _ORDERING) for op in node.ops)):
                found.append(Finding(filename, node.lineno, function, f'{sorted(whos)[0]}-literal', expression))
        elif isinstance(node, ast.Assign) and not allowed:
            for target in node.targets:
                if (isinstance(target, ast.Name) and _constant_who(target.id)
                        and _int_literal(node.value)):
                    found.append(Finding(filename, node.lineno, function, 'constant-definition',
                                         ast.unparse(node)))
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and id(node) not in docstrings and filename not in INSTANCE_ALLOWED_MODULES):
            match = INSTANCE_NAME.search(node.value)
            if match and (INSTANCE_TOKEN.match(node.value) or id(node) in compared):
                found.append(Finding(filename, node.lineno, function, 'instance-name',
                                     f'{match.group(0)} in {node.value[:60]!r}'))
    return sorted(found, key=lambda f: (f.file, f.line, f.kind, f.expression))


def repository_findings(root: Path = POLICY_ROOT) -> list[Finding]:
    found: list[Finding] = []
    for path in sorted(root.glob('*.py')):
        found.extend(findings_in(path.read_text(encoding='utf-8'), path.name))
    return found


def finding_key(finding: Finding) -> str:
    return f'{finding.file}:{finding.function}: {finding.kind}: {finding.expression}'


def render(finding: Finding) -> str:
    return f'{finding.file}:{finding.line}: {finding.kind}: {finding.expression}'


def summary(findings: list[Finding]) -> str:
    kinds = Counter(finding.kind for finding in findings)
    magic_eater = sum('PLAYER_CLASS_MAGIC_EATER' in finding.constants for finding in findings)
    per_kind = ', '.join(f'{kind} {count}' for kind, count in sorted(kinds.items()))
    return f'{LABEL}: per kind: {per_kind or "none"}; PLAYER_CLASS_MAGIC_EATER checks: {magic_eater}'


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    findings = repository_findings()
    if '--list' in argv:
        for finding in findings:
            print(render(finding))
    print(summary(findings))
    return lint_baseline.gate(LINT, LABEL, findings, finding_key, render=render, argv=argv)


if __name__ == '__main__':
    raise SystemExit(main())
