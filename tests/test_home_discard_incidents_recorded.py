"""2026-10-05 discard incidents, with immutable captured boards/decisions.

DECLARED CONSTRUCTED: no policy checkpoint was recorded. Pending ledgers are
rebuilt from posted commands; later boards after changed commands are explicit
alternatives. The shared captured skill list supplies missing external lore.
No selector, readiness evaluator or owner dispatcher is mocked.
"""
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.model import parse_snapshot, _parse_items, STORE_HOME
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from hengbot.home_errand import HomeErrandRequest
from hengbot.home_visit import HomeVisitRequest, HomeVisitKind
from hengbot.claim_register import observe
import test_homefull3_recorded as homefull3

FIXTURE = Path(__file__).parent / 'fixtures/home-discard-20261005.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    '65d0410ee93e88d95c065fb56eb3c0e1b05d75f862c525a498af9ca1bc144747')
PINS = json.loads(gzip.decompress(FIXTURE.read_bytes()))


def row(stamp, line):
    return next(e['row'] for e in PINS[stamp]['states'] if e['line'] == line)


def policy_at(board, enforced):
    p = HengbotPolicy()
    p.prime(board)
    skill = next(e['row'] for e in PINS['220530']['states']
                 if e['row'].get('knowledge', {}).get('category') == 'skill_exp')
    p.consume_skill_knowledge(skill)
    p._town_claim_bar_enforced = enforced
    p._in_store_ops_enabled = True
    return p


def catalogue(stamp):
    knowledge = [e['row'] for e in PINS[stamp]['states']
                 if e['row'].get('knowledge', {}).get('category') == 'home'][-1]
    return tuple(_parse_items(knowledge['knowledge']['items'], protocol=3))


