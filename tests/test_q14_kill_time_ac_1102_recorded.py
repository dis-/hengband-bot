"""2026-11-02 n1-c life-102: Q14 refused by toughest-kill-time at AC 100.

Decision 3141 (04:22:13, turn 1057356) passed QUEST_14's three-turn-threat
(116 against 451 x 0.50) and was refused by ``toughest-kill-time``:
main_hand_melee_output 3.0 while the force gate measured 24.0 DPS.  The
War Hammer (3d3) (+3,+5) was wielded on the board and the Shovel was in the
pack (the restore of decisions 3108-3109 had already run), so the digger was
not the cause.  The kill-time output was measured at the generic AC 100,
where the Lv12 Magic-Eater only hits at the 5% floor, while the force gate
measured the same weapon at QUEST_14's reference_ac 20 (the Warg's real AC,
①案 2026-07-18).  Both readiness DPS values now use that one armour class.

The recorded town board goes through the public ``choose_key`` and the
posted key through the production executor.  Fixture:
tests/extract_q14_kill_time_ac_1102_fixture.py.

DECLARED RECONSTRUCTED: a new process on the recorded board, with the
repository's quest, monster, strategy and town-map data the CLI loads, the
recorded skill and Home knowledge rows, and the staff-sequence record of
the 04:27 incident checkpoint.  The Magic-Eater staff recharge still owns
the town first (the recorded me-staff:travel-morivant, unchanged).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from tests.test_me_nokey_1031_recorded import PostedKey
from tests.test_q14_lv8_1102_recorded import Q14Lv8ThreatRecordedTest


FIXTURE = Path(__file__).with_name("fixtures") / "q14-kill-time-ac-1102.json.gz"


class Q14KillTimeReferenceAcRecordedTest(PostedKey):
    # PostedKey.post: the travel macro needs the game's 256-key queue.
    recorded_policy = Q14Lv8ThreatRecordedTest.recorded_policy

    @classmethod
    def setUpClass(cls):
        Q14Lv8ThreatRecordedTest.setUpClass.__func__(cls)
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def test_recorded_board_measures_kill_time_at_the_force_reference_ac(self):
        decision = self.case["decision"]
        self.assertEqual((decision["decision_sequence"], decision["turn"], decision["reason"]),
                         (3141, 1057356, "me-staff:travel-morivant"))
        recorded = decision["fixedquest_readiness"]
        self.assertEqual((recorded["reason"], recorded["main_hand_melee_output"]),
                         ("toughest-kill-time", 3.0))
        weapon = next(it for it in self.case["board"]["equipment"] if it["slot"] == "main_hand")
        self.assertEqual(weapon["tval"], 21)  # the War Hammer, not the Shovel (tval 20)

        policy, raw = self.recorded_policy()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = policy.choose_key(board)
        readiness = policy._fixed_quest_readiness
        self.assertEqual(readiness["quest_id"], 14)
        self.assertEqual(readiness["strategy_force"]["reference_ac"], 20)
        self.assertEqual(readiness["toughest_hp"], 36)
        # Hasted output over baseline turns: twice the force gate's per-action DPS.
        self.assertAlmostEqual(readiness["main_hand_melee_output"],
                               2 * readiness["strategy_force"]["dps"]["measured"])
        self.assertGreaterEqual(readiness["entry_melee_output"] * 10, readiness["toughest_hp"])
        self.assertEqual(readiness["reason"], "ready")
        self.assertTrue(readiness["verdict"])
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant")
        # DECLARED CONSTRUCTED (PostedKey): the engine's reply to the travel command.
        self.post(policy, raw, key)


if __name__ == "__main__":
    import unittest
    unittest.main()
