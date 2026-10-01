"""Recorded entrance attachment; stop at the first changed key (row 7)."""
import tests  # noqa: F401
import gzip
import json
import pickle
import tempfile
import unittest
from pathlib import Path
from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.warrior_optimization import load_character_calibration

FIXTURES = Path(__file__).parent / "fixtures"


def records(kind):
    with gzip.open(FIXTURES / f"live33-calibration-{kind}-20261001.jsonl.gz", "rt", encoding="utf8") as source:
        return list(map(json.loads, source))


def attached(on):
    raw = records("state")
    policy = HengbotPolicy()
    policy._character_calibration = load_character_calibration(
        FIXTURES / "live33-character-calibration-20261001.json")
    policy._character_calibration_loaded = True
    policy._town_claim_bar_enforced = on
    policy._crossarea_fundraising_enforced = True
    policy.observe_town_visit_epoch(True, 1140181)
    policy.consume_skill_knowledge(raw[1])
    policy.consume_home_knowledge(tuple(_parse_items(raw[3]["knowledge"]["items"])))
    return policy, raw


class Live33CalibrationTest(unittest.TestCase):
    def test_recorded_deposit_continues_and_shadow_agrees(self):
        live = {row["decision_sequence"]: row for row in records("decisions")
                if "decision_sequence" in row}
        for checkpoint in (False, True):
            results = []
            for on in (False, True):
                policy, raw = attached(on)
                for seq, index in ((5, 10), (6, 11)):
                    board = parse_snapshot(raw[index], {})
                    key = policy.choose_key(board)
                    self.assertEqual(key, live[seq]["key"])
                    self.assertEqual(policy.last_reason, live[seq]["reason"])
                    policy.confirm_key_posted(key)
                self.assertFalse(policy._calibration_stripped_unrestored)
                self.assertEqual(len(policy._calibration_restore_signatures), 5)
                if checkpoint:
                    # Derived registry contains local predicates; rebuild it
                    # after serialization without changing physical debt.
                    policy._town_need_specs = None
                    policy = pickle.loads(pickle.dumps(policy))
                board = parse_snapshot(raw[20], {})
                key = policy.choose_key(board)
                shadow = policy._s33_shadow_verdict(board, key)
                results.append((key, policy.last_reason, shadow["would_stop"]))
                self.assertEqual(key, "5")
                self.assertEqual(policy.last_reason, "home:atomic-deposit")
                self.assertEqual(policy._calibration_phase, "deposit")
                self.assertIsNotNone(policy._home_atomic_deposit_pending)
                self.assertIsNone(shadow["would_stop"])
                print("live33 first divergence", repr(key), policy.last_reason,
                      "live", repr(live[7]["key"]), live[7]["reason"], "shadow", shadow["would_stop"])
            self.assertEqual(results[0], results[1])

    def test_restart_reconciles_only_observed_redress_debt(self):
        policy, raw = attached(True)
        board = policy.with_known_skill_exp(parse_snapshot(raw[10], {}))
        worn = next(item for item in board.equipment if item.is_equipment)
        carried = next(item for item in board.inventory if item.is_equipment)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            for entries, expected in (([], False),
                    ([[worn.slot, equipment_identity(worn)]], False),
                    ([["main_hand", equipment_identity(carried)]], True)):
                path.write_text(json.dumps({"redress_obligation": entries}), encoding="utf8")
                restarted = HengbotPolicy()
                restarted._character_calibration_path = path
                restarted._town_claim_bar_enforced = True
                restarted._calibration_observe(board)
                self.assertEqual(restarted._calibration_stripped_unrestored, expected)
                self.assertEqual(restarted._calibration_restore_signatures, [])
                self.assertEqual(bool(json.loads(path.read_text(encoding="utf8")).get("redress_obligation")), expected)
                restored = pickle.loads(pickle.dumps(restarted))
                restored._calibration_observe(board)
                self.assertEqual(restored._calibration_stripped_unrestored, expected)


if __name__ == "__main__":
    unittest.main()
