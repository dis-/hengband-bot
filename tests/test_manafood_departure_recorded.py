"""Recorded recovery board and decision-derived departure food pins.

The retained state file begins at turn 8750123: no raw town board survives
for 15:59-16:11. Departure walls are explicitly constructed from the
recorded 3/15 requirement; Home stock and other readiness are constructed.
Recovery uses the verbatim 16:36:11 board on a fresh policy, no live files.
"""
import tests  # noqa: F401
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import (
    DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE, Snapshot, Position, STORE_MAGIC,
    TVAL_WAND, SV_STAFF_IDENTIFY, TVAL_STAFF, parse_snapshot,
    TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import FOOD_TYPE_MANA, EAT_KEY, UP_STAIRS_KEY
from policy_fixtures import grid, item, player


class ManafoodRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parent / 'fixtures/manafood-20261004.json.gz'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == (
            'efc038dc6a9851951742ff004e992be1b569b878a935c1e67f01e79041cfaa3d'
        )
        cls.fixture = json.loads(gzip.decompress(path.read_bytes()))

    def recovery(self):
        board = parse_snapshot(self.fixture['boards']['8795606']['raw'])
        policy = HengbotPolicy()
        policy._observe(board)
        return policy, board

    def departure(self):
        # DECLARED CONSTRUCTION: 3 eligible carried charges, known Home stock.
        row = next(r['raw'] for r in self.fixture['decisions'] if r['row'] == 576)
        food = next(r for r in row['procurement_requirements'] if r['item'] == 'Device charges for food')
        self.assertEqual((food['current'], food['target']), (3, 15))
        board = Snapshot(
            player(10, 10, class_id=0, food_type=FOOD_TYPE_MANA),
            {Position(10, 10): grid(10, 10)}, [],
            inventory=[item('a', TVAL_WAND, 1, charges=food['current'])],
            town_flag=True, turn=row['turn'],
        )
        policy = HengbotPolicy()
        policy.consume_home_knowledge((item('b', TVAL_WAND, 2, charges=30),))
        policy._target_dungeon_id = 3
        board = replace(board, inventory=[*board.inventory,
                        item('r', TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=20)])
        return policy, board

    def test_recorded_recovery_reads_recall(self):
        policy, board = self.recovery()
        self.assertEqual((board.turn, board.floor_key, board.player.food_state),
                         (8795606, (3, 23, 0), 'hungry'))
        self.assertEqual(policy._count_mana_food_uses(board), 0)
        key = policy._mana_food_survival_override_key(board)
        self.assertEqual(policy.last_reason, 'return:recall')
        self.assertEqual(key, 'r' + policy._find_recall_scroll(board).slot)
        self.assertTrue(policy._returning_to_town)

    def test_recorded_recovery_public_decision_after_observed_skills(self):
        # DECLARED WALL: restart's observed ~f row at the same parked turn;
        # this removes only bookkeeping, never a survival/return predicate.
        policy = HengbotPolicy()
        board = parse_snapshot(self.fixture['boards']['8795606']['raw'])
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, 'periodic:skill-exp-knowledge')
        policy.consume_skill_knowledge(self.fixture['recovery_knowledge']['raw'])
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, 'return:recall')

    def test_recovery_continues_countdown_then_absorbs_found_charge(self):
        policy, board = self.recovery()
        recalling = replace(board, player=replace(board.player, recalling=True))
        policy._mana_food_survival_override_key(recalling)
        self.assertTrue(policy.last_reason.startswith('return:'))
        found = replace(recalling, inventory=[*board.inventory, item('z', TVAL_WAND, 1, charges=1)])
        self.assertEqual(policy._mana_food_survival_override_key(found), EAT_KEY + 'z')
        self.assertEqual(policy.last_reason, 'survival:mana-absorb')

    def test_recovery_without_recall_ascends(self):
        policy, board = self.recovery()
        pos = board.player.position
        board = replace(board, inventory=[i for i in board.inventory if not i.is_recall_scroll],
                        grids={pos: grid(pos.y, pos.x, upstairs=True)})
        self.assertEqual(policy._mana_food_survival_override_key(board), UP_STAIRS_KEY)
        self.assertEqual(policy.last_reason, 'return:ascend')

    def test_no_return_route_retains_terminal(self):
        policy, board = self.recovery()
        pos = board.player.position
        board = replace(board, inventory=[],
                        player=replace(board.player, blind=True, confused=True),
                        grids={pos: grid(pos.y, pos.x)})
        policy = HengbotPolicy()  # No recorded map-memory routes on this wall.
        policy._mana_food_survival_override_key(board)
        self.assertEqual(policy.last_reason, 'town:blocked:survival-mana-no-charges')

    def test_recorded_departure_home_stock_cannot_satisfy_food_leaf(self):
        policy, board = self.departure()
        self.assertEqual(policy._count_mana_food_uses(board), 3)
        self.assertFalse(policy._food_ready(board))
        self.assertFalse(policy._recall_town_departure_conjuncts(board)['food_ready'])
        self.assertEqual(policy._count_mana_food_devices(board), 1)
        # Same carried shortage after a safe target switch / prepare latch.
        for mode in ('prepare', 'mine', 'scavenge'):
            policy._fundraising_mode = mode
            self.assertFalse(policy._recall_town_departure_conjuncts(board)['food_ready'])
        policy._target_dungeon_id = 12
        self.assertFalse(policy._recall_town_departure_conjuncts(board)['food_ready'])

    def test_suppressed_walk_in_still_requires_carried_food(self):
        policy, board = self.departure()
        policy._town_restock_suppressed = True
        self.assertTrue(policy._descent_is_blocked(board))
        self.assertIn(policy._descent_refusal_reason,
                      {'food-departure-shortage', 'recall-departure-shortage'})

    def test_withdrawn_charges_satisfy_departure(self):
        policy, board = self.departure()
        board = replace(board, inventory=[item('a', TVAL_WAND, 1, count=2, charges=8)])
        self.assertTrue(policy._recall_town_departure_conjuncts(board)['food_ready'])

    def test_first_run_food_waiver_never_waives_recall_stock(self):
        policy, board = self.departure()
        policy._fundraising_mode = 'scavenge'
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._fundraising_runs_started = 0
        policy.consume_home_knowledge(())
        policy._town_store_attempted[STORE_MAGIC] = board.turn
        board = replace(board, inventory=[])
        self.assertTrue(policy._departure_food_ready(board))
        self.assertTrue(policy._descent_is_blocked(board))
        self.assertEqual(policy._descent_refusal_reason, 'recall-departure-shortage')

    def test_first_run_waiver_requires_exhausted_home_and_shop(self):
        policy, board = self.departure()
        board = replace(board, inventory=[])
        policy._fundraising_mode = 'scavenge'
        policy._target_dungeon_id = DUNGEON_YEEK_CAVE
        policy._fundraising_runs_started = 0
        policy.consume_home_knowledge(())
        self.assertFalse(policy._departure_food_ready(board))
        policy._town_store_attempted[STORE_MAGIC] = board.turn
        self.assertTrue(policy._departure_food_ready(board))
        hungry = replace(board, player=replace(board.player, food_state='hungry'))
        self.assertFalse(policy._departure_food_ready(hungry))
        policy._fundraising_runs_started = 1
        self.assertFalse(policy._departure_food_ready(board))
        policy._fundraising_runs_started = 0
        policy.consume_home_knowledge((item('c', TVAL_WAND, 2, charges=30),))
        self.assertFalse(policy._departure_food_ready(board))

    def test_identify_reserve_is_preserved(self):
        policy, board = self.departure()
        board = replace(board, inventory=[item('a', TVAL_STAFF, SV_STAFF_IDENTIFY, charges=15)])
        self.assertLess(policy._count_mana_food_uses(board), 15)
        self.assertFalse(policy._food_ready(board))

    def test_armed_town_recall_is_not_cancelled_for_food_alone(self):
        policy, board = self.departure()
        board = replace(board, player=replace(board.player, recalling=True),
                        recall_dungeon_id=3)
        policy._startup_town_recall = True
        policy._pending_recall_dungeon_id = 3
        # The food gate still refuses a fresh departure on the same board.
        self.assertFalse(policy._recall_town_departure_conjuncts(board)['food_ready'])
        self.assertNotIn('food-shortage', policy._recall_unready_blockers(board, 3))
        self.assertIsNone(policy._town_cancel_unsafe_recall_key(board))

    def test_repetition_recall_requires_carried_food(self):
        policy, board = self.departure()
        policy._town_blocked_reason = 'repetition'
        policy._target_dungeon_id = DUNGEON_ANGBAND
        board = replace(board, angband_recall_unlocked=True,
                        entered_dungeon_ids=(DUNGEON_ANGBAND,),
                        recall_dungeon_id=DUNGEON_ANGBAND,
                        dungeon_recall_depths={DUNGEON_ANGBAND: 1})
        key = policy._town_blocked_key(board)
        self.assertFalse(key.startswith('r'))
        stocked = replace(board, inventory=[*board.inventory,
                          item('c', TVAL_WAND, 2, count=2, charges=8)])
        key = policy._town_blocked_key(stocked)
        self.assertTrue(key.startswith('r'))
        self.assertEqual(policy.last_reason, 'town:repetition-depart:recall')


if __name__ == '__main__':
    unittest.main()
