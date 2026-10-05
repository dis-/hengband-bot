#!/usr/bin/env python3
"""Default-deny producer and item-intent census, with reviewed exact baselines.

This is a conservative AST check, not a town predicate solver. Dungeon paths
and data helpers are retained explicitly; no module or family is exempt.
Baselines are inputs to review, never updated by running the checker.
"""
from __future__ import annotations

import ast
from collections import defaultdict
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / 'src' / 'hengbot'
PRODUCER_BASELINE = Path(__file__).with_name('town_producer_baseline.json')
INTENT_BASELINE = Path(__file__).with_name('item_intent_baseline.json')
INTENT_NAME = re.compile(r'pending|retry|reserv|deferred|inflight|errand')
IDENTITY_NAME = re.compile(r'(?:signature|identity|slot|letter|item_sig)(?:$|_)')
IDENTITIES = {'item_signature', '_item_signature', 'equipment_identity',
              'equipment_move_identity', 'InventoryItem', 'StoreItem',
              'EquipmentTransactionSession', 'EquipmentTransactionPlan',
              'HomeErrandExecutor', 'HomeVisitExecutor', 'EquipmentMutationExecutor',
              'HomeDisposalState', 'OwnedEquipmentCatalog'}


def name(node):
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ''


def local_nodes(function):
    """Skip nested definitions, whose returns belong to a separate function."""
    def walk(node):
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                yield from walk(child)
    for statement in function.body:
        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from walk(statement)


def collect(sources):
    functions = {}
    for filename, source in sources.items():
        tree = ast.parse(source)
        def walk(node, scope=''):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified = scope + child.name
                    if not isinstance(child, ast.ClassDef):
                        functions[f'{filename}:{qualified}'] = child
                    walk(child, qualified + '.')
                else:
                    walk(child, scope)
        walk(tree)
    return functions


def policy_class_names(sources):
    classes = {}
    aliases = {}
    for source in sources.values():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef):
                classes[node.name] = {name(base) for base in node.bases}
            elif isinstance(node, ast.ImportFrom):
                aliases.update({alias.asname: alias.name for alias in node.names if alias.asname})
    result = {'HengbotPolicy'}
    queue = list(result)
    while queue:
        for base in classes.get(queue.pop(), ()):
            base = aliases.get(base, base)
            if base not in result:
                result.add(base)
                queue.append(base)
    # Include named mixins in small source fixtures and unresolved inheritance;
    # this enlarges the census, never exempts a producer.
    return result | {cls for cls in classes if cls.endswith('Mixin')}


