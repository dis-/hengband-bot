import sys
import unittest
from pathlib import Path
import json
from collections import Counter
import tests  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from item_sink_lint import (ADAPTER_PATH, POLICY_ROOT, analyze_repository,
                            analyze_source, direct_calls, producer_names)


class ItemSinkLintTest(unittest.TestCase):
    def test_repository_item_sinks(self):
        self.assertEqual(analyze_repository(), [])

    def test_raw_deposit_mutant_fails(self):
        self.assertTrue(analyze_source("def new_selector(item):\n return 'd' + item.slot\n", names=set()))

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
    self._record_decision_claim(snapshot, key)
    return key
'''
        findings = analyze_source(source, 'policy.py', names=set(), check_exit=True)
        self.assertTrue(any('exactly one non-None return' in finding for finding in findings))

    def test_none_exit_cannot_bypass_final_record(self):
        source = """
def choose_key(self, snapshot):
    if stop:
        return None
    key = self._enforce_town_claim_result(snapshot, key)
    self._record_decision_claim(snapshot, key)
    return key
"""
        self.assertTrue(analyze_source(source, 'policy.py', names=set()))

    def test_returned_key_must_be_the_recorded_final_key(self):
        source = """
def choose_key(self, snapshot):
    key = self._enforce_town_claim_result(snapshot, key)
    self._record_decision_claim(snapshot, other)
    return key
"""
        self.assertTrue(analyze_source(source, 'policy.py', names=set()))

    def test_enforcement_result_cannot_be_discarded_at_exit(self):
        source = """
def choose_key(self, snapshot):
    discarded = self._enforce_town_claim_result(snapshot, key)
    self._record_decision_claim(snapshot, key)
    return key
"""
        self.assertTrue(analyze_source(source, 'policy.py', names=set()))

    def test_low_level_adapter_cannot_bypass_verdict_in_a_new_module(self):
        for source in (
            'def selector(executor, snapshot, item):\n return executor.request_wield(snapshot, "goal", item, "main_hand", {})',
            'def selector(executor, snapshot):\n return executor.request_takeoff(snapshot, "goal", "a")',
            'def selector(executor, snapshot, item):\n mutate = executor.request_wield\n return mutate(snapshot, "goal", item, "main_hand", {})',
            'def selector(policy, item):\n destroy = policy._destroy_item_key\n return destroy(item)',
        ):
            self.assertTrue(analyze_source(source, 'town_new_selector.py', names=set()))
