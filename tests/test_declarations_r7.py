"""Recorded declaration gap classes, reduced to their producer handoffs."""

import unittest
import tests  # noqa: F401
from dataclasses import replace
from types import SimpleNamespace

from hengbot.claim_register import observe
from hengbot.model import (DUNGEON_ANGBAND, PLAYER_CLASS_WARRIOR, Position,
                           TVAL_DIGGING,
                           TVAL_SCROLL, TVAL_FOOD, TVAL_FLASK, TVAL_POTION,
                           SV_SCROLL_WORD_OF_RECALL, SV_FLASK_OIL)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit
from hengbot.home_errand import HomeErrandRequest
from test_policy import (Snapshot, StoreState, STORE_HOME, TVAL_LITE,
                         SV_LITE_LANTERN, grid, item, player)
from hengbot.policy_constants import CHARACTER_DUMP_MACRO, REST_MACRO
from policy_fixtures import set_completed_equipment_optimization


def bind(policy, family, key):
    claim = policy._claim_register.declare(
        family, observe(("r7-producer",), 8, "store-operation"))
    policy._record_execution_declaration(claim, key, policy.last_reason)
    return policy._claim_register.current.execution


def town_board(*, hurt=False):
    return Snapshot(
        player(10, 10, hp=200 if hurt else 255, max_hp=255,
               gold=2000, class_id=PLAYER_CLASS_WARRIOR),
        {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
        width=198, height=66, town_flag=True,
        inventory=[
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=9),
            item("t", TVAL_SCROLL, 9, count=9),
            item("f", TVAL_FOOD, 35, count=9),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=9, fuel=500),
            item("c", TVAL_POTION, 36, count=9),
        ],
        equipment=[item("g", TVAL_LITE, SV_LITE_LANTERN,
                        fuel=5000, is_equipment=True)],
        recall_dungeon_id=DUNGEON_ANGBAND, angband_recall_unlocked=True,
    )


class SurvivalRows(unittest.TestCase):
    def test_stuck_sequence_2_recovery_has_final_survival_offer(self):
        policy = HengbotPolicy()
        board = town_board(hurt=True)
        key = policy._town_special_key(board)
        self.assertEqual((key, policy.last_reason), (REST_MACRO, "town:recover"))
        declaration = bind(policy, "survival", key)
        self.assertEqual((declaration.state, declaration.next_step),
                         ("acting", "player.rest"))


class BookkeepingRows(unittest.TestCase):
    def test_tour_departure_dump_binds_bookkeeping(self):
        policy = HengbotPolicy()
        board = town_board()
        set_completed_equipment_optimization(policy)
        policy._deepest_level = 8
        policy._target_dungeon_id = DUNGEON_ANGBAND
        key = policy._town_special_key(board)
        self.assertEqual((key, policy.last_reason),
                         (CHARACTER_DUMP_MACRO, "town:character-dump"))
        declaration = bind(policy, "bookkeeping", key)
        self.assertEqual((declaration.producer, declaration.next_step),
                         ("bookkeeping", "character.dump-before-departure"))


if __name__ == "__main__":
    unittest.main()