def producer_census(sources):
    # Respect import direction: a same-named method in a driver that imports
    # policy is not a policy descendant. Include imports inside function bodies.
    imports = {}
    for filename, source in sources.items():
        imported = set()
        for node in ast.walk(ast.parse(source)):
            modules = []
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    package = filename.split('/')[:-node.level]
                    module = '/'.join(package + (node.module.split('.') if node.module else []))
                    modules.append(module)
                    modules.extend((module + '/' if module else '') + alias.name for alias in node.names)
                elif node.module and (node.module == 'hengbot' or node.module.startswith('hengbot.')):
                    module = '' if node.module == 'hengbot' else node.module.removeprefix('hengbot.').replace('.', '/')
                    modules.append(module)
                    modules.extend((module + '/' if module else '') + alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name.removeprefix('hengbot.').replace('.', '/')
                               for alias in node.names if alias.name.startswith('hengbot.'))
            for module in modules:
                imported.update({module + '.py', (module + '/' if module else '') + '__init__.py'})
        imports[filename] = imported
    allowed = {'policy.py'} & sources.keys()
    queue = list(allowed)
    while queue:
        for filename in imports[queue.pop()] & sources.keys() - allowed:
            allowed.add(filename)
            queue.append(filename)
    sources = {filename: source for filename, source in sources.items() if filename in allowed}
    functions = collect(sources)
    policy_classes = policy_class_names(sources)
    import_aliases = {}
    module_aliases = {}
    class_aliases = {}
    constants = {}
    for filename, source in sources.items():
        tree = ast.parse(source)
        import_aliases[filename] = {alias.asname: alias.name for node in ast.walk(tree)
                                   if isinstance(node, ast.ImportFrom)
                                   for alias in node.names if alias.asname}
        constants[filename] = {target.id: node.value for node in tree.body
                               if isinstance(node, ast.Assign)
                               for target in node.targets if isinstance(target, ast.Name)
                               and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)}
        module_aliases[filename] = {target.id: node.value for node in tree.body
                                   if isinstance(node, ast.Assign)
                                   for target in node.targets if isinstance(target, ast.Name)
                                   and isinstance(node.value, (ast.Name, ast.Attribute))}
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef):
                class_aliases[cls.name] = {target.id: node.value for node in cls.body
                                          if isinstance(node, ast.Assign)
                                          for target in node.targets if isinstance(target, ast.Name)
                                          and isinstance(node.value, (ast.Name, ast.Attribute))}
    by_name = defaultdict(set)
    for site, function in functions.items():
        by_name[function.name].add(site)
    def resolve(symbol, caller, seen=frozenset()):
        if isinstance(symbol, ast.Attribute) and name(symbol.value) == 'self':
            owner = caller.split(':', 1)[1].split('.')[0]
            owners = policy_classes if owner in policy_classes else {owner}
            aliases = set()
            for cls in owners:
                marker = cls + '.' + symbol.attr
                value = class_aliases.get(cls, {}).get(symbol.attr)
                if value is not None and marker not in seen:
                    if isinstance(value, ast.Name):
                        aliases |= resolve(value, caller, seen | {marker})
                        value = ast.Attribute(value=ast.Name(id='self'), attr=value.id)
                    aliases |= resolve(value, caller, seen | {marker})
            return aliases | {site for site in by_name[symbol.attr]
                    if site.split(':', 1)[1].split('.')[0] in (
                        owners)}
        if isinstance(symbol, ast.Name):
            if symbol.id in module_aliases[caller.split(':')[0]] and symbol.id not in seen:
                return resolve(module_aliases[caller.split(':')[0]][symbol.id], caller, seen | {symbol.id})
            resolved = import_aliases[caller.split(':')[0]].get(symbol.id, symbol.id)
            local = {site for site in by_name[resolved] if site.split(':')[0] == caller.split(':')[0]}
            return local or by_name[resolved]
        if (isinstance(symbol, ast.Call) and name(symbol.func) == 'getattr'
                and len(symbol.args) >= 2 and isinstance(symbol.args[1], ast.Constant)
                and isinstance(symbol.args[1].value, str)):
            return resolve(ast.Attribute(value=symbol.args[0], attr=symbol.args[1].value), caller)
        return by_name[name(symbol)]
    edges = {}
    for site, function in functions.items():
        nodes = list(local_nodes(function))
        aliases = {}
        for node in nodes:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = name(node.value)
        calls = [node.func for node in nodes if isinstance(node, ast.Call)]
        # Callback names (including lambda bodies) and assigned method aliases.
        calls += [node for node in nodes if isinstance(node, (ast.Name, ast.Attribute))
                  and (name(node) in by_name or isinstance(node, ast.Name)
                       and node.id in (import_aliases[site.split(':')[0]].keys()
                                       | module_aliases[site.split(':')[0]].keys()))]
        calls += [node for node in nodes if isinstance(node, ast.Call) and name(node.func) == 'getattr']
        edges[site] = set().union(*(resolve(call, site) for call in calls)) if calls else set()
    reach = {site for site, function in functions.items()
             if site.endswith(':HengbotPolicy.choose_key')}
    queue = list(reach)
    while queue:
        for callee in edges[queue.pop()] - reach:
            reach.add(callee)
            queue.append(callee)

    # Any reachable string-returning function is a candidate, even if its
    # caller currently discards that return. This also covers stored callbacks
    # and new literal-key producers without depending on *_key naming.
    candidates = {}
    for site in sorted(reach):
        function = functions[site]
        nodes = list(local_nodes(function))
        writes = defaultdict(list)
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    writes[ast.unparse(target)].append(node.value)
        def string_value(expr, seen=frozenset()):
            if expr is None:
                return False
            symbol = ast.unparse(expr)
            if isinstance(expr, ast.Name) and expr.id in constants[site.split(':')[0]]:
                return True
            if symbol in writes and symbol not in seen:
                return any(string_value(value, seen | {symbol}) for value in writes[symbol])
            if isinstance(expr, ast.Constant):
                return isinstance(expr.value, str)
            if isinstance(expr, ast.JoinedStr):
                return True
            if isinstance(expr, (ast.Name, ast.Attribute)):
                return bool(re.search(r'key|macro|command', name(expr), re.I))
            if isinstance(expr, ast.Call):
                return bool(re.search(r'key|command|emit|step_toward|decide|request_wield|request_takeoff', name(expr.func)))
            if isinstance(expr, ast.IfExp):
                return string_value(expr.body, seen) or string_value(expr.orelse, seen)
            if isinstance(expr, (ast.BoolOp, ast.BinOp, ast.Subscript)):
                return any(string_value(child, seen) for child in ast.iter_child_nodes(expr))
            return False
        returns = [node.value for node in nodes if isinstance(node, ast.Return)]
        typed = function.returns is not None and 'str' in ast.unparse(function.returns)
        root_result = site.endswith(':HengbotPolicy.choose_key') and any(
            value is not None and not (isinstance(value, ast.Constant) and value.value is None)
            for value in returns)
        if typed or root_result or any(string_value(value) for value in returns):
            marked = any(isinstance(decorator, ast.Call) and name(decorator.func) == 'claims'
                         for decorator in function.decorator_list)
            candidates[site] = {'name': function.name, 'marked': marked,
                                'line': function.lineno}

    # Follow return-value dependencies as well, independent of names or
    # annotations: return new_producer(), key = new_producer(); return key,
    # aliases, callbacks and composed/subscripted results cannot hide a producer.
    queue = list(candidates)
    processed = set()
    while queue:
        site = queue.pop()
        if site in processed:
            continue
        processed.add(site)
        function = functions[site]
        nodes = list(local_nodes(function))
        writes = defaultdict(list)
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    writes[ast.unparse(target)].append(node.value)
        def dependencies(expr, seen=frozenset()):
            if expr is None:
                return set()
            symbol = ast.unparse(expr)
            result = set()
            if symbol in writes and symbol not in seen:
                for value in writes[symbol]:
                    result |= dependencies(value, seen | {symbol})
            if isinstance(expr, ast.Call):
                result |= resolve(expr.func, site)
                if name(expr.func) in writes:
                    for value in writes[name(expr.func)]:
                        result |= resolve(value, site)
            if isinstance(expr, ast.IfExp):
                children = [expr.body, expr.orelse]
            elif isinstance(expr, (ast.Compare, ast.UnaryOp)):
                children = []
            else:
                children = ast.iter_child_nodes(expr)
            for child in children:
                result |= dependencies(child, seen)
            return result
        callees = set()
        for node in nodes:
            if isinstance(node, ast.Return):
                callees |= dependencies(node.value)
        for callee in callees & reach:
            if callee not in candidates:
                fn = functions[callee]
                if not any(isinstance(n, ast.Return) and n.value is not None for n in local_nodes(fn)):
                    continue
                candidates[callee] = {'name': fn.name, 'line': fn.lineno,
                    'marked': any(isinstance(d, ast.Call) and name(d.func) == 'claims' for d in fn.decorator_list)}
            queue.append(callee)
    return candidates


