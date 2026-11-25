#!/usr/bin/env python3
"""Every producer that seeks out a guardian or a strong unique asks the one gate (finale_prep).

Owner 2026-11-26 (verbatim), the answer to 「決戦の準備中（体力回復と*体力回復*を集めている間）の
n1-c の戦い方をどう変えますか？」: 「守護者は追わないが、薬は今まで通り使う」 -- while the finale is
prepared no dungeon guardian or strong unique is sought out (``hengbot.finale_prep.forbids_hunting``).
This lint reads ``src/hengbot`` and fails on

- a ``GATED`` function whose body does not call ``finale_prep.forbids_hunting``;
- a function that asks a hunt's question or starts one outside ``GATED`` and ``FOLLOWERS``:
  a call of ``_guardian_fight_viable`` (can the guardian be beaten) or ``_target_guardian_floor_id``
  (the guardian hunted on this floor), a write of a value other than None to ``_conquest_committed``
  (the conquest latch) or to ``_esp_threat_hunt`` (a committed hunt of sensed hostiles), a write of
  ``"conquest"`` to ``_target_dungeon_reason``;
- a ``GATED`` or ``FOLLOWERS`` row the source no longer has.

A new hunt producer: call ``finale_prep.forbids_hunting`` in it and add a ``GATED`` row, or, when it
only acts on a gated producer's answer, a ``FOLLOWERS`` row naming that producer.

    python scripts/finale_hunt_gate_lint.py      # exit 1 on a finding
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"

GATE_MODULE = "finale_prep"
GATE = "forbids_hunting"

# (module, function): what it seeks out; its body asks the gate.
GATED = {
    ("policy_quest", "_conquest_target"): "the conquest target (the guardian's dungeon)",
    ("policy", "_target_guardian_floor_id"): "the guardian hunted on the target's final floor",
    ("policy", "_guardian_floor_blocked"): "the descent onto an unconquered guardian floor",
    ("policy_combat", "_esp_threat_rest_key"): "the committed STRONG hunt of sensed hostiles",
}
# (module, function): the gated producer whose answer it acts on.
FOLLOWERS = {
    ("hunt_target", "_guardian_race"): "policy._target_guardian_floor_id",
    ("policy", "_viable_target_guardian_visible"): "policy._target_guardian_floor_id",
    ("policy_observation", "_observe"): "policy_quest._conquest_target",
}
# The questions and the commitments of a hunt.
CALLS = {"_guardian_fight_viable", "_target_guardian_floor_id"}
LATCHES = {"_conquest_committed", "_esp_threat_hunt"}
REASON = "_target_dungeon_reason"
CONQUEST = "conquest"


def _owners(tree):
    """The innermost enclosing function's name of every node."""
    owner = {}

    def walk(node, current):
        for child in ast.iter_child_nodes(node):
            owner[child] = current
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                else current
            walk(child, inner)
    walk(tree, "<module>")
    return owner


def _asks_gate(function) -> bool:
    return any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == GATE and isinstance(node.func.value, ast.Name)
               and node.func.value.id == GATE_MODULE
               for node in ast.walk(function))


def _signal(node) -> str | None:
    """What hunt ``node`` asks or starts, else None."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr in CALLS:
        return f"calls {node.func.attr}"
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if not isinstance(target, ast.Attribute):
                continue
            value = node.value
            if target.attr in LATCHES and not (isinstance(value, ast.Constant)
                                               and value.value is None):
                return f"writes {target.attr}"
            if target.attr == REASON and isinstance(value, ast.Constant) \
                    and value.value == CONQUEST:
                return f"writes {REASON} = {CONQUEST!r}"
    return None


def main() -> int:
    findings = []
    seen = set()
    for path in sorted(POLICY_ROOT.glob("*.py")):
        module = path.stem
        if module == GATE_MODULE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owner = _owners(tree)
        for node in ast.walk(tree):
            where = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and (module, node.name) in GATED:
                seen.add((module, node.name))
                if not _asks_gate(node):
                    findings.append(f"{where}: {node.name} ({GATED[(module, node.name)]}) does "
                                    f"not ask {GATE_MODULE}.{GATE}")
            signal = _signal(node)
            if signal is None:
                continue
            function = owner.get(node, "<module>")
            row = (module, function)
            if row in GATED or row in FOLLOWERS:
                seen.add(row)
                continue
            findings.append(f"{where}: {function} {signal} without {GATE_MODULE}.{GATE} "
                            f"(add a GATED row and ask the gate, or a FOLLOWERS row)")
    for row in sorted((set(GATED) | set(FOLLOWERS)) - seen):
        findings.append(f"row {row} names nothing the source has")
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
