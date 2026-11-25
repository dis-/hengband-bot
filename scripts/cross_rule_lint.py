#!/usr/bin/env python3
"""The producers of the cross-layer rules (hengbot.cross_rules.REGISTRY) that do not pass the
rule's registered point.

Maintainability review of the dungeon decisions 2026-11-15 (N1, stage 2).  The decision order
has a table and a lint (dungeon_ladder); the rules that cross the layers had neither, so a new
walker that does not read the shared left-cell record, or a new rest that skips the uncurse,
passed silently.  This lists, from the AST of ``src/hengbot``, every producer of each rule and
whether it reaches the rule's point (a reference to it in its body, or in a function it calls,
transitively; calls are resolved by module, by the policy's methods for ``self.``/``policy.``,
and by name otherwise, so "reaches" is generous and a listed gap is a real absence of the
point on every path the source names).

The gaps known on 2026-11-15 are the report's (REPORT.md §4) and are the owner's questions
Q2-Q4/Q6, not this lint's to fix: they are kept in ``scripts/cross_rule_baseline.json`` and
printed as an advisory list.  The lint fails on:

- a gap not in the baseline (a new producer outside the rule's point);
- a registry point that names nothing in the source;
- the registry of what a *Destruction* forgets (``monster_memory.DESTRUCTION_FORGETS``)
  disagreeing with the source: a ``monster_memory.Kind``, a module's ``forget_floor_visit`` over
  monsters or a ``forget_destroyed`` that is not a row, or a row whose way is missing.

    python scripts/cross_rule_lint.py [--write-baseline] [--print]
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hengbot import cross_rules  # noqa: E402

SRC = ROOT / "src" / "hengbot"
BASELINE = ROOT / "scripts" / "cross_rule_baseline.json"
POLICY = "@policy"
POLICY_NAMES = {"self", "policy", "owner"}


def _modules() -> dict:
    return {path.stem: ast.parse(path.read_text(encoding="utf-8"), str(path))
            for path in sorted(SRC.glob("*.py"))}


class Index:
    """Every function of the package, the calls it makes and the names it references."""

    def __init__(self, modules: dict):
        self.modules = modules
        self.defs: dict = {}        # (owner, name) -> [(module, node)]
        self.imports: dict = {}     # module -> {alias: module}
        self.from_names: dict = {}  # module -> {name: (module, name)}
        for module, tree in modules.items():
            aliases, names = {}, {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module == "hengbot":
                        for alias in node.names:
                            aliases[alias.asname or alias.name] = alias.name
                    elif node.module.startswith("hengbot."):
                        source = node.module.split(".", 1)[1]
                        for alias in node.names:
                            names[alias.asname or alias.name] = (source, alias.name)
            self.imports[module] = aliases
            self.from_names[module] = names
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.defs.setdefault((module, node.name), []).append((module, node))
                elif isinstance(node, ast.ClassDef):
                    owner = POLICY if module.startswith("policy") else f"{module}.{node.name}"
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            self.defs.setdefault((owner, item.name), []).append((module, item))
                            self.defs.setdefault(("*", item.name), []).append((module, item))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.defs.setdefault(("*", node.name), []).append((module, node))
        self._memo: dict = {}
        self._refs: dict = {}

    def targets(self, module: str, call: ast.expr) -> list:
        """The definitions a call (or a reference to a function) may name."""
        if isinstance(call, ast.Name):
            if (module, call.id) in self.defs:
                return [(module, call.id)]
            if call.id in self.from_names[module]:
                return [self.from_names[module][call.id]]
            return []
        if isinstance(call, ast.Attribute):
            value = call.value
            if isinstance(value, ast.Name):
                if value.id in self.imports[module]:
                    return [(self.imports[module][value.id], call.attr)]
                if value.id in POLICY_NAMES:
                    return [(POLICY, call.attr)]
            if isinstance(value, ast.Attribute) and value.attr == "policy":
                return [(POLICY, call.attr)]
            return [("*", call.attr)]
        return []

    def _called(self, module: str, node) -> set:
        """The definitions the body calls (a call by a bare attribute name only when few
        functions carry that name: ``x.key()`` is not every ``key`` of the package)."""
        found = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                for target in self.targets(module, sub.func):
                    if target[0] != "*" or len(self.defs.get(target, ())) <= 3:
                        found.add(target)
        return found

    def references(self, module: str, node) -> set:
        """Qualified names the body references: (module, name) and (POLICY|'*', name)."""
        found = set()
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Name, ast.Attribute)):
                for target in self.targets(module, sub):
                    found.add(target)
                    found.add(("*", target[1]))
        return found

    def reaches(self, module: str, node, points: frozenset, stop: frozenset) -> bool:
        """Whether the body, or a function it names (``stop`` names excluded), transitively,
        references a point.  ``points``: qualified (module, name) / (POLICY, name).  A fixpoint
        over every function, computed once per (points, stop): deterministic."""
        key = (points, stop)
        if key not in self._memo:
            self._memo[key] = self._closure(points, stop)
        return id(node) in self._memo[key]

    def _closure(self, points: frozenset, stop: frozenset) -> set:
        nodes = {}
        for rows in self.defs.values():
            for source, sub in rows:
                nodes[id(sub)] = (source, sub)
        edges, reached = {}, set()
        for ident, (source, sub) in nodes.items():
            refs = self._refs.get(ident)
            if refs is None:
                refs = self._refs[ident] = self.references(source, sub)
            if refs & points:
                reached.add(ident)
            edges[ident] = {id(callee) for target in self._called(source, sub) if target[1] not in stop
                            for _module, callee in self.defs.get(target, ())}
        changed = True
        while changed:
            changed = False
            for ident, callees in edges.items():
                if ident not in reached and callees & reached:
                    reached.add(ident)
                    changed = True
        return reached


def _functions(tree):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield item


def _calls(node, names) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in names:
                return True
    return False


def _qualified(points) -> frozenset:
    out = set()
    for point in points:
        owner, name = point.split(":", 1) if ":" in point else ("*", point)
        out.add((POLICY if owner == "policy" else owner, name))
    return frozenset(out)


def _string_constants(tree) -> dict:
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _reason_strings(index, module, node) -> set:
    """String literals and module string constants the function references."""
    constants = _string_constants(index.modules[module])
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            found.add(sub.value)
        elif isinstance(sub, ast.Name) and sub.id in constants:
            found.add(constants[sub.id])
        elif isinstance(sub, ast.Name) and sub.id in index.from_names[module]:
            source, name = index.from_names[module][sub.id]
            value = _string_constants(index.modules.get(source, ast.Module([], []))).get(name)
            if value is not None:
                found.add(value)
    return found


def _returns_keys(node, key_names) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return) and sub.value is not None:
            for each in ast.walk(sub.value):
                name = each.id if isinstance(each, ast.Name) else (
                    each.attr if isinstance(each, ast.Attribute) else None)
                if name in key_names:
                    return True
    return False


def _references_any(node, pattern) -> bool:
    for sub in ast.walk(node):
        name = sub.id if isinstance(sub, ast.Name) else (
            sub.attr if isinstance(sub, ast.Attribute) else None)
        if name and pattern.match(name):
            return True
    return False


def producers(index: Index, rule) -> list:
    """(module, function) of every producer of ``rule`` (cross_rules.CrossRule)."""
    skip = re.compile(cross_rules.TOWN_MODULES)
    out = []
    escape_reasons = None
    if rule.name == cross_rules.ESCAPE_LINE_OF_FIRE:
        from hengbot.line_of_fire import PROOF_REASONS
        from hengbot.policy_constants import EMERGENCY_ESCAPE_REASONS, RELOCATING_ESCAPE_REASONS
        escape_reasons = (set(EMERGENCY_ESCAPE_REASONS) | set(RELOCATING_ESCAPE_REASONS)) - set(PROOF_REASONS)
    teleport = re.compile(cross_rules.TELEPORT_MEANS)
    for module, tree in index.modules.items():
        if skip.match(module) or module in rule.point_modules:
            continue
        for node in _functions(tree):
            if node.name in rule.helpers or re.search(cross_rules.TOWN_FUNCTIONS, node.name):
                continue
            if rule.name == cross_rules.LEFT_CELLS:
                hit = _calls(node, set(rule.helpers))
            elif rule.name == cross_rules.UNCURSE_BEFORE_REST:
                hit = (_returns_keys(node, cross_rules.REST_KEY_NAMES)
                       and module not in cross_rules.LAYERS_AFTER_SAFE_NOW)
            elif rule.name == cross_rules.ESCAPE_LINE_OF_FIRE:
                hit = bool(_reason_strings(index, module, node) & escape_reasons)
            elif rule.name == cross_rules.DEEP_TELEPORT:
                # A read or a use composed here: the function touches a teleport means and
                # calls a key composer (a selector of the means is not a producer).
                hit = (_references_any(node, teleport)
                       and _calls(node, cross_rules.KEY_COMPOSERS))
            else:
                hit = False
            if hit:
                out.append((module, node))
    return out


COUNTS: dict = {}  # rule -> producers found (for the printout)


def _exit_asks(index, module: str, function: str, call: str) -> bool:
    """Whether ``module``'s ``function`` (a top-level function or a method) calls ``call``."""
    if module not in index.modules:
        return False
    for node in _functions(index.modules[module]):
        if node.name == function:
            return _calls(node, {call})
    return False