class DiscardIncidentsTest(unittest.TestCase):
    def decide(self, p, b):
        key = p.choose_key(b)
        for field in ('declaration_mismatch', 'claim_verdict_conflict', 'violation'):
            self.assertIsNone(p.decision_claim[field], (field, p.last_reason, p.decision_claim))
        self.assertIsNone(p._s33_shadow_verdict(b, key)['would_stop'])
        if key:
            p.confirm_key_posted(key)
        return key

    def test_full_pack_historical_wait_advances_to_carried_sale_or_destroy(self):
        pin = PINS['220530']
        self.assertTrue(any(e['row'].get('reason') ==
            'town:blocked:home-full-no-sellable-surplus' for e in pin['decisions']))
        b = parse_snapshot([e['row'] for e in pin['states']
                            if e['row'].get('type') == 'player_turn'][-1])
        self.assertEqual(len(b.inventory), 23)
        for enforced in (False, True):
            for refused in (False, True):
                p = policy_at(b, enforced)
                p.consume_home_knowledge(catalogue('220530'))
                # CONSTRUCTED blocked deposit owner; with stores refused the
                # same captured pack must reach destruction instead of wait.
                target = b.inventory[-1]
                p._begin_home_full_relief(b, ((p._item_signature(target), 1, 1),), refused=True)
                if refused:
                    p._store_sale_refused.update(range(7))
                key = self.decide(p, b)
                self.assertTrue(p._home_full_relief.get('pack_only'), (key, p.last_reason))
                self.assertEqual(p._home_full_relief['mode'], 'destroy' if refused else 'sale')
                self.assertNotIn('blocked', p.last_reason)
                if refused:
                    self.assertIn('k', key)
                    self.assertIsNone(p._home_atomic_withdraw_pending)

    def test_identification_autodestroy_observation_advances_to_fresh_catalogue(self):
        self.assertTrue(any(e['row'].get('reason') ==
            'town:blocked:home-full-identification-effect-unresolved'
            for e in PINS['220912']['decisions']))
        before, after = parse_snapshot(row('220912', 68)), parse_snapshot(row('220912', 69))
        target = next(i for i in before.inventory if i.slot == 'r')
        self.assertFalse(target.known)
        self.assertFalse(any(i.tval == target.tval for i in after.inventory))
        for enforced in (False, True):
            p = policy_at(before, enforced)
            p.consume_home_knowledge(catalogue('220912'))
            sig = p._item_signature(target)
            p._begin_home_full_relief(before, ((p._item_signature(before.inventory[0]), 1, 1),), refused=True)
            p._home_full_relief.update(sale=(sig, STORE_HOME, 0), withdrawn=True,
                mode='identify', identifying=(target.tval, target.count,
                frozenset(p._item_signature(i) for i in before.inventory), False, False))
            p._claim_register.declare('identification', observe(('identified',), 8,
                source='store-operation'), floor=before.floor_key)
            key = self.decide(p, after)
            self.assertIsNone(p._home_full_relief)
            self.assertTrue(key.startswith('~9'), (key, p.last_reason))
            self.assertIsNotNone(p._home_full_retry_deposits)

    def test_posted_gloves_take_advances_directly_to_destroy_without_home_reentry(self):
        historical = [e['row'] for e in PINS['221036']['decisions']]
        self.assertEqual([x['reason'] for x in historical[-4:]], [
            'home-errand:atomic-withdraw:full-home-discard', 'shop:travel:await-entry',
            'policy:none-store-exit', 'home-errand:request-knowledge:full-home-discard'])
        before, after = parse_snapshot(row('221036', 81)), parse_snapshot(row('221036', 85))
        target = next(i for i in after.inventory if i.slot == 'r')
        for enforced in (False, True):
            p = policy_at(before, enforced)
            p.consume_home_knowledge(catalogue('221036'))
            sig = p._item_signature(target)
            deposits = ((p._item_signature(before.inventory[0]), 1, 1),)
            p._begin_home_full_relief(before, deposits, refused=True)
            p._home_full_relief.update(sale=(sig, STORE_HOME, 0), mode='destroy')
            p._file_home_errand(before, HomeErrandRequest(sig, 1, 'home-catalog',
                'full-home-discard'), knowledge_current=True)
            p._home_errand.post(0)
            p._home_pending_item = sig
            p._home_pending_quantity = 1
            p._home_atomic_withdraw_pending = (sig, 0, target, 1)
            p._home_atomic_withdraw_posted_turn = before.turn
            p._home_atomic_withdraw_index = next(i for i, item in enumerate(
                p._home_knowledge_items) if p._item_signature(item) == sig)
            p._home_visit.file(HomeVisitRequest(HomeVisitKind.WITHDRAW, 'home-errand', sig))
            p._home_visit.begin_approach(1)
            p._prepare_home_visit_operation('take', sig, ('captured',))
            command = historical[-4]['key']
            p._store_visit = StoreVisit('home-errand', 'shopping', STORE_HOME,
                StoreVisitPhase.OPERATING, opened_sequence=1, operation_posted=True,
                operation_released=True, operation_key=command,
                operation_producer_family='home-errand',
                claim_operation_identity=(STORE_HOME, 1, command))
            key = self.decide(p, after)
            self.assertEqual(key, '01kr', (key, p.last_reason))
            self.assertEqual(p.last_reason, 'home:full-destroy-surplus')
            self.assertIsNone(p._home_atomic_withdraw_pending)

    def test_unresolved_identification_releases_owner_and_skips_visibly(self):
        before = parse_snapshot(row('220912', 68))
        target = next(i for i in before.inventory if i.slot == 'r')
        for enforced in (False, True):
            p = policy_at(before, enforced)
            p.consume_home_knowledge(catalogue('220912'))
            sig = p._item_signature(target)
            p._begin_home_full_relief(before, ((p._item_signature(before.inventory[0]), 1, 1),), refused=True)
            p._home_full_relief.update(sale=(sig, STORE_HOME, 0), withdrawn=True,
                mode='identify', identifying=(target.tval, target.count,
                frozenset(p._item_signature(i) for i in before.inventory), False, False))
            p._claim_register.declare('identification', observe(('identified',), 8,
                source='store-operation'), floor=before.floor_key)
            unchanged = replace(before, turn=before.turn + 1)
            key = self.decide(p, unchanged)
            self.assertTrue(p.last_reason.endswith('home:full-skip:identification-effect-unresolved'), (key, p.last_reason))
            self.assertEqual(p._home_full_relief['skipped'][sig], 'identification-effect-unresolved')
            self.assertIsNone(p._home_full_relief['sale'])
            self.assertNotIn('k', key)
            # The next public decision selects another shelf item; the old
            # candidate cannot issue another identification command.
            outside = replace(unchanged, turn=unchanged.turn + 1)
            key = self.decide(p, outside)
            self.assertTrue(key.startswith('~9'), (key, p.last_reason))
            p.consume_home_knowledge(tuple(i for i in catalogue('220912')
                if p._item_signature(i) != sig))
            key = self.decide(p, replace(outside, turn=outside.turn + 1))
            self.assertNotEqual(p._home_full_relief['sale'][0], sig)

    def test_knowledge_request_exits_store_before_macro(self):
        inside = parse_snapshot(row('221036', 87))
        for enforced in (False, True):
            p = policy_at(inside, enforced)
            sig = p._item_signature(inside.inventory[-1])
            p._file_home_errand(inside, HomeErrandRequest(sig, 1, 'home-catalog',
                'full-home-discard'), knowledge_current=False)
            key = self.decide(p, inside)
            self.assertEqual(key, '\x1b', p.last_reason)
            self.assertFalse(p._home_knowledge_scan_inflight)
            self.assertIn(p.decision_claim['owner'], ('home-errand', 'home-scan'))
            outside = replace(inside, store=None, turn=inside.turn + 1)
            key = self.decide(p, outside)
            self.assertTrue(key.startswith('~9'), (key, p.last_reason))

    def test_changed_known_source_cannot_impersonate_identified_target(self):
        # CONSTRUCTED same-tval ambiguity: the unknown staff disappears while
        # the known Identify source changes only its displayed charge count.
        b = parse_snapshot(row('220912', 68))
        target = replace(next(i for i in b.inventory if i.slot == 'r'),
            name='unknown staff', tval=55, sval=-1, is_equipment=False)
        source = replace(next(i for i in b.inventory if i.slot == 'p'),
            name='Identify staff (8 charges)', count=1)
        b = replace(b, inventory=tuple(target if i.slot == 'r' else
            source if i.slot == 'p' else i for i in b.inventory))
        for enforced in (False, True):
            p = policy_at(b, enforced)
            p.consume_home_knowledge(catalogue('220912'))
            sig = p._item_signature(target)
            p._begin_home_full_relief(b, ((p._item_signature(b.inventory[0]), 1, 1),), refused=True)
            p._home_full_relief.update(sale=(sig, STORE_HOME, 0), withdrawn=True,
                mode='identify', identifying=(target.tval, 1,
                frozenset(p._item_signature(i) for i in b.inventory), False, False),
                identification_counts={(source.tval, source.sval): sum(
                    i.count for i in b.inventory if i.known
                    and (i.tval, i.sval) == (source.tval, source.sval))})
            p._claim_register.declare('identification', observe(('identified',), 8,
                source='store-operation'), floor=b.floor_key)
            after = replace(b, turn=b.turn + 1, inventory=tuple(
                replace(i, name='Identify staff (7 charges)', charges=i.charges - 1)
                if i.slot == 'p' else i for i in b.inventory if i.slot != 'r'))
            key = self.decide(p, after)
            self.assertTrue(p.last_reason.endswith('home:full-skip:identification-effect-unresolved'), (key, p.last_reason, target.tval, source.tval))
            self.assertIsNone(p._home_full_relief['sale'])
            self.assertNotIn('k', key)
            self.assertTrue(any(i.slot == 'p' for i in after.inventory))

    def test_refused_surplus_sale_falls_back_to_observed_destruction(self):
        b = parse_snapshot(row('221036', 85))
        target = next(i for i in b.inventory if i.slot == 'r')
        for enforced in (False, True):
            p = policy_at(b, enforced)
            p.consume_home_knowledge(catalogue('221036'))
            sig = p._item_signature(target)
            p._begin_home_full_relief(b, ((p._item_signature(b.inventory[0]), 1, 1),), refused=True)
            p._home_full_relief.update(sale=(sig, 1, 0), withdrawn=True, mode='sale')
            p._unsellable_items.add(sig)
            key = self.decide(p, b)
            self.assertEqual(key, '01kr', p.last_reason)
            self.assertEqual(p._home_full_relief['mode'], 'destroy')
            self.assertEqual(p._home_full_relief['remaining'], 1)