def ladder_producers(source):
    return {node.args[0].value for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and name(node.func) in {'Rung', '_decide', '_rewrite', '_town', '_fallback'} and node.args
            and isinstance(node.args[0], ast.Constant)}


def intent_census(sources):
    functions = collect(sources)
    policy_classes = policy_class_names(sources)
    item_returns = {fn.name for fn in functions.values() if fn.returns is not None
                    and any(kind in ast.unparse(fn.returns) for kind in ('InventoryItem', 'StoreItem'))}
    result = defaultdict(set)
    for site, function in functions.items():
        # Only policy and its mixins, not unrelated executor self attributes.
        owner = site.split(':', 1)[1].split('.')[0]
        if owner not in policy_classes:
            continue
        nodes = list(local_nodes(function))
        tainted = {argument.arg for argument in (*function.args.args, *function.args.kwonlyargs)
                   if argument.arg in {'item', 'inventory_item', 'store_item'}
                   or argument.annotation is not None and any(
                       kind in ast.unparse(argument.annotation) for kind in ('InventoryItem', 'StoreItem'))}
        assignments = [node for node in nodes if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))]
        def sensitive(value):
            return any(isinstance(node, ast.Call) and name(node.func) in IDENTITIES | item_returns
                       or isinstance(node, ast.Name) and (node.id in tainted or IDENTITY_NAME.search(node.id))
                       or isinstance(node, ast.Attribute) and node.attr in {
                           'slot', 'letter', 'signature', 'item_identity', 'move_identity',
                           'inventory', 'equipment'}
                       for node in ast.walk(value))
        changed = True
        while changed:
            changed = False
            for node in assignments:
                if node.value is None or not sensitive(node.value):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for child in ast.walk(target):
                        if isinstance(child, ast.Name) and child.id != 'self' and child.id not in tainted:
                            tainted.add(child.id)
                            changed = True
        for node in nodes:
            targets = (node.targets if isinstance(node, ast.Assign) else [node.target]
                       if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) else [])
            if isinstance(node, ast.Call) and name(node.func) == 'setattr' and len(node.args) >= 3:
                if isinstance(node.args[0], ast.Name) and node.args[0].id == 'self' and isinstance(node.args[1], ast.Constant):
                    attr = node.args[1].value
                    if isinstance(attr, str) and (INTENT_NAME.search(attr) or sensitive(node.args[2])):
                        result[attr].add(site)
            for target in targets:
                for child in ast.walk(target):
                    if (isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name)
                            and child.value.id == 'self' and (INTENT_NAME.search(child.attr)
                            or getattr(node, 'value', None) is not None and sensitive(node.value)
                            or isinstance(target, ast.Subscript) and sensitive(target))):
                        result[child.attr].add(site)
            # In-place additions also persist identities without an assignment.
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                target = node.func.value
                if (node.func.attr in {'add', 'append', 'extend', 'update', 'setdefault'}
                        and isinstance(target, ast.Attribute) and name(target.value) == 'self'
                        and (INTENT_NAME.search(target.attr) or any(sensitive(arg) for arg in node.args))):
                    result[target.attr].add(site)
    return dict(result)


