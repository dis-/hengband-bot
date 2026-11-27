#!/usr/bin/env python3
"""Every place the policy stops the bot on purpose is listed and classified.

MAINTAINABILITY.md rule 2 (2026-11-27): a requirement the character cannot meet (attack, HP, a
quest it will not take, a sold-out item) never stops the bot; it gives up that stage and goes on.
A stop (``blocked``, ``livelock``, an empty key) is allowed only when a mechanism broke (no route,
a screen that does not advance, a key out of step).

A *stop reason* is a decision reason the driver halts on (``cli._policy_final_stop_required``):

* a member of ``policy_constants.POLICY_FINAL_STOP_REASONS`` or a reason starting with one of
  ``POLICY_FINAL_STOP_PREFIXES`` or the ``ownership:`` prefixes cli tests beside them
  (``OWNERSHIP_STOP_PREFIXES``, checked against cli.py's text);
* ``livelock:exhausted`` (cli stops at once: ``livelock-exhausted``);
* any ``town:blocked:*`` (cli stops after ``TOWN_BLOCKED_STOP_LIMIT`` of them in one visit), and the
  other ``<family>:blocked:*`` / ``stop:*`` reasons (``quest:blocked:*`` holds end in the loop
  guard or in a final stop).

A *stop site* is an assignment of a reason fragment to a slot a composer sends under a stop
prefix (``SLOTS``: ``x._town_blocked_reason = <fragment>``, resolved through locals and the
callers' arguments), or a string (a literal, an f-string's resolved shape, a module constant or an
imported one: reason_registry_lint.Scanner resolves them) with a stop reason's shape inside a
function of ``src/hengbot``, where it is sent rather than read: not inside a comparison, a
``startswith`` / ``is_stop`` / ``.get`` test, a subscript or a dict key.  Its key is
``<module>:<function>: <shape>`` (a shape keeps ``*`` for the parts that cannot be resolved).

``scripts/designed_stop_lint_sites.json`` lists every site with a reviewed ``kind``:

* ``mechanism``: a route, screen or input failure (allowed by rule 2);
* ``requirement``: stops because a requirement is unmet (not allowed by rule 2).  Each such entry
  must carry ``"debt": "<why it cannot release yet>"``: the list of them is the to-do list;
* ``owner-halt``: a deliberate halt the owner asked for by name.

The lint fails when a site is not in the list (a new stop must be classified), when an entry has
no valid kind, or when a ``requirement`` entry has no ``debt``.  Listed entries no longer found are
reported (shrink the list by hand).  ``--sites`` prints every site with its kind; ``--add-new``
appends the unlisted sites as ``"kind": "unclassified"`` for review (still failing until
classified).

An empty key (``None`` from ``choose_key``, cli's ``no-key-exhausted``) is not inventoried: every
producer returns ``None`` for "not mine", so the halting empty key has no source site.
"""
from __future__ import annotations

import ast
from collections import Counter
import json
from pathlib import Path
import re
import sys

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import reason_registry_lint as registry  # noqa: E402  -- puts src on the path
from reason_registry_lint import WILD, Scanner, repository_sources  # noqa: E402

from hengbot import policy_constants  # noqa: E402

POLICY_ROOT = registry.POLICY_ROOT
LIST_PATH = SCRIPTS / 'designed_stop_lint_sites.json'
LABEL = 'designed-stop-lint'
KINDS = ('mechanism', 'requirement', 'owner-halt')

# cli._policy_final_stop_required tests these beside POLICY_FINAL_STOP_PREFIXES.
OWNERSHIP_STOP_PREFIXES = ('ownership:holder-silent:', 'ownership:declaration-',
                           'ownership:contract-conflict:fundraising:')
FINAL_REASONS = frozenset(policy_constants.POLICY_FINAL_STOP_REASONS) | {'livelock:exhausted'}
FINAL_PREFIXES = tuple(policy_constants.POLICY_FINAL_STOP_PREFIXES) + OWNERSHIP_STOP_PREFIXES
BLOCKED_FAMILY = re.compile(r'^[a-z][a-z0-9-]*:blocked:|^stop:')

