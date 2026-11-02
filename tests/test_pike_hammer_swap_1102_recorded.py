"""n1-c life-105 (2026-11-02 15:35-15:38): the Pike and the War Hammer swapped forever.

In Home, after each deposit, the optimizer planned the weapon that was NOT
worn; the next board withdrew it (decisions 1411 ``5pI`` and 1419 ``5pJ``).
Two loop stops in 30 minutes retired the character.

The flip was the depth-band descent.  Band 20 (the deepest band any owned set
satisfies) has the (Defender) Pike sets.  The half-melee check looked only at
the set the operational selector preferred, and that preference starts from
the worn loadout:
  - War Hammer worn: the Pike with the worn paper armour, 21.03 of 41.38
    (ratio 0.508) -> band 20 accepted, swap to the Pike (decision 1411);
  - Pike worn: the Pike with the Home all-resist chain mail (-2 to-hit),
    20.17 (ratio 0.487) -> band 20 refused, band 19, swap to the War Hammer
    (decision 1419) although the Pike set with the paper armour keeps 21.03.
The existing half-melee limit now filters every set of the band against the
unconstrained best before the selector chooses, so band 20 is accepted from
both boards and the Pike stays.

Every decision goes through the public choose_key; the in-Home leave key is
posted through the production executor.  DECLARED: the ~f skill list is the
row the same character's restarted process read at the stop turn 1485835
(the skill list of the looping process is not in the capture).
Fixture: tests/extract_pike_hammer_swap_1102_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files

import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import load_character_calibration
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness
from tests.test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "pike-hammer-swap-1102.json.gz"
SHA256 = "65108fa6750c16746f4258a09e2c268e774ae68ba250053f5ea4ac0f5378ec75"
PIKE = "f0ee32295a81e4dc"
HAMMER = "003d875483a6942a"
FIRE_RING = "5cd0c22e94465fd6"


class PikeHammerSwapRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(payload))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def policy(self, raw):
        directory = Path(self.enterContext(TemporaryDirectory()))
        policy = _policy(directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        calibration = directory / "recorded-calibration.json"
        calibration.write_text(json.dumps(self.data["calibration"]), encoding="utf-8")
        policy._character_calibration = load_character_calibration(calibration)
        self.assertIsNotNone(policy._character_calibration)
        policy._character_calibration_loaded = True
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy.consume_skill_knowledge(self.data["skill_exp"])
        policy.test_directory = directory
        return policy

    def decide(self, policy, raw):
        _decoded, snapshots = _consume_response_sequence(
            [json.dumps(raw, ensure_ascii=False)], policy, lambda _key: True,
            self.monrace, knowledge_ledger_path=policy.test_directory / "knowledge.jsonl")
        return policy.choose_key(snapshots[-1]), policy.last_reason

    def leave_home_plan(self, inside, outside):
        boards = self.data["boards"]
        policy = self.policy(boards[inside])
        key, _reason = self.decide(policy, boards[inside])
        self.assertEqual(key, "\x1b")
        self.post(policy, boards[inside], key, boards[outside])
        session = policy._equipment_transaction_session
        self.assertIsNotNone(session)
        return [(action.kind, action.item_id.split(":")[1], action.target_slot)
                for action in session.plan.actions]

    def test_recorded_withdrawals_flip_band_20(self):
        decisions = self.data["decisions"]
        self.assertEqual(
            [(row["turn"], row["key"], row["transaction_next"]["item_id"])
             for _, row in sorted(decisions.items())],
            [(1485513, "5pI\x1b", f"home:{PIKE}:0"), (1485543, "5pJ\x1b", f"home:{HAMMER}:0")])
        band_20 = [row["band_descent"][-1 if row["key"] == "5pI\x1b" else -2]
                   for _, row in sorted(decisions.items())]
        self.assertEqual([(row["band"], row["refusal_reason"]) for row in band_20],
                         [(20, None), (20, "melee-ratio")])

    def test_worn_pike_stays_and_the_hammer_is_not_withdrawn(self):
        # 9afd9203e: [('withdraw', HAMMER, None), ('takeoff', PIKE, 'main_hand'),
        #             ('equip', HAMMER, 'main_hand'), ('deposit', PIKE, None)].
        plan = self.leave_home_plan("pike-worn-in-home", "pike-worn-outside")
        self.assertNotIn(HAMMER, [item for _kind, item, _slot in plan])
        self.assertEqual(plan, [("withdraw", FIRE_RING, None), ("equip", FIRE_RING, "sub_ring")])

    def test_control_worn_hammer_still_takes_the_band_20_pike(self):
        plan = self.leave_home_plan("hammer-worn-in-home", "hammer-worn-outside")
        self.assertEqual(plan, [("withdraw", PIKE, None), ("takeoff", HAMMER, "main_hand"),
                                ("equip", PIKE, "main_hand"), ("deposit", HAMMER, None)])


if __name__ == "__main__":
    import unittest
    unittest.main()
