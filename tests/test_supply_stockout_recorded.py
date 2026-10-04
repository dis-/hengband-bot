"""October 5 CCW stockout board, with explicit constructed retry controls."""
import tests  # noqa: F401 -- isolate all runtime writes
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import (
    DUNGEON_YEEK_CAVE, STORE_ALCHEMIST, STORE_BLACK, STORE_MAGIC, STORE_TEMPLE,
    SV_DIGGING_SHOVEL, SV_POTION_CURE_CRITICAL, SV_SCROLL_DETECT_TREASURE,
    SV_SCROLL_REMOVE_CURSE, TVAL_DIGGING, TVAL_POTION, TVAL_SCROLL, StoreState, parse_snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_supply import supply_ledger_observer_memo
from policy_fixtures import item, store_item, seed_confirmed_loadout

FIXTURE = Path(__file__).parent / 'fixtures/stockout-20261005.json.gz'
SHA256 = '61e97b9ae7849ad684dfced9dead285002f2ecffb2e4a5334e3cee446164e797'


class SupplyStockoutRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(FIXTURE.read_bytes()))

    def scene(self):
        board = parse_snapshot(self.pin['board'])
        policy = HengbotPolicy()
        policy.prime(board)
        # Constructed policy context: the recorded decision has no checkpoint.
        # Its recall destination is Orc Cave 23; the worn loadout is complete,
        # Home work resolved, and the terminal restock pass already exhausted.
        policy._target_dungeon_id = 3
        seed_confirmed_loadout(policy, board)
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        self.exhaust_suppliers(policy, board)
        return policy, board

    def exhaust_suppliers(self, policy, board):
        policy._target_dungeon_id = 3
        policy._home_knowledge_current = True
        policy._equipment_catalog.home_scan_complete = True
        policy._town_store_attempted.update({
            STORE_TEMPLE: board.turn, STORE_ALCHEMIST: board.turn,
            STORE_BLACK: board.turn,
        })
        policy._town_restock_suppressed = True

    def kit(self, board):
        return replace(board, inventory=(*board.inventory,
            item('n', TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE),
            item('o', TVAL_DIGGING, SV_DIGGING_SHOVEL)))

    def test_recorded_terminal_now_starts_one_mining_run(self):
        policy, board = self.scene()
        recorded = self.pin['decision']
        self.assertEqual(recorded['time'], '2026-10-05T01:30:57+0900')
        self.assertEqual(recorded['reason'], 'town:blocked:departure-unsatisfiable')
        self.assertEqual(recorded['departure_block']['failed'], ['cure_critical_ready'])
        self.assertEqual(policy._departure_block_state(board)['failed'], ['cure_critical_ready'])
        self.assertEqual(policy.procurement_requirements(board), recorded['procurement_requirements'])
        self.assertEqual(policy._town_special_key(board), '5')
        self.assertEqual(policy.last_reason, 'town:supply-stockout-mining')
        self.assertEqual((policy._fundraising_mode, policy._planned_mining_runs), ('prepare', 1))
        self.assertEqual(policy._fundraising_gold_target(), 27_783)
        self.assertFalse(policy._town_restock_suppressed)
        # The existing gold set-end must not cancel a time-pass above 20,000.
        policy._end_fundraising_set_at_gold_target(board)
        self.assertEqual(policy._fundraising_mode, 'prepare')
        kit = self.kit(board)
        policy._town_special_key(kit)
        self.assertEqual(policy._fundraising_mode, 'mine')
        self.assertTrue(policy._fundraising_departure_ready(kit))
        self.assertFalse(policy._cure_critical_ready(kit))
        self.assertFalse(all(policy._recall_town_departure_conjuncts(kit).values()))
        self.assertFalse(policy._dungeon_entry_allowed(kit, via_recall=True, destination_depth=50))

    def test_three_completed_cycles_retry_stores_then_stop(self):
        policy, board = self.scene()
        for cycle in range(3):
            self.exhaust_suppliers(policy, board)
            self.assertEqual(policy._town_special_key(board), '5')
            self.assertEqual(policy.last_reason, 'town:supply-stockout-mining')
            policy._fundraising_mode = 'mine'
            mining = replace(board, floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
                             turn=board.turn + 1)
            policy._observe(mining)
            board = replace(board, turn=board.turn + 2)
            policy._observe(board)
            self.assertEqual(policy._supply_stockout_cycles, cycle + 1)
            self.assertEqual(policy._mining_runs_completed, 1)
            self.assertFalse(policy._town_store_attempted)
            policy._town_special_key(board)
            self.assertIsNone(policy._fundraising_mode)
            self.assertIsNone(policy._supply_stockout_gold_target)
            # Counter survives restoration and the fresh-town reset.
            policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.exhaust_suppliers(policy, board)
        self.assertEqual(policy._town_special_key(board), '5')
        self.assertEqual(policy.last_reason, 'town:blocked:departure-unsatisfiable')
        self.assertIsNone(policy._fundraising_mode)

    def test_another_failed_conjunct_keeps_existing_terminal(self):
        policy, board = self.scene()
        board = replace(board, player=replace(board.player, hp=board.player.hp - 1))
        self.assertIn('hp_full', policy._departure_block_state(board)['failed'])
        self.assertIsNone(policy._supply_stockout_mining_key(board))
        self.assertEqual(policy._town_special_key(board), 'R&\r')
        self.assertEqual(policy.last_reason, 'town:recover')
        self.assertIsNone(policy._fundraising_mode)

    def test_zero_recall_and_cure_stockouts_share_the_one_run_path(self):
        policy, board = self.scene()
        board = replace(board, inventory=tuple(
            gear for gear in board.inventory if not gear.is_recall_scroll))
        self.assertEqual(set(policy._departure_block_state(board)['failed']),
                         {'recall_departure_ready', 'cure_critical_ready'})
        self.assertEqual(policy._town_special_key(board), '5')
        self.assertEqual(policy.last_reason, 'town:supply-stockout-mining')
        policy._fundraising_mode = 'mine'
        self.assertFalse(policy._dungeon_entry_allowed(
            board, via_recall=True, destination_depth=23))

    def test_unaffordable_stock_does_not_start_stockout_timepass(self):
        policy, board = self.scene()
        ware = store_item('a', TVAL_POTION, SV_POTION_CURE_CRITICAL, price=100_000)
        policy._town_supplier_stock[STORE_TEMPLE] = StoreState(STORE_TEMPLE, [ware])
        self.assertEqual(policy.procurement_requirements(board)[0]['blocked_reason'],
                         'no-actionable-supplier')
        self.assertIsNone(policy._supply_stockout_mining_key(board))
        self.assertIsNone(policy._fundraising_mode)

    def test_delta_gold_target_even_with_known_treasure_and_checkpoint(self):
        policy, board = self.scene()
        policy._town_special_key(board)
        policy._fundraising_mode = 'mine'
        policy._known_treasure.add(board.player.position)
        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertFalse(policy._fundraising_facts(board).objective_achieved)
        # Preparation can rebuild its partial plan; this remains one run.
        policy._planned_mining_runs = None
        self.assertEqual(policy._effective_mining_run_target(), 1)
        earned = replace(board, player=replace(board.player, gold=27_783))
        facts = policy._fundraising_facts(earned)
        self.assertTrue(facts.objective_achieved)
        self.assertFalse(facts.known_treasure)

    def test_old_checkpoints_default_new_attributes(self):
        policy, board = self.scene()
        del policy._supply_stockout_cycles
        del policy._supply_stockout_gold_target
        policy = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertEqual(policy._supply_stockout_cycles, 0)
        self.assertIsNone(policy._supply_stockout_gold_target)
        self.assertEqual(policy._town_special_key(board), '5')

    def test_home_remove_curse_deferral_changes_memoized_obtainability(self):
        policy, board = self.scene()
        board = replace(board, equipment=tuple(
            replace(gear, is_cursed=True) if gear.slot == 'main_hand' else gear
            for gear in board.equipment))
        scroll = item('a', TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        policy.consume_home_knowledge((scroll,))
        policy._town_store_attempted[STORE_MAGIC] = board.turn
        with supply_ledger_observer_memo():
            first = policy._supply_ledger(board, 23)['remove-curse']
            self.assertTrue(first.obtainable)
            policy._deferred_home_items.add(policy._item_signature(scroll))
            deferred = policy._supply_ledger(board, 23)['remove-curse']
            self.assertFalse(deferred.obtainable)
            policy._deferred_home_items.clear()
            self.assertEqual(policy._supply_ledger(board, 23)['remove-curse'], first)


if __name__ == '__main__':
    unittest.main()
