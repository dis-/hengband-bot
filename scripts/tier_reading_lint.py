"""The threat tier compared directly outside the threat modules.

Whole-bot maintainability review 2026-11-18 (S6 / 6(a)-9): "is this T1" was read six ways
(review 11-17 N3); threat_tiers now names the readings (``alone_t1``, ``cannot_win``,
``tier_of``, ``leave_due`` ...), but a module may still compare a tier with ``T1`` / ``T2`` /
``T3`` itself, and each such comparison is a reading of its own (``tier == T1`` is not
``cannot_win``: the cost-capped reading whose damage lower bound reaches the HP is T1 there).

Findings: a comparison (``==``, ``!=``, ``in``, ``not in``, ``is``) one side of which is a tier
(``threat_tiers.T1``, a bare ``T2``, the string ``"T3"``, a tuple or set of them, or
``STRONG_ON_THE_WAY``) in a module of src/hengbot other than the threat modules (``OWNERS``).
The comparisons there when the lint joined are ``BASELINE``, each with why it is not a named
reader; a comparison beyond them fails.  Read the tier through a threat_tiers reader instead
(``alone_t1`` for "this one monster cannot be won against"), or, if the comparison is the
reading the rule wants, add it to ``BASELINE`` with why (scripts/allowlist_growth.py reports
the growth).

A key never holds a line number: ``<module>.py:<function>: <comparison>`` with a count, so an
edit that only moves code does not trip it.

    python scripts/tier_reading_lint.py           # exit 1 on a comparison not in BASELINE
    python scripts/tier_reading_lint.py --print   # every comparison's key
"""

from __future__ import annotations

import ast
from collections import Counter
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
TIERS = frozenset({"T1", "T2", "T3"})
# Names of tier collections (threat_tiers): comparing with them is comparing with tiers.
TIER_COLLECTIONS = frozenset({"STRONG_ON_THE_WAY"})
# The threat modules: the tiers are computed (threat_projection), held (threat_tier_memory:
# the hysteresis threat_tiers.tiered reads) and named (threat_tiers) there.
OWNERS = frozenset({"threat_tiers", "threat_projection", "threat_tier_memory"})

# Each comparison outside the threat modules on 2026-11-19 (main b7137c8a58), with why it is
# not one of threat_tiers' named readers.  None is an alias of one: routing any of them
# through alone_t1 / cannot_win would change its answer on the cost-capped reading.
# key -> (count, why)
BASELINE = {
    "angband_finale_battle.py:shunned.compute: reading.tier in threat_tiers.STRONG_ON_THE_WAY": (
        1, "the 99F/100F walks' strong non-targets (owner 2026-11-24 「射線を通さないように近づく」): "
           "strong alone from contact, T1 or T2, as _sensed_strong's group members are read"),
    "guardian_landing.py:t1_landing: guardian_tier(policy, snapshot, info) == threat_tiers.T1": (
        1, "the dungeon guardian's own tier from contact (memoised per guardian, decision_memo) "
           "on its unconquered last floor; cannot_win would add the cost-capped reading"),
    "heroism_potion.py:strong: assessment.tier in (threat_tiers.T1, threat_tiers.T2)": (
        1, "T2 or worse (owner 2026-11-11 the T2-or-worse fear caster); its own second half reads "
           "the cost-capped engagement as no weaker than T2 (n1-b life-370)"),
    "hunt_target.py:_guardian_beatable: tier in (threat_tiers.T2, threat_tiers.T3)": (
        1, "the guardian is hunted only at T2 or T3 from contact (owner 2026-11-08 「勝てる段の"
           "時だけ追う」): T1 and undecided are not; not the negation of cannot_win"),
    "loot_walk.py:life_danger: threat_tiers.tier_of(policy, snapshot, in_view) in "
    "(threat_tiers.T1, threat_tiers.T2)": (
        1, "the owner's 命の危険 for the loot walk: a strong (T1 or T2) engagement in view"),
    "policy_combat.py:CombatMixin._strong_fight_speed_key: "
    "threat_tiers.tier_of(self, snapshot, hostiles) == threat_tiers.T3": (
        1, "threat tiers plan step 8 (owner OQ-5, C-5): no Potion of Speed in a fight the free "
           "attacks win (T3)"),
    "resist_potion.py:ladder_key: tiers.tier == threat_tiers.T1": (
        1, "the resistance potion acts per tier (T1 leaves, T2 drinks unless the supply plan "
           "answers, T3 does not drink): the tier itself is the branch, not a yes/no reading"),
    "resist_potion.py:ladder_key: tiers.tier == threat_tiers.T2": (
        2, "the same per-tier branch (T2 without a selected plan leaves; T2 drinks)"),
    "resist_potion.py:ladder_key: tiers.tier == threat_tiers.T3": (
        1, "the same per-tier branch (T3: no potion)"),
    "summoner_loot.py:applies: threat_tiers.tier_of(policy, snapshot, hostiles) == threat_tiers.T3": (
        1, "a summoner in the open on a T3 board at full HP (owner 2026-11-10, n1-b life-367 "
           "P6): *Destruction* only when it deletes nothing of value, else the pocket"),
}


