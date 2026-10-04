"""October 4 curse/procurement/mining incident pins and explicit controls."""
import tests  # noqa: F401
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest
import copy

from hengbot.model import (
    STORE_ALCHEMIST, STORE_BLACK, STORE_HOME, STORE_MAGIC, STORE_TEMPLE, StoreState,
    SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE, TVAL_SCROLL,
    SV_POTION_SPEED, TVAL_POTION,
    _parse_items, parse_snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import MINING_THREAT_FREE_LIMIT, STUCK_ESCAPE_LIMIT
from hengbot.protocol import snapshot_protocol_version
from policy_fixtures import item, store_item
import test_input_executor as executor_fixture
from hengbot.input_executor import OperationExecutor, Operation

FIXTURE = Path(__file__).parent / 'fixtures/curse-priority-20261004.json.gz'
SHA256 = '36e551ef1ee3d37da716de8d5e4191390b9989aa450376bcb7cd5741ced91a8f'


class CursePriorityRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        with gzip.open(FIXTURE, 'rt', encoding='utf-8') as stream:
            cls.pins = json.load(stream)

    def board(self, label):
        return parse_snapshot(self.pins[label]['data'])

    def policy(self, board, home=False):
        policy = HengbotPolicy()
        policy.prime(board)
        if home:
            raw = self.pins['home']['data']
            policy.consume_home_knowledge(tuple(_parse_items(
                raw['knowledge']['items'], protocol=snapshot_protocol_version(raw))))
        return policy

    def test_recorded_curse_onset_and_departure_block_are_equipped(self):
        before = self.pins['9002633']['data']['equipment']
        after = self.pins['9018634']['data']['equipment']
        self.assertFalse(next(it for it in before if it['slot'] == 'main_hand')['is_cursed'])
        self.assertTrue(next(it for it in after if it['slot'] == 'main_hand')['is_cursed'])
        board = self.board('blocked')
        policy = self.policy(board)
        self.assertTrue(next(it for it in board.equipment if it.slot == 'main_hand').is_cursed)
        self.assertFalse(policy._combat_weapon_ready(board))
        self.assertIn('remove-curse', policy._supply_ledger(board, 23))
        self.assertFalse(policy._town_departure_conjuncts(board)['remove_curse_ready'])

    def test_recorded_home_has_normal_scroll_and_owns_cure_before_shopping(self):
        board = self.board('blocked')
        policy = self.policy(board, home=True)
        reserve = next(it for it in policy._home_knowledge_items
                       if it.tval == TVAL_SCROLL and it.sval == SV_SCROLL_REMOVE_CURSE)
        # Typed source data corrects the provisional *Remove Curse* claim.
        self.assertEqual(reserve.sval, SV_SCROLL_REMOVE_CURSE)
        policy._bind_home_star_remove_curse_withdrawal(board)
        self.assertEqual(policy._home_pending_item, policy._item_signature(reserve))
        self.assertEqual(policy._home_pending_quantity, 1)
        status = policy._supply_ledger(board, 23)['remove-curse']
        self.assertEqual((status.count, status.required_departure, status.stores), (0, 1, (STORE_HOME,)))
        needs = policy._town_need_candidates(board)
        self.assertIn((STORE_HOME, 'home-star-remove-curse-use'),
                      {(need.store_type, need.category) for need in needs})
        self.assertEqual(policy._derived_home_visit_request(board).item_identity,
                         policy._item_signature(reserve))
        self.assertIsNotNone(policy._shopping_approach_step(
            board, STORE_HOME, requester='store-router'))
        home_position = next(pos for pos, cell in board.grids.items()
                             if cell.store_number == STORE_HOME)
        entrance = replace(board, player=replace(board.player, position=home_position))
        # Constructed UI control: a 26-row Home page addresses recorded slot 20
        # as u. The normal scroll must use the real atomic withdrawal controller.
        policy._home_page_size = 26
        self.assertEqual(policy._atomic_home_withdraw_key(entrance, home_position), '5pu\x1b')
        self.assertEqual(policy._home_atomic_withdraw_pending[0], policy._item_signature(reserve))
        # Constructed surplus-gold shelf can offer an optional strong reserve;
        # it must not bypass the recorded normal scroll already in Home.
        ware = store_item('a', TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, price=100)
        shop = replace(board, player=replace(board.player, gold=20000),
                       store=StoreState(STORE_TEMPLE, [ware]))
        shopper = self.policy(shop, home=True)
        self.assertEqual(shopper._affordable_star_remove_curse(shop), ware)
        self.assertIsNone(shopper._next_purchase(shop))

    def test_home_withdrawn_scroll_is_read_and_observed_cure_releases_need(self):
        board = self.board('town')
        policy = self.policy(board, home=True)
        reserve = next(it for it in policy._home_knowledge_items
                       if it.tval == TVAL_SCROLL and it.sval == SV_SCROLL_REMOVE_CURSE)
        carried = replace(reserve, slot='z')
        gained = replace(board, inventory=(*board.inventory, carried))
        self.assertEqual(policy._town_remove_curse_key(gained), 'rz')
        # Constructed control: keep the existing strong-first carried choice.
        both = replace(gained, inventory=(*gained.inventory,
                       item('y', TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE)))
        self.assertEqual(self.policy(both)._town_remove_curse_key(both), 'ry')
        cured = replace(board, equipment=tuple(replace(it, is_cursed=False) for it in board.equipment))
        policy._observe_remove_curse(cured)
        self.assertIsNone(policy._remove_curse_watch)
        self.assertNotIn('remove-curse', policy._supply_ledger(cured, 23))

    def test_home_star_reserve_control_satisfies_normal_curse(self):
        board = self.board('blocked')
        policy = self.policy(board)
        star = item('a', TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE)
        policy.consume_home_knowledge((star,))
        policy._bind_home_star_remove_curse_withdrawal(board)
        self.assertEqual(policy._home_pending_item, policy._item_signature(star))
        gained = replace(board, inventory=(*board.inventory, replace(star, slot='z')))
        self.assertEqual(policy._town_remove_curse_key(gained), 'rz')

    def test_shop_control_buys_required_cure_and_keeps_visible_unaffordable_need(self):
        board = self.board('town')
        ware = store_item('a', TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE, price=100)
        shop = replace(board, store=StoreState(STORE_ALCHEMIST, [ware]))
        policy = self.policy(shop)
        policy.consume_home_knowledge(())
        self.assertEqual(policy._next_purchase(shop), ware)
        self.assertEqual(policy._procurement_missing_amount(shop, ware), 1)
        carried = replace(shop, inventory=(*shop.inventory,
                           item('z', TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)))
        self.assertEqual(policy._procurement_missing_amount(carried, ware), 0)
        poor = replace(shop, player=replace(shop.player, gold=0))
        self.assertIsNone(policy._next_purchase(poor))
        self.assertTrue(policy._remove_curse_service_available(shop))
        self.assertFalse(policy._remove_curse_service_available(poor))
        self.assertEqual(policy._supply_ledger(poor, 23)['remove-curse'].count, 0)
        self.assertFalse(policy._town_departure_conjuncts(poor)['remove_curse_ready'])
        exhausted = self.policy(poor)
        exhausted.consume_home_knowledge(())
        exhausted._town_store_attempted.update({store: poor.turn for store in
                                               (STORE_ALCHEMIST, STORE_TEMPLE, STORE_MAGIC, STORE_BLACK)})
        shortage = next(row for row in exhausted.procurement_requirements(poor)
                        if row['item'] == 'Remove Curse scrolls')
        self.assertEqual(shortage, dict(item='Remove Curse scrolls', current=0,
                                       target=1, missing=1, blocked_reason='no-actionable-supplier'))

    def test_black_market_reserve_includes_required_curse_cost(self):
        board = self.board('town')
        policy = self.policy(board)
        # Compare a single ledger delta on otherwise identical recorded boards.
        cured = replace(board, equipment=tuple(replace(it, is_cursed=False) for it in board.equipment))
        policy._observed_departure_prices.update({
            'recall': (1, 1), 'food': (1, 1), 'oil': (1, 1),
            'teleport': (1, 1), 'cure-critical': (1, 1),
            'light': (1, 1), 'identify-staff': (1, 1), 'remove-curse': (100, 1)})
        base = policy._required_departure_supply_reserve(cured)
        required = policy._required_departure_supply_reserve(board)
        self.assertIsNotNone(base)
        self.assertEqual(required, base + 100)
        # A carried cure owns the next errand until it has been read.
        carrying = replace(board, inventory=(*board.inventory,
                           item('z', TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)),
                           store=StoreState(STORE_BLACK, [
                               store_item('a', TVAL_POTION, SV_POTION_SPEED, price=1)]))
        self.assertIsNone(policy._black_market_optional_purchase(carrying))
        self.assertIsNotNone(policy._black_market_optional_purchase(
            replace(carrying, equipment=cured.equipment)))

    def test_recorded_mining_cursed_weapon_returns_and_keeps_ownership(self):
        board = self.board('mine')
        policy = self.policy(board)
        policy._fundraising_mode = 'mine'
        policy._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
        key = policy._fundraising_key(board, [])
        self.assertIsNotNone(key)
        self.assertNotEqual(key, 'ta')
        self.assertEqual(policy.last_reason, 'fundraise:return-cursed-weapon')
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._fundraising_mode, 'mine')
        # Constructed control: no known staircase after a stuck search must
        # retain the Recall owner even when cursed mining initiated the return.
        no_stairs = replace(board, grids={})
        returning = self.policy(no_stairs)
        returning._fundraising_mode = 'mine'
        returning._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
        returning._stuck_escape_streak = STUCK_ESCAPE_LIMIT
        self.assertTrue(returning._fundraising_key(no_stairs, []).startswith('r'))
        self.assertEqual(returning.last_reason, 'fundraise:recall-stuck')
        self.assertTrue(OperationExecutor._is_recall_depth_confirm(
            returning.last_reason, self.pins['recall-prompt']['data']['text']))
        next_key = policy._fundraising_key(board, [])
        self.assertIsNotNone(next_key)
        self.assertNotEqual(next_key, '>')
        self.assertTrue(policy.last_reason.startswith('fundraise:'))
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._fundraising_mode, 'mine')

    def test_heavy_and_permanent_controls_choose_usable_kind(self):
        board = self.board('town')
        policy = self.policy(board)
        for worn in board.equipment:
            if worn.is_cursed:
                policy._heavy_cursed_items.add(policy._item_signature(worn))
        normal = item('z', TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)
        gained = replace(board, inventory=(*board.inventory, normal))
        self.assertIsNone(policy._town_remove_curse_key(gained))
        self.assertIn('star-remove-curse', policy._supply_ledger(gained, 23))
        self.assertIn('*Remove Curse* scrolls',
                      {row['item'] for row in policy.procurement_requirements(gained)})
        self.assertIn(('star-remove-curse', 1), policy._cross_town_shortages(gained))
        strong_ware = store_item('a', TVAL_SCROLL, SV_SCROLL_STAR_REMOVE_CURSE, price=100)
        self.assertEqual(policy._cross_town_item_categories(strong_ware),
                         ('remove-curse', 'star-remove-curse'))
        shelf = replace(gained, store=StoreState(STORE_TEMPLE, [strong_ware]))
        policy._observe_cross_town_shelf(shelf)
        self.assertEqual(policy._town_visit_ledger.shelf_observations[
            (STORE_TEMPLE, 'star-remove-curse')], ((100, 1),))
        star = replace(normal, sval=SV_SCROLL_STAR_REMOVE_CURSE)
        gained = replace(board, inventory=(*board.inventory, star))
        self.assertEqual(policy._town_remove_curse_key(gained), 'rz')
        policy._observe_remove_curse(board)  # Consumed, but curse unchanged.
        self.assertTrue(policy._permanent_cursed_items)
        # Prove each remaining target through another consumed, ineffective
        # strong scroll instead of pre-completing its permanent-curse state.
        for _ in range(sum(worn.is_cursed for worn in board.equipment) - 1):
            self.assertEqual(policy._town_remove_curse_key(gained), 'rz')
            policy._observe_remove_curse(board)
        self.assertIsNone(policy._required_remove_curse_kind(board))
        self.assertTrue(policy._combat_weapon_ready(board))

    def test_legacy_checkpoint_without_permanent_curse_field_still_reads(self):
        board = self.board('blocked')
        policy = self.policy(board)
        del policy._permanent_cursed_items
        carried = replace(board, inventory=(*board.inventory,
                          item('z', TVAL_SCROLL, SV_SCROLL_REMOVE_CURSE)))
        self.assertEqual(policy._town_remove_curse_key(carried), 'rz')
        policy._observe_remove_curse(carried)
        self.assertEqual(policy._permanent_cursed_items, set())


class CurseRecallExecutorRecordedTest(executor_fixture.ProductionHarness):
    def test_recorded_stuck_recall_owner_answers_depth_prompt_n(self):
        with gzip.open(FIXTURE, 'rt', encoding='utf-8') as stream:
            pins = json.load(stream)
        raw = pins['recall']['data']
        decision = pins['stuck:recall-escape']['data']
        game = executor_fixture.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_fixture.command_screen(raw['turn'])
        game.screens = [executor_fixture.prompt_screen(pins['recall-prompt']['data']['text']),
                        executor_fixture.command_screen(raw['turn'] + 1)]
        game, _client, executor = self.make(game)
        executor.observe_boundary(deadline=9999999999)
        result = executor.submit(Operation(
            decision['decision_sequence'], decision['reason'], decision['key'],
            executor.ready_board), deadline=9999999999)
        self.assertEqual(result.outcome, 'completed', result.reason)
        self.assertEqual(game.accepted, [decision['key'], 'n'])


if __name__ == '__main__':
    unittest.main()
