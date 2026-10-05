"""2026-10-04 incident pins. Boards and decision rows are immutable.

DECLARED CONSTRUCTED: the logs contain no policy checkpoint. Rebuild the
posted Home ledger from its captured command. Static monster combat defaults
only fill missing external lore; captured perception/positions stay intact.
Later responses after the first changed command are constructed alternatives.
"""
import gzip
import json
import ast
import hashlib
from pathlib import Path
from dataclasses import replace
import unittest
import tests
from hengbot.model import parse_snapshot, _parse_items, InventoryItem, STORE_HOME, TVAL_BOTTLE, TVAL_POTION
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from hengbot.home_visit import HomeVisitKind, HomeVisitRequest
from hengbot.home_errand import HomeErrandRequest
from hengbot.claim_register import observe
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
import test_home_full_relief_recorded as full_relief

FIXTURE = Path(__file__).parent / 'fixtures/homefull3-20261004.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == 'b82afc4fee7282211fdda4884e2fc3edbec2682dddc675ca93d74cc7a00b695d'
PIN = json.loads(gzip.decompress(FIXTURE.read_bytes()))
ROWS = {e['line']: e['row'] for e in PIN['state-upto-1344.jsonl.gz']['states']}
CROWS = {e['line']: e['row'] for e in PIN['state-upto-1150.jsonl.gz']['states']}


def board(row):
    lore = {m['race_id']: MonraceKnowledge(10, 110, False, False)
            for m in row.get('visible_monsters', []) + row.get('detected_monsters', [])}
    return parse_snapshot(row, lore)


def policy_at(snapshot, enforced=False):
    p = HengbotPolicy()
    p.prime(snapshot)
    p.consume_skill_knowledge(ROWS[4260])
    p._town_claim_bar_enforced = enforced
    p._crossarea_fundraising_enforced = True
    p._in_store_ops_enabled = True
    return p


