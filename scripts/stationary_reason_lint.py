#!/usr/bin/env python3
"""Every wait or rest the policy sends names a reason the loop guard knows, or a bound.

Whole-bot maintainability review 2026-11-23, K3 / (a)-1.  The driver's position loop guard
(cli._cell_loop_guard_applies, LOOP_WINDOW = 40 decisions on <= LOOP_MAX_DISTINCT cells) stops
the bot when it stays on a handful of cells; the reasons that hold the player on one cell by
design are rows of ``reasons.STATIONARY_ROWS`` (HOLD / EXEMPT / QUEST_COMBAT / ACTION), each with
its own leash.  Nothing tied a new wait to that table: a hold under a reason missing from it
stops the bot as loop-detected once it lasts 40 decisions (11-06 Q18's rest, 11-11 Q25's trap
search, 11-13 Q25's recharge rest, 11-23 n1-a life-535's blind wait).

A *wait site* is, in ``src/hengbot``,

* a ``return <expr>`` whose value resolves (reason_registry_lint.Scanner: literals, module and
  imported constants, locals) to the wait key ``"5"`` (policy_constants.WAIT_KEY) or to a rest
  command ``R<count or &>\\r`` (REST_MACRO, ``R100\\r``, ``f"R{n}\\r"``), with the reason the same
  function puts into ``last_reason`` before it (the nearest assignment on the way up the
  statement lists; one inside an earlier ``if`` / ``with`` / ``try`` counts with all its
  branches);
* a call whose first argument is such a key with a ``reason=`` keyword
  (``DecisionCandidate(WAIT_KEY, reason=...)``).

A wait site is fine when every shape of its reason is

* ``reasons.stationary(shape)`` (a row of STATIONARY_ROWS), or
* a row of ``reasons.BOUNDED_WAITS``: the reason names the module constant that bounds it
  (checked to exist), so the hold ends by itself and the guard may count it.

Otherwise it is a finding ``<file>:<line>: unregistered wait <reason> (<key>)``.  The findings of
2026-11-23 are recorded in ``scripts/stationary_reason_lint_baseline.json`` (lint_baseline: keys
are ``<file>:<function>: <message>`` with counts, never line numbers); only a finding beyond that
baseline fails.  A wait whose reason the scanner cannot resolve (a parameter with no caller,
``self.last_reason``) is not a finding.

``--sites`` lists every wait site with its verdict.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import reason_registry_lint as registry  # noqa: E402
from reason_registry_lint import WILD, Scanner, _is_reason_target, repository_sources  # noqa: E402

from hengbot import reasons  # noqa: E402  -- reason_registry_lint put src on the path

POLICY_ROOT = registry.POLICY_ROOT
LINT = 'stationary_reason_lint'
WAIT_KEY = '5'
REST_COMMAND = re.compile(r'^R(&|\d+|\*)\r$')


def key_kind(shapes) -> str | None:
    """``wait`` / ``rest`` when the resolved key shapes include the wait key or a rest command."""
    shapes = set(shapes)
    if WAIT_KEY in shapes:
        return 'wait'
    if any(REST_COMMAND.match(shape) for shape in shapes):
        return 'rest'
    return None


def _parents(tree) -> dict:
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


_TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _assigned_reasons(statement) -> list:
    """The ``last_reason`` values a statement assigns that reach the statement after it: a
    simple assignment, or one inside a branch of an ``if`` / ``with`` / ``try`` / loop that does
    not end in ``return`` / ``raise`` / ``continue`` / ``break`` (nested functions are not
    looked into)."""
    out = []
    if isinstance(statement, ast.Assign):
        for target in statement.targets:
            if _is_reason_target(target):
                out.append(statement.value)
            elif isinstance(target, ast.Tuple):
                for index, element in enumerate(target.elts):
                    if (_is_reason_target(element) and isinstance(statement.value, ast.Tuple)
                            and len(statement.value.elts) == len(target.elts)):
                        out.append(statement.value.elts[index])
        return out
    if isinstance(statement, ast.AnnAssign):
        return [statement.value] if _is_reason_target(statement.target) and statement.value else []
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return []
    blocks = [value for _, value in ast.iter_fields(statement)
              if isinstance(value, list) and value and isinstance(value[0], ast.stmt)]
    if isinstance(statement, ast.Try):
        blocks += [handler.body for handler in statement.handlers]
    for block in blocks:
        if isinstance(block[-1], _TERMINATORS):
            continue
        for inner in reversed(block):
            found = _assigned_reasons(inner)
            if found:
                out.extend(found)
                break
    return out


def preceding_reasons(node, parents) -> list | None:
    """The ``last_reason`` values set before ``node`` on the way up its function's statement
    lists; None when the function sets none before it."""
    current = node
    while True:
        parent = parents.get(current)
        if parent is None:
            return None
        for _, value in ast.iter_fields(parent):
            if isinstance(value, list) and current in value:
                for sibling in reversed(value[:value.index(current)]):
                    found = _assigned_reasons(sibling)
                    if found:
                        return found
        if isinstance(parent, _FUNCTIONS):
            return None
        current = parent


def _function_of(node, parents):
    current = parents.get(node)
    while current is not None and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
        current = parents.get(current)
    return current


def bounded_findings() -> list[str]:
    """A ``reasons.BOUNDED_WAITS`` row whose bound is not a module constant."""
    findings = []
    for row in reasons.BOUNDED_WAITS:
        module, _, name = row.bound.rpartition('.')
        path = POLICY_ROOT / f'{module}.py'
        if not module or not path.exists():
            findings.append(f'bounded wait {row.reason!r}: no module {module!r} for {row.bound!r}')
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        names = {target.id for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
                 for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
                 if isinstance(target, ast.Name)}
        if name not in names:
            findings.append(f'bounded wait {row.reason!r}: {row.bound!r} is not a module constant')
        if not row.rule:
            findings.append(f'bounded wait {row.reason!r}: no rule')
    return findings


def registered(shape: str) -> bool:
    return reasons.stationary(shape) or shape in {row.reason for row in reasons.BOUNDED_WAITS}


def sites(sources: dict[str, str] | None = None) -> list[tuple[str, int, str, str, frozenset]]:
    """Every wait site: (module, line, function, key kind, reason shapes)."""
    sources = sources if sources is not None else repository_sources()
    scanner = Scanner(sources)
    out = []
    for module, source in sorted(sources.items()):
        tree = scanner.modules[module].tree
        parents = _parents(tree)
        for node in ast.walk(tree):
            reason_exprs = None
            if isinstance(node, ast.Return) and node.value is not None:
                kind = key_kind(scanner.resolve(module, node.value, node.value))
                if kind is None:
                    continue
                reason_exprs = preceding_reasons(node, parents)
            elif isinstance(node, ast.Call) and node.args and any(k.arg == 'reason' for k in node.keywords):
                kind = key_kind(scanner.resolve(module, node.args[0], node.args[0]))
                if kind is None:
                    continue
                reason_exprs = [k.value for k in node.keywords if k.arg == 'reason']
            else:
                continue
            shapes = set()
            for expr in reason_exprs or []:
                shapes |= scanner.resolve(module, expr, expr)
            function = _function_of(node, parents)
            out.append((module, node.lineno, function.name if function else '<module>', kind,
                        frozenset(shapes - {WILD})))
    # ``self.last_reason = self.last_reason.replace(old, new, 1)`` relabels the wait a helper sent
    # (policy._fruitless_disengage relabels combat:disengage-* as combat:avoid-unprofitable-unique-*):
    # every wait shape with ``old`` arrives under the new name as well (as reason_registry_lint).
    relabelled = []
    for module, line, function, old, new in _relabels(scanner, sources):
        for _, _, _, kind, shapes in out:
            moved = frozenset(shape.replace(old, new, 1) for shape in shapes if old in shape)
            if moved:
                relabelled.append((module, line, function, kind, moved))
    return out + relabelled


def _relabels(scanner, sources) -> list[tuple[str, int, str, str, str]]:
    """(module, line, function, old, new) of every ``last_reason = <reason>.replace(old, new)``."""
    out = []
    for module in sorted(sources):
        tree = scanner.modules[module].tree
        parents = _parents(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not any(_is_reason_target(t) for t in node.targets):
                continue
            value = node.value
            if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                    and value.func.attr == 'replace' and len(value.args) >= 2
                    and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in value.args[:2])):
                function = _function_of(node, parents)
                out.append((module, node.lineno, function.name if function else '<module>',
                            value.args[0].value, value.args[1].value))
    return out


def findings(sources: dict[str, str] | None = None) -> list[str]:
    out = []
    for module, line, _, kind, shapes in sites(sources):
        for shape in sorted(shapes):
            if not registered(shape):
                out.append(f'{module}.py:{line}: unregistered {kind} {shape!r}')
    return out


def new_findings(sources: dict[str, str] | None = None) -> list[str]:
    """The findings beyond the recorded baseline (what fails the lint)."""
    import lint_baseline
    found = findings(sources)
    new, _ = lint_baseline.new_findings(
        LINT, found, lambda finding: lint_baseline.line_finding_key(finding, POLICY_ROOT))
    return new


def main(argv: list[str] | None = None) -> int:
    import lint_baseline
    argv = sys.argv[1:] if argv is None else argv
    if '--sites' in argv:
        for module, line, function, kind, shapes in sites():
            verdict = 'ok' if shapes and all(registered(s) for s in shapes) else (
                'unresolved' if not shapes else 'UNREGISTERED')
            print(f'{module}.py:{line}\t{function}\t{kind}\t{",".join(sorted(shapes)) or "-"}\t{verdict}')
        return 0
    broken = bounded_findings()
    for finding in broken:
        print(f'stationary-reason-lint: {finding}')
    code = lint_baseline.gate(
        LINT, 'stationary-reason-lint', findings(),
        lambda finding: lint_baseline.line_finding_key(finding, POLICY_ROOT), argv=argv)
    return 1 if broken else code


if __name__ == '__main__':
    raise SystemExit(main())