# Calls whose string arguments are read (tested, looked up), not sent.
_READ_CALLS = frozenset({
    'startswith', 'endswith', 'removeprefix', 'removesuffix', 'partition', 'rpartition', 'split',
    'find', 'index', 'count', 'get', 'pop', 'discard', 'remove', 'is_stop', 'stop_message',
    'stationary', 'lookup', 'is_survival', 'replace', 'setdefault', 'print', 'format', 'len',
    'registration',
})
# Attributes a reason fragment is parked in before a composer sends it under a prefix
# (``policy._town_blocked_reason = "pack-full-no-room"``; ``_town_blocked_key`` sends
# ``town:blocked:<it>``).  The assignment is the site.
SLOTS = {'_town_blocked_reason': 'town:blocked:'}


def halts(shape: str) -> str | None:
    """How the driver halts on ``shape``: ``final``, ``town-fuse``, ``blocked`` or None."""
    if shape in FINAL_REASONS or shape.startswith(FINAL_PREFIXES):
        return 'final'
    if shape.startswith('town:blocked:'):
        return 'town-fuse'
    if BLOCKED_FAMILY.match(shape):
        return 'blocked'
    return None


_PARTS = (ast.JoinedStr, ast.FormattedValue, ast.BinOp, ast.IfExp, ast.BoolOp, ast.Tuple,
          ast.List, ast.Set, ast.Starred)


def _is_part(node, parent) -> bool:
    """``node`` is a piece of a bigger string expression (resolved as the whole)."""
    return isinstance(parent, (ast.JoinedStr, ast.FormattedValue)) or (
        isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Add))


def _read_context(node, parents) -> bool:
    """``node`` is compared, tested or looked up rather than sent."""
    child = node
    parent = parents.get(id(node))
    while parent is not None:
        if isinstance(parent, ast.Compare):
            return True
        if isinstance(parent, ast.Subscript):
            return child is parent.slice
        if isinstance(parent, ast.Dict):
            return any(child is key for key in parent.keys)
        if isinstance(parent, ast.Call):
            callee = parent.func.attr if isinstance(parent.func, ast.Attribute) else (
                parent.func.id if isinstance(parent.func, ast.Name) else None)
            return callee in _READ_CALLS and child is not parent.func
        if isinstance(parent, ast.keyword):
            child, parent = parent, parents.get(id(parent))
            continue
        if not isinstance(parent, _PARTS):
            return False
        child, parent = parent, parents.get(id(parent))
    return False


def _resolvable(scanner: Scanner, module: str, node) -> bool:
    """Only literals and module (or imported) constants: a parameter or a local is the caller's
    site, found where its value is written."""
    if isinstance(node, (ast.Constant, ast.JoinedStr, ast.BinOp)):
        return True
    if isinstance(node, ast.Name):
        known = scanner.modules[module]
        return node.id in known.constants or node.id in known.imports
    return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)


def _walk(tree):
    """Every node once, with its parent and the qualified name of the function around it (None at
    module level), and the parent map ``_read_context`` climbs."""
    parents: dict[int, ast.AST] = {}
    out = []
    stack = [(tree, '', None)]
    while stack:
        node, prefix, function = stack.pop()
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
            out.append((child, function))
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f'{prefix}{child.name}'
                stack.append((child, name + '.', name))
            elif isinstance(child, ast.ClassDef):
                stack.append((child, f'{prefix}{child.name}.', function))
            else:
                stack.append((child, prefix, function))
    return out, parents


_CANDIDATES = (ast.Constant, ast.JoinedStr, ast.BinOp, ast.Name, ast.Attribute)


def stop_sites(sources: dict[str, str]) -> dict[str, tuple[str, int, str]]:
    """``<module>:<function>: <shape>`` -> (module, first line, how it halts)."""
    scanner = Scanner(sources)
    sites: dict[str, tuple[str, int, str]] = {}
    constants: dict[tuple[str, str], set] = {}
    for module in sorted(sources):
        nodes, parents = _walk(scanner.modules[module].tree)
        for node, function in nodes:
            if function is None:
                continue
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    prefix = SLOTS.get(target.attr) if isinstance(target, ast.Attribute) else None
                    if prefix is None:
                        continue
                    try:
                        values = scanner.resolve(module, node.value, node.value)
                    except RecursionError:
                        values = {WILD}
                    for value in values:
                        _add(sites, module, function, node.lineno, registry._normal(prefix + value))
                continue
            if not isinstance(node, _CANDIDATES):
                continue
            if isinstance(node, ast.Constant):
                if not isinstance(node.value, str) or halts(node.value) is None:
                    continue
            elif isinstance(node, ast.BinOp) and not isinstance(node.op, ast.Add):
                continue
            if _is_part(node, parents.get(id(node))) or not _resolvable(scanner, module, node):
                continue
            if isinstance(node, ast.JoinedStr) and any(
                    isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Attribute)
                    and part.value.attr in SLOTS for part in node.values):
                continue  # the composer of a parked fragment: the slot's assignments are the sites
            try:
                if isinstance(node, ast.Name):
                    cache = (module, node.id)
                    if cache not in constants:
                        constants[cache] = scanner._resolve_constant(module, node.id)
                    shapes = constants[cache]
                elif isinstance(node, ast.Constant):
                    shapes = {node.value}
                else:
                    shapes = scanner.resolve(module, node, node)
            except RecursionError:
                continue
            shapes = [shape for shape in shapes
                      if shape != WILD and not shape.startswith(WILD) and halts(shape)]
            if not shapes or _read_context(node, parents):
                continue
            for shape in shapes:
                _add(sites, module, function, node.lineno, shape)
    return dict(sorted(sites.items()))