class RecordedHomeFull3Test(unittest.TestCase):
    def assert_owner(self, p, b, key):
        for name in ('declaration_mismatch', 'claim_verdict_conflict', 'violation'):
            self.assertIsNone(p.decision_claim[name], (name, p.decision_claim))
        self.assertIsNone(p._s33_shadow_verdict(b, key)['would_stop'])

    def test_A_released_partial_deposit_keeps_home_owner_with_detected_townspeople(self):
        before, after = board(ROWS[4263]), board(ROWS[4272])
        historical = PIN['autorecover-20261004-134213-equipment-transaction-home-route-repeat-terminal.bot-decisions.jsonl.gz']
        self.assertEqual(historical[3]['row']['reason'], 'periodic:character-dump')
        self.assertFalse(after.visible_monsters)
        self.assertTrue(any(m.hostile for m in after.detected_monsters))
        for enforced in (False, True):
            p = policy_at(after, enforced)
            targets = [i for i in before.inventory if i.slot in 'wuomliga']
            entries = tuple((p._item_signature(i), i.count, i.count) for i in targets)
            command = 'dw22\rdudodm3\rdl2\rdidgda\x1b'
            p._home_atomic_deposit_pending = (entries, None, before.turn, 0)
            p._home_entry_operation_posted = True
            p._store_visit = StoreVisit('town-errand', 'shopping', STORE_HOME,
                StoreVisitPhase.OPERATING, opened_sequence=1, posted_sequence=1,
                posted_turn=before.turn, operation_posted=True, operation_released=True,
                operation_key=command, operation_producer_family='home-visit',
                claim_operation_identity=(STORE_HOME, 1, command))
            p._home_visit.file(HomeVisitRequest(HomeVisitKind.DEPOSIT, 'weight-overload', entries[0][0]))
            p._home_visit.begin_approach(1)
            p._prepare_home_visit_operation('put', entries[0][0], ('captured',))
            key = p.choose_key(after)
            self.assertIn('home:atomic-deposit-await-confirmation', p.last_reason)
            self.assertEqual(p._home_atomic_deposit_pending[3], 1)
            self.assertEqual(p.decision_claim['owner'], 'home-visit')
            self.assert_owner(p, after, key)
            self.assertFalse(p._store_visit.operation_effect_observed)

    def test_B_first_outside_home_withdraws_instead_of_routing_to_alchemist(self):
        home, outside = board(ROWS[4291]), board(ROWS[4292])
        catalogue = tuple(_parse_items(ROWS[4288]['knowledge']['items'], protocol=3))
        for enforced in (False, True):
            p = policy_at(home, enforced)
            p.consume_home_knowledge(catalogue)
            blocked = home.inventory[0]
            p._begin_home_full_relief(home, ((p._item_signature(blocked), blocked.count, blocked.count),), refused=True)
            key = p.choose_key(home)
            self.assertEqual(key, '\x1b')
            self.assert_owner(p, home, key)
            p.confirm_key_posted(key)
            key = p.choose_key(outside)
            self.assertTrue(key.startswith('5p'), (key, p.last_reason, p.home_route_refusal_state()))
            self.assertEqual(p._shopping_approach_store_type, STORE_HOME)
            self.assertEqual(p.decision_claim['owner'], 'home-errand')
            self.assert_owner(p, outside, key)
            self.assertIsNotNone(p._home_atomic_withdraw_pending)

    def test_C_stale_catalogue_has_owner_declared_request_and_wait(self):
        b = board(CROWS[96])
        historical = next(e for e in PIN['decisions-tail-1150.jsonl.gz'] if e['row']['turn'] == b.turn)
        self.assertEqual(historical['line'], 2547)
        self.assertEqual(historical['row']['s33_shadow']['would_stop'], 'ownership:declaration-missing:home-errand')
        for enforced in (False, True):
            p = policy_at(b, enforced)
            prior = next(e for e in PIN['decisions-tail-1150.jsonl.gz'] if e['line'] == 2546)
            signature = ast.literal_eval(prior['row']['claim']['goal']['expectation'][0])
            p.consume_skill_knowledge(PIN['state-upto-1150.jsonl.gz']['knowledge']['skill_exp'][1])
            stale = PIN['state-upto-1150.jsonl.gz']['knowledge']['home'][1]
            p.consume_home_knowledge(tuple(_parse_items(stale['knowledge']['items'], protocol=3)))
            p._invalidate_home_observation()
            # Captured diagnostics at row 2547: the ordinary Home allowance is
            # three, all three passes charged. Knowledge remains the errand's
            # prerequisite even when the ordinary entrance projection is spent.
            p._town_visit_ledger.unsatisfied_passes[STORE_HOME] = 3
            request = HomeErrandRequest(signature, 1, 'home-catalog', 'full-home-sale')
            p._file_home_errand(b, request, knowledge_current=False)
            p._claim_register.declare('home-errand', observe(('home-request',), 8, source='store-operation'), floor=b.floor_key)
            key = p.choose_key(b)
            self.assertTrue(key.startswith('~9'), (key, p.last_reason))
            self.assertEqual(p.decision_claim['owner'], 'home-errand')
            self.assert_owner(p, b, key)
            p.confirm_key_posted(key)
            delayed = replace(b, turn=b.turn + 1)
            key = p.choose_key(delayed)
            self.assertEqual(key, '5')
            self.assertEqual(p.decision_claim['owner'], 'home-errand')
            self.assert_owner(p, delayed, key)


