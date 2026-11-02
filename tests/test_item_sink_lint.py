import ast
import sys
import unittest
from pathlib import Path
import json
from collections import Counter
import tests  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from item_sink_lint import (ADAPTER_PATH, POLICY_ROOT, analyze_repository,
                            analyze_source, direct_calls, producer_names)
import town_structure_lint as lint  # noqa: E402


class ItemSinkLintTest(unittest.TestCase):
    def test_repository_item_sinks(self):
        self.assertEqual(analyze_repository(), [])

    def test_raw_deposit_mutant_fails(self):
        self.assertTrue(analyze_source("def new_selector(item):\n return 'd' + item.slot\n", names=set()))

    def test_raw_consumption_command_mutations_fail(self):
        for prefix in ('q', 'r', 'E', 'u', 'a', 'z', 'f', 'v', '\\F'):
            with self.subTest(prefix=prefix):
                source = f'def new_selector(item):\n return {prefix!r} + item.slot\n'
                self.assertTrue(any('raw item command' in f for f in analyze_source(source, names=set())))
        for constant in ('QUAFF_KEY', 'READ_KEY', 'EAT_KEY', 'USE_STAFF_KEY',
                         'AIM_WAND_KEY', 'ZAP_ROD_KEY', 'FIRE_KEY', 'THROW_KEY', 'REFILL_KEY'):
            source = f'def new_selector(item):\n return {constant} + item.slot\n'
            self.assertTrue(analyze_source(source, names=set()))
        for source in (
            'from hengbot.policy_constants import QUAFF_KEY as Q\ndef consume(item):\n return Q + item.slot',
            'Q = QUAFF_KEY\ndef consume(item):\n return Q + item.slot',
            'Q = "q"\ndef consume(item):\n return Q + item.slot',
            'def consume(item):\n return "\\\\F{}".format(item.slot)',
        ):
            self.assertTrue(analyze_source(source, names=set()))

    def test_building_menu_pin_does_not_exempt_item_command_in_same_function(self):
        source = 'def _fixed_quest_building_key(item):\n return "q" + item.slot\n'
        self.assertTrue(analyze_source(source, 'policy_quest.py', names=set()))

    def test_rumor_menu_macro_pin_is_exact(self):
        source = 'RUMOR_KEY = "r"\nRUMOR_READ_KEY = RUMOR_KEY + "\\r"\n'
        self.assertEqual(analyze_source(source, 'policy_constants.py', names=set()), [])
        self.assertTrue(analyze_source(source + 'RAW = RUMOR_KEY + slot\n',
                                       'policy_constants.py', names=set()))
        self.assertTrue(analyze_source(source + 'OTHER = RUMOR_KEY + "\\r"\n',
                                       'policy_constants.py', names=set()))

    def test_tower_recharge_menu_pin_is_exact(self):
        # The Tower of Sorcery's 'a' (building_recharge_all) + 'y', moved out of
        # policy by db16ffae5; an item 'a' (aim a wand) in the module still fails.
        source = ('RECHARGE_ALL_ACTION_KEY = "a"\n'
                  'RECHARGE_ALL_TAIL = RECHARGE_ALL_ACTION_KEY + "y" + LEAVE_STORE_KEY\n')
        self.assertEqual(analyze_source(source, 'morivant_tower.py', names=set()), [])
        self.assertTrue(analyze_source(source + 'def aim(item):\n return RECHARGE_ALL_ACTION_KEY + item.slot\n',
                                       'morivant_tower.py', names=set()))
        self.assertTrue(analyze_source(source + 'AGAIN = RECHARGE_ALL_ACTION_KEY + "y"\n',
                                       'morivant_tower.py', names=set()))

    def test_new_selector_cannot_serialize_reserved_item_without_verdict(self):
        for expression in ('item_command("deposit", reserved)',
                           'item_command("deposit", reserved, None)',
                           'item_command("deposit", reserved, True)',
                           'checked_item_command(policy, "deposit", reserved, None)'):
            with self.subTest(expression=expression):
                self.assertTrue(any('requires a ReservationVerdict' in finding for finding in
                    analyze_source('def new_selector(policy, reserved):\n return ' + expression,
                                   names=set())))

    def test_verdict_construction_outside_core_fails(self):
        self.assertTrue(analyze_source('def bypass(item):\n return ReservationVerdict("sell")', names=set()))

    def test_new_direct_producer_mutant_fails(self):
        source = '''
@claims(ClaimOwner.HOME_VISIT)
def town_producer(self, snapshot):
    return None
def new_path(self, snapshot):
    return self.town_producer(snapshot)
'''
        self.assertTrue(any('outside its entry/adapter' in finding
                            for finding in analyze_source(source, names=set())))
        admitted = source.replace('return self.town_producer(snapshot)',
            'return self._town_producer_entry("pinned-rung", lambda: self.town_producer(snapshot))')
        self.assertEqual(analyze_source(admitted, names=set()), [])

    def test_new_call_in_existing_adapter_is_rejected(self):
        original = 'def adapter(self, snapshot):\n self.town_producer(snapshot)\n'
        rows = list(direct_calls(original, {'town_producer'}))
        adapters = {'mutant.py:adapter': {rows[0][1]: 1}}
        self.assertEqual(analyze_source(original, names={'town_producer'}, adapters=adapters), [])
        mutant = original + ' self.town_producer(snapshot)\n'
        self.assertTrue(analyze_source(mutant, names={'town_producer'}, adapters=adapters))
        moved = 'def adapter(self, snapshot):\n if bypass:\n  self.town_producer(snapshot)\n'
        self.assertTrue(analyze_source(moved, names={'town_producer'}, adapters=adapters))

    def test_every_pinned_adapter_call_still_exists(self):
        adapters = json.loads(ADAPTER_PATH.read_text(encoding='utf8'))
        names = producer_names()
        sources = {path.name: path.read_text(encoding='utf8') for path in POLICY_ROOT.glob('*.py')}
        current = {}
        for filename, source in sources.items():
            for function, expression, _line in direct_calls(source, names):
                current.setdefault(f'{filename}:{function}', Counter())[expression] += 1
        for site, expressions in adapters.items():
            with self.subTest(site=site):
                self.assertEqual(current.get(site), Counter(expressions))
        for required in ('policy_home.py:_home_full_relief_key', 'policy_shop.py:_shop_core',
                         'policy_town.py:_town_procurement_decision',
                         'policy_town.py:_return_to_town_key', 'policy.py:_choose_key'):
            self.assertIn(required, adapters)

    def test_raw_command_forms_and_aliases_fail(self):
        for expression in ('SELL_KEY + item.slot', 'BUY_KEY + letter',
                           'f"0{item.count}{DESTROY_COMMAND}{item.slot}"',
                           'f"d{item.slot}"', 'WIELD_KEY + item.slot',
                           'TAKEOFF_KEY + slot_key', 'INSCRIBE_KEY + item.slot'):
            with self.subTest(expression=expression):
                self.assertTrue(analyze_source('def new_path(item, letter, slot_key):\n return ' + expression,
                                               names=set()))
        self.assertTrue(analyze_source('def alias(item):\n prefix = SELL_KEY\n return prefix + item.slot',
                                       names=set()))
        for expression in ('"d{}".format(item.slot)', '"d%s" % item.slot',
                           '"".join(["d", item.slot])'):
            self.assertTrue(analyze_source('def formatting(item):\n return ' + expression, names=set()))
        self.assertTrue(analyze_source('def alias(item):\n prefix = "d"\n return prefix + item.slot',
                                       names=set()))

    def test_serializer_alias_and_overwritten_verdict_are_rejected(self):
        alias = '''
serialize = item_command
def bypass(item):
    return serialize("deposit", item, None)
'''
        self.assertTrue(analyze_source(alias, names=set()))
        overwritten = '''
def bypass(policy, snapshot, item):
    verdict = reservation_verdict(policy, snapshot, item, "home-visit", "deposit")
    verdict = None
    return item_command("deposit", item, verdict)
'''
        self.assertTrue(analyze_source(overwritten, names=set()))

    def test_serializer_has_required_verdict_signature(self):
        for signature in ('kind, item', 'kind, item, verdict=None', 'kind, item, verdict'):
            self.assertTrue(analyze_source(f'def item_command({signature}):\n return "d" + item.slot',
                                           'item_reservation.py', names=set()))

    def test_public_exit_mutant_is_rejected(self):
        source = '''
def choose_key(self, snapshot):
    if bypass:
        return "d" + snapshot.inventory[0].slot
    town_advance_hold(self, snapshot, key)
    return key
'''
        findings = analyze_source(source, 'policy.py', names=set(), check_exit=True)
        self.assertTrue(any('exactly one non-None return' in finding for finding in findings))

    def test_none_exit_cannot_bypass_final_record(self):
        source = """
def choose_key(self, snapshot):
    if stop:
        return None
    town_advance_hold(self, snapshot, key)
    return key
"""
        self.assertTrue(analyze_source(source, 'policy.py', names=set()))

    def test_returned_key_must_be_the_recorded_final_key(self):
        source = """
def choose_key(self, snapshot):
    town_advance_hold(self, snapshot, other)
    return key
"""
        self.assertTrue(analyze_source(source, 'policy.py', names=set()))

    def test_observation_after_the_record_keeps_the_exit(self):
        # f7131f80e: the town cycle detector reads the final key after the record.
        exit_source = """
def choose_key(self, snapshot):
    town_advance_hold(self, snapshot, key)
    self._town_progress_note_command(key)
    return key
"""
        self.assertEqual(analyze_source(exit_source, 'policy.py', names=set()), [])
        for tail in ('    key = self._town_progress_note_command(key)\n',
                     '    self._town_progress_note_command(key := other)\n',
                     '    town_advance_hold(self, snapshot, other)\n'):
            with self.subTest(tail=tail):
                mutant = exit_source.replace('    self._town_progress_note_command(key)\n', tail)
                self.assertTrue(analyze_source(mutant, 'policy.py', names=set()))

    def test_low_level_adapter_cannot_bypass_verdict_in_a_new_module(self):
        for source in (
            'def selector(executor, snapshot, item):\n return executor.request_wield(snapshot, "goal", item, "main_hand", {})',
            'def selector(executor, snapshot):\n return executor.request_takeoff(snapshot, "goal", "a")',
            'def selector(executor, snapshot, item):\n mutate = executor.request_wield\n return mutate(snapshot, "goal", item, "main_hand", {})',
            'def selector(policy, item):\n destroy = policy._destroy_item_key\n return destroy(item)',
        ):
            self.assertTrue(analyze_source(source, 'town_new_selector.py', names=set()))


