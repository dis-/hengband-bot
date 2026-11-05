#!/usr/bin/env python3
"""The dungeon decision ladder as the source says it is, against hengbot.dungeon_ladder.

The order of the rungs is the order of ``return`` in ``HengbotPolicy._decide``:
nothing else states it.  This reads that order from the AST and fails when the
table in ``hengbot/dungeon_ladder.py`` says anything else, so a reorder is a
visible one-line diff of the table in the same commit.  ``--print`` lists the
rows as the source has them, for writing the table's diff.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hengbot import dungeon_ladder as ladder  # noqa: E402

POLICY_ROOT = ROOT / 'src' / 'hengbot'
LADDER_START = '_build_grid_index'
ENTRY = '_town_producer_entry'
# They send the step a rung already chose: the rung is the row, not its key.
COMPOSERS = ('_step_toward', '_direction_key')


class Row(NamedTuple):
    name: str
    kind: str
    line: int


def dotted(node) -> str:
    """``a.b.c`` for names and attributes, with ``self.`` dropped."""
    if isinstance(node, ast.Name):
        return '' if node.id == 'self' else node.id
    if isinstance(node, ast.Attribute):
        owner = dotted(node.value)
        return f'{owner}.{node.attr}' if owner else node.attr
    return ''


def _function(tree, name):
    return next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name)


def _entry_name(call) -> str | None:
    if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr == ENTRY and call.args
            and isinstance(call.args[0], ast.Constant)):
        return call.args[0].value
    return None


def _call_name(call) -> str:
    """The callee, with a selecting module constant: ``me_powers.power_key:DARK``."""
    name = dotted(call.func)
    for argument in call.args:
        if isinstance(argument, ast.Attribute) and argument.attr.isupper():
            return f'{name}:{argument.attr}'
    return name


def _returned_name(node) -> str | None:
    """``x`` of ``return x`` and of ``return x.key``."""
    value = node.value
    if isinstance(value, ast.Attribute) and value.attr == 'key':
        value = value.value
    return value.id if isinstance(value, ast.Name) else None


def _returns(statements):
    return [node for statement in statements for node in ast.walk(statement)
            if isinstance(node, ast.Return)]


def _returns_name(statements, name) -> bool:
    return any(_returned_name(node) == name for node in _returns(statements))


def _reason_text(value) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    if isinstance(value, ast.IfExp):
        parts = (_reason_text(value.body), _reason_text(value.orelse))
        return '|'.join(parts) if all(parts) else None
    return None


def _reason_of(statement) -> str | None:
    if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
            and dotted(statement.targets[0]) == 'last_reason'):
        return _reason_text(statement.value)
    return None


def _direct(call) -> bool:
    return isinstance(call, ast.Call) and _entry_name(call) is None and bool(dotted(call.func))


def _block_rows(block, rows):
    """The rows of one statement list: a key handed back, or a reason then a return."""
    reason_seen = False
    for index, statement in enumerate(block):
        reason = _reason_of(statement)
        if reason is not None and _returns(block[index + 1:]):
            rows.append(Row(reason, 'inline', statement.lineno))
            reason_seen = True
        if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name) and _direct(statement.value)
                and index + 1 < len(block) and isinstance(block[index + 1], ast.If)
                and _returns_name(block[index + 1].body, statement.targets[0].id)):
            rows.append(Row(_call_name(statement.value), 'direct', statement.lineno))
        if isinstance(statement, ast.If):
            for node in ast.walk(statement.test):
                if (isinstance(node, ast.NamedExpr) and _direct(node.value)
                        and _returns_name(statement.body, node.target.id)):
                    rows.append(Row(_call_name(node.value), 'direct', node.lineno))
        if isinstance(statement, ast.Return) and not reason_seen:
            value = statement.value
            if _direct(value) and not dotted(value.func).startswith(COMPOSERS):
                rows.append(Row(_call_name(value), 'direct', statement.lineno))
            elif value is None or isinstance(value, ast.Constant) or (
                    isinstance(value, ast.Name) and value.id.isupper()):
                text = getattr(value, 'id', getattr(value, 'value', None))
                rows.append(Row(f'return:{text}', 'inline', statement.lineno))


def _blocks(statement):
    for field in ('body', 'orelse', 'finalbody'):
        block = getattr(statement, field, None)
        if isinstance(block, list):
            yield block
    for handler in getattr(statement, 'handlers', ()):
        yield handler.body


def _walk_blocks(block, rows):
    _block_rows(block, rows)
    for statement in block:
        for inner in _blocks(statement):
            _walk_blocks(inner, rows)


def ladder_rows(policy_source: str) -> list[Row]:
    """Every rung of ``_decide`` from the shared ladder's start, in source order."""
    decide = _function(ast.parse(policy_source), '_decide')
    start = next(index for index, statement in enumerate(decide.body)
                 if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                 and dotted(statement.value.func) == LADDER_START)
    ladder = decide.body[start:]
    rows: list[Row] = []
    for statement in ladder:
        for node in ast.walk(statement):
            name = _entry_name(node)
            if name is not None and not name.startswith(COMPOSERS):
                rows.append(Row(name, 'entry', node.lineno))
    _walk_blocks(ladder, rows)
    return sorted(rows, key=lambda row: row.line)


