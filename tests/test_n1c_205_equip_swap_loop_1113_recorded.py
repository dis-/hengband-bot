"""n1-c life-205's Home glove swap (2026-11-13 20:06-20:14, loop detector 20:09:23 and 20:11:55).

Recorded: the town-arrival checkpoint of the 20:06 visit, journal rows 0-24
and sidecar files (tests/extract_n1c_205_equip_swap_loop_1113_fixture.py),
through the public choose_key.

The Magic-Eater (Lv46) swapped two gloves through Home every second: row 2
(the Cestus 'Kyousoku' worn) planned the Gauntlets of Slaying, row 24 (the
Gauntlets worn) planned the Cestus back.  The catalog is past the incremental
threshold, so the optimizer chose from the worn loadout's one-swap
neighbourhood, and its selection is relative to the field: the shieldless
two-handed grip of the spear is a neighbour of both, at 388.9 melee and 30.3
survival turns with the Cestus (AC 5+13) but 396.7 and 28.1 with the
Gauntlets (AC 2+6).  Above the 30-turn floor it raises the 95% melee cut
past the Cestus set (367.8), so the Gauntlets set (375.4) wins; below it the
cut stays low, the Cestus set stays and wins on the secondary value.

The selection now grows the field to the union of the neighbourhoods of the
chosen sets until the choice's own neighbourhood is in it
(warrior_optimization.optimize_single_slot_closure): both boards choose over
the same field and plan the same target.

DECLARED RECONSTRUCTED: the policy reaches row 24 (the Gauntlets worn) only
along the recorded swap.  Rows 0-23 are therefore decided with the recorded
single-neighbourhood selection (the closure replaced by the one optimization
it used to be) and must match the recorded keys and reasons; row 24 is then
decided by the production selection.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-205-equip-swap-loop-1113"
CESTUS_WORN_ROW = 2
GAUNTLETS_WORN_ROW = 24
GAUNTLETS = "489ecf86822a8ea6"   # 殺戮のガントレット (+1,+2) [2,+6]
CESTUS = "9059edba1a8d20d0"      # ☆セスタス『驚速』 [5,+13] (+3隠密) {+隠赤r劣(器}
BOUQUET = "e57febe109bbd817"     # ☆ナイト・シールド『薔薇のブーケ』 [10,+16] (+4)
TURBO = "68bf3150c4f06d5a"       # ☆ミラー・シールド『ターボ』 [10,+22] (+3)


def single_neighbourhood(current, neighbours, optimize):
    """The selection as recorded: one optimization over the worn loadout's neighbours."""
    return optimize(tuple(neighbours(current)))


class N1c205EquipSwapLoop1113RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def decide(self, row):
        board = self.steps[row][1]()
        return board, self.policy.choose_key(board), self.policy.last_reason

    def post(self, key):
        policy = self.policy
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay_recorded(self, rows):
        for row in range(rows):
            _board, key, reason = self.decide(row)
            self.assertEqual((key, reason),
                             (self.recorded[row]["key"], self.recorded[row]["reason"]), row)
            self.post(key)

    def equips(self):
        """{slot: item digest} the planned transaction puts on."""
        session = self.policy._equipment_transaction_session
        self.assertIsNotNone(session)
        return {action.target_slot: action.item_id.split(":")[1]
                for action in session.plan.actions if action.kind == "equip"}

    def worn(self, board, slot):
        return next(item for item in board.equipment if item.slot == slot)

    def test_both_gloves_plan_the_same_loadout(self):
        self.assertEqual(
            [(self.recorded[row]["key"], self.recorded[row]["reason"])
             for row in (CESTUS_WORN_ROW, GAUNTLETS_WORN_ROW)],
            [("\x1b`n(.", "equipment-transaction:travel-home")] * 2)
        with mock.patch("hengbot.warrior_optimization.optimize_single_slot_closure",
                        single_neighbourhood, create=True):
            self.replay_recorded(GAUNTLETS_WORN_ROW)
        board, _key, _reason = self.decide(GAUNTLETS_WORN_ROW)
        self.assertIn("ガントレット", self.worn(board, "arms").name)
        self.assertIn("薔薇のブーケ", self.worn(board, "sub_hand").name)
        # Recorded: {"arms": CESTUS}.  The worn Gauntlets stay.
        self.assertEqual(self.equips(), {"sub_hand": TURBO})
        self.assertNotIn(CESTUS, self.equips().values())

        self.setUp()
        self.replay_recorded(CESTUS_WORN_ROW)
        board, _key, reason = self.decide(CESTUS_WORN_ROW)
        self.assertIn("セスタス", self.worn(board, "arms").name)
        self.assertEqual(reason, "equipment-transaction:travel-home")
        self.assertIn("薔薇のブーケ", self.worn(board, "sub_hand").name)
        # Recorded: {"arms": GAUNTLETS} with the Bouquet kept, whose board then
        # planned the Cestus back.  Now the same loadout as from the Gauntlets:
        # the Gauntlets with the Turbo mirror shield.
        self.assertEqual(self.equips(), {"arms": GAUNTLETS, "sub_hand": TURBO})
        self.assertNotIn(BOUQUET, self.equips().values())


if __name__ == "__main__":
    unittest.main()