class ProducerMarkTest(unittest.TestCase):
    """The claims marks the item-sink review keys on (#47, 2026-11-01 triage).

    7dceaccad inserted _opening_q1_torches_reserved between the
    ``@claims(ClaimOwner.COMBAT)`` line and _ranged_attack_key: the predicate
    took the mark, the ranged-attack producer lost it, and its six reviewed
    direct calls (summoner kill, choke, ESP hunt, melee swarm, fundraising
    loadout, guarded loot) left the review unnoticed.
    """

    def test_ranged_attack_producer_keeps_its_combat_mark(self):
        from hengbot.claim_register import CLAIM_OWNER_ATTRIBUTE, ClaimOwner
        from hengbot.policy import HengbotPolicy
        self.assertIs(getattr(HengbotPolicy._ranged_attack_key, CLAIM_OWNER_ATTRIBUTE, None),
                      ClaimOwner.COMBAT)
        self.assertFalse(hasattr(HengbotPolicy._opening_q1_torches_reserved, CLAIM_OWNER_ATTRIBUTE))
        self.assertIn('_ranged_attack_key', producer_names())
        self.assertNotIn('_opening_q1_torches_reserved', producer_names())


def _policy_sources(body, extra=None):
    sources = {'policy.py': 'class HengbotPolicy:\n' + body, 'claim_ladder.py': ''}
    sources.update(extra or {})
    return sources