def gaps(index: Index) -> dict:
    """rule -> sorted 'module:function' producers that do not reach the rule's point."""
    out = {}
    for rule in cross_rules.REGISTRY:
        if rule.name == cross_rules.DESTRUCTION_FORGET:
            from hengbot import monster_memory
            out[rule.name] = sorted(f"memory:{attribute}"
                                    for attribute in cross_rules.UNFORGOTTEN_MONSTER_MEMORIES)
            COUNTS[rule.name] = len(monster_memory.DESTRUCTION_FORGETS)
            continue
        points, stop = _qualified(rule.points), frozenset(rule.helpers)
        found = producers(index, rule)
        COUNTS[rule.name] = len({(module, node.name) for module, node in found})
        if rule.exit_point is not None and _exit_asks(index, *rule.exit_point):
            out[rule.name] = []  # every key passes the exit, which asks the point
            continue
        out[rule.name] = sorted({f"{module}:{node.name}"
                                 for module, node in found
                                 if not index.reaches(module, node, points, stop)})
    return out


def _visit_memory(tree, constants) -> str | None:
    """The memory a module's ``forget_floor_visit`` drops: its MEMORY constant, else the first
    policy attribute the function assigns."""
    for name in ("MEMORY", "_MEMORY", "TIER_MEMORY"):
        if name in constants:
            return constants[name]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "forget_floor_visit":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for target in sub.targets:
                        if isinstance(target, ast.Attribute):
                            return target.attr
    return None


