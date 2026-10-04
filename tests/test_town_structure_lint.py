import ast
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import town_structure_lint as lint


class TownStructureLintTest(unittest.TestCase):
    def sources(self, body, helpers='', extra=None):
        sources = {'policy.py': 'class HengbotPolicy:\n' + body + helpers,
                   'claim_ladder.py': ''}
        sources.update(extra or {})
        return sources

    def test_repository_exact_reviewed_baselines(self):
        self.assertEqual(lint.analyze_repository(), [])

    def test_mutations_in_actual_repository_town_paths(self):
        sources = {path.relative_to(lint.POLICY_ROOT).as_posix(): path.read_text(encoding='utf8')
                   for path in lint.POLICY_ROOT.rglob('*.py')}
        producers = json.loads(lint.PRODUCER_BASELINE.read_text(encoding='utf8'))
        intents = json.loads(lint.INTENT_BASELINE.read_text(encoding='utf8'))

        tree = ast.parse(sources['policy.py'])
        policy = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'HengbotPolicy')
        choose = next(node for node in policy.body if isinstance(node, ast.FunctionDef) and node.name == '_choose_key')
        choose.body.insert(0, ast.parse('if snapshot.in_town:\n return self._new_town_work(snapshot)').body[0])
        policy.body.append(ast.parse('def _new_town_work(self, snapshot):\n return "5"').body[0])
        mutant = dict(sources, **{'policy.py': ast.unparse(ast.fix_missing_locations(tree))})
        self.assertTrue(any('HengbotPolicy._new_town_work: new unregistered' in finding
                            for finding in lint.analyze_sources(mutant, producers, intents)))

        tree = ast.parse(sources['policy.py'])
        policy = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'HengbotPolicy')
        read = next(node for node in policy.body if isinstance(node, ast.FunctionDef) and node.name == '_read_key')
        read.body[:0] = ast.parse('signature = self._item_signature(item)\nself._foo_pending = signature').body
        mutant = dict(sources, **{'policy.py': ast.unparse(ast.fix_missing_locations(tree))})
        self.assertTrue(any('_foo_pending: new unregistered item intent' in finding
                            for finding in lint.analyze_sources(mutant, producers, intents)))

        from item_sink_lint import analyze_source, ADAPTER_PATH, producer_names
        tree = ast.parse(sources['policy.py'])
        policy = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'HengbotPolicy')
        read = next(node for node in policy.body if isinstance(node, ast.FunctionDef) and node.name == '_read_key')
        read.body.insert(0, ast.parse('return "q" + item.slot').body[0])
        self.assertTrue(any('raw item command' in finding for finding in analyze_source(
            ast.unparse(ast.fix_missing_locations(tree)), 'policy.py', names=producer_names(),
            adapters=json.loads(ADAPTER_PATH.read_text(encoding='utf8')))))

    def test_undecorated_town_wait_producer_mutation(self):
        original = self.sources(' def choose_key(self, snapshot):\n  return None\n')
        self.assertEqual(lint.analyze_sources(original, {}, {}), [])
        mutant = self.sources(
            ' def choose_key(self, snapshot):\n  key = self._new_town_work(snapshot)\n  return key\n',
            ' def _new_town_work(self, snapshot):\n  return "5"\n')
        findings = lint.analyze_sources(mutant, {}, {})
        self.assertTrue(any('_new_town_work: new unregistered' in f for f in findings))

    def test_alias_callback_and_opaque_return_paths_are_default_deny(self):
        for expression in ('self._new_town_work(snapshot)',
                           'self._adapter(lambda: self._new_town_work(snapshot))',
                           'getattr(self, "_new_town_work")(snapshot)',
                           'call(snapshot)'):
            source = self.sources(
                ' def choose_key(self, snapshot):\n  call = self._new_town_work\n  key = ' + expression + '\n  return key\n',
                ' def _new_town_work(self, snapshot):\n  return "5"\n'
                ' def _adapter(self, call):\n  return call()\n')
            with self.subTest(expression=expression):
                self.assertTrue(any('_new_town_work: new unregistered' in f
                                    for f in lint.analyze_sources(source, {}, {})))

    def test_module_alias_of_new_producer_is_default_deny(self):
        for expression in ('work(snapshot)', 'self.adapt(work, snapshot)'):
            sources = self.sources(' def choose_key(self, snapshot):\n  return ' + expression + '\n',
                ' def adapt(self, call, snapshot):\n  return call(snapshot)\n')
            sources['policy.py'] += '\ndef new_producer(snapshot):\n return "5"\nwork = new_producer\n'
            self.assertTrue(any('policy.py:new_producer: new unregistered' in finding
                                for finding in lint.analyze_sources(sources, {}, {})))

    def test_method_alias_of_new_producer_is_default_deny(self):
        sources = self.sources(' def choose_key(self, snapshot):\n  return self.work(snapshot)\n',
            ' def new_producer(self, snapshot):\n  return "5"\n work = new_producer\n')
        self.assertTrue(any('HengbotPolicy.new_producer: new unregistered' in finding
                            for finding in lint.analyze_sources(sources, {}, {})))

    def test_registration_requires_both_marker_and_ladder(self):
        body = (' def choose_key(self, snapshot):\n  return self._new_town_work(snapshot)\n'
                ' @claims("home-visit")\n def _new_town_work(self, snapshot):\n  return "5"\n')
        sources = self.sources(body)
        baseline = {'policy.py:HengbotPolicy.choose_key': 'delegated adapter: public decision exit.'}
        self.assertTrue(any('_new_town_work: new unregistered' in f
                            for f in lint.analyze_sources(sources, baseline, {})))
        sources['claim_ladder.py'] = '_decide("_new_town_work", "home-visit")'
        self.assertEqual(lint.analyze_sources(sources, baseline, {}), [])
        sources['policy.py'] = sources['policy.py'].replace(' @claims("home-visit")\n', '')
        self.assertTrue(lint.analyze_sources(sources, baseline, {}))

    def test_relative_import_mixin_is_included(self):
        sources = self.sources(' def choose_key(self, snapshot):\n  return self.new_work(snapshot)\n',
            extra={'new_mixin.py': 'class NewMixin:\n def new_work(self, snapshot):\n  return "5"\n'})
        sources['policy.py'] = 'from .new_mixin import NewMixin\n' + sources['policy.py']
        self.assertTrue(any('NewMixin.new_work: new unregistered' in f
                            for f in lint.analyze_sources(sources, {}, {})))

    def test_subpackage_and_import_alias_producer_is_included(self):
        sources = self.sources(' def choose_key(self, snapshot):\n  return work(snapshot)\n',
            extra={'town/work.py': 'WAIT = "5"\ndef produce(snapshot):\n return WAIT\n'})
        sources['policy.py'] = 'from hengbot.town.work import produce as work\n' + sources['policy.py']
        self.assertTrue(any('town/work.py:produce: new unregistered' in f
                            for f in lint.analyze_sources(sources, {}, {})))

    def test_relative_package_import_and_callback_alias_are_resolved(self):
        for import_line, expression in (
            ('from . import work', 'work.produce(snapshot)'),
            ('from hengbot import work', 'work.produce(snapshot)'),
            ('from hengbot.work import produce as callback', 'self.adapt(callback, snapshot)'),
        ):
            sources = self.sources(' def choose_key(self, snapshot):\n  return ' + expression + '\n',
                ' def adapt(self, call, snapshot):\n  return call(snapshot)\n',
                {'work.py': 'def produce(snapshot):\n return "5"\n'})
            sources['policy.py'] = import_line + '\n' + sources['policy.py']
            self.assertTrue(any('work.py:produce: new unregistered' in f
                                for f in lint.analyze_sources(sources, {}, {})))

    def test_ancestor_with_non_mixin_name_is_scanned(self):
        sources = self.sources(' def choose_key(self, snapshot):\n  return None\n', extra={
            'ancestor.py': 'class ItemWork:\n def prepare(self, item):\n  self.future_item = item\n'})
        sources['policy.py'] = 'from .ancestor import ItemWork\n' + sources['policy.py'].replace(
            'class HengbotPolicy:', 'class HengbotPolicy(ItemWork):')
        self.assertTrue(any('future_item: new unregistered item intent' in f
                            for f in lint.analyze_sources(sources, {}, {})))

    def test_reverse_import_driver_is_not_a_policy_descendant(self):
        sources = self.sources(' def choose_key(self, snapshot):\n  return None\n', extra={
            'driver.py': 'from hengbot.policy import HengbotPolicy\ndef new_work():\n return "5"\n'})
        self.assertEqual(lint.analyze_sources(sources, {}, {}), [])

    def test_stale_producer_baseline_entry_fails(self):
        sources = self.sources(' def choose_key(self, snapshot):\n  return None\n')
        self.assertTrue(any('disappeared' in f for f in lint.analyze_sources(sources,
            {'policy.py:HengbotPolicy.removed': 'pure helper: old helper.'}, {})))

    def test_new_pending_signature_attribute_mutation(self):
        for statement in ('self._foo_pending = signature',
                          'self._foo_pending = self._item_signature(item)',
                          'setattr(self, "_foo_pending", signature)',
                          'self._foo_pending.append(signature)'):
            sources = self.sources(' def choose_key(self, snapshot):\n  return None\n'
                ' def remember(self, item):\n  signature = self._item_signature(item)\n  ' + statement + '\n')
            with self.subTest(statement=statement):
                self.assertTrue(any('_foo_pending: new unregistered item intent' in f
                                    for f in lint.analyze_sources(sources, {}, {})))

    def test_signature_identity_and_typed_item_without_pending_name(self):
        for expr, annotation in (('self._item_signature(item)', ''),
                                 ('equipment_identity(item)', ''),
                                 ('equipment_move_identity(item)', ''),
                                 ('InventoryItem()', ''), ('item', ': InventoryItem')):
            sources = self.sources(' def choose_key(self, snapshot):\n  return None\n'
                f' def remember(self, item{annotation}):\n  selected = {expr}\n  self.future_operation = selected\n')
            self.assertTrue(any('future_operation: new unregistered' in f
                                for f in lint.analyze_sources(sources, {}, {})))

    def test_signature_parameter_slot_and_dictionary_key_intents(self):
        for parameters, statement in (
            ('signature', 'self.future_operation = signature'),
            ('item', 'self.future_slot = item.slot'),
            ('signature', 'self.future_operation[signature] = True'),
            ('snapshot', 'self.future_operation = snapshot.inventory[0]'),
        ):
            sources = self.sources(' def choose_key(self, snapshot):\n  return None\n'
                f' def remember(self, {parameters}):\n  {statement}\n')
            self.assertTrue(any('new unregistered item intent' in f
                                for f in lint.analyze_sources(sources, {}, {})))

    def test_registered_source_requires_composed_component(self):
        sources = self.sources(' def choose_key(self, snapshot):\n  self._foo_pending = None\n  return None\n')
        sources['item_reservation.py'] = 'ITEM_RESERVATION_SOURCES = {"_foo_pending": ("unused", "future operation")}\n'
        self.assertTrue(any('composed predicate' in f for f in lint.analyze_sources(sources, {}, {})))
        sources['item_reservation.py'] += '_SOURCE_PREDICATES = {"unused": predicate}\n'
        self.assertEqual(lint.analyze_sources(sources, {}, {}), [])

    def test_explicit_non_item_intent_reason_and_staleness(self):
        sources = self.sources(' def choose_key(self, snapshot):\n  self._probe_pending = True\n  return None\n')
        exclusion = {'_probe_pending': 'UI observation flag, not an item selector.'}
        self.assertEqual(lint.analyze_sources(sources, {}, exclusion), [])
        self.assertTrue(lint.analyze_sources(sources, {}, {'_probe_pending': ''}))
        sources['policy.py'] = sources['policy.py'].replace('  self._probe_pending = True\n', '')
        self.assertTrue(any('disappeared' in f for f in lint.analyze_sources(sources, {}, exclusion)))

    def test_empty_or_unreviewed_baseline_reasons_fail(self):
        self.assertTrue(lint.analyze_sources(self.sources(' def choose_key(self, snapshot):\n  return "5"\n'),
            {'policy.py:HengbotPolicy.choose_key': 'exempt module'}, {}))


if __name__ == '__main__':
    unittest.main()