class DiscardCompleteCycleTest(unittest.TestCase):
    setUpClass = classmethod(homefull3.ConstructedDiscardTest.setUpClass.__func__)
    decide = homefull3.ConstructedDiscardTest.decide
    refuse = homefull3.ConstructedDiscardTest.refuse
    home_page = homefull3.ConstructedDiscardTest.home_page
    scene = homefull3.ConstructedDiscardTest.scene

    def test_full_home_withdraw_destroy_fresh_catalogue_deposit_observed(self):
        # The existing constructed driver asserts both destroy effects and
        # their fresh catalogues. Extend the final deposit to its observed
        # inventory effect in a separate explicit complete-cycle scene.
        from hengbot.model import Position
        for enforced in (False, True):
            p, b, stock, entries, key = self.scene(enforced)
            b, key = self.decide(p, b, messages=(), player=replace(b.player,
                position=Position(10, 14)), store=self.home_page(stock))
            b, key = self.decide(p, b, store=None)
            for taken in (stock[-1], stock[-2]):
                b, key = self.decide(p, b, inventory=(*b.inventory, replace(taken, slot='s')))
                self.assertEqual(key, '01ks')
                self.assertIsNone(p._home_atomic_deposit_pending)
                b, wait = self.decide(p, b)
                self.assertIn('await-effect', p.last_reason)
                self.assertIsNone(p._home_atomic_deposit_pending)
                b, key = self.decide(p, b, inventory=tuple(i for i in b.inventory if i.slot != 's'))
                self.assertTrue(key.startswith('~9'))
                stock = tuple(i for i in stock if p._item_signature(i) != p._item_signature(taken))
                p.consume_home_knowledge(stock)
                if p._home_full_relief is not None:
                    b, key = self.decide(p, b)
                    self.assertIsNotNone(p._home_atomic_withdraw_pending)
            self.assertIsNone(p._home_full_relief)
            b, key = self.decide(p, b, store=self.home_page(stock))
            if key == '\x1b':
                b, key = self.decide(p, b, store=None)
                b, key = self.decide(p, b, store=self.home_page(stock))
            self.assertTrue(key.startswith('d'), (key, p.last_reason))
            pending = p._home_atomic_deposit_pending
            self.assertIsNotNone(pending)
            deposited = {entry[0] for entry in pending[0]}
            b, key = self.decide(p, b, store=None, inventory=tuple(
                i for i in b.inventory if p._item_signature(i) not in deposited))
            self.assertIsNone(p._home_atomic_deposit_pending)
            self.assertTrue(deposited.isdisjoint(p._item_signature(i) for i in b.inventory))
