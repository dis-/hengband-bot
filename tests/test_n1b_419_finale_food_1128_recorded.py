"""A drained food wand among the three no longer stops the finale's preparation (n1-b life-419,
MAINTAINABILITY.md 2).

Recorded (tests/extract_n1b_419_finale_food_1128_fixture.py, ``n1b-419-finale-food-1128``): the
town-arrival checkpoint of 2026-11-28 07:23:06 (Zombie Magic-Eater CL50, build bot-ad2db18c6,
speed +37 at arrival and +26 on the stop board, slow digestion worn, arrival turn 14707739).  Every finale supply was
owned and carried (Restore Mana 204 of 34, the ten Scrolls of Recharging of 2026-11-26 among them);
the pack held 謎の魔法棒 {@E1} (19), {@E2} (0) and {@E3} (19), each known with its charges (the
game's own 「(0回分)」), the Home none.  At row 85 the phase reached its food step and stopped as
``food:wonder-uncharged`` on the {@E2}, and from then on the town repeated
``town:blocked:finale-prep-stopped:food:wonder-uncharged`` until loop-detected (07:24:03).

Owner 2026-11-26 (verbatim) 「魔力充填の巻物を10巻持っていき、空腹かつ3本とも空の場合のみ充填して食料と
する」: the drained wand is the battle's to refill (finale_recharge_food), and the 38 charges left are
the departure's food many times over (finale_prep ``food_done``).

Every row is replayed through the public ``choose_key`` with the recorded key posted after it (no
exception on any row).  From row 15 on the replay picks other Home pieces than the record's
equipment transaction (on the deployed build and on main alike: the fixture leaves the loadout report
out), so rows 15-89 are listed, not asserted.

DECLARED CONSTRUCTED: on the recorded stop board (row 85) the replayed policy's phase is set at its
food step (the diverged equipment transaction kept the replay from reaching it by itself).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, finale_prep, food_supply
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.magic_eater_devices import staple_charges, staple_needs_recharge
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import FOOD_TYPE_MANA
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-419-finale-food-1128"
REPRODUCED = range(0, 15)
STOP_ROW = 85
STOP_REASON = "town:blocked:finale-prep-stopped:food:wonder-uncharged"
WANDS = {"@E1": 19, "@E2": 0, "@E3": 19}


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class FinaleFood419RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.recorded = [(row["key"], row["reason"]) for row in journal]
        cls.replayed = []
        for row, (recorded, supply) in enumerate(steps):
            board = supply()
            if row == STOP_ROW:
                cls.stop_board, cls.stop_checkpoint = board, checkpoint_bytes(policy)
            cls.replayed.append(decide(policy, board))
            post(policy, recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_whole_visit_runs_through_choose_key(self):
        self.assertEqual(len(self.replayed), len(self.recorded))
        self.assertEqual(self.recorded[STOP_ROW], ("1", STOP_REASON))
        for row in REPRODUCED:
            self.assertEqual(self.replayed[row], self.recorded[row], row)
        self.assertNotIn(STOP_REASON, [reason for _key, reason in self.replayed])

    def test_the_recorded_board(self):
        board = self.stop_board
        self.assertEqual(board.player.food_type, FOOD_TYPE_MANA)
        stacks = finale_prep.food_stacks(board)
        self.assertEqual({item.inscription: item.charges for item in stacks}, WANDS)
        self.assertTrue(all(item.known and item.count == 1 for item in stacks))
        self.assertEqual(angband_finale.carried(board, angband_finale.RECHARGING),
                         angband_finale.RECHARGING_CARRY)
        # 36 (speed +26 on the stop board, speed-table.cpp) - 5 (slow digestion) every 50 game
        # turns; a charge is 5000 food (cmd-eat.cpp): 38 charges, about 300000 game turns.
        self.assertEqual(board.player.speed, 136)
        self.assertEqual(food_supply.digestion_per_interval(board.player), 31)
        self.assertEqual(staple_charges(board), 19)
        self.assertFalse(staple_needs_recharge(board))
        self.assertTrue(finale_prep.food_done(board))

    def test_the_food_step_goes_on_to_the_loadout(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.stop_checkpoint)
        held = finale_prep.phase(policy)
        held.step, held.in_town, held.stopped = finale_prep.FOOD, True, None  # DECLARED
        held.since, held.food_dropped = policy._decision_sequence, None
        self.assertIsNone(finale_prep.town_key(policy, self.stop_board))
        self.assertIsNone(held.stopped)
        key, reason = decide(policy, self.stop_board)
        self.assertNotEqual(reason, STOP_REASON)
        self.assertNotIn("finale-prep-stopped", reason)
        self.assertIsNone(held.stopped)
        self.assertNotIn(held.step, (finale_prep.FOOD, finale_prep.STOPPED))
        self.assertIn((finale_prep.LOADOUT, f"{finale_prep.FOOD_WANDS} wands"),
                      [(step, note) for _seq, step, note in held.log])


if __name__ == "__main__":
    unittest.main()