def after_decide_rows(policy_source: str) -> list[str]:
    """What ``_choose_key`` may put in place of the ladder's key after the last ``_decide``."""
    choose = _function(ast.parse(policy_source), '_choose_key')
    last = max(node.lineno for node in ast.walk(choose)
               if isinstance(node, ast.Call) and dotted(node.func) == '_decide')
    found = []
    for node in ast.walk(choose):
        if (isinstance(node, ast.Assign) and node.lineno > last and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'key'
                and isinstance(node.value, ast.Call)
                and any(isinstance(argument, ast.Name) and argument.id == 'key'
                        for argument in node.value.args)):
            found.append((node.lineno, dotted(node.value.func)))
    return [name for _, name in sorted(found)]


def _operand_name(operand) -> str:
    """The rung of one ``or`` operand; ``(rung() if test else None)`` is that rung."""
    if isinstance(operand, ast.IfExp):
        operand = operand.body
    return dotted(operand.func) if isinstance(operand, ast.Call) else ''


def plan_branches(module_source: str) -> list[tuple[str, ...]]:
    """The rungs of each key-returning branch of a plan module's ``key``, in order."""
    branches = []
    bound = {}
    nodes = (node for node in ast.walk(_function(ast.parse(module_source), 'key'))
             if isinstance(node, (ast.Assign, ast.Return)))
    for node in sorted(nodes, key=lambda node: node.lineno):
        if isinstance(node, ast.Assign):
            if isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call):
                bound[node.targets[0].id] = dotted(node.value.func)
        elif isinstance(node.value, ast.BoolOp):
            branches.append(tuple(_operand_name(operand) for operand in node.value.values))
        elif isinstance(node.value, ast.Name) and node.value.id in bound:
            branches.append((bound[node.value.id],))
    return branches


def _first_difference(table, source) -> str:
    for index, (said, found) in enumerate(zip(table, source)):
        if (said.name, said.kind) != found[:2]:
            return (f'ladder row {index}: the table says {said.name} ({said.kind}), '
                    f'_decide line {found.line} has {found.name} ({found.kind})')
    return f'ladder length: the table has {len(table)} rows, _decide {len(source)}'


def _branch_findings(plan, branch) -> list[str]:
    """Survival, then the summons, then the plan's own order: the shape 4b04bafa56 restored."""
    where = f'{plan.rung} "{branch.board}"'
    roles = [role for _, role in branch.rungs]
    if ladder.OWN not in roles:
        return []
    if roles.count(ladder.SUMMONS) != 1:
        return [f'{where}: its own order runs without the summon rules']
    summons = roles.index(ladder.SUMMONS)
    findings = []
    if ladder.OWN in roles[:summons]:
        findings.append(f'{where}: its own order returns over the summon rules')
    if ladder.SURVIVAL in roles[summons:]:
        findings.append(f'{where}: a survival rung stands below the summon rules')
    if branch.enemy and ladder.SURVIVAL not in roles:
        findings.append(f'{where}: an enemy is on this board and no survival rung answers it')
    return findings


