"""23:55/23:56 issue #33 follow-up, captured on d6a68666.

No checkpoint exists. DECLARED CONSTRUCTED: the blocked deposit, skips and
route diagnostic are rebuilt from the recorded commands. Later boards after
changed commands are explicit alternatives, never a claimed live replay.
Selectors, reservations, route admission and dispatch are not mocked.
"""
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.model import parse_snapshot, _parse_items, STORE_HOME, StoreItem, InventoryItem, TVAL_BOTTLE
from hengbot.policy import HengbotPolicy
from hengbot.home_errand import HomeErrandRequest

FIXTURE = Path(__file__).parent / 'fixtures/home-nosurplus-20261005-2356.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    'ac59ef30ddbb91d2f3855bbd94017dbc1195df8c435ddc03c5a2955a6ea07560')
PIN = json.loads(gzip.decompress(FIXTURE.read_bytes()))
ROWS = {e['line']: e['row'] for e in PIN['states']}


def setup(enforced=False, line=1039):
    b = parse_snapshot(ROWS[line])
    p = HengbotPolicy()
    p.prime(b)
    p.consume_skill_knowledge(ROWS[1009])
    p.consume_home_knowledge(tuple(_parse_items(ROWS[1038]['knowledge']['items'], protocol=3)))
    p._refresh_carried_equipment_catalog(b)
    p._equipment_optimization_last_depth = 49  # captured decision 8507
    p._town_claim_bar_enforced = enforced
    p._in_store_ops_enabled = True
    p._home_page_size = ROWS[1012]['store']['page_size']  # captured 52-letter Home pages
    deposit = next(i for i in b.inventory if i.slot == 'r')
    p._begin_home_full_relief(b, ((p._item_signature(deposit), deposit.count, deposit.count),), refused=True)
    unknown = next(i for i in parse_snapshot(ROWS[1035]).inventory if i.slot == 's')
    p._home_full_relief['skipped'] = {p._item_signature(unknown): 'identification-effect-unresolved'}
    return p, b


