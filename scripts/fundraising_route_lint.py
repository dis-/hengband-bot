#!/usr/bin/env python3
"""Every opening of a 1F mining set passes the one gate (fundraising_route).

Owner 2026-11-25 (verbatim): 「帰還の深さ50F以上なら潜る」 -- a character whose recall depth is 50F
or deeper never opens the Yeek cave 1F mining set for an errand's gold; it dives
(``hengbot.fundraising_route``, ``dives`` and ``open_set``).  This lint reads ``src/hengbot`` and
fails on

- an assignment of ``"prepare"`` to ``_fundraising_mode`` (also inside a conditional expression)
  outside ``fundraising_route`` and the in-run transitions of an open set (``IN_RUN``);
- ``morivant_tower.start_fundraising_run`` or ``FundraisingMixin._open_one_mining_run`` whose body
  does not call ``fundraising_route.open_set``;
- a call of ``start_fundraising_run``, ``open_set``, ``dives`` or ``_start_fundraising`` in the
  policy without its cause, or with a cause that is not a ``fundraising_route`` constant of
  ``CAUSES``;
- a caller of ``_settle_fundraising_detection`` (it writes ``"prepare"`` and ``"scavenge"``) not
  in ``DETECTION_SETTLERS``, and a settler that may open a set from none (``GATED_SETTLERS``)
  without a ``fundraising_route`` call;
- an ``IN_RUN``, ``DETECTION_SETTLERS`` or ``GATED_SETTLERS`` row the source no longer has.

A new opening: call ``fundraising_route.open_set`` with its cause (a new cause is a row of
``fundraising_route.DIVE_CAUSES`` or ``DEPARTURE_CAUSES``).

    python scripts/fundraising_route_lint.py      # exit 1 on a finding
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "src" / "hengbot"
sys.path.insert(0, str(ROOT / "src"))

from hengbot import fundraising_route  # noqa: E402

GATE = "fundraising_route"
MODE = "_fundraising_mode"
PREPARE = "prepare"

# (module, function): why it may write "prepare" without the gate (an open set's own step).
IN_RUN = {
    ("policy", "prime"): "a restarted process standing on the Yeek cave 1F resumes the run there",
    ("policy", "_restart_fundraising_for_unaffordable_departure"):
        "an open set in mode mine goes back to its preparation",
    ("policy_fundraising", "_settle_fundraising_detection"):
        "the open set's detection settles (prepare or scavenge); its callers are DETECTION_SETTLERS",
    ("policy_shop", "_shop_core"): "an open scavenge set goes back to its preparation",
}
# The openers whose body must ask the gate.
OPENERS = {
    ("morivant_tower", "start_fundraising_run"),
    ("policy_fundraising", "_open_one_mining_run"),
}
# (module, function): the callers of _settle_fundraising_detection.
DETECTION_SETTLERS = {
    ("policy_fundraising", "_fundraising_key"): "an open scavenge set no longer allowed",
    ("policy_town", "_town_terminal_transitions"): "an open set's detection in town",
    ("policy_town", "_break_town_cycle"): "the cycle break; may open from none (GATED_SETTLERS)",
    ("town_terminal", "_commit_fundraising_run"): "an open set's committed run",
    ("policy_fundraising", "_settle_diggerless_scavenge"):
        "an open set (prepare or mine) no digger can be had for scavenges 1F (n1-b life-420)",
}
# The settlers that may open a set from none: they must ask the gate.
GATED_SETTLERS = {("policy_town", "_break_town_cycle")}
CAUSED_CALLS = {"start_fundraising_run": 3, "open_set": 2, "dives": 2, "_start_fundraising": 1}
# The gate's wrappers pass their own ``cause`` parameter on.
PASS_THROUGH = {("morivant_tower", "start_fundraising_run"), ("policy", "_start_fundraising")}


def _functions(tree):
    """(name, node) of every function, the innermost enclosing one for each node."""
    owner = {}

    def walk(node, current):
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                else current
            owner[child] = inner
            walk(child, inner)
    walk(tree, "<module>")
    return owner


def _has_prepare(value) -> bool:
    return any(isinstance(node, ast.Constant) and node.value == PREPARE
               for node in ast.walk(value))


def _gate_call(node, name) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == name and isinstance(node.func.value, ast.Name)
            and node.func.value.id == GATE)


def _cause_ok(arg) -> bool:
    return (isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name)
            and arg.value.id == GATE and getattr(fundraising_route, arg.attr, None)
            in fundraising_route.CAUSES)


def main() -> int:
    findings = []
    seen_in_run, seen_settlers, seen_openers = set(), set(), set()
    gated_ok = set()
    for path in sorted(POLICY_ROOT.glob("*.py")):
        module = path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owner = _functions(tree)
        for node in ast.walk(tree):
            function = owner.get(node, "<module>")
            where = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and (module, node.name) in OPENERS:
                seen_openers.add((module, node.name))
                if not any(_gate_call(sub, "open_set") for sub in ast.walk(node)):
                    findings.append(f"{where}: {node.name} opens a set without "
                                    f"{GATE}.open_set")
            if isinstance(node, ast.Assign) and module != GATE:
                writes_mode = any(isinstance(target, ast.Attribute) and target.attr == MODE
                                  for target in node.targets)
                if writes_mode and _has_prepare(node.value):
                    if (module, function) in IN_RUN:
                        seen_in_run.add((module, function))
                    else:
                        findings.append(f"{where}: {MODE} = 'prepare' outside the gate in "
                                        f"{function} (call {GATE}.open_set with a cause)")
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            attr = node.func.attr
            if attr == "_settle_fundraising_detection" and function != attr:
                if (module, function) in DETECTION_SETTLERS:
                    seen_settlers.add((module, function))
                else:
                    findings.append(f"{where}: {function} settles the fundraising detection "
                                    f"(add a DETECTION_SETTLERS row, gate an opening)")
            if (module, function) in GATED_SETTLERS and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id == GATE:
                gated_ok.add((module, function))
            if attr not in CAUSED_CALLS or module == GATE:
                continue
            if attr in {"open_set", "dives"} and not (
                    isinstance(node.func.value, ast.Name) and node.func.value.id == GATE):
                continue
            index = CAUSED_CALLS[attr]
            cause = node.args[index] if len(node.args) > index else next(
                (kw.value for kw in node.keywords if kw.arg == "cause"), None)
            passed = ((module, function) in PASS_THROUGH and isinstance(cause, ast.Name)
                      and cause.id == "cause")
            if cause is None or not (passed or _cause_ok(cause)):
                findings.append(f"{where}: {attr} without a {GATE} cause in {function}")
    for row in sorted(set(IN_RUN) - seen_in_run):
        findings.append(f"IN_RUN row {row} names nothing the source has")
    for row in sorted(set(DETECTION_SETTLERS) - seen_settlers):
        findings.append(f"DETECTION_SETTLERS row {row} names nothing the source has")
    for row in sorted(OPENERS - seen_openers):
        findings.append(f"OPENERS row {row} names nothing the source has")
    for row in sorted(GATED_SETTLERS - gated_ok):
        findings.append(f"GATED_SETTLERS row {row} does not ask {GATE}")
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
