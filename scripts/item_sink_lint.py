#!/usr/bin/env python3
"""Default-deny item serializers and new direct claims-producer calls.

The adapter manifest pins exact calls within file:function sites, including
their multiplicity. It is reviewed source, never refreshed by the checker.
"""
from __future__ import annotations

import ast
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / 'src' / 'hengbot'
ADAPTER_PATH = Path(__file__).with_name('item_sink_adapters.json')
PREFIXES = {'d', 'p', 'k', 'w', 't', '{', '}'}
CONSTANTS = {'SELL_KEY', 'BUY_KEY', 'DEPOSIT_KEY', 'WITHDRAW_KEY',
             'DESTROY_COMMAND', 'DESTROY_KEY', 'WIELD_KEY', 'TAKEOFF_KEY',
             'INSCRIBE_KEY', 'UNINSCRIBE_KEY'}
STANDALONE_ADAPTERS = {
    ('equipment_mutation.py', 'request_wield'),
    ('equipment_mutation.py', 'request_takeoff'),
    ('policy_home.py', '_destroy_item_key'),
}


def _name(node):
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ''


def _functions(tree):
    return [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _producers(tree):
    return {function.name for function in _functions(tree)
            if any(isinstance(decorator, ast.Call) and _name(decorator.func) == 'claims'
                   for decorator in function.decorator_list)}


def producer_names():
    return set().union(*(_producers(ast.parse(path.read_text(encoding='utf8')))
                        for path in POLICY_ROOT.glob('*.py')))


def _ancestors(node, parents):
    while node in parents:
        node = parents[node]
        yield node


def direct_calls(source, names):
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    aliases = {}
    for assignment in ast.walk(tree):
        if isinstance(assignment, ast.Assign) and _name(assignment.value) in names:
            for target in assignment.targets:
                if isinstance(target, ast.Name):
                    aliases[target.id] = _name(assignment.value)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or aliases.get(_name(node.func), _name(node.func)) not in names:
            continue
        ancestors = list(_ancestors(node, parents))
        admitted = any(isinstance(ancestor, ast.Lambda)
                       and isinstance(parents.get(ancestor), ast.Call)
                       and _name(parents[ancestor].func) == '_town_producer_entry'
                       for ancestor in ancestors)
        if admitted:
            continue
        function = next((ancestor.name for ancestor in ancestors
                         if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef))), '<module>')
        guards = []
        child = node
        for ancestor in ancestors:
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                break
            if isinstance(ancestor, (ast.If, ast.While)):
                branch = 'body' if child in ancestor.body else 'orelse'
                guards.append(f'{type(ancestor).__name__}:{branch}:{ast.unparse(ancestor.test)}')
            elif isinstance(ancestor, (ast.For, ast.AsyncFor)):
                guards.append(f'For:{ast.unparse(ancestor.iter)}')
            child = ancestor
        expression = ast.unparse(node) + ' @ ' + ' / '.join(reversed(guards))
        yield function, expression, node.lineno


def _terms(node):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _terms(node.left) + _terms(node.right)
    if isinstance(node, ast.JoinedStr):
        return [value.value if isinstance(value, ast.FormattedValue) else value for value in node.values]
    return [node]


def _valid_verdict(function, verdict):
    if isinstance(verdict, ast.Call) and _name(verdict.func) == 'reservation_verdict':
        return True
    if not isinstance(verdict, ast.Name) or function is None:
        return False
    typed = any(argument.arg == verdict.id and _name(argument.annotation) == 'ReservationVerdict'
                for argument in (*function.args.args, *function.args.kwonlyargs))
    writes = [assignment.value for assignment in ast.walk(function)
              if isinstance(assignment, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == verdict.id
                      for target in assignment.targets)]
    trusted = lambda value: isinstance(value, ast.Call) and _name(value.func) in {
        'reservation_verdict', 'standalone_verdict'}
    return (typed or bool(writes)) and all(trusted(value) for value in writes)


