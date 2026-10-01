"""Capture historical gear collaborators for one named batchfixB replay.

Historical source is read from git. Town/guardian/ownership behavior stays live;
the fixture supplies only the gear decision whose subsequent boards were recorded.
"""
import gzip
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capture_reconcile_optimizer import historical_functions, BASE
from hengbot import equipment_optimizer as optimizer
from hengbot import warrior_equipment_evaluator as melee
from hengbot import warrior_optimization as preparation
from recorded_equipment_decisions import decode, encode, input_signature

CASES = {
    "guardian": "tests.test_guardian_recall_pingpong_recorded",
    "overweight": "tests.test_overweight_home_unreachable_recorded",
}


def main(case):
    namespace = historical_functions(optimizer, {"optimize_loadout", "_stable_operational_best"})
    old_bonus = historical_functions(melee, {"_distributed_bonus"})["_distributed_bonus"]
    records = {}

    def capture(items, evaluator, **kwargs):
        signature = input_signature(items, kwargs)
        if signature in records:
            return decode(records[signature])
        result = namespace["optimize_loadout"](items, evaluator, **kwargs)
        encoded = encode(result)
        if signature not in records:
            records[signature] = encoded
            print("CAPTURED", signature, None if result.best is None else
                  [(slot, item.id) for slot, item in result.best.loadout.slots], flush=True)
        return result

    with patch.object(preparation, "optimize_loadout", capture), \
            patch.object(melee, "_distributed_bonus", old_bonus):
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromName(CASES[case]))
    payload = json.dumps({"source_revision": BASE, "module": CASES[case],
                          "results": records}, ensure_ascii=True).encode()
    (Path("tests/fixtures") / f"{case}.optimizer.json.gz").write_bytes(
        gzip.compress(payload, mtime=0))
    print("CAPTURE", case, len(records), result.wasSuccessful(), flush=True)
    return result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(not main(sys.argv[1]))
