"""Quest 25 on n1-c life-221 (2026-11-23 05:00:12-05:00:13): INT drained beside a floor restore potion, recorded.

Owner 2026-11-23 「数マス以内なら拾って飲む」: during a quest, on the plan's quiet board, a known restore
potion of a drained ability lying within a few walking steps is walked to, picked up and drunk, and the
plan goes on (quest_plan_base ``floor_restore_key``, FLOOR_RESTORE_MAX_STEPS walking steps).

n1-c life-221 (Magic-Eater Lv39): a shadow demon drained INT 18→17 and WIS at 05:00:11 on [5,1].  The
found Restore Intelligence (sval 43) lay on [7,1], two steps off.  Decisions 61351 and 61359
(``quest25:rest-recharge``) and 61363 (``quest-strategy:hold`` '5') stayed on [5,1]; the potion was
picked up only by the closing sweep at 05:03:48 and drunk in town (tests/test_n1c_221_q25_int_drain_1123_recorded.py).

Recorded: tests/fixtures/n1c-221-q25-floor-restore-1123.json.gz
(tests/extract_n1c_221_q25_floor_restore_1123_fixture.py): the board of decision 61363 and the decision
rows 61351, 61359 and 61363.  The bound is checked on the recorded board of
tests/fixtures/n1c-221-q25-int-drain-1123.json.gz ([1,3], the potions six and more steps off).  Every
decision is the public ``choose_key`` of a fresh policy restoring the battle record through the real path.

DECLARED RECONSTRUCTED: the battle record (phase ``stragglers`` -- after phase 2, the wait on [5,1]; on
main it answers the recorded ``quest-strategy:hold`` '5' -- and ``druj`` for
the far board, the earlier kills, ``ready``, ranged style) and the remembered magic-eater lists, as
tests/test_n1c_220_q25_speed_retry_1122_recorded.py.
DECLARED CONSTRUCTED: the player on [7,1] (the walk's end: the pickup), and the board after the pickup
(the potion carried, the cell's found row removed: the drink).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import quest_plan_base
from hengbot.model import TVAL_POTION
from tests.test_n1c_220_q25_speed_retry_1122_recorded import WALL_PASSER_KILLS, _Replay
from tests.test_n1c_221_q25_int_drain_1123_recorded import board as far_board, with_restore_int

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-221-q25-floor-restore-1123.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

ROWS = {row["decision_sequence"]: row for row in CASE["decisions"]}
RESTS, HOLD = (61351, 61359), 61363
POTION_CELL = (7, 1)
SV_RESTORE_INT = 43
PHASE = "stragglers"
# The reasons by their text (quest_plan_base FLOOR_RESTORE_*): main has no such names.
WALK_REASON = "quest-strategy:floor-restore-walk"
PICKUP_REASON = "quest-strategy:floor-restore-pickup"


def board():
    return copy.deepcopy(CASE["board"])


def on_the_potion(raw):
    """DECLARED CONSTRUCTED: the walk's end, the player on the potion's cell."""
    raw["player"]["y"], raw["player"]["x"] = POTION_CELL
    return raw


def picked_up(raw):
    """DECLARED CONSTRUCTED: after the pickup, the potion carried and the cell's found rows gone."""
    grid = raw["grid_map"]
    for name in ("found_items", "found_item_ids", "found_item_names"):
        grid[name] = [row for row in grid[name] if tuple(row[:2]) != POTION_CELL]
    return with_restore_int(raw)


class TheRecordingTest(unittest.TestCase):
    def test_the_quiet_board_beside_the_potion(self):
        for sequence in RESTS:
            self.assertEqual(ROWS[sequence]["reason"], "quest25:rest-recharge")
        self.assertEqual((ROWS[HOLD]["reason"], ROWS[HOLD]["key"]), (quest_plan_base.HOLD_REASON, "5"))
        raw = board()
        self.assertEqual(raw["turn"], ROWS[HOLD]["turn"])
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (5, 1))
        self.assertEqual(raw["visible_monsters"], [])
        self.assertTrue(raw["player"]["stats"]["int"]["drained"])
        self.assertIn([*POTION_CELL, {"sval": SV_RESTORE_INT}], raw["grid_map"]["found_item_ids"])
        self.assertIn([*POTION_CELL, "知能復活の薬"], raw["grid_map"]["found_item_names"])


class TheFloorRestoreTest(_Replay):
    def decide_on(self, raw, phase=PHASE):
        return self.decide(self.policy(raw, phase, WALL_PASSER_KILLS), raw)

    def test_the_plan_walks_to_the_potion(self):
        self.assertEqual(self.decide_on(board()), ("2", WALK_REASON))

    def test_on_the_cell_it_is_picked_up(self):
        self.assertEqual(self.decide_on(on_the_potion(board())),
                         ("g", PICKUP_REASON))

    def test_once_carried_it_is_drunk(self):
        raw = picked_up(on_the_potion(board()))
        slot = next(item["slot"] for item in raw["inventory"]
                    if (item["tval"], item["sval"]) == (TVAL_POTION, SV_RESTORE_INT))
        self.assertEqual(self.decide_on(raw), ("q" + slot, quest_plan_base.RESTORE_REASON))

    def test_a_potion_beyond_a_few_steps_is_left(self):
        _key, reason = self.decide_on(far_board(), "druj")
        self.assertNotIn(reason, (WALK_REASON,
                                  PICKUP_REASON))


if __name__ == "__main__":
    unittest.main()