class ConstructedDiscardTest(unittest.TestCase):
    setUpClass = classmethod(full_relief.HomeFullReliefTest.setUpClass.__func__)
    decide = full_relief.HomeFullReliefTest.decide
    refuse = full_relief.HomeFullReliefTest.refuse
    home_page = full_relief.HomeFullReliefTest.home_page

    # Reuse the public decision/assertion driver, without replacing policy
    # collaborators. The existing module covers the two-sale recovery.
    def scene(self, enforced=False, *, sellable=False):
        p, b, stock, entries = full_relief.relief_scene(self.pins[0], enforced, safe=1 if sellable else 0)
        # DECLARED CONSTRUCTED observed store refusal of an otherwise unneeded
        # potion kind (75, 20). It has positive base cost but zero
        # realizable buy value; it is outside the automatic junk kinds.
        junk = InventoryItem('home', 'ordinary unsellable', 1, TVAL_POTION,
                             20, True, True, fully_known=True)
        p._baseitem_costs[(junk.tval, junk.sval)] = 500
        p._unsellable_items.add(p._item_signature(junk))
        bottle = InventoryItem('home', 'empty bottle', 1, TVAL_BOTTLE, 0, True, True, fully_known=True)
        stock = (*stock[:-2], junk, bottle)
        p.consume_home_knowledge(stock)
        b, key = self.refuse(p, b)
        return p, b, stock, entries, key

    def test_D_sell_first_even_when_autodestroy_stock_exists(self):
        p, b, stock, entries, key = self.scene(sellable=True)
        self.assertEqual(p._home_full_relief.get('mode'), 'sale')
        self.assertEqual(p._home_errand.request.purpose, 'full-home-sale')

    def test_D_autodestroy_first_and_waits_for_destroy_effect_before_deposit(self):
        for enforced in (False, True):
            p, b, stock, entries, key = self.scene(enforced)
            self.assertEqual(p._home_full_relief.get('mode'), 'destroy')
            self.assertEqual(p._home_errand.request.signature[0], 'empty bottle')
            from hengbot.model import Position
            b, key = self.decide(p, b, messages=(), player=replace(b.player, position=Position(10, 14)), store=self.home_page(stock))
            self.assertEqual(key, '\x1b')
            b, key = self.decide(p, b, store=None)
            self.assertIn('p', key)
            taken = replace(stock[-1], slot='s')
            b, key = self.decide(p, b, inventory=(*b.inventory, taken))
            self.assertEqual(key, '01ks')
            self.assertEqual(p._home_full_relief['remaining'], len(entries))
            b, key = self.decide(p, b)
            self.assertIn(key, '123456789')  # existing entrance step-off may replace WAIT
            self.assertIn('home:full-destroy-await-effect', p.last_reason)
            self.assertIsNone(p._home_atomic_deposit_pending)
            b, key = self.decide(p, b, inventory=tuple(i for i in b.inventory if i.slot != 's'))
            self.assertEqual(p._home_full_relief['remaining'], len(entries) - 1)
            self.assertEqual(key, HOME_KNOWLEDGE_MACRO)
            # DECLARED CONSTRUCTED second take/destroy and refreshed catalogue.
            stock = stock[:-1]
            p.consume_home_knowledge(stock)
            b, key = self.decide(p, b)
            self.assertEqual(p._home_errand.request.signature[0], 'ordinary unsellable')
            self.assertIsNotNone(p._home_atomic_withdraw_pending)
            b, key = self.decide(p, b, inventory=(*b.inventory, replace(stock[-1], slot='s')))
            self.assertEqual(key, '01ks')
            b, key = self.decide(p, b, inventory=tuple(i for i in b.inventory if i.slot != 's'))
            self.assertIsNone(p._home_full_relief)
            self.assertEqual(key, HOME_KNOWLEDGE_MACRO)
            p.consume_home_knowledge(stock[:-1])
            b, key = self.decide(p, b, store=self.home_page(stock[:-1]))
            if key == '\x1b':
                b, key = self.decide(p, b, store=None)
                b, key = self.decide(p, b, store=self.home_page(stock[:-1]))
            self.assertTrue(key.startswith('d'), (key, p.last_reason))
            self.assertIsNotNone(p._home_atomic_deposit_pending)

    def test_D_artifacts_unknown_superior_and_reservations_are_not_destroy_candidates(self):
        p, b, stock, entries, key = self.scene()
        bottle = stock[-1]
        for item in (replace(bottle, is_artifact=True), replace(bottle, known=False),
                     replace(bottle, fully_known=False, is_ego=True, pseudo_feeling='excellent')):
            self.assertIsNone(p._home_full_discard_candidate(b, item))
        # Departure Recall stack uses the same retention authority.
        from hengbot.model import TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL
        recall = replace(bottle, name='Recall', tval=TVAL_SCROLL, sval=SV_SCROLL_WORD_OF_RECALL)
        missing_recall = replace(b, inventory=tuple(i for i in b.inventory if not i.is_recall_scroll))
        self.assertIsNone(p._home_full_discard_candidate(missing_recall, recall))
        weapon = next(i for i in b.equipment if i.is_melee_weapon)
        self.assertIsNone(p._home_full_discard_candidate(b, replace(weapon, known=True, fully_known=True)))

    def test_D_unknown_is_identified_then_revalidated_before_destroy(self):
        from hengbot.model import TVAL_SCROLL, SV_SCROLL_IDENTIFY, TVAL_POTION, SV_POTION_SLEEP, Position
        for enforced in (False, True):
            p, b, stock, entries = full_relief.relief_scene(self.pins[0], enforced, safe=0)
            unknown = InventoryItem('home', 'unknown junk', 1, TVAL_POTION, -1, False, False)
            p._baseitem_costs[(TVAL_POTION, SV_POTION_SLEEP)] = 0
            stock = (*stock[:-1], unknown)
            source = InventoryItem('t', 'Identify', 1, TVAL_SCROLL, SV_SCROLL_IDENTIFY, True, True)
            b = replace(b, inventory=(*b.inventory, source))
            # CONSTRUCTED approval for the added ID source: this scene checks
            # identification, rather than selling an optional spare scroll.
            from hengbot.home_disposal import signature_key
            p._home_disposal._atomic_write_json(p._home_disposal.decisions_path, {
                "decisions": {signature_key(sig): decision for sig, decision in {
                    **p._home_disposal.decisions,
                    p._item_signature(source): "keep"}.items()}})
            p._home_disposal.reload_decisions()
            p.consume_home_knowledge(stock)
            b, key = self.refuse(p, b)
            self.assertEqual(p._home_full_relief.get('mode'), 'identify')
            b, key = self.decide(p, b, messages=(), player=replace(b.player, position=Position(10, 14)), store=self.home_page(stock))
            b, key = self.decide(p, b, store=None)
            taken = replace(unknown, slot='s')
            b, key = self.decide(p, b, inventory=(*b.inventory, taken))
            self.assertEqual(key[-1], 's')
            self.assertIn(key[0], 'ru')
            identify_command, source_slot = key[:2]
            self.assertEqual(p.decision_claim['owner'], 'identification')
            self.assertIsNone(p._home_atomic_deposit_pending)
            identified = replace(taken, name='Sleep potion', sval=SV_POTION_SLEEP,
                                 aware=True, known=True, fully_known=True)
            b, key = self.decide(p, b, inventory=tuple(
                identified if i.slot == 's' else replace(i, charges=i.charges - 1)
                if identify_command == 'u' and i.slot == source_slot else i
                for i in b.inventory
                if not (identify_command == 'r' and i.slot == source_slot)))
            self.assertEqual(key, '01ks')
            self.assertEqual(p._home_full_relief['remaining'], len(entries))

    def test_D_shop_rejected_value_is_zero_even_if_base_cost_is_positive(self):
        p, b, stock, entries, key = self.scene()
        ordinary = stock[-2]
        p._baseitem_costs[(ordinary.tval, ordinary.sval)] = 10000
        # An observed refusal cannot become a sale merely from its base cost.
        self.assertIsNone(p._home_full_sale_candidate(b, ordinary))
        self.assertEqual(p._home_full_discard_rank(b, ordinary)[1], 0)
        corpse = replace(ordinary, name='corpse', tval=10, sval=0)
        p._baseitem_costs[(10, 0)] = 10000
        self.assertIsNone(p._home_full_sale_candidate(b, corpse))
        self.assertEqual(p._home_full_discard_rank(b, corpse)[1], 0)

if __name__ == '__main__':
    unittest.main()
