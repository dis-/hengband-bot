"""Extract frozen collaborator results, one explicitly named pin module/process.

Run from reconcile with PYTHONPATH=src;tests;scripts. Historical functions are
loaded read-only from git; no production source or other worktree is changed.
"""
import ast
import gzip
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests  # noqa: F401
from hengbot import equipment_optimizer as optimizer
from hengbot import warrior_equipment_evaluator as melee
from hengbot import warrior_optimization as preparation
from recorded_equipment_decisions import encode, input_signature

BASE = "d7429e7b"
CASES = {
    "town": "tests.test_town_approach_retired_recorded",
    "live27": "tests.test_identify_staff_live27_recorded",
    "classC2": "tests.test_classC2_departure_recorded",
}


def historical_functions(module, names):
    source = subprocess.check_output(
        ["git", "show", f"{BASE}:src/hengbot/{module.__name__.split('.')[-1]}.py"],
        encoding="utf8")
    tree = ast.parse(source)
    tree.body = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = dict(vars(module))
    exec(compile(tree, f"{BASE}:{module.__name__}", "exec"), namespace)
    return namespace


def main(case):
    namespace = historical_functions(optimizer, {"optimize_loadout", "_stable_operational_best"})
    old_bonus = historical_functions(melee, {"_distributed_bonus"})["_distributed_bonus"]
    records = {}
    evidence = []
    original = preparation.optimize_loadout

    def capture(items, evaluator, **kwargs):
        signature = input_signature(items, kwargs)
        kwargs["candidate_loadouts"] = tuple(kwargs["candidate_loadouts"])
        with patch.object(melee, "_distributed_bonus", old_bonus):
            old = namespace["optimize_loadout"](items, evaluator, **kwargs)
        # Cache belongs to a single prepare call and retains old arithmetic.
        # Comparison of the half-melee selector on identical evaluated values
        # isolates the optimizer ordering change from arithmetic corrections.
        new = original(items, evaluator, **kwargs)
        def chosen(result):
            if result.best is None:
                return None
            return {"mode": result.best.loadout.hand_mode,
                    "slots": {slot: {"id": item.id, "name": item.item.name}
                              for slot, item in result.best.loadout.slots},
                    "metrics": encode(result.best.metrics), "depth": result.chosen_depth}
        row = {"signature": signature, "old": chosen(old), "new_selector": chosen(new)}
        if signature not in records:
            evidence.append(row)
            print("OPTIMIZER", json.dumps(row, ensure_ascii=True), flush=True)
            records[signature] = encode(old)
        return old

    with patch.object(preparation, "optimize_loadout", capture), \
            patch.object(melee, "_distributed_bonus", old_bonus):
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromName(CASES[case]))
    directory = Path("validation/reconcile")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{case}-optimizer-evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf8")
    payload = json.dumps({"source_revision": BASE, "module": CASES[case],
                          "results": records}, ensure_ascii=True).encode()
    path = Path("tests/fixtures") / f"{case}.optimizer.json.gz"
    path.write_bytes(gzip.compress(payload, mtime=0))
    print("CAPTURE", case, len(records), "success", result.wasSuccessful(), flush=True)
    return result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if main(sys.argv[1]) else 1)
