"""AST census of direction keys escaping the step gate and raw warning reads.

This is a structural ratchet, not a control-flow proof. Track direction keys
through local assignments to returns/offers conservatively, including wrappers
and tails. Only explicit non-movement command prefixes, missile suffixes and
the melee lint's existing sites are excluded. No other call to _step_toward in
the same function can authorize a raw direction key.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import melee_site_lint as melee_lint

POLICY_ROOT = Path(__file__).resolve().parents[1] / "src" / "hengbot"
GATE = ("policy_navigation.py", "_step_toward")

# Counts are per composing call, not per return/offer of the same key.
MOVEMENT_BYPASSES = {
    ("policy.py", "_town_holder_declared_key"): (1, "Declared town route checks confirms only; offers a bare step."),
    ("policy.py", "_town_holder_wait_key"): (2, "Entrance/store resume fallbacks check confirms only; offer bare steps."),
    ("policy.py", "_break_livelock"): (1, "Breakout selection and confirm check precede a bare replacement key."),
    ("policy_town.py", "_boxed_town_breakout_key"): (1, "Boxed-town probe returns a raw alternate-store step before commit."),
    ("policy_fundraising.py", "_mining_tunnel_key"): (1, "Unmarked non-enterable wall receives a bare mark-bump key."),
}
WARNING_READ_BYPASSES = {
    ("policy_navigation.py", "_step_toward"): (1, "After predicate refusal, membership selects the sanctioned forced walk."),
    ("policy_navigation.py", "_explore_step"): (2, "Exploration merges the latch into avoidance even when supplies are exhausted."),
    ("policy_combat.py", "_refresh_paralyzer_avoidance"): (1, "Paralyzer-ring cleanup preserves latched warning avoidance."),
    ("policy_supply.py", "_unseen_reverse_choke_step"): (2, "First-step and BFS filters exclude every latched cell unconditionally."),
    ("policy_town.py", "_town_entrance_step_off_key"): (1, "Entrance exit candidates exclude every latched cell unconditionally."),
}
WARNING_OWNERS = {
    ("policy_navigation.py", "_warning_step_refused"): 1,
    ("policy_helpers.py", "_latch_warning_refusal"): 1,
    ("policy_observation.py", "_observe"): 1,
    ("policy_observation.py", "_refresh_warning_avoidance"): 1,
}
COMMAND_PREFIXES = {
    "OPEN_KEY", "CHEST_OPEN_KEY", "CHEST_DISARM_KEY", "TUNNEL_KEY", "ALTER_KEY",
}


def _function(node: ast.AST, parents: dict) -> ast.AST | None:
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


def _command_prefix(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id in COMMAND_PREFIXES


def _carries_key(node: ast.AST, origin: ast.Call, aliases: set[str]) -> bool:
    if node is origin or isinstance(node, ast.Name) and node.id in aliases:
        return True
    if isinstance(node, (ast.Compare, ast.UnaryOp)):
        return False  # a direction comparison is not an emitted movement
    if isinstance(node, ast.keyword) and node.arg == "suffix":
        return False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and _command_prefix(node.left):
        return False
    return any(_carries_key(child, origin, aliases) for child in ast.iter_child_nodes(node))


def _emitted(origin: ast.Call, function: ast.AST, parents: dict) -> bool:
    # Restrict propagation to this function; nested producers have their own scope.
    nodes = [node for node in ast.walk(function) if _function(node, parents) is function]
    aliases: set[str] = set()
    assignments = [node for node in nodes if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))]
    while True:
        before = aliases.copy()
        for assignment in assignments:
            if assignment.value is not None and _carries_key(assignment.value, origin, aliases):
                targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
                aliases.update(target.id for target in targets if isinstance(target, ast.Name))
        if aliases == before:
            break
    for node in nodes:
        if isinstance(node, ast.Return) and node.value is not None and _carries_key(node.value, origin, aliases):
            return True
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_offer_execution" and node.args
                and _carries_key(node.args[0], origin, aliases)):
            return True
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_offer_execution"
                and any(kw.arg == "key" and _carries_key(kw.value, origin, aliases) for kw in node.keywords)):
            return True
    return False


def scan_source(source: str, filename: str = "<source>") -> tuple[list[tuple], list[tuple]]:
    """Return (movement composing sites, warning reads) as (file, function, line)."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    movement, reads = [], []
    for node in ast.walk(tree):
        function = _function(node, parents)
        name = getattr(function, "name", "<module>")
        if (isinstance(node, ast.Attribute) and node.attr == "_warning_refused_cells"
                and isinstance(node.ctx, ast.Load)):
            reads.append((filename, name, node.lineno))
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_direction_key"):
            continue
        # Share the exact melee classification, including ALTER_KEY and suffix=.
        if melee_lint._is_site(node, parents):
            continue
        if function is None or _emitted(node, function, parents):
            movement.append((filename, name, node.lineno))
    return movement, reads


def census_findings(sites: list[tuple], expected: dict) -> list[str]:
    actual = Counter(site[:2] for site in sites)
    return [f"{file}:{function}: expected {expected.get((file, function), 0)}, found {actual[(file, function)]}"
            for file, function in sorted(actual.keys() | expected.keys())
            if actual[(file, function)] != expected.get((file, function), 0)]


def analyze_repository(root: Path = POLICY_ROOT) -> tuple[int, int, list[str]]:
    movement, reads = [], []
    for path in sorted(root.rglob("*.py")):
        steps, raw_reads = scan_source(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix())
        movement.extend(steps)
        reads.extend(raw_reads)
    expected_steps = {name: count for name, (count, _) in MOVEMENT_BYPASSES.items()}
    expected_reads = {name: count for name, (count, _) in WARNING_READ_BYPASSES.items()}
    return len(movement), len(reads), (
        census_findings(movement, {GATE: 1, **expected_steps})
        + census_findings(reads, {**WARNING_OWNERS, **expected_reads})
    )
