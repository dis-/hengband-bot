"""Read-only diagnostics of the first Home knowledge replay divergences."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "validation" / "suitefix2" / sys.argv[2] if len(sys.argv) > 2 else ROOT
sys.path[:0] = [str(SOURCE / "src"), str(SOURCE), str(SOURCE / "tests"), str(SOURCE / "scripts")]
import tests
from test_town_approach_retired_recorded import TownApproachRetiredRecordedTest as Approach
from test_town_cure_supplier_recorded import TownCureSupplierRecordedTest as Cure

def facts(policy, board):
    request = policy._home_errand.request
    return dict(turn=board.turn, in_town=board.in_town,
                store=board.store.store_type if board.store else None,
                needs_knowledge=policy._home_errand.needs_knowledge,
                scan_inflight=policy._home_knowledge_scan_inflight,
                knowledge_current=policy._home_knowledge_current,
                purpose=request.purpose if request else None,
                atomic_deposit_pending=policy._home_atomic_deposit_pending is not None,
                atomic_withdraw_pending=policy._home_atomic_withdraw_pending is not None,
                physical_hostiles=bool(policy._physical_hostiles(board)),
                hp=[board.player.hp, board.player.max_hp], food=board.player.food_state)

evidence = {}
if sys.argv[1] == "approach":
    Approach.setUpClass()
    original = Approach._decide
    index = [0]
    def inspect(policy, board, **kwargs):
        before = facts(policy, board)
        row = original(policy, board, **kwargs)
        live = Approach.recorded[index[0]]
        if index[0] >= 1177:
            evidence[str(index[0])] = dict(before=before, live=live,
                                           current=row)
        index[0] += 1
        return row
    Approach._decide = staticmethod(inspect)
    try:
        Approach._replay()
    except AssertionError as exc:
        evidence["first_divergence"] = str(exc)
else:
    if sys.argv[1] == "cure-boundary":
        # Diagnostic prefix only; this is not a truncated acceptance test.
        sys.modules[Cure.__module__].CHECKPOINT = 30
    original = Cure._step.__func__
    def inspect(cls, policy, index, **kwargs):
        captured = {}
        def before(index, policy, board):
            captured.update(facts(policy, board))
        result = original(cls, policy, index, prepare=before, **kwargs)
        if result[:2] != (cls.recorded[index]["key"], cls.recorded[index]["reason"]):
            evidence[str(index)] = dict(before=captured, live=cls.recorded[index],
                                        current=list(result[:2]), claim=policy.decision_claim)
        return result
    Cure._step = classmethod(inspect)
    Cure.setUpClass()
    Cure.tearDownClass()
suffix = "-" + sys.argv[2] if len(sys.argv) > 2 else ""
out = ROOT / "validation" / "suitefix2" / (sys.argv[1] + suffix + "-divergences.json")
out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf8")
print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
