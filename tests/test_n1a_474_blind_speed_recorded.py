"""Recorded replay of the n1-a life-474 death of 2026-11-03 21:39 (鉄獄49階).

Source: tests/fixtures/death-n1a-474-1103.json.gz
(tests/extract_n1a_474_blind_speed_fixture.py): the Lv37 warrior's explore
steps at HP 774/774 and the board of turn 2312011, where 「何かが暗黒の嵐の呪文を
念じた。」 took HP to 505 and blinded it.  It drank Cure Critical Wounds (``qb``)
with three Potions of Speed carried and no Healing; the next two spells killed
it.  「呪文を念じた」 was also missing from the unseen spell messages, so the
board did not count as an unseen caster's hit.

Owner 2026-11-04: 「スピードの薬を先に飲む。加えて、体力が減っているand盲目の
状態では致命傷の治癒より体力回復の薬を優先して使用する。」

DECLARED CONSTRUCTED, on the recorded board: the speed field shown hasted
(+10, yellow; the board after the dose), a Potion of Healing added to the pack
(the character carried none), the board after the dose (no new message), and
HP 600 for a hit below the 1/3 line.

Owner 2026-11-04 (answer): 「低い時は体力回復が先」.  Below the low-HP threshold
a carried Healing goes before the Speed dose.  LowHpHealingFirstRecordedTest
plays the recorded blind board at HP 310/731 (threshold 431) of
tests/test_lethal_unseen_caster_recorded.py, which carried both potions.
DECLARED CONSTRUCTED there: the same board with the Healing stack removed.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import unseen_strike
from tests import test_lethal_unseen_caster_recorded as lethal
from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1a-474-1103.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

STORM = 2312011
SPEED_KEY, CURE_KEY, HEALING_KEY = "qa", "qb", "qc"
HASTED = {"speed": 120, "speed_display": {"color": "yellow", "riding": False,
                                          "text": "加速 (+10)", "value": 10}}


def storm_board():
    return copy.deepcopy(CASE["boards"][-1])


def hasted(raw):
    raw["player"].update(copy.deepcopy(HASTED))
    return raw


def with_healing(raw):
    """The recorded pack with a Potion of Healing after Cure Critical Wounds,
    the later rows' labels moved on by one (the game's pack order)."""
    inventory = raw["inventory"]
    potion = dict(copy.deepcopy(inventory[1]), count=2, name="体力回復の薬", sval=37, slot="c")
    for row in inventory[2:]:
        row["slot"] = chr(ord(row["slot"]) + 1)
    inventory.insert(2, potion)
    return raw


def after_dose(raw):
    """The next player board: the dose took effect, nothing new has happened."""
    return dict(hasted(raw), turn=raw["turn"] + 10, messages=[])


class BlindSpeedFirstRecordedTest(d57.PostedDeathKey):
    def decide(self, *boards):
        """Replay the sighted steps, then decide ``boards`` in order; each key
        goes through the executor.  The last (key, reason) is returned."""
        policy = d57.loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])
        for raw in CASE["boards"][:-1]:
            policy.confirm_key_posted(d57.loops.decide(policy, copy.deepcopy(raw)))
        for raw in boards:
            key = d57.loops.decide(policy, raw)
            answer = key, policy.last_reason
            self.post(policy, raw, key)
            policy.confirm_key_posted(key)
        return answer

    def test_recorded_row(self):
        self.assertEqual(d57.recorded(CASE)[STORM], ("item:cure-critical", CURE_KEY))
        raw = storm_board()
        self.assertEqual((raw["player"]["hp"], raw["player"]["max_hp"]), (505, 774))
        self.assertIn("何かが暗黒の嵐の呪文を念じた。", raw["messages"])
        self.assertEqual([row["sval"] for row in raw["inventory"][:2]], [29, 36])

    def test_speed_before_the_cure_then_the_cure(self):
        speed = self.decide(storm_board())
        self.assertEqual(speed, (SPEED_KEY, unseen_strike.SPEED_REASON))
        self.assertEqual(self.decide(storm_board(), after_dose(storm_board()))[0], CURE_KEY)

    def test_already_hasted_goes_straight_to_the_cure(self):
        self.assertEqual(self.decide(hasted(storm_board()))[0], CURE_KEY)

    def test_speed_outranks_healing(self):
        self.assertEqual(self.decide(with_healing(storm_board()))[0], SPEED_KEY)

    def test_hasted_cures_with_healing(self):
        board = with_healing(storm_board())
        self.assertEqual(self.decide(hasted(copy.deepcopy(board))),
                         (HEALING_KEY, "emergency:cure-status-healing"))
        self.assertEqual(self.decide(copy.deepcopy(board), after_dose(copy.deepcopy(board))),
                         (HEALING_KEY, "emergency:cure-status-healing"))

    def test_a_named_attacker_gets_healing_and_no_speed(self):
        """Rule 2 is not limited to an unseen caster; rule 1 is."""
        raw = with_healing(storm_board())
        raw["messages"] = ["ヴラスタに噛まれた。", "目が見えなくなってしまった！"]
        key, reason = self.decide(raw)
        self.assertEqual(key, HEALING_KEY, reason)

    def test_above_the_line_the_cheap_cure_stays(self):
        raw = with_healing(storm_board())
        raw["player"]["hp"] = 600
        self.assertEqual(self.decide(raw)[0], CURE_KEY)


class LowHpHealingFirstRecordedTest(lethal._Replay):
    def decide_blind_board(self, line=None):
        self._decide(lethal.B_WARMUP)
        return self._decide(lethal.B_CURE, line)

    def test_below_the_threshold_healing_goes_first(self):
        board, key, reason = self.decide_blind_board()
        player = board.player
        self.assertTrue(player.blind)
        self.assertEqual((player.hp, player.max_hp), (310, 731))
        self.assertEqual(self.policy._low_hp_walk_threshold(player.max_hp), 431)
        healing = next(item for item in board.inventory
                       if item.is_potion and item.sval == 37)
        self.assertEqual(key, "q" + healing.slot, reason)

    def test_below_the_threshold_without_healing_speed_goes_first(self):
        raw = json.loads(self.boards[lethal.B_CURE])
        inventory = [row for row in raw["inventory"]
                     if not (row.get("tval") == 75 and row.get("sval") == 37)]
        self.assertEqual(len(inventory), len(raw["inventory"]) - 1)
        board, key, reason = self.decide_blind_board(
            self._constructed(lethal.B_CURE, inventory=inventory))
        speed = next(item for item in board.inventory
                     if item.is_potion and item.sval == 29)
        self.assertEqual((key, reason), ("q" + speed.slot, unseen_strike.SPEED_REASON))


if __name__ == "__main__":
    unittest.main()
