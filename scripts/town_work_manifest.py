"""Generate/check slice-0 town work coverage. Never invent review entries.

The reviewed map is separate from the older producer baseline. The output
contains the conservative census, decorators, registries, literal ladder
callbacks, producer references/calls, direct decision branches and driver sends.
AST digests make edits (including new branches in old functions) fail the gate.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import gzip
import json
import re
from pathlib import Path

import town_structure_lint as lint

ROOT = lint.ROOT
REVIEW = ROOT / 'scripts/town_work_review.json'
OUTPUT = ROOT / 'scripts/town_work_manifest.json.gz'
INDEX = ROOT / 'src/hengbot/town_work_sites.json'
REGISTRY_REVIEW = ROOT / 'scripts/town_work_registry_review.json'
SEAM_NAMES = {'_offer_execution', '_offer_execution_awaiting',
              '_offer_execution_no_step', '_offer_execution_done',
              '_town_producer_entry', 'send', 'submit_operation',
              '_post_and_barrier', '_post_wm', 'post_keys', 'wm_post'}
REGISTRIES = {'_town_need_registry', '_purchase_rungs'}


def sources():
    return {p.relative_to(lint.POLICY_ROOT).as_posix(): p.read_text(encoding='utf8')
            for p in lint.POLICY_ROOT.rglob('*.py')}


def digest(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def registry_inventory(source):
    result = []
    for site, fn in lint.collect(source).items():
        if fn.name == '_town_need_registry':
            assignment = next(n for n in lint.local_nodes(fn) if isinstance(n, ast.Assign)
                              and any(lint.name(t) == 'entries' for t in n.targets))
            for node in assignment.value.elts:
                category, ordering, count, blocking = ast.literal_eval(node)
                for occurrence in range(count):
                    result.append(dict(id=f'need:{category}:{ordering}:{occurrence}',
                                       caller=site, line=node.lineno, callee='_TownNeedLookup.produces',
                                       category=category, ordering=ordering, occurrence=occurrence,
                                       departure_blocking=blocking, ast_sha256=digest(node),
                                       expression=ast.unparse(node)))
        if fn.name == '_purchase_rungs':
            for node in lint.local_nodes(fn):
                if isinstance(node, ast.Call) and lint.name(node.func) == 'rung':
                    value = node.args[0]
                    identifier = value.value if isinstance(value, ast.Constant) else ast.unparse(value)
                    result.append(dict(id=f'purchase:{identifier}', caller=site, line=node.lineno,
                                       callee='rung/match -> _atomic_shop_transaction_key',
                                       category=ast.unparse(node.args[1]),
                                       ast_sha256=digest(node), expression=ast.unparse(node)))
    return result


def inventory(source):
    functions = lint.collect(source)
    census = lint.producer_census(source)
    names = {fn.name: [] for fn in functions.values()}
    for site, fn in functions.items():
        names[fn.name].append(site)
    selected = set(census)
    origins = {site: ['census'] for site in census}
    design = (ROOT / 'SOL-DESIGN-town-progress.md').read_text(encoding='utf8')
    design = design.split('## Code-derived inventory and evidence boundary', 1)[1].split('## Recorded failures', 1)[0]
    design_names = set(re.findall(r'\b_[A-Za-z0-9_]+', design))
    for site, fn in functions.items():
        tags = []
        if fn.name in design_names or site.split(':')[1].split('.')[0] in {'HomeErrandExecutor', 'HomeVisitExecutor'}:
            tags.append('design-table/entrance')
        if any(isinstance(n, ast.Call) and lint.name(n.func) == 'claims'
               for n in fn.decorator_list):
            tags.append('claims')
        if fn.name in REGISTRIES:
            tags.append('registry')
        if fn.name in {'choose_key', '_choose_key', '_town_producer_entry'}:
            tags.append('decision')
        if fn.name in SEAM_NAMES or fn.name.startswith(('_send_', '_consume_response_')):
            tags.append('emit/driver')
        if any(isinstance(n, ast.Call) and lint.name(n.func) in SEAM_NAMES
               for n in lint.local_nodes(fn)):
            tags.append('emit/driver')
        if tags:
            selected.add(site)
            origins.setdefault(site, []).extend(tags)
    # The ladder uses literal method/rung names. Include all resolved methods,
    # independently of census reachability or whether they have a decorator.
    for rung in lint.ladder_producers(source.get('claim_ladder.py', '')):
        for site in names.get(str(rung).split('#')[0], ()):
            selected.add(site)
            origins.setdefault(site, []).append('ladder')
    return functions, selected, origins, names


def generate(source, reviewed, registry_review=None):
    functions, selected, origins, names = inventory(source)
    missing = sorted(selected - reviewed.keys())
    stale = sorted(reviewed.keys() - selected)
    if missing or stale:
        raise ValueError(f'unmapped candidates={missing}; stale reviews={stale}')
    registry_review = (json.loads(REGISTRY_REVIEW.read_text(encoding='utf8'))
                       if registry_review is None else registry_review)
    registry = registry_inventory(source)
    registry_ids = {row['id'] for row in registry}
    if registry_ids != registry_review.keys():
        raise ValueError(f'unmapped registry={sorted(registry_ids - registry_review.keys())}; '
                         f'stale registry={sorted(registry_review.keys() - registry_ids)}')
    for row in registry:
        row.update(rows=registry_review[row['id']], admission='_town_producer_entry / town_work.validate_emit',
                   observer='shadow-v1; row-specific effect pending',
                   delegation='lookup/select -> mapped purchase/Home/use child; no independent progress',
                   possible_town_context='town maintenance registry')
    entries = []
    for site in sorted(selected):
        fn = functions[site]
        review = reviewed[site]
        if not all(review.get(k) for k in ('classification', 'rows', 'context', 'evidence')):
            raise ValueError(f'{site}: incomplete work review')
        entries.append(dict(site=site, line=fn.lineno, end_line=fn.end_lineno,
                            ast_sha256=digest(fn), origins=sorted(set(origins[site])),
                            return_evidence=[dict(line=n.lineno, expression=ast.unparse(n.value))
                                             for n in lint.local_nodes(fn)
                                             if isinstance(n, ast.Return) and n.value is not None],
                            predicate_evidence=[dict(line=n.lineno, predicate=ast.unparse(n.test))
                                                for n in lint.local_nodes(fn)
                                                if isinstance(n, (ast.If, ast.IfExp))],
                            **review))
    calls = []
    for caller, fn in sorted(functions.items()):
        for node in lint.local_nodes(fn):
            callee = lint.name(node.func) if isinstance(node, ast.Call) else lint.name(node)
            targets = [site for site in names.get(callee, ()) if site in selected]
            # References account for callbacks, aliases and registry lambdas.
            if not isinstance(node, (ast.Call, ast.Name, ast.Attribute)):
                targets = []
            if targets or isinstance(node, ast.Call) and callee in SEAM_NAMES:
                calls.append(dict(caller=caller, line=node.lineno, callee=callee,
                                  targets=sorted(targets), expression=ast.unparse(node),
                                  ast_sha256=digest(node),
                                  possible_town_context='conservative; use callee review',
                                  rows=sorted({r for target in targets for r in reviewed[target]['rows']}),
                                  admission='_town_producer_entry / town_work.validate_emit',
                                  observer='shadow-v1; no effect credit',
                                  delegation='selected child; no independent success'))
            # Direct branches and post-decision/driver rewrites get individual
            # evidence even when there is no named callee (e.g. LEAVE override).
            if caller in selected and (
                isinstance(node, ast.Return)
                or isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
                and any(lint.name(t) in {'key', 'probe', 'floor_clear'}
                        for t in (node.targets if isinstance(node, ast.Assign) else [node.target]))
            ):
                calls.append(dict(caller=caller, line=node.lineno, callee='<branch>', targets=[caller],
                                  expression=ast.unparse(node), ast_sha256=digest(node),
                                  possible_town_context=reviewed[caller]['context'],
                                  rows=reviewed[caller]['rows'],
                                  admission='_town_producer_entry / town_work.validate_emit',
                                  observer='shadow-v1; no effect credit',
                                  delegation=reviewed[caller].get('delegation', 'selected child')))
    # Top-level ladder registrations are not function bodies. Capture each
    # occurrence (including synthetic town-errand and fallback dispatchers).
    ladder_sites = []
    for node in ast.walk(ast.parse(source.get('claim_ladder.py', ''))):
        if (isinstance(node, ast.Call) and lint.name(node.func) in {'_decide','_rewrite','_town','_fallback'}
                and node.args and isinstance(node.args[0], ast.Constant)):
            producer = node.args[0].value
            resolved = names.get(str(producer).split('#')[0], [])
            if producer == 'navigator.decide':
                resolved = ['quest_navigator.py:QuestFloorNavigator.decide']
            if not resolved and str(producer).startswith(('town-errand:', 'fallback:')):
                resolved = ['policy.py:HengbotPolicy._choose_key']
            if not resolved:
                raise ValueError(f'unmapped ladder callback {producer}')
            ladder_sites.append(dict(caller='claim_ladder.py:_RUNGS', line=node.lineno,
                                     callee=producer, targets=resolved,
                                     rows=sorted({r for t in resolved for r in reviewed[t]['rows']}),
                                     expression=ast.unparse(node), ast_sha256=digest(node),
                                     admission='_town_producer_entry / town_work.validate_emit',
                                     observer='shadow-v1; no effect credit',
                                     possible_town_context='reviewed targets; conservative',
                                     delegation='selected child; no independent success'))
    return dict(schema=1, design='SOL-DESIGN-town-progress.md slice 0',
                mode='shadow (operator override); no key changes',
                candidates=len(entries), unmapped=0, entries=entries,
                call_sites=calls, registry_sites=registry, ladder_sites=ladder_sites)


def check_repository():
    try:
        expected = generate(sources(), json.loads(REVIEW.read_text(encoding='utf8')))
        actual = json.loads(gzip.decompress(OUTPUT.read_bytes()))
        index = json.loads(INDEX.read_text(encoding='utf8'))
        return ([] if expected == actual and index == runtime_index(expected)
                else ['generated town work manifest is stale; review then regenerate'])
    except (ValueError, OSError) as error:
        return [str(error)]


def runtime_index(data):
    return {entry['site']: {k: entry[k] for k in
                           ('classification', 'rows', 'delegation', 'line', 'end_line', 'ast_sha256')}
            for entry in data['entries']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    if args.write:
        data = generate(sources(), json.loads(REVIEW.read_text(encoding='utf8')))
        OUTPUT.write_bytes(gzip.compress((json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode(), mtime=0))
        INDEX.write_text(json.dumps(runtime_index(data), ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        print(f'town-work-manifest: {data["candidates"]} candidates, {len(data["call_sites"])} sites, zero unmapped')
        return 0
    findings = check_repository()
    print(f'town-work-manifest: {len(findings)} violation(s)')
    for finding in findings:
        print(finding)
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