def _is_tier(node) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr in TIERS or node.attr in TIER_COLLECTIONS
    if isinstance(node, ast.Name):
        return node.id in TIERS or node.id in TIER_COLLECTIONS
    if isinstance(node, ast.Constant):
        return node.value in TIERS
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return any(_is_tier(element) for element in node.elts)
    return False


class _Comparisons(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.stack: list[str] = []
        self.sites: list[tuple[str, int]] = []   # (key, line)

    def _scope(self, node) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scope

    def visit_Compare(self, node) -> None:
        operands = [node.left, *node.comparators]
        for index, op in enumerate(node.ops):
            left, right = operands[index], operands[index + 1]
            if _is_tier(left) or _is_tier(right):
                comparison = ast.Compare(left=left, ops=[op], comparators=[right])
                function = ".".join(self.stack) or "<module>"
                self.sites.append((f"{self.module}.py:{function}: {ast.unparse(comparison)}",
                                   node.lineno))
        self.generic_visit(node)


def sites(root: Path = POLICY_ROOT) -> list[tuple[str, int]]:
    """(key, line) of every tier comparison outside the threat modules."""
    found = []
    for path in sorted(root.glob("*.py")):
        if path.stem in OWNERS:
            continue
        visitor = _Comparisons(path.stem)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        found += visitor.sites
    return found


def findings(root: Path = POLICY_ROOT, baseline: dict | None = None) -> tuple[list[str], list[str]]:
    """(new, stale): comparisons beyond ``BASELINE``'s count, and baseline keys no longer found."""
    baseline = BASELINE if baseline is None else baseline
    remaining = Counter({key: count for key, (count, _why) in baseline.items()})
    new = []
    for key, line in sites(root):
        if remaining[key] > 0:
            remaining[key] -= 1
        else:
            module = key.split(":", 1)[0]
            new.append(f"{module}:{line} compares a threat tier directly ({key.split(': ', 1)[1]}) "
                       f"outside the threat modules: read it through a threat_tiers reader "
                       f"(alone_t1, cannot_win, tier_of ...), or add {key!r} to "
                       f"tier_reading_lint.BASELINE with why")
    stale = sorted(f"BASELINE entry no longer found ({count} left): {key}"
                   for key, count in remaining.items() if count > 0)
    return new, stale


def main(argv: list[str]) -> int:
    if "--print" in argv:
        for key, line in sites():
            print(f"{line:6d} {key}")
        return 0
    new, stale = findings()
    for line in new + stale:
        print(line)
    print(f"tier_reading_lint: {len(new)} new comparison(s), {len(stale)} stale baseline entr(ies)")
    return 1 if new or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