def _add(sites: dict, module: str, function: str, line: int, shape: str) -> None:
    if shape == WILD or shape.startswith(WILD):
        return
    how = halts(shape)
    if how is None:
        return
    key = f'{module}:{function}: {shape}'
    if key not in sites or line < sites[key][1]:
        sites[key] = (module, line, how)


def load_list(path: Path = LIST_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))['sites']


def write_list(entries: dict[str, dict], path: Path = LIST_PATH) -> None:
    payload = {
        '_comment': ('Reviewed stop sites (MAINTAINABILITY.md rule 2, 2026-11-27). Keys are '
                     '<module>:<function>: <reason shape>. kind: mechanism | requirement | '
                     'owner-halt; a requirement entry carries "debt" (why it cannot release yet). '
                     'python scripts/designed_stop_lint.py --sites lists the sites.'),
        'sites': dict(sorted(entries.items())),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8', newline='\n')


def check(sites: dict[str, tuple], entries: dict[str, dict]) -> tuple[list[str], list[str]]:
    """(failures, stale entries)."""
    failures = []
    for key in sites:
        entry = entries.get(key)
        if entry is None:
            failures.append(f'unlisted stop site (classify it in {LIST_PATH.name}): {key}')
            continue
        kind = entry.get('kind')
        if kind not in KINDS:
            failures.append(f'kind must be one of {"/".join(KINDS)} (got {kind!r}): {key}')
        elif kind == 'requirement' and not str(entry.get('debt', '')).strip():
            failures.append(f'requirement stop without "debt" (rule 2 forbids it; say why it '
                            f'cannot release yet): {key}')
    stale = sorted(key for key in entries if key not in sites)
    return failures, stale


def cli_prefixes_drift(cli_source: str) -> list[str]:
    return [f'OWNERSHIP_STOP_PREFIXES entry {prefix!r} no longer appears in cli.py; re-read '
            '_policy_final_stop_required' for prefix in OWNERSHIP_STOP_PREFIXES
            if repr(prefix).strip("'") not in cli_source]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sources = repository_sources()
    sites = stop_sites(sources)
    entries = load_list()
    if '--add-new' in argv:
        added = {key: {'kind': 'unclassified', 'halts': how}
                 for key, (_module, _line, how) in sites.items() if key not in entries}
        write_list({**entries, **added})
        print(f'{LABEL}: appended {len(added)} unlisted site(s) as unclassified')
        entries = load_list()
    failures, stale = check(sites, entries)
    failures += cli_prefixes_drift(sources.get('cli', ''))
    if '--sites' in argv:
        for key, (module, line, how) in sites.items():
            entry = entries.get(key, {})
            print(f'{module}.py:{line}: [{entry.get("kind", "UNLISTED")}] ({how}) {key}')
    for failure in failures:
        print(f'{LABEL}: {failure}')
    for key in stale:
        print(f'{LABEL}: listed site no longer found (remove it): {key}')
    kinds = Counter(entries.get(key, {}).get('kind', 'unlisted') for key in sites)
    print(f'{LABEL}: {len(sites)} stop site(s): '
          + ', '.join(f'{kind} {count}' for kind, count in sorted(kinds.items()))
          + f'; {len(failures)} failure(s), {len(stale)} stale entr(ies)')
    if '--requirements' in argv:
        for key in sites:
            entry = entries.get(key, {})
            if entry.get('kind') == 'requirement':
                print(f'requirement: {key} -- debt: {entry.get("debt", "")}')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
