"""A stat-stick sub-hand weapon that ruins the blows is not worn (n1-b life-421, 2026-11-28).

Owner 2026-11-28 (verbatim): 「二刀流の装備評価あってる？全然強くなさそうだけど」.  n1-b life-421
(Klackon Magic-Eater CL31) accepted quest 31 at 18:12 and its equipment transaction wielded
☆鎖つき鉄球『超兄貴』 (3d4) (+19,+11) (+5 STR/CON) in the sub hand beside ★ブロード・スピア『ロンギヌス』
(2d9) (+13,+14): HP 475 -> 568, and in the quest nearly every blow missed.

The melee number was true: the evaluator (warrior_equipment_evaluator.evaluate_warrior_melee, the
one answer the optimiser and the quest readiness both read) gave the set 9.1 a turn (hit chance 5%
in both hands: the two-weapon penalty of player-status.cpp:1820-1850 at two_weapon_skill 1040 takes
the hands' to-hit to -95 and -90, and hit_chance floors a non-positive reliability at 5%,
attack-accuracy.cpp:45-48) against 78.1 for the spear alone.  The optimiser chose it anyway: its
attack cuts read the larger of the blows and the absorbed attack (64.2 for every set), so the 9.1
was never cut and the STR/CON stick won on survival.  The fix reads melee in the cuts again.

Recorded (tests/extract_n1b_421_dual_wield_1128_fixture.py): the town-arrival checkpoint of 18:12:50
and its 66 journal rows.  DECLARED CONSTRUCTED: the arrival's character calibration (sidecar) with
the policy's current mutation signature, adopted after row 3 (the live process re-derived it from
the dump of row 2, a file the capture does not hold; without it the replay reads
``calibration-required`` where the live process searched).  Row 5 is not compared (the replay's
power-list timer differs from the live process's).  From row 21 the bot's keys differ from the
record's (it starts no swap); the boards stay the recorded ones, so those rows only check that no
decision blocks or raises.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import dataclasses
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import staged_prompt_chain_matches
from hengbot.speed_valuation import time_melee
from hengbot.warrior_equipment_evaluator import _dual_wield_penalty
from hengbot.warrior_optimization import load_character_calibration, save_character_calibration
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-421-dual-wield-1128"
CALIBRATED_ROW = 3
TIMER_ROW = 5
SEARCHED_ROW = 21
LAST_ROW = 65
QUEST = 31
SPEAR = "★ブロード・スピア『ロンギヌス』"
STICK = "☆鎖つき鉄球『超兄貴』"


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


def hand_names(loadout):
    return {slot: owned.item.name for slot, owned in loadout.slots
            if slot in ("main_hand", "sub_hand")}


class DualWield421RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        policy, _journal, steps = load(FIXTURE, scratch)
        cls.policy = policy
        cls.rows = []
        for recorded, supply in steps[:LAST_ROW + 1]:
            board = supply()
            if recorded["row"] == CALIBRATED_ROW:
                cls._adopt_calibration(policy, scratch)
            decided = decide(policy, board)
            if recorded["row"] == SEARCHED_ROW:
                # After the decision: ``choose_key`` fills the board's two-weapon skill (~f).
                with contextlib.redirect_stdout(io.StringIO()):
                    cls.preparation = policy._prepare_equipment_optimization(board)
            cls.rows.append((recorded, decided, board))
            post(policy, decided[0] if recorded["row"] >= SEARCHED_ROW else recorded["key"])

    @staticmethod
    def _adopt_calibration(policy, scratch):
        """DECLARED CONSTRUCTED (module docstring): the sidecar calibration with the policy's
        mutation signature."""
        recorded = Path(policy._character_calibration_path)
        value = load_character_calibration(recorded)
        fixed = scratch / "calibration-1812.json"
        save_character_calibration(fixed, dataclasses.replace(
            value, mutation_signature=tuple(policy._mutation_signature or ())))
        adopt_calibration(policy, fixed, scratch)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_recorded_rows_replay(self):
        for recorded, decided, _board in self.rows[:SEARCHED_ROW]:
            if recorded["row"] != TIMER_ROW:
                self.assertEqual(decided, (recorded["key"], recorded["reason"]), recorded["row"])

    def test_the_spear_alone_is_the_target(self):
        result = self.preparation.result
        self.assertEqual(self.preparation.blockers, ())
        best = result.best
        hands = hand_names(best.loadout)
        self.assertTrue(hands["main_hand"].startswith(SPEAR), hands)
        self.assertNotIn(STICK, " ".join(hands.values()))
        # The stick's sets keep under half the blows: the half-melee limit cuts them.
        dual = [entry for entry in result.chosen_band_entries
                if entry.loadout.hand_mode == "dual_wield"
                and STICK in entry.loadout.item_at("sub_hand").item.name]
        self.assertTrue(dual)
        for entry in dual:
            self.assertLess(time_melee(entry.metrics) * 2, time_melee(best.metrics))
        self.assertGreater(best.metrics.expected_dps, best.metrics.device_dps)

    def test_the_penalty_is_the_game_formula(self):
        """player-status.cpp:1827 and :1847: (100 - skill / 160) - (130 - weight) / 8 (C++
        division truncates toward zero), +10 for a polearm; at two_weapon_skill 1040."""
        catalogue = self.policy._equipment_catalog.items
        spear = next(owned for owned in catalogue if owned.item.name.startswith(SPEAR))
        stick = next(owned for owned in catalogue if owned.item.name.startswith(STICK))
        def game(weight, polearm):
            pull = 130 - weight
            truncated = -(-pull // 8) if pull < 0 else pull // 8
            return (100 - 1040 // 160) - truncated + (10 if polearm else 0)

        fake = dataclasses.make_dataclass("Inputs", [("two_weapon_skill", int)])(1040)
        self.assertEqual(_dual_wield_penalty(fake, spear, stick),
                         game(spear.item.weight, spear.item.tval == 22))
        self.assertEqual(_dual_wield_penalty(fake, stick, stick),
                         game(stick.item.weight, stick.item.tval == 22))

    def test_nothing_blocks_and_the_entry_reads_readiness(self):
        for recorded, decided, _board in self.rows[SEARCHED_ROW:]:
            self.assertFalse(str(decided[1]).startswith("town:blocked"), recorded)
        # The recorded boards after the record's swap wear the stick: the quest's entry reads
        # the acceptance's readiness on them and refuses (strategy-force).
        recorded, _decided, board = self.rows[-1]
        self.assertTrue(any(item.name.startswith(STICK) for item in board.equipment))
        with contextlib.redirect_stdout(io.StringIO()):
            ready = self.policy._fixed_quest_ready_for_travel(board, QUEST)
        self.assertFalse(ready)
        self.assertEqual(self.policy._fixed_quest_readiness.get("reason"), "strategy-force")



if __name__ == "__main__":
    unittest.main()