def _floor_keyed(index: Index) -> dict:
    """attribute -> module: every policy attribute the source stores the floor key in (as the
    value, or the first of a tuple), directly or by ``setattr`` with a module constant."""
    def keyed(value) -> bool:
        if isinstance(value, ast.Tuple) and value.elts:
            value = value.elts[0]
        return (isinstance(value, ast.Attribute) and value.attr == "floor_key"
                and isinstance(value.value, ast.Name) and value.value.id == "snapshot")

    found = {}
    for module, tree in index.modules.items():
        constants = _string_constants(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and keyed(node.value):
                for target in node.targets:
                    if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                            and target.value.id in POLICY_NAMES):
                        found.setdefault(target.attr, module)
            elif (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setattr"
                    and len(node.args) == 3 and keyed(node.args[2])):
                name = node.args[1]
                attribute = (name.value if isinstance(name, ast.Constant) else
                             constants.get(name.id) if isinstance(name, ast.Name) else None)
                if attribute:
                    found.setdefault(attribute, module)
    return found


def registry_problems(index: Index) -> list:
    problems = []
    for rule in cross_rules.REGISTRY:
        for point in _qualified(rule.points):
            if not index.defs.get(point):
                problems.append(f"{rule.name}: point {point[0]}:{point[1]} names nothing")
    # The memories a *Destruction* forgets (monster_memory.DESTRUCTION_FORGETS, the one registry)
    # against the source: every monster_memory Kind, every module forgetting a floor visit of
    # monsters, every module with a ``forget_destroyed`` is a row, and every row's way is there.
    from hengbot import monster_memory
    declared = {row.attribute: row for row in monster_memory.DESTRUCTION_FORGETS}
    found = {}
    for module, tree in index.modules.items():
        constants = _string_constants(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if (name == "Kind" and node.args and isinstance(node.args[0], ast.Constant)
                        and (module == "monster_memory" or "monster_memory" in ast.unparse(func))):
                    found[node.args[0].value] = module
        source = (SRC / f"{module}.py").read_text(encoding="utf-8")
        if "def forget_floor_visit" in source and re.search(r"race_id|\(index, race\)", source):
            memory = _visit_memory(tree, constants)
            found[memory or f"<{module}>"] = module
        if "def forget_destroyed" in source and module not in {
                row.module for row in monster_memory.DESTRUCTION_FORGETS}:
            found[f"<{module}.forget_destroyed>"] = module
    for attribute, module in sorted(found.items()):
        if attribute not in declared:
            problems.append(f"destruction-forget: monster memory {attribute} ({module}) is not "
                            f"declared in monster_memory.DESTRUCTION_FORGETS")
    kinds = {kind.attribute for kind in (*monster_memory.KINDS, monster_memory.BREEDER_SEEN)}
    for row in monster_memory.DESTRUCTION_FORGETS:
        tree = index.modules.get(row.module)
        names = {node.name for node in _functions(tree)} if tree is not None else set()
        if row.how == "kind" and row.attribute not in kinds:
            problems.append(f"destruction-forget: {row.attribute} is no monster_memory Kind")
        elif row.how == "visit" and "forget_floor_visit" not in names:
            problems.append(f"destruction-forget: {row.module} has no forget_floor_visit")
        elif row.how == "keys" and "forget_destroyed" not in names:
            problems.append(f"destruction-forget: {row.module} has no forget_destroyed")
    # Owner 2026-11-15 Q7: a memory keyed by the floor key alone is forgotten on every floor
    # change (floor_visit_memory.VISIT_MEMORIES), or kept on purpose with its reason (KEPT).
    from hengbot import floor_visit_memory
    covered = {row[0] for row in floor_visit_memory.VISIT_MEMORIES} | set(floor_visit_memory.KEPT)
    for attribute, module in sorted(_floor_keyed(index).items()):
        if attribute not in covered and not module.startswith(("policy_town", "town_", "policy_shop",
                                                                "policy_home", "cli")):
            problems.append(f"floor-visit: {attribute} ({module}) keeps the floor key and is "
                            "neither in floor_visit_memory.VISIT_MEMORIES nor KEPT")
    if cross_rules.UNFORGOTTEN_MONSTER_MEMORIES:
        problems.append("destruction-forget: UNFORGOTTEN_MONSTER_MEMORIES lists "
                        f"{sorted(cross_rules.UNFORGOTTEN_MONSTER_MEMORIES)}")
    return problems


# -- the quest plans' single readings (contradiction audit 2026-11-25, (a)-1..(a)-3) --------------

# (a)-1: the one "never moves" predicate (quest_plan_base.never_moves / flags_never_move).  The
# functions that port the game's terrain crossing (monster_can_cross_terrain: an AQUATIC one only on
# water) read AQUATIC as a crossing rule, not as "never comes": they are listed with their reason.
MOVE_FLAGS = frozenset({"NEVER_MOVE", "AQUATIC"})
MOVE_FLAG_READERS = {
    ("quest_plan_base", "flags_never_move"): "the one predicate",
    ("quest_exposure", "can_reach"): "monster_can_cross_terrain's port (the walk over the map)",
    ("quest_wait_placement", "_crosses"): "monster_can_cross_terrain's port (one step)",
}


def _docstrings(tree) -> set:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def _enclosing(tree) -> dict:
    """Node id -> the name of the innermost top-level or method function holding it."""
    owner = {}

    def visit(node, name):
        for child in ast.iter_child_nodes(node):
            here = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else name
            owner[id(child)] = here
            visit(child, here)

    visit(tree, None)
    return owner


def _quest_modules(modules: dict) -> dict:
    return {module: tree for module, tree in modules.items() if module.startswith("quest_")}


def move_flag_problems(modules: dict) -> list:
    problems = []
    for module, tree in _quest_modules(modules).items():
        docs, owner = _docstrings(tree), _enclosing(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and node.value in MOVE_FLAGS and id(node) not in docs
                    and (module, owner.get(id(node))) not in MOVE_FLAG_READERS):
                problems.append(f"never-moves: {module}.py:{node.lineno} reads {node.value} directly "
                                "(quest_plan_base.never_moves is the one predicate)")
    return problems


def main(argv) -> int:
    index = Index(_modules())
    found = gaps(index)
    problems = registry_problems(index) + move_flag_problems(index.modules)
    if "--write-baseline" in argv:
        BASELINE.write_text(json.dumps(found, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                            newline="\n")
        print(f"wrote {BASELINE.name}")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    new = []
    for rule, rows in found.items():
        known = set(baseline.get(rule, ()))
        print(f"{rule}: {COUNTS.get(rule, 0)} producer(s), {len(rows)} outside the point (advisory)")
        if "--print" in argv:
            for row in rows:
                print(f"  {'NEW ' if row not in known else ''}{row}")
        new += [f"{rule}: new gap {row}" for row in rows if row not in known]
    for line in problems + new:
        print(line)
    print(f"cross-rule-lint: {len(problems) + len(new)} violation(s)")
    return 1 if problems or new else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
