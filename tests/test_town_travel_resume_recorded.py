"""#47: a held inn travel resumes with the travel command (owner 2026-11-01
「街での移動は可能な限りトラベルコマンドを活用して」).

D52 (town_travel) sends the inn legs by the game's travel command to the
inn's side, but the travel offer was _town_travel_key's generic route.resume
while the leg's own step declared town.teleport.resume, for every
quest-request leg (the Magic-Eater inn legs, the Q2 tower trip,
fixedquest:q<id>-travel, prepare-return).

The recorded board is n1-c life-067 at the Tower after stage 1
(tests/fixtures/me-staff-loops-20261031.json.gz "inn", the board of
test_me_tower_trips_recorded.test_inn_leg_travels_beside_the_inn): the inn
leg back to the Outpost.  Every decision is the public ``choose_key``; every
key goes through the production executor (test_me_nokey_1031_recorded.PostedKey).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from hengbot import me_staff_sequence as sequence
from hengbot.town_travel import is_travel_macro
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_me_tower_trips_recorded import loops_policy

OUTPOST = 0
REASON = "me-staff:return-to-shop"


class HeldInnTravelRecordedTest(nokey.PostedKey):
    def setUp(self):
        self.case, self.policy = loops_policy("inn")
        self.raw = self.case["boards"][0]
        sequence.state(self.policy).searched_towns[2] = self.raw["turn"]

    def travel(self):
        key = loops.decide(self.policy, self.raw)
        self.assertEqual(self.policy.last_reason, REASON, key)
        self.assertTrue(is_travel_macro(key), key)
        return key

    def test_inn_travel_declares_the_legs_own_resume(self):
        key = self.travel()
        execution = self.policy._claim_register.current.execution
        # Unfixed: route.resume ('store', (42, 93)).
        self.assertEqual((execution.next_step, execution.continuation, execution.arguments),
                         ("town.teleport.resume", "town.teleport.resume", (OUTPOST, REASON)))
        self.post(self.policy, self.raw, key)


if __name__ == "__main__":
    unittest.main()