def source_registry(source):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(name(t) == 'ITEM_RESERVATION_SOURCES' for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


def analyze_sources(sources, producer_baseline, intent_baseline):
    findings = []
    candidates = producer_census(sources)
    ladder = ladder_producers(sources.get('claim_ladder.py', ''))
    unregistered = {site for site, row in candidates.items()
                    if not (row['marked'] and row['name'] in ladder)}
    for site in sorted(unregistered - producer_baseline.keys()):
        findings.append(f'{site}: new unregistered key-returning producer; requires @claims and claim_ladder registration')
    for site in sorted(producer_baseline.keys() - unregistered):
        findings.append(f'{site}: producer baseline entry disappeared or became registered; review/remove it')
    for site, reason in producer_baseline.items():
        if not isinstance(reason, str) or not reason.startswith(('dungeon-only:', 'pure helper:', 'delegated adapter:', 'town producer to migrate:')):
            findings.append(f'{site}: producer baseline needs a reviewed reason category')
    intents = intent_census(sources)
    registry = source_registry(sources.get('item_reservation.py', ''))
    core = ast.parse(sources.get('item_reservation.py', ''))
    components = set()
    for node in core.body:
        if isinstance(node, ast.Assign) and any(name(t) == '_SOURCE_PREDICATES' for t in node.targets):
            if isinstance(node.value, ast.Dict):
                components = {key.value for key in node.value.keys if isinstance(key, ast.Constant)}
    for attr, entry in registry.items():
        if (not isinstance(entry, tuple) or len(entry) != 2 or entry[0] not in components
                or not isinstance(entry[1], str) or not entry[1].strip()):
            findings.append(f'{attr}: reservation source requires a composed predicate component and reviewed reason')
    for attr in sorted(intents.keys() - registry.keys() - intent_baseline.keys()):
        findings.append(f'{attr}: new unregistered item intent ({", ".join(sorted(intents[attr]))})')
    for attr in sorted((registry.keys() | intent_baseline.keys()) - intents.keys()):
        findings.append(f'{attr}: item-intent baseline/source disappeared; review/remove it')
    for attr in registry.keys() & intent_baseline.keys():
        findings.append(f'{attr}: item intent cannot be both a source and an exclusion')
    for attr, reason in intent_baseline.items():
        if not isinstance(reason, str) or not reason.strip():
            findings.append(f'{attr}: non-item-intent exclusion needs a reason')
    return findings


def analyze_repository():
    sources = {path.relative_to(POLICY_ROOT).as_posix(): path.read_text(encoding='utf8')
               for path in POLICY_ROOT.rglob('*.py')}
    findings = analyze_sources(sources, json.loads(PRODUCER_BASELINE.read_text(encoding='utf8')),
                               json.loads(INTENT_BASELINE.read_text(encoding='utf8')))
    from town_work_manifest import check_repository
    return findings + check_repository()


def main():
    findings = analyze_repository()
    for finding in findings:
        print('town-structure-lint: ' + finding)
    print(f'town-structure-lint: {len(findings)} violation(s)')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