def _rule_findings(names) -> list[str]:
    findings = []
    for rule in ladder.OWNER_RULES:
        ahead = names[:names.index(rule.rung)]
        for name in sorted(set(ahead) - rule.ahead.keys()):
            findings.append(f'{name} returns over the {rule.name} rule ({rule.rung}) '
                            'and OWNER_RULES gives no reason')
        for name in sorted(rule.ahead.keys() - set(ahead)):
            findings.append(f'OWNER_RULES says {name} stands ahead of {rule.rung}; it does not')
        for plan in rule.below_rule:
            if names.index(plan) < names.index(rule.rung):
                findings.append(f'{plan} returns over the {rule.name} rule ({rule.rung})')
    plans = {plan.rung for plan in ladder.FLOOR_PLANS}
    below = {plan for rule in ladder.OWNER_RULES for plan in rule.below_rule}
    for layer in ladder.LADDER:
        if layer.name.startswith('plan') and not {rung.name for rung in layer.rungs} & (plans | below):
            findings.append(f'layer {layer.name}: no plan of it is placed against the owner rules')
    return findings


def _preemption_findings(layers) -> list[str]:
    """Each rung above the combat rungs is refused while attacked, or says why not."""
    findings = []
    for layer in layers:
        for rung in layer.rungs:
            if rung.preempted and rung.kind != 'entry':
                findings.append(f'{rung.name}: preempted but {rung.kind}: the gate is in the entry')
            if rung.preempted and rung.exempt:
                findings.append(f'{rung.name}: both preempted and exempt')
            if (layer.name in ladder.SURVIVAL_CHECKED_LAYERS
                    and not rung.preempted and not rung.exempt):
                findings.append(f'{rung.name}: above the combat rungs, neither preempted '
                                'nor exempt with a reason')
    return findings


def analyze(policy_source: str, plan_sources: dict[str, str]) -> list[str]:
    """Everything the table says against these sources; [] when they agree."""
    table = ladder.rows()
    source = ladder_rows(policy_source)
    findings = []
    if [(rung.name, rung.kind) for rung in table] != [row[:2] for row in source]:
        findings.append(_first_difference(table, source))
    after = after_decide_rows(policy_source)
    if list(ladder.AFTER_DECIDE) != after:
        findings.append(f'after _decide: the table says {list(ladder.AFTER_DECIDE)}, _choose_key has {after}')
    findings.extend(_rule_findings([rung.name for rung in table]))
    findings.extend(_preemption_findings(ladder.LADDER))
    for plan in ladder.FLOOR_PLANS:
        said = [tuple(name for name, _ in branch.rungs) for branch in plan.branches]
        found = plan_branches(plan_sources[plan.module])
        if said != found:
            findings.append(f'{plan.rung}: the table says {said}, the module has {found}')
        for branch in plan.branches:
            findings.extend(_branch_findings(plan, branch))
    return findings


def repository_sources() -> tuple[str, dict[str, str]]:
    def read(name):
        return (POLICY_ROOT / f'{name}.py').read_text(encoding='utf8')
    return read('policy'), {plan.module: read(plan.module) for plan in ladder.FLOOR_PLANS}


def analyze_repository() -> list[str]:
    policy_source, plan_sources = repository_sources()
    return analyze(policy_source, plan_sources)


def _print() -> None:
    policy_source, plan_sources = repository_sources()
    for row in ladder_rows(policy_source):
        print(f'{row.line:6} {row.kind:7} {row.name}')
    print('after _decide:', after_decide_rows(policy_source))
    for module, source in plan_sources.items():
        print(module, plan_branches(source))


def main() -> int:
    if sys.argv[1:] == ['--print']:
        _print()
        return 0
    findings = analyze_repository()
    for finding in findings:
        print(f'dungeon-ladder-lint: {finding}')
    print(f'dungeon-ladder-lint: {len(findings)} violation(s)')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