class ItemIntentLintTest(unittest.TestCase):
    """The item-intent half of town_structure_lint, which item_sink_lint runs.

    Moved from the retired tests.test_town_structure_lint (2026-11-01) with the producer baseline removed.
    """
    def test_mutations_in_actual_repository_paths(self):
        sources = {path.relative_to(lint.POLICY_ROOT).as_posix(): path.read_text(encoding='utf8')
                   for path in lint.POLICY_ROOT.rglob('*.py')}
        intents = json.loads(lint.INTENT_BASELINE.read_text(encoding='utf8'))

        def mutated_read_key(statements):
            tree = ast.parse(sources['policy.py'])
            policy = next(node for node in tree.body
                          if isinstance(node, ast.ClassDef) and node.name == 'HengbotPolicy')
            read = next(node for node in policy.body
                        if isinstance(node, ast.FunctionDef) and node.name == '_read_key')
            read.body[:0] = ast.parse(statements).body
            return ast.unparse(ast.fix_missing_locations(tree))

        mutant = dict(sources, **{'policy.py': mutated_read_key(
            'signature = self._item_signature(item)\nself._foo_pending = signature')})
        self.assertTrue(any('_foo_pending: new unregistered item intent' in finding
                            for finding in lint.analyze_sources(mutant, intents)))
        self.assertTrue(any('raw item command' in finding for finding in analyze_source(
            mutated_read_key('return "q" + item.slot'), 'policy.py', names=producer_names(),
            adapters=json.loads(ADAPTER_PATH.read_text(encoding='utf8')))))

    def test_ancestor_with_non_mixin_name_is_scanned(self):
        sources = _policy_sources(' def choose_key(self, snapshot):\n  return None\n', extra={
            'ancestor.py': 'class ItemWork:\n def prepare(self, item):\n  self.future_item = item\n'})
        sources['policy.py'] = 'from .ancestor import ItemWork\n' + sources['policy.py'].replace(
            'class HengbotPolicy:', 'class HengbotPolicy(ItemWork):')
        self.assertTrue(any('future_item: new unregistered item intent' in f
                            for f in lint.analyze_sources(sources, {})))

    def test_module_function_writing_through_policy_is_scanned(self):
        # #47 (2026-11-01 triage): mining_loadout.remember_combat_hands writes the
        # registered _normal_weapon_identity through its ``policy`` parameter;
        # the census saw only ``self`` and reported the source as disappeared.
        sources = _policy_sources(' def choose_key(self, snapshot):\n  return None\n', extra={
            'loadout.py': ('def remember(policy, item):\n policy._kept_identity = equipment_identity(item)\n'
                           'def helper(executor, item):\n executor._other_identity = equipment_identity(item)\n')})
        findings = lint.analyze_sources(sources, {})
        self.assertTrue(any('_kept_identity: new unregistered item intent (loadout.py:remember)' in f
                            for f in findings), findings)
        self.assertFalse(any('_other_identity' in f for f in findings), findings)
        repository = lint.intent_census({path.relative_to(POLICY_ROOT).as_posix(): path.read_text(encoding='utf8')
                                         for path in POLICY_ROOT.rglob('*.py')})
        self.assertIn('mining_loadout.py:remember_combat_hands', repository['_normal_weapon_identity'])

    def test_reverse_import_driver_has_no_findings(self):
        sources = _policy_sources(' def choose_key(self, snapshot):\n  return None\n', extra={
            'driver.py': 'from hengbot.policy import HengbotPolicy\ndef new_work():\n return "5"\n'})
        self.assertEqual(lint.analyze_sources(sources, {}), [])

    def test_new_pending_signature_attribute_mutation(self):
        for statement in ('self._foo_pending = signature',
                          'self._foo_pending = self._item_signature(item)',
                          'setattr(self, "_foo_pending", signature)',
                          'self._foo_pending.append(signature)'):
            sources = _policy_sources(' def choose_key(self, snapshot):\n  return None\n'
                ' def remember(self, item):\n  signature = self._item_signature(item)\n  ' + statement + '\n')
            with self.subTest(statement=statement):
                self.assertTrue(any('_foo_pending: new unregistered item intent' in f
                                    for f in lint.analyze_sources(sources, {})))

    def test_signature_identity_and_typed_item_without_pending_name(self):
        for expr, annotation in (('self._item_signature(item)', ''),
                                 ('equipment_identity(item)', ''),
                                 ('equipment_move_identity(item)', ''),
                                 ('InventoryItem()', ''), ('item', ': InventoryItem')):
            sources = _policy_sources(' def choose_key(self, snapshot):\n  return None\n'
                f' def remember(self, item{annotation}):\n  selected = {expr}\n  self.future_operation = selected\n')
            with self.subTest(expr=expr):
                self.assertTrue(any('future_operation: new unregistered' in f
                                    for f in lint.analyze_sources(sources, {})))

    def test_signature_parameter_slot_and_dictionary_key_intents(self):
        for parameters, statement in (
            ('signature', 'self.future_operation = signature'),
            ('item', 'self.future_slot = item.slot'),
            ('signature', 'self.future_operation[signature] = True'),
            ('snapshot', 'self.future_operation = snapshot.inventory[0]'),
        ):
            sources = _policy_sources(' def choose_key(self, snapshot):\n  return None\n'
                f' def remember(self, {parameters}):\n  {statement}\n')
            with self.subTest(statement=statement):
                self.assertTrue(any('new unregistered item intent' in f
                                    for f in lint.analyze_sources(sources, {})))

    def test_registered_source_requires_composed_component(self):
        sources = _policy_sources(' def choose_key(self, snapshot):\n  self._foo_pending = None\n  return None\n')
        sources['item_reservation.py'] = ('ITEM_RESERVATION_SOURCES = '
                                          '{"_foo_pending": ("unused", "future operation")}\n')
        self.assertTrue(any('composed predicate' in f for f in lint.analyze_sources(sources, {})))
        sources['item_reservation.py'] += '_SOURCE_PREDICATES = {"unused": predicate}\n'
        self.assertEqual(lint.analyze_sources(sources, {}), [])

    def test_explicit_non_item_intent_reason_and_staleness(self):
        sources = _policy_sources(' def choose_key(self, snapshot):\n  self._probe_pending = True\n  return None\n')
        exclusion = {'_probe_pending': 'UI observation flag, not an item selector.'}
        self.assertEqual(lint.analyze_sources(sources, exclusion), [])
        self.assertTrue(lint.analyze_sources(sources, {'_probe_pending': ''}))
        sources['policy.py'] = sources['policy.py'].replace('  self._probe_pending = True\n', '')
        self.assertTrue(any('disappeared' in f for f in lint.analyze_sources(sources, exclusion)))
