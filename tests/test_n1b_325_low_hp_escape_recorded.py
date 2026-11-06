"""n1-b life-325 (2026-11-06 19:23, 城33階, Lv29): the low-HP escape with a summoner in view.

Owner 2026-11-06: 「HP が低い時、召喚する敵・引き寄せる敵・速い敵が見えていれば、退却の1歩で
済まさずテレポートか帰還を読む。2回目の緊急で町へ戻る判断が付かない点と、壁の隣で召喚の緊急が
消える点も直す。」

Recorded: at turn 2100389 (HP 153/386) the low-HP walk gate turned a seek-loot step into a
Teleportation read (``rd``), the dive's second emergency, without latching the town return.
At 2100397 (HP 155, 13 hostiles in view: the hasted 智天使 summoner, ten hasted jackals, a
キング・コブラ and the TELE_TO セイレーン) the summoner emergency was dropped because a
neighbour touched the wall row y=18, and the walk gate let one ``summoner:retreat`` step
(``6``) through.  The siren pulled the player back; at 2100412 it was blind at HP 27.

Source: tests/fixtures/n1b-325-low-hp-escape-1106.json.gz
(tests/extract_n1b_325_low_hp_escape_fixture.py).  The policy starts on the 2100389 board,
whose replay already reproduces both recorded decisions; the record's dive emergency count
before that read (decision row ``over_extension.dive_emergencies`` = 1) is set on the policy.
Every decision goes through the public ``choose_key``; a test says when it edits a board or
patches a judgment (DECLARED CONSTRUCTED).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-325-low-hp-escape-1106.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

READ, RETREAT = 2100389, 2100397
CHERUB, SIREN, JACKAL, KING_COBRA = 511, 1272, 35, 171
TVAL_SCROLL, SV_TELEPORT, SV_RECALL = 70, 9, 11


def replay(*, until, emergencies=1, change=None):
    """The policy, board and key on ``until``; ``change`` edits that board."""
    boards = [copy.deepcopy(raw) for raw in CASE["boards"] if READ <= raw["turn"] <= until]
    policy = d57.loops.new_policy(dict(CASE, boards=boards), CASE["skill"],
                                  monraces=CASE["monraces"])
    policy._dive_emergencies = emergencies
    for raw in boards:
        if raw["turn"] == until and change is not None:
            change(raw)
        key = d57.loops.decide(policy, raw)
        if raw["turn"] == until:
            return policy, raw, key
        policy.confirm_key_posted(key)
    raise AssertionError(until)



class RecordedRowsTest(unittest.TestCase):
    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        self.assertEqual(recorded[READ], ("emergency:teleport", "rd"))
        self.assertEqual(recorded[RETREAT], ("summoner:retreat", "6"))
        rows = {row["turn"]: row for row in CASE["decisions"]}
        self.assertEqual(rows[READ]["over_extension"]["dive_emergencies"], 1)
        self.assertEqual(rows[RETREAT]["over_extension"]["dive_emergencies"], 2)
        self.assertIsNone(rows[RETREAT]["over_extension"]["last_return_trigger"])
        board = next(raw for raw in CASE["boards"] if raw["turn"] == RETREAT)
        self.assertEqual((board["player"]["hp"], board["player"]["max_hp"]), (155, 386))
        self.assertEqual(len(board["visible_monsters"]), 13)


class SecondEmergencyReturnTest(unittest.TestCase):
    def test_the_walk_gate_read_latches_the_town_return(self):
        policy, _raw, key = replay(until=READ)
        self.assertEqual((key, policy.last_reason), ("rd", "emergency:teleport"))
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, "emergency-repeat")
        self.assertEqual(policy._survival_return_trigger, "emergency-repeat")

    def test_control_the_first_emergency_latches_no_return(self):
        policy, _raw, key = replay(until=READ, emergencies=0)
        self.assertEqual((key, policy.last_reason), ("rd", "emergency:teleport"))
        self.assertFalse(policy._returning_to_town)
        self.assertIsNone(policy._last_return_trigger)


if __name__ == "__main__":
    unittest.main()