class FollowupRecordedTest(unittest.TestCase):
    def decide(self, p, b):
        key = p.choose_key(b)
        for field in ('declaration_mismatch', 'claim_verdict_conflict', 'violation'):
            self.assertIsNone(p.decision_claim[field], (key, p.last_reason, field, p.decision_claim))
        self.assertIsNone(p._s33_shadow_verdict(b, key)['would_stop'])
        if key:
            p.confirm_key_posted(key)
        return key

    def test_recorded_no_surplus_now_selects_sale_or_destroy(self):
        historical = [e['row'] for e in PIN['decisions']]
        self.assertTrue(any(r.get('reason') == 'town:blocked:home-full-no-sellable-surplus'
                            and r['turn'] == 12692322 for r in historical))
        for enforced in (False, True):
            for refused in (False, True):
                p, b = setup(enforced)
                self.assertEqual(len(p._home_knowledge_items), 238)
                self.assertEqual(len(b.inventory), 20)
                if refused:
                    p._store_sale_refused.update(range(7))
                self.decide(p, b)
                self.assertNotIn('blocked', p.last_reason)
                self.assertEqual(p._home_full_relief['mode'], 'destroy' if refused else 'sale')
                self.assertIsNotNone(p._home_full_relief['sale'])

    def test_unused_captured_ammo_is_surplus_under_both_selectors(self):
        p, b = setup()
        items = p._home_knowledge_items[211:]
        self.assertEqual(len(items), 27)
        self.assertTrue(all(i.is_ammo for i in items))
        for item in items:
            with self.subTest(kind=(item.tval, item.sval), name=item.name):
                self.assertIsNotNone(p._home_full_sale_candidate(b, item))
                self.assertIsNotNone(p._home_full_discard_candidate(b, item))
        # The captured active crossbow's selected bolts remain departure kit.
        self.assertTrue(all(p._home_full_discard_candidate(b, i) is None
                            for i in p._home_knowledge_items[199:211]))
        self.assertTrue(all(p._home_full_discard_candidate(b, i) is None
                            for i in p._home_knowledge_items if i.is_artifact))

    def test_route_failure_diagnostic_cannot_refuse_visible_home_route(self):
        self.assertTrue(any(e['row'].get('reason') == 'town:blocked:home-full-surplus-store-unreachable'
                            for e in PIN['decisions']))
        for enforced in (False, True):
            p, b = setup(enforced)
            target = p._home_knowledge_items[211]
            sig = p._item_signature(target)
            p._home_full_relief.update(sale=(sig, 2, 0), mode='sale')
            p._file_home_errand(b, HomeErrandRequest(sig, target.count, 'home-catalog',
                'full-home-sale'), knowledge_current=True)
            p._home_pending_item = sig
            p._home_pending_quantity = target.count
            p._town_blocked_reason = 'home-full-surplus-store-unreachable'
            key = self.decide(p, b)
            self.assertIsNone(p._town_blocked_reason, (key, p.last_reason))
            self.assertEqual(key, '7', (key, p.last_reason))
            self.assertEqual(p.last_reason, 'shop:approach')
            # CONSTRUCTED arrival after the selected one-step route; Home
            # withdrawal is composed from the captured full catalogue.
            arrived = replace(b, turn=b.turn + 1,
                              player=replace(b.player, position=p._shopping_approach_goal))
            key = self.decide(p, arrived)
            self.assertEqual(key, '')  # captured entry's lagged surface envelope
            # Next outside board is the existing entry-unobserved release;
            # it admits the catalogue-backed one-shot withdrawal.
            key = self.decide(p, replace(arrived, turn=arrived.turn + 1))
            self.assertTrue(key.startswith('5'), (key, p.last_reason))
            self.assertIn('atomic-withdraw', p.last_reason)

    def test_catalogue_dominance_survives_the_captured_home_to_pack_move(self):
        p, b = setup()
        item = p._home_knowledge_items[99]
        self.assertTrue(p._is_disposable_dominated_armour(b, item))
        self.assertIsNotNone(p._home_full_discard_candidate(b, item))
        shelf = tuple(i for i in p._home_knowledge_items if i is not item)
        carried = replace(item, slot='u')
        after = replace(b, inventory=(*b.inventory, carried))
        p.consume_home_knowledge(shelf)
        p._refresh_carried_equipment_catalog(after)
        probe = replace(after, inventory=b.inventory)
        self.assertIsNotNone(p._home_full_discard_candidate(probe, carried))

    def test_captured_expired_torch_withdraw_destroy_observe_then_deposit(self):
        for enforced in (False, True):
            p, b = setup(enforced)
            # CONSTRUCTED blocked deposit: one additional Healing potion over
            # the captured ten-potion carry target. Captured Home stock, pack
            # identities and page geometry otherwise remain unchanged.
            healing = next(i for i in b.inventory if i.tval == 75 and i.sval == 37)
            b = replace(b, player=replace(b.player, position=parse_snapshot(ROWS[1015]).player.position),
                        inventory=tuple(replace(i, count=i.count + 1) if i is healing else i
                                        for i in b.inventory))
            p.prime(b)
            p._home_full_relief['deposits'] = ((p._item_signature(healing), healing.count + 1, 1),)
            p._home_full_relief['remaining'] = 1
            p._store_sale_refused.update(range(7))
            key = self.decide(p, b)
            self.assertIn('atomic-withdraw', p.last_reason, (key, p.last_reason))
            self.assertFalse(p._home_full_relief.get('pack_only'))
            sig = p._home_full_relief['sale'][0]
            target = next(i for i in p._home_knowledge_items if p._item_signature(i) == sig)
            self.assertTrue(target.is_torch and target.known and target.fuel == 0)
            shelf = tuple(i for i in p._home_knowledge_items if i is not target)
            taken = replace(target, slot='u')
            after = replace(b, turn=b.turn + 1, inventory=(*b.inventory, taken))
            key = self.decide(p, after)
            self.assertEqual(key, '01ku', p.last_reason)
            self.assertIsNone(p._home_atomic_deposit_pending)
            self.assertEqual(p._home_full_relief['remaining'], 1)
            unchanged = replace(after, turn=after.turn + 1)
            self.decide(p, unchanged)
            self.assertIn('destroy-await-effect', p.last_reason)
            self.assertIsNone(p._home_atomic_deposit_pending)
            removed = replace(unchanged, turn=unchanged.turn + 1, inventory=b.inventory)
            key = self.decide(p, removed)
            self.assertIsNone(p._home_full_relief)
            self.assertTrue(key.startswith('~9'), (key, p.last_reason))
            p.consume_home_knowledge(shelf)
            # CONSTRUCTED Home response to the new route/deposit command.
            page = replace(parse_snapshot(ROWS[1012]).store,
                stock_num=len(shelf), items=[StoreItem(chr(ord('a') + n) if n < 26
                    else chr(ord('A') + n - 26), i.name, i.count, i.tval, i.sval, 0,
                    known=i.known, aware=i.aware, fully_known=i.fully_known,
                    is_equipment=i.is_equipment, known_flags=i.known_flags)
                    for n, i in enumerate(shelf[:52])])
            inside = replace(removed, turn=removed.turn + 1, store=page)
            key = self.decide(p, inside)
            if key == '\x1b':
                outside = replace(inside, turn=inside.turn + 1, store=None)
                self.decide(p, outside)
                inside = replace(outside, turn=outside.turn + 1, store=page)
                key = self.decide(p, inside)
            self.assertTrue(key.startswith('d'), (key, p.last_reason))
            self.assertIsNotNone(p._home_atomic_deposit_pending)
            entries = p._home_atomic_deposit_pending[0]
            quantities = {sig: quantity for sig, before, quantity in entries}
            deposited = replace(inside, turn=inside.turn + 1, store=None,
                inventory=tuple(replace(i, count=i.count - quantities.get(p._item_signature(i), 0))
                                for i in inside.inventory
                                if i.count > quantities.get(p._item_signature(i), 0)))
            self.decide(p, deposited)
            self.assertIsNone(p._home_full_retry_deposits)
            self.assertIsNone(p._home_full_relief)
            self.assertTrue(p._home_atomic_deposit_pending is None
                            or p._home_atomic_deposit_pending[0] != entries)
            self.assertEqual(next(i.count for i in deposited.inventory
                                  if i.tval == 75 and i.sval == 37), healing.count)

    def test_full_pack_duplicate_junk_observes_one_physical_removal(self):
        p, b = setup()
        junk = tuple(InventoryItem(slot, 'duplicate empty bottle', 1, TVAL_BOTTLE, 0,
                                   True, True, fully_known=True) for slot in 'uvw')
        b = replace(b, inventory=(*b.inventory, *junk))
        p._home_full_relief['skipped'].update({p._item_signature(i): 'constructed-protected'
                                              for i in b.inventory if i not in junk})
        key = self.decide(p, b)
        self.assertEqual(key, '01ku', (key, p.last_reason))
        self.assertEqual(p._home_full_relief['sale'][2], 2)
        self.assertTrue(p._home_full_relief['pack_only'])
        after = replace(b, turn=b.turn + 1, inventory=tuple(i for i in b.inventory if i.slot != 'u'))
        self.decide(p, after)
        self.assertNotIn('destroy-await-effect', p.last_reason)
        self.assertNotIn('destroy_posted', p._home_full_relief)

    def test_known_sale_value_ranks_enchantments_and_junk_zero(self):
        from hengbot.store_sale import known_sale_value
        p, b = setup()
        plain = p._home_knowledge_items[211]
        enchanted = p._home_knowledge_items[224]
        self.assertLess(known_sale_value(plain, 1), known_sale_value(enchanted, 1))
        self.assertEqual(known_sale_value(replace(enchanted, is_cursed=True), 1), 0)
        self.assertIsNone(known_sale_value(replace(plain, known=False), 1))

    def test_average_feeling_does_not_override_equipment_candidacy(self):
        p, b = setup()
        ring = replace(p._home_knowledge_items[5], pseudo_feeling='average')
        self.assertTrue(ring.known)
        self.assertIsNone(p._home_full_discard_candidate(b, ring))
        self.assertIsNone(p._home_full_sale_candidate(b, ring))

    def test_matching_pack_deposit_is_reserved_against_home_merge(self):
        p, b = setup()
        arrow = p._home_knowledge_items[211]
        carried = replace(arrow, slot='u', count=2)
        b = replace(b, inventory=(*b.inventory, carried))
        p._home_full_relief['deposits'] = ((p._item_signature(carried), 2, 2),)
        self.assertEqual(p._retention_reservation(b, carried), 0)
        self.assertIsNone(p._home_full_sale_candidate(b, arrow))
        self.assertIsNone(p._home_full_discard_candidate(b, arrow))

    def test_free_pack_slot_keeps_home_source_when_signatures_match(self):
        for inscription in ('', ' {surplus}'):
            with self.subTest(inscription=inscription):
                p, b = setup()
                arrow = p._home_knowledge_items[211]
                carried = replace(arrow, slot='u', count=2, name=arrow.name + inscription)
                b = replace(b, inventory=(*b.inventory, carried))
                # CONSTRUCTED single candidate shelf and an identical pack
                # stack, optionally inscribed. Count the same move identity
                # before/after take; an inscription is not a withdrawal.
                p.consume_home_knowledge((arrow,))
                p._store_sale_refused.update(range(7))
                self.decide(p, b)
                self.assertNotIn('blocked', p.last_reason)
                self.assertEqual(p._home_full_relief['mode'], 'destroy')
                self.assertFalse(p._home_full_relief.get('pack_only'))
                self.assertEqual(p._home_full_relief['sale'][2], 2)
                self.assertFalse(p._home_full_relief['withdrawn'])
                self.assertEqual(p._home_errand.request.quantity, arrow.count)
                # No observed take: the existing carried stack must not be
                # mistaken for incoming shelf stock or destroyed in its place.
                key = p._home_full_relief_key(replace(b, turn=b.turn + 1))
                self.assertFalse(p._home_full_relief['withdrawn'])
                self.assertFalse(key and key.startswith('01k'), (key, p.last_reason))

    def test_free_pack_carried_junk_is_not_falsely_reported_protected(self):
        p, b = setup()
        junk = InventoryItem('u', 'unneeded bottle', 1, TVAL_BOTTLE, 0,
                             True, True, fully_known=True)
        b = replace(b, inventory=(*b.inventory, junk))
        # CONSTRUCTED all-protected shelf and no other carried candidate.
        # The user's exhaustive-surplus rule still permits carried junk;
        # its destruction must never credit a Home shelf slot.
        p.consume_home_knowledge((p._home_knowledge_items[5],))
        p._home_full_relief['skipped'].update({p._item_signature(i): 'constructed-protected'
                                             for i in b.inventory if i is not junk})
        p._store_sale_refused.update(range(7))
        self.assertEqual(self.decide(p, b), '01ku')
        self.assertTrue(p._home_full_relief['pack_only'])
        self.assertEqual(p._home_full_relief['remaining'], 1)

    def test_one_destroy_effect_continues_remaining_withdrawn_duplicates(self):
        p, b = setup()
        junk = tuple(InventoryItem(slot, 'taken duplicate bottle', 1, TVAL_BOTTLE, 0,
                                   True, True, fully_known=True) for slot in 'uvw')
        b = replace(b, inventory=(*b.inventory, *junk))
        sig = p._item_signature(junk[0])
        p._home_full_relief.update(sale=(sig, STORE_HOME, 0), withdrawn=True, mode='destroy')
        self.assertEqual(self.decide(p, b), '01ku')
        after = replace(b, turn=b.turn + 1, inventory=tuple(i for i in b.inventory if i.slot != 'u'))
        self.assertEqual(self.decide(p, after), '01kv')
        self.assertNotIn('await-effect', p.last_reason)
        self.assertEqual(p._home_full_relief['remaining'], 1)
        unchanged = replace(after, turn=after.turn + 1)
        self.decide(p, unchanged)
        self.assertIn('destroy-await-effect', p.last_reason)


if __name__ == '__main__':
    unittest.main()