def analyze_source(source, filename='mutant.py', *, names=None, adapters=None,
                   check_exit=False):
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    findings = []
    names = (producer_names() if names is None else names) | _producers(tree)
    adapters = {} if adapters is None else adapters
    protected_names = {'ReservationVerdict', 'standalone_verdict', 'item_command',
                       'checked_item_command', '_historical_item_command'}
    call_aliases = {}
    for assignment in ast.walk(tree):
        if isinstance(assignment, ast.Assign) and _name(assignment.value) in protected_names:
            for target in assignment.targets:
                if isinstance(target, ast.Name):
                    call_aliases[target.id] = _name(assignment.value)
        elif isinstance(assignment, ast.ImportFrom):
            for alias in assignment.names:
                if alias.name in protected_names and alias.asname:
                    call_aliases[alias.asname] = alias.name
    calls = list(direct_calls(source, names))
    counts = Counter((function, expression) for function, expression, _line in calls)
    for (function, expression), count in counts.items():
        expected = adapters.get(f'{filename}:{function}', {}).get(expression, 0)
        if count > expected:
            line = next(line for name, expr, line in calls if (name, expr) == (function, expression))
            findings.append(f'line {line}: {function} calls a claims producer outside its entry/adapter')

    for node in ast.walk(tree):
        function = next((ancestor for ancestor in _ancestors(node, parents)
                         if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
        function_name = function.name if function else '<module>'
        serializer = filename == 'item_reservation.py' and function_name == 'item_command'
        if isinstance(node, ast.Call):
            name = call_aliases.get(_name(node.func), _name(node.func))
            if name == 'ReservationVerdict' and filename != 'item_reservation.py':
                findings.append(f'line {node.lineno}: only item_reservation.py constructs ReservationVerdict')
            if name == 'standalone_verdict' and filename != 'item_reservation.py' and (
                    filename, function_name) not in STANDALONE_ADAPTERS:
                findings.append(f'line {node.lineno}: standalone verdict outside pinned low-level adapter')
            if name in {'item_command', 'checked_item_command', '_historical_item_command'}:
                index = 3 if name == 'checked_item_command' else 2
                verdict = node.args[index] if len(node.args) > index else next(
                    (keyword.value for keyword in node.keywords if keyword.arg == 'verdict'), None)
                if not _valid_verdict(function, verdict):
                    findings.append(f'line {node.lineno}: serializer requires a ReservationVerdict')
            if name == '_destroy_item_key':
                snapshot = node.args[1] if len(node.args) > 1 else next(
                    (keyword.value for keyword in node.keywords if keyword.arg == 'snapshot'), None)
                policy = next((keyword.value for keyword in node.keywords if keyword.arg == 'policy'), None)
                if (snapshot is None or isinstance(snapshot, ast.Constant) and snapshot.value is None
                        or policy is None or isinstance(policy, ast.Constant) and policy.value is None):
                    findings.append(f'line {node.lineno}: destruction adapter requires the decision snapshot and policy')
            if name in {'request_wield', 'request_takeoff'} and filename.startswith('policy'):
                verdict = next((keyword.value for keyword in node.keywords if keyword.arg == 'verdict'), None)
                if not _valid_verdict(function, verdict):
                    findings.append(f'line {node.lineno}: equipment adapter requires a reservation verdict')
        composition = isinstance(node, (ast.BinOp, ast.JoinedStr))
        terms = _terms(node)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            terms = [node.left, node.right]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == 'format' and isinstance(node.func.value, ast.Constant):
                terms = [node.func.value, *node.args]
                composition = True
            elif (node.func.attr == 'join' and node.args
                  and isinstance(node.args[0], (ast.List, ast.Tuple))):
                terms = node.args[0].elts
                composition = True
        if composition and not serializer:
            aliases = {}
            if function is not None:
                for assignment in ast.walk(function):
                    if isinstance(assignment, ast.Assign) and isinstance(assignment.value, ast.Name):
                        for target in assignment.targets:
                            if isinstance(target, ast.Name):
                                aliases[target.id] = assignment.value.id
                    elif (isinstance(assignment, ast.Assign)
                          and isinstance(assignment.value, ast.Constant)
                          and assignment.value.value in PREFIXES):
                        for target in assignment.targets:
                            if isinstance(target, ast.Name):
                                aliases[target.id] = assignment.value.value
            for index, term in enumerate(terms[:-1]):
                name = _name(term)
                seen = set()
                while name in aliases and name not in seen:
                    seen.add(name)
                    name = aliases[name]
                literal = term.value if isinstance(term, ast.Constant) else None
                format_prefix = (isinstance(literal, str) and len(literal) > 1
                                 and literal[0] in PREFIXES and literal[1] in '{%')
                if name in CONSTANTS | PREFIXES or literal in PREFIXES or format_prefix:
                    findings.append(f'line {node.lineno}: {function_name} composes a raw item command')
                    break
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'item_command':
            arguments = node.args.args
            if (filename != 'item_reservation.py' or len(arguments) != 3
                    or arguments[-1].arg != 'verdict'
                    or _name(arguments[-1].annotation) != 'ReservationVerdict'
                    or node.args.defaults):
                findings.append(f'line {node.lineno}: item_command must require a ReservationVerdict')
        if check_exit and filename == 'policy.py' and isinstance(node, ast.FunctionDef) and node.name == 'choose_key':
            returns = [child for child in ast.walk(node) if isinstance(child, ast.Return)
                       and next((ancestor for ancestor in _ancestors(child, parents)
                                 if isinstance(ancestor, ast.FunctionDef)), None) is node]
            non_none = [child for child in returns if child.value is not None
                        and not (isinstance(child.value, ast.Constant) and child.value.value is None)]
            if len(non_none) != 1:
                findings.append(f'line {node.lineno}: choose_key must have exactly one non-None return site')
            elif (len(node.body) < 2 or not isinstance(node.body[-1], ast.Return)
                  or not isinstance(node.body[-2], ast.Expr)
                  or not isinstance(node.body[-2].value, ast.Call)
                  or _name(node.body[-2].value.func) != '_record_decision_claim'):
                findings.append(f'line {node.lineno}: choose_key exit must record its decision claim')
    return sorted(set(findings))


def analyze_repository(*, check_exit=False):
    names = producer_names()
    adapters = json.loads(ADAPTER_PATH.read_text(encoding='utf8'))
    findings = []
    current = {}
    for path in sorted(POLICY_ROOT.glob('*.py')):
        source = path.read_text(encoding='utf8')
        findings.extend(f'{path.name}: {finding}' for finding in analyze_source(
            source, path.name, names=names, adapters=adapters, check_exit=check_exit))
        for function, expression, _line in direct_calls(source, names):
            site = f'{path.name}:{function}'
            current.setdefault(site, Counter())[expression] += 1
    for site, expressions in adapters.items():
        if current.get(site) != Counter(expressions):
            findings.append(f'{site}: pinned adapter call site changed or disappeared')
    return findings


def main():
    findings = analyze_repository()
    for finding in findings:
        print(f'item-sink-lint: {finding}')
    print(f'item-sink-lint: {len(findings)} violation(s)')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
