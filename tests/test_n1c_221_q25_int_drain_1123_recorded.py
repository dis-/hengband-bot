"""Quest 25 on n1-c life-221 (2026-11-23 05:00-05:03): INT drained, the quest fought on, recorded.

QUEST_25 ``consumable_plan.other`` 「経験値復活の薬と腕力復活の薬を2本ずつ持参し、敵がいない時に下がっていれば
飲む」 (quest_plan_base ``_restore`` on the plan's quiet board) and the town rule ``_stat_restore_quaff_key``
(a drained ability, its restore potion carried, no hostile: quaff); owner 2026-11-08
(me-int-loadout) 「魔法成功率は生存に貢献する」: the Magic-Eater's absorbed powers fail by INT.

n1-c life-221 (Magic-Eater Lv39):

 * Decision 61207 (05:00:00, [7,1]): 「知能復活の薬がある。」 -- a Potion of Restore Intelligence on the
   floor under the player, not carried (the plan's hold does not pick up; the closing sweep does).
 * Decisions 61340 / 61345 (05:00:11): a shadow demon's touches, 「ひどく愚かになった気がする。」 and
   「ひどく無知になった気がする。」: INT 18→17 (index 15→14), WIS drained.
 * Decisions 61828 and 62859 (quiet boards, ``quest25:rest-recharge``): the quest went on with INT
   drained (absorbed-power fail rates raised) until 63089 (05:03:48), when the closing sweep picked
   the potion up; it was drunk in town (``restore:quaff-int``, 05:04:17).

The fix: quest_plan_base ``_restore`` drinks, on the plan's quiet board, the carried restore potion of
every drained ability (not only the plan's Restore Strength / Restore Life Levels).  Whether the plan
should also step off its walk to pick a floor restore potion up mid-quest is an owner question; this
test pins only the carried potion.

Recorded: tests/fixtures/n1c-221-q25-int-drain-1123.json.gz
(tests/extract_n1c_221_q25_int_drain_1123_fixture.py): the board of decision 62859 ([1,3], no hostile
in view, the Druj sensed far off; INT and WIS drained) and the decision rows above.  Every decision is
the public ``choose_key`` of a fresh policy restoring the battle record through the real path.

DECLARED RECONSTRUCTED: the battle record (phase ``druj``, the earlier phases' kills, ``ready``, ranged
style) and the remembered magic-eater lists, as tests/test_n1c_220_q25_speed_retry_1122_recorded.py.
DECLARED CONSTRUCTED: one Potion of Restore Intelligence carried (inserted after the Restore Strength
row, the later rows relettered): the potion the sweep picked up, carried before the quiet board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.model import SV_POTION_RESTORE_INT, SV_POTION_RESTORE_STR, TVAL_POTION
from hengbot import quest_plan_base
from tests.test_n1c_220_q25_speed_retry_1122_recorded import WALL_PASSER_KILLS, _Replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-221-q25-int-drain-1123.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

ROWS = {row["decision_sequence"]: row for row in CASE["decisions"]}
FLOOR_POTION, DRAIN_INT, DRAIN_WIS, FIRST_REST, QUIET_REST, SWEEP_PICKUP = (
    61207, 61340, 61345, 61828, 62859, 63089)
PHASE = "druj"


def board():
    return copy.deepcopy(CASE["board"])


def with_restore_int(raw):
    """DECLARED CONSTRUCTED: the Potion of Restore Intelligence carried after the Restore Strength row."""
    inventory = raw["inventory"]
    index = next(i for i, item in enumerate(inventory)
                 if (item["tval"], item["sval"]) == (TVAL_POTION, SV_POTION_RESTORE_STR))
    potion = copy.deepcopy(inventory[index])
    potion.update(sval=SV_POTION_RESTORE_INT, count=1, name="知能復活の薬", inscription="")
    inventory.insert(index + 1, potion)
    for slot, item in enumerate(inventory):
        item["slot"] = chr(ord("a") + slot)
    return raw


class TheRecordingTest(unittest.TestCase):
    def test_the_drain_and_the_floor_potion(self):
        self.assertIn("知能復活の薬がある。", ROWS[FLOOR_POTION]["messages"][0])
        self.assertIn("ひどく愚かになった気がする。", " ".join(ROWS[DRAIN_INT]["messages"]))
        self.assertIn("ひどく無知になった気がする。", " ".join(ROWS[DRAIN_WIS]["messages"]))
        self.assertIn("知能復活の薬(g)を拾った。", " ".join(ROWS[SWEEP_PICKUP]["messages"]))
        for sequence in (FIRST_REST, QUIET_REST):
            self.assertEqual(ROWS[sequence]["reason"], "quest25:rest-recharge")
        raw = board()
        self.assertEqual(raw["turn"], ROWS[QUIET_REST]["turn"])
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (1, 3))
        self.assertEqual(raw["visible_monsters"], [])
        stats = raw["player"]["stats"]
        self.assertTrue(stats["int"]["drained"] and stats["wis"]["drained"])
        self.assertEqual((stats["int"]["use"], stats["int"]["top"]), (17, 18))
        self.assertFalse(any((item["tval"], item["sval"]) == (TVAL_POTION, SV_POTION_RESTORE_INT)
                             for item in raw["inventory"]))


class TheQuietBoardTest(_Replay):
    def test_a_carried_restore_intelligence_is_drunk(self):
        raw = with_restore_int(board())
        policy = self.policy(raw, PHASE, WALL_PASSER_KILLS)
        self.assertEqual(self.decide(policy, raw), ("qf", quest_plan_base.RESTORE_REASON))

    def test_without_the_potion_the_plan_goes_on(self):
        raw = board()
        policy = self.policy(raw, PHASE, WALL_PASSER_KILLS)
        key, reason = self.decide(policy, raw)
        self.assertNotEqual(reason, quest_plan_base.RESTORE_REASON)
        self.assertFalse(key.startswith("q"))


if __name__ == "__main__":
    unittest.main()
