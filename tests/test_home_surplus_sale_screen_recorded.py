"""2026-10-05 sale failures: immutable decisions and B's actual store board.

No checkpoint or post-sale screen was supplied. Relief/visit state is rebuilt
from the withdrawal/route decisions; protocol 2 bypasses the missing attach
skill cache, with the last recorded map carried forward. A has decisions only:
its policy replay explicitly reconstructs the named boots from B's board and
uses A's recorded slot/visit. It is not an exact A snapshot replay.
"""
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tests  # noqa: F401 -- isolate runtime files

from hengbot.model import parse_snapshot, STORE_ARMOURY, STORE_BLACK, STORE_HOME
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase


FIXTURE = Path(__file__).parent / 'fixtures/home-surplus-sale-screen-20261005.json.gz'
SHA256 = 'e4c80991c8e2a6008d6558cbcac9e19ef08652ff97702381b3acb3b4844182f2'


class HomeSurplusSaleScreenRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(payload))

    def board(self):
        row = dict(self.data['B_states'][-1]['row'], grid_map=self.data['B_grid_map'])
        return replace(parse_snapshot(row), protocol_version=2)

    def policy_at(self, board, *, enabled, enforced=False, opened=6335):
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = enforced
        policy._in_store_ops_enabled = enabled
        policy.observe_store_screen(True)
        target = next(i for i in board.inventory if i.inscription == '@0')
        policy._home_full_relief = {
            'town': policy._effective_town_id(board),
            'sale': (policy._item_signature(target), STORE_ARMOURY, 0),
            'withdrawn': True, 'remaining': 1, 'deposits': (),
        }
        policy._store_visit = StoreVisit('town-errand', 'shopping', STORE_ARMOURY,
            StoreVisitPhase.OPERATING, opened_sequence=opened)
        return policy, target

    def assert_owned_leave(self, policy, board):
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ('\x1b', 'shop:unsellable-home-full-surplus-sale-refused'))
        self.assertIsNone(policy._batch_sell_pending)
        self.assertEqual(policy.decision_claim['owner'], 'shop-sell')
        self.assertEqual(policy._claim_register.current.execution.producer, 'shop-sell')
        for name in ('declaration_mismatch', 'claim_verdict_conflict', 'violation'):
            self.assertIsNone(policy.decision_claim[name])
        self.assertIsNone(policy._s33_shadow_verdict(board, key)['would_stop'])
        self.assertNotIn(STORE_ARMOURY, policy._store_sale_refused)

    def test_A_recorded_failure_and_reconstructed_owned_refusal(self):
        rows = [e['row'] for e in self.data['A_decisions']]
        self.assertEqual([r['decision_sequence'] for r in rows], list(range(1128, 1133)))
        self.assertEqual([r['key'] for r in rows],
                         ['5  pb\x1b', '\x1b`n".', '{o@0\r', 'd0y', '\x1b'])
        self.assertEqual(rows[3]['reason'], 'shop:in-store-sell')
        self.assertEqual(self.data['A_breaker']['cause'], 'unowned-screen')
        self.assertEqual(self.data['A_breaker']['decision_sequence'], 1131)
        # A's message identifies the same boots [2,-2], without B's sale tag.
        board = self.board()
        target = next(i for i in board.inventory if i.inscription == '@0')
        self.assertEqual(target.name.split(']')[0], rows[3]['messages'][0].split(']')[0])
        # DECLARED CONSTRUCTED: A's inventory/skill checkpoint is absent.
        board = replace(board, turn=rows[3]['turn'], inventory=tuple(
            replace(i, slot='o') if i == target else
            replace(i, slot='q') if i.slot == 'o' else i
            for i in board.inventory))
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, _ = self.policy_at(board, enabled=True, enforced=enforced, opened=1129)
                self.assert_owned_leave(policy, board)

    def test_B_recorded_singleton_and_posted_tail_now_leave(self):
        board = self.board()
        target = next(i for i in board.inventory if i.inscription == '@0')
        self.assertEqual((target.slot, target.count, target.tval, target.sval, target.to_a),
                         ('q', 1, 30, 2, -2))
        self.assertTrue(target.known and target.fully_known and target.is_ego)
        self.assertFalse(target.is_cursed or target.is_broken or target.is_artifact)
        self.assertEqual(self.data['B_states'][-1]['line'], 74)
        self.assertEqual(board.turn, 11524631)
        decision = self.data['B_decisions'][-1]['row']
        self.assertEqual((decision['reason'], decision['key']),
                         ('shop:one-shot-sale-compose', 'd0y'))
        self.assertEqual(''.join(e['row']['character'] for e in self.data['B_posted']), 'd0y')
        self.assertIn('in_store_breaker=unowned-screen', self.data['B_stderr'])
        self.assertIn('reason=unowned unknown: unrecognized-store-input', self.data['B_stderr'])
        for enforced in (False, True):
            with self.subTest(enforced=enforced):
                policy, _ = self.policy_at(board, enabled=False, enforced=enforced)
                self.assert_owned_leave(policy, board)

    def test_shared_acceptance_excludes_negative_armour_even_in_black_market(self):
        board = self.board()
        policy, target = self.policy_at(board, enabled=True)
        for tval in range(30, 39):
            with self.subTest(tval=tval):
                armour = replace(target, tval=tval)
                self.assertFalse(policy._store_accepts_sale(STORE_ARMOURY, armour))
                self.assertFalse(policy._store_accepts_sale(STORE_BLACK, armour))
                self.assertTrue(policy._store_accepts_sale(STORE_HOME, armour))
        self.assertTrue(policy._store_accepts_sale(STORE_ARMOURY, replace(target, to_a=0)))
        self.assertTrue(policy._store_accepts_sale(STORE_ARMOURY, replace(target, known=False)))
        self.assertFalse(policy._store_accepts_sale(STORE_ARMOURY, replace(target, is_artifact=True)))

    def test_batch_selection_uses_the_same_acceptance_gate(self):
        board = self.board()
        policy, target = self.policy_at(board, enabled=False)
        self.assertEqual(policy._current_store_sale_candidates(board), [])
        self.assertIsNone(policy._batch_sell_key(board, [target]))
        self.assertIsNone(policy._batch_sell_pending)

    def test_pending_inscription_rechecks_acceptance_on_observed_board(self):
        board = self.board()
        policy, target = self.policy_at(board, enabled=True)
        # DECLARED CONSTRUCTED: an older accepted plan survived to this board.
        policy._batch_sell_pending = {
            'store_type': STORE_ARMOURY, 'phase': 'await-inscription',
            'entries': [{'signature': policy._sale_item_identity(target), 'tag': '0'}],
            'before_gold': board.player.gold,
        }
        self.assertIsNone(policy._in_store_selection(board))
        self.assertEqual(policy._batch_sell_key(board), '\x1b')
        self.assertEqual(policy.last_reason, 'shop:sale-unaccepted-leave')
        self.assertIsNone(policy._batch_sell_pending)

    def test_accepted_sale_still_uses_observed_stack_quantity_and_item_verdict(self):
        board = self.board()
        original = next(i for i in board.inventory if i.inscription == '@0')
        for count, expected in ((1, 'd0y'), (3, 'd03\ry')):
            with self.subTest(count=count):
                # DECLARED CONSTRUCTED: accepted armour and quantity boundary.
                target = replace(original, to_a=0, count=count)
                current = replace(board, inventory=tuple(
                    target if i == original else i for i in board.inventory))
                policy, _ = self.policy_at(current, enabled=True, enforced=True)
                key = policy.choose_key(current)
                self.assertEqual((key, policy.last_reason), (expected, 'shop:in-store-sell'))
                self.assertEqual(policy._in_store_entry_ledger['pending']['kind'], 'sell')
                self.assertEqual(policy._store_visit.operation_key, key)
                self.assertIsNone(policy._s33_shadow_verdict(current, key)['would_stop'])

    def test_inscription_merge_recomposes_quantity_from_the_observed_stack(self):
        board = self.board()
        original = next(i for i in board.inventory if i.inscription == '@0')
        # DECLARED CONSTRUCTED: a singleton plan, then an observed stack of 3.
        target = replace(original, to_a=0, count=3)
        after = replace(board, inventory=tuple(
            target if i == original else i for i in board.inventory))
        untagged = replace(target, count=1, inscription='',
                           name=target.name.replace(', @0', ''))
        before = replace(board, inventory=tuple(
            untagged if i == original else i for i in board.inventory))
        policy = HengbotPolicy()
        policy.prime(before)
        policy._town_claim_bar_enforced = True
        policy._in_store_ops_enabled = True
        policy.observe_store_screen(True)
        policy._home_full_relief = {
            'town': policy._effective_town_id(before),
            'sale': (policy._item_signature(untagged), STORE_ARMOURY, 0),
            'withdrawn': True, 'remaining': 1, 'deposits': (),
        }
        policy._store_visit = StoreVisit('town-errand', 'shopping', STORE_ARMOURY,
            StoreVisitPhase.OPERATING, opened_sequence=6335)
        inscription = policy.choose_key(before)
        self.assertEqual((inscription, policy.last_reason), ('{q@0\r', 'shop:in-store-inscribe'))
        self.assertEqual(policy._batch_sell_pending['entries'][0]['count'], 1)
        policy.confirm_key_posted(inscription)
        key = policy.choose_key(after)
        self.assertEqual((key, policy.last_reason), ('d03\ry', 'shop:in-store-sell'))
        entry = policy._batch_sell_pending['entries'][0]
        self.assertEqual((entry['count'], entry['quantity']), (3, 3))
        self.assertIsNone(policy._s33_shadow_verdict(after, key)['would_stop'])


class SaleZeroValueRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = (Path(__file__).parent / 'fixtures/sale-zero-value-20261005.json.gz').read_bytes()
        assert hashlib.sha256(payload).hexdigest() == '4ead2e73fd2acfb4f38aef66759317b81b6320cee1dd9cd8ee5a2c62dfbc24ba'
        cls.data = json.loads(gzip.decompress(payload))

    def scene(self):
        row = dict(self.data['states'][0]['row'], grid_map=self.data['grid_map'])
        board = replace(parse_snapshot(row), protocol_version=2)
        policy = HengbotPolicy(baseitem_costs={(75, 9): 0})
        policy.prime(board)
        policy.observe_store_screen(True)
        return policy, board, board.inventory[0]

    def test_recorded_trip_and_later_board_are_explicitly_distinct(self):
        rows = [e['row'] for e in self.data['decisions']]
        self.assertEqual([r['decision_sequence'] for r in rows], [1727, 1728, 1729])
        self.assertEqual([r['key'] for r in rows], ['{a@0\r', 'd05\ry', '\x1b'])
        self.assertEqual([r['reason'] for r in rows],
                         ['shop:in-store-inscribe', 'shop:in-store-sell',
                          'store:in-store-breaker:unowned-screen'])
        self.assertEqual([e['line'] for e in self.data['decisions']], [2352, 2353, 2354])
        self.assertEqual(rows[1]['turn'], 12278410)
        policy, board, target = self.scene()
        self.assertEqual(self.data['states'][0]['line'], 2336)
        self.assertEqual(board.turn, 12455838)
        self.assertEqual((target.slot, target.tval, target.sval, target.count, target.inscription),
                         ('a', 75, 9, 5, '@0'))
        self.assertTrue(target.known and target.aware and target.is_broken)
        self.assertFalse(policy._store_accepts_sale(board.store.store_type, target))

    def test_zero_value_rejected_by_selection_and_all_emission_seams(self):
        policy, board, target = self.scene()
        self.assertIsNone(policy._find_low_level_sale(board))
        self.assertNotIn(target, policy._current_store_sale_candidates(board))
        self.assertIsNone(policy._home_full_sale_candidate(board, target))
        self.assertIsNone(policy._town_organization_sale_store(board, target))
        self.assertIsNone(policy._batch_sale_entry(board, target, '0'))
        self.assertIsNone(policy._batch_sell_key(board, [target]))
        self.assertEqual(policy._store_sell_key(board, target, 'shop:sell-test'), '\x1b')
        self.assertIsNone(policy._batch_sell_pending)

    def test_pending_inscription_and_in_store_preview_recheck_value(self):
        policy, board, target = self.scene()
        policy._batch_sell_pending = {
            'store_type': board.store.store_type, 'phase': 'await-inscription',
            'entries': [{'signature': policy._sale_item_identity(target), 'tag': '0'}],
            'before_gold': board.player.gold,
        }
        self.assertIsNone(policy._in_store_selection(board))
        self.assertEqual(policy._batch_sell_key(board), '\x1b')
        self.assertEqual(policy.last_reason, 'shop:sale-unaccepted-leave')
        self.assertIsNone(policy._batch_sell_pending)

    def test_reverting_acceptance_restores_the_recorded_bad_tail(self):
        policy, board, target = self.scene()
        # Declared reconstruction from the later board, not a trip checkpoint.
        # This pin fails if the eligibility correction is removed.
        with patch.object(policy, '_store_accepts_sale', return_value=True):
            self.assertEqual(policy._batch_sale_entry(board, target, '0')['sell'], 'd05\ry')
        self.assertIsNone(policy._batch_sale_entry(board, target, '0'))

    def test_positive_stack_keeps_correct_quantity_overwrite_chain(self):
        policy, board, target = self.scene()
        # Declared counterfactual: change the zero-cost potion into Cure Light.
        target = replace(target, sval=34, is_broken=False, name='Cure Light Wounds {@0}')
        board = replace(board, inventory=(target,))
        for count, quantity in ((1, 1), (5, 5), (15, 15), (50, 50)):
            current = replace(target, count=count)
            view = replace(board, inventory=(current,))
            with patch.object(policy, '_retention_surplus', return_value=quantity):
                entry = policy._batch_sale_entry(view, current, '0')
            self.assertEqual(entry['sell'], 'd0' + (f'{quantity}\r' if count > 1 else '') + 'y')
        with patch.object(policy, '_retention_surplus', return_value=2):
            entry = policy._batch_sale_entry(replace(board, inventory=(replace(target, count=5),)),
                                             replace(target, count=5), '0')
        self.assertEqual(entry['sell'], 'd02\ry')

    def test_visible_zero_classes_and_unknown_flavor_boundary(self):
        from hengbot.store_sale import ZERO_BASE_KINDS
        policy, board, original = self.scene()
        from hengbot.store_sale import _value_knowledge
        self.assertEqual(ZERO_BASE_KINDS, frozenset(
            tuple(map(int, kind.split(':'))) for kind, value in _value_knowledge()['baseitems'].items()
            if value['cost'] <= 0))
        for tval, sval in ZERO_BASE_KINDS:
            target = replace(original, tval=tval, sval=sval, is_broken=False)
            self.assertFalse(policy._store_accepts_sale(STORE_BLACK, target), (tval, sval))
            self.assertTrue(policy._store_accepts_sale(STORE_HOME, target))
        for target in (
            replace(original, sval=34, is_broken=True),
            replace(original, sval=34, is_broken=False, is_cursed=True),
            replace(original, tval=23, sval=17, is_broken=False, to_h=-2, to_d=1),
            replace(original, tval=18, sval=1, is_broken=False, to_h=1, to_d=-2),
            replace(original, tval=45, sval=24, is_broken=False, to_a=-2),
            replace(original, tval=39, sval=1, is_broken=False, pval=-1),
            replace(original, tval=7, sval=1, is_broken=False, pval=0),
            replace(original, tval=23, sval=17, is_broken=False,
                    damage_dice_num=0, damage_dice_sides=5),
            replace(original, tval=75, sval=999, is_broken=False),
        ):
            self.assertFalse(policy._store_accepts_sale(STORE_BLACK, target))
        unknown = replace(original, aware=False, known=False, is_broken=False, sval=-1)
        self.assertTrue(policy._store_accepts_sale(board.store.store_type, unknown))
        aware = replace(original, known=False, is_broken=False)
        self.assertFalse(policy._store_accepts_sale(board.store.store_type, aware))


    def test_definition_zero_cost_ego_and_fixed_artifact_classes(self):
        from hengbot.store_sale import _value_knowledge, EGO_SLOTS
        policy, board, original = self.scene()
        knowledge = _value_knowledge()
        for ego in knowledge['egos']:
            if ego['cost'] > 0:
                continue
            kind, base = next((kind, base) for kind, base in knowledge['baseitems'].items()
                              if base['cost'] > 0
                              and EGO_SLOTS.get(int(kind.split(':')[0])) == ego['slot'])
            tval, sval = map(int, kind.split(':'))
            num, sides = map(int, base['base_dice'].split('d'))
            target = replace(original, name='item ' + ego['name']['en'], tval=tval,
                             sval=sval, is_broken=False, is_ego=True, fully_known=True,
                             pval=0, charges=0, damage_dice_num=num, damage_dice_sides=sides)
            self.assertFalse(policy._store_accepts_sale(STORE_BLACK, target), target.name)
        for artifact in knowledge['artifacts']:
            if artifact['cost'] > 0:
                continue
            kind = artifact['base_item']
            target = replace(original, name=artifact['name']['en'],
                             tval=kind['type_value'], sval=kind['subtype_value'],
                             is_broken=False, is_artifact=True, fully_known=True)
            self.assertFalse(policy._store_accepts_sale(STORE_BLACK, target), target.name)

    def test_flag_value_total_and_fixed_artifact_early_return(self):
        from hengbot.store_sale import _flag_cost, _value_knowledge
        policy, board, original = self.scene()
        knowledge = _value_knowledge()
        numbers = knowledge['flag_numbers']
        flags = lambda *names: frozenset(numbers[name] for name in names)
        self.assertEqual(_flag_cost(flags('KILL_DRAGON', 'SLAY_DRAGON'), 0, knowledge), 2800)
        self.assertEqual(_flag_cost(flags('BRAND_ACID', 'BRAND_COLD'), 0, knowledge), 12600)
        self.assertEqual(_flag_cost(flags('VAMPIRIC', 'BRAND_COLD'), 0, knowledge), 11500)
        sword = replace(original, tval=23, sval=17, name='Long Sword', is_broken=False,
                        damage_dice_num=2, damage_dice_sides=5, pval=0, fully_known=True, known_flags=flags('DRAIN_EXP'))
        self.assertFalse(policy._store_accepts_sale(STORE_BLACK, sword))
        self.assertTrue(policy._store_accepts_sale(STORE_BLACK,
            replace(sword, known_flags=flags('DRAIN_EXP', 'TELEPATHY'))))
        artifact = next(e for e in knowledge['artifacts'] if e['name']['en'] == 'of Galadriel')
        kind = artifact['base_item']
        fixed = replace(original, tval=kind['type_value'], sval=kind['subtype_value'],
                        name='The Phial of Galadriel', is_artifact=True, is_broken=False,
                        fully_known=True, pval=-1, to_a=-10)
        self.assertTrue(policy._store_accepts_sale(STORE_BLACK, fixed))
        self.assertFalse(policy._store_accepts_sale(STORE_BLACK,
            replace(fixed, known_flags=flags('DRAIN_EXP'))))

    def test_type_exceptions_are_shared_with_the_value_gate(self):
        from hengbot.model import STORE_GENERAL, STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON
        from hengbot.model import SV_HAFTED_WIZSTAFF, SPELLBOOK_TVALS, TVAL_HISSATSU_BOOK
        policy, board, original = self.scene()
        plain = replace(original, is_broken=False)
        self.assertTrue(policy._store_accepts_sale(STORE_GENERAL, replace(plain, sval=0)))
        self.assertFalse(policy._store_accepts_sale(STORE_GENERAL, replace(plain, sval=34)))
        rod = replace(plain, tval=66, sval=12)
        self.assertTrue(policy._store_accepts_sale(STORE_GENERAL, rod))
        self.assertFalse(policy._store_accepts_sale(STORE_GENERAL, replace(rod, sval=5)))
        wizard = replace(plain, tval=21, sval=SV_HAFTED_WIZSTAFF)
        self.assertFalse(policy._store_accepts_sale(STORE_WEAPON, wizard))
        self.assertTrue(policy._store_accepts_sale(STORE_MAGIC, wizard))
        sword = replace(plain, tval=23, sval=17, damage_dice_num=2, damage_dice_sides=5, pval=0)
        self.assertFalse(policy._store_accepts_sale(STORE_TEMPLE, sword))
        self.assertTrue(policy._store_accepts_sale(STORE_TEMPLE,
            replace(sword, known_flags=frozenset({92}))))
        for tval in SPELLBOOK_TVALS:
            book = replace(plain, tval=tval, sval=2)
            self.assertEqual(policy._store_accepts_sale(8, book), tval != TVAL_HISSATSU_BOOK)
        self.assertTrue(policy._store_accepts_sale(9, original))

    def test_unpriced_artifact_rival_still_occupies_its_numeric_tag(self):
        from hengbot.store_sale import _value_knowledge
        policy, board, original = self.scene()
        artifact = next(e for e in _value_knowledge()['artifacts']
                        if e['base_item']['type_value'] == 45 and e['cost'] > 0)
        kind = artifact['base_item']
        # Declared constructed: the game's known fixed-artifact value is
        # positive, while the bot cannot price its still-hidden extra flags.
        rival = replace(original, slot='a', name=artifact['name']['en'] + ' {@0}',
                        tval=kind['type_value'], sval=kind['subtype_value'], count=1,
                        pval=0, charges=0, is_broken=False, is_artifact=True,
                        fully_known=False)
        intended = replace(original, slot='b', name='Cure Light Wounds {@0}',
                           sval=34, count=1, pval=0, charges=0, is_broken=False)
        board = replace(board, inventory=(rival, intended))
        self.assertFalse(policy._store_accepts_sale(board.store.store_type, rival))
        self.assertTrue(policy._store_accepts_sale(board.store.store_type, intended))
        self.assertFalse(policy._sale_tag_is_unique(board, intended, '0'))
        self.assertEqual(policy._batch_sell_key(board, [intended]), '{b@1\r')
        tagged = replace(intended, inscription='@1', name='Cure Light Wounds {@1}')
        observed = replace(board, inventory=(rival, tagged))
        self.assertEqual(policy._batch_sell_key(observed), 'd1y')


    def test_shared_ego_names_use_the_equipment_kind(self):
        from hengbot.store_sale import _value_knowledge, _named_definition
        policy, board, original = self.scene()
        knowledge = _value_knowledge()
        helmet = replace(original, tval=32, sval=2, name='Helm of Darkness',
                         is_broken=False, is_ego=True, fully_known=True,
                         pval=0, charges=0, damage_dice_num=0, damage_dice_sides=0)
        lamp = replace(helmet, tval=39, sval=1, name='Lamp of Darkness')
        self.assertEqual(_named_definition(helmet, knowledge['egos'])['cost'], 800)
        self.assertEqual(_named_definition(lamp, knowledge['egos'])['cost'], 0)
        self.assertTrue(policy._store_accepts_sale(STORE_ARMOURY, helmet))
        self.assertFalse(policy._store_accepts_sale(STORE_BLACK, lamp))
        sword = replace(helmet, tval=23, sval=17, name='Long Sword of Slaying',
                        to_a=-10, damage_dice_num=2, damage_dice_sides=5)
        self.assertEqual(_named_definition(sword, knowledge['egos'])['cost'], 500)
        self.assertFalse(policy._store_accepts_sale(STORE_BLACK, sword))


if __name__ == '__main__':
    unittest.main()
