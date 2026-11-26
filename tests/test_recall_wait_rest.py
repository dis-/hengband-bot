import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest
from dataclasses import replace

from policy_fixtures import grid, hostile, item, player, set_completed_equipment_optimization

from hengbot.model import (
    DUNGEON_ANGBAND, PLAYER_CLASS_WARRIOR, SV_FLASK_OIL, SV_LITE_LANTERN, SV_SCROLL_WORD_OF_RECALL,
    TVAL_FLASK, TVAL_FOOD, TVAL_LITE, TVAL_POTION, TVAL_SCROLL, Position, Snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import REST_MACRO, WAIT_KEY


class DungeonRecallWaitRestTest(unittest.TestCase):
    """return:wait-recall: one rest until the recall fires when calm (owner 2026-11-26)."""

    FLOOR = (1, 5, 0)

    def _snap(self, **player_kwargs):
        kwargs = dict(food=6000, word_recall=12)
        kwargs.update(player_kwargs)
        return Snapshot(
            player(10, 10, **kwargs),
            {Position(10, 10): grid(10, 10)},
            [],
            floor_key=self.FLOOR,
        )

    def test_calm_wait_rests_until_the_recall_fires(self):
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(self._snap()), REST_MACRO)
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_hungry_still_rests(self):
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(self._snap(food=1500)), REST_MACRO)
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_sensed_hostile_nearby_keeps_the_one_turn_wait(self):
        # A known low-level monster sensed out of view moves without disturbing a rest
        # (monster-move.cpp:458): within sight range the wait stays one turn a decision.
        snap = replace(self._snap(), detected_monsters=[hostile(1, 10, 25, distance=15, asleep=True)])
        policy = HengbotPolicy()
        key = policy.choose_key(snap)
        self.assertEqual(key, WAIT_KEY)
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_far_sensed_hostile_still_rests(self):
        snap = replace(self._snap(), detected_monsters=[hostile(1, 10, 60, distance=50, asleep=True)])
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), REST_MACRO)
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_blind_is_not_rested_by_the_recall_wait(self):
        # Blindness has its own rest until sight (blind:wait-sight); the recall wait sends none.
        policy = HengbotPolicy()
        key = policy.choose_key(self._snap(blind=True))
        self.assertNotEqual((key, policy.last_reason), (REST_MACRO, "return:wait-recall"))

    def test_poisoned_keeps_the_one_turn_wait(self):
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(self._snap(poisoned=True)), WAIT_KEY)
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_a_hit_since_the_last_board_keeps_the_one_turn_wait(self):
        policy = HengbotPolicy()
        policy.choose_key(self._snap(hp=20, max_hp=20))
        self.assertEqual(policy.choose_key(self._snap(hp=15, max_hp=20)), WAIT_KEY)
        self.assertEqual(policy.last_reason, "return:wait-recall")

    def test_finale_floor_never_rests(self):
        # Owner 2026-11-21 (LOCKED) 「99F 100Fでの休憩は許可していない」.
        snap = replace(self._snap(), floor_key=(DUNGEON_ANGBAND, 99, 0))
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), WAIT_KEY)
        self.assertEqual(policy.last_reason, "return:wait-recall")


class TownRecallWaitRestTest(unittest.TestCase):
    """town:wait-recall: the same rest in town, never on an entrance."""

    def _town(self, *, here=None, monsters=()):
        inv = [
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=9),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=9),
        ]
        snap = Snapshot(
            player(10, 10, hp=255, max_hp=255, gold=2000, class_id=PLAYER_CLASS_WARRIOR,
                   word_recall=12),
            {Position(10, 10): here or grid(10, 10),
             Position(10, 11): grid(10, 11), Position(11, 10): grid(11, 10)},
            list(monsters),
            floor_key=(0, 0, 0),
            width=198,
            height=66,
            town_flag=True,
            inventory=inv,
            equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True)],
            recall_dungeon_id=DUNGEON_ANGBAND,
            recall_depth=23,
            angband_recall_unlocked=True,
        )
        pol = HengbotPolicy()
        set_completed_equipment_optimization(pol)
        pol._deepest_level = 23
        pol._target_dungeon_id = DUNGEON_ANGBAND
        pol._char_dump_done_this_visit = True
        return pol, snap

    def test_calm_town_wait_rests(self):
        pol, snap = self._town()
        self.assertEqual(pol.choose_key(snap), REST_MACRO)
        self.assertEqual(pol.last_reason, "town:wait-recall")

    def test_town_wait_with_a_townsperson_in_view_holds_one_turn(self):
        pol, snap = self._town(monsters=[hostile(1, 10, 14, distance=4)])
        self.assertEqual(pol.choose_key(snap), WAIT_KEY)
        self.assertEqual(pol.last_reason, "town:wait-recall")

    def test_no_rest_on_a_store_entrance(self):
        # The wait on a building door stays the one-turn hold, which the entrance guard turns
        # into a step off the door (a rest would pass that guard and stand on the door).
        pol, snap = self._town(here=grid(10, 10, building_type=1, building_special=0))
        self.assertEqual(pol.choose_key(snap), "6")
        self.assertEqual(pol.last_reason, "town:entrance-step-off:town:wait-recall")


if __name__ == "__main__":
    unittest.main()
