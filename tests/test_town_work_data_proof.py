"""The town-work review tax (#47, owner 2026-11-01 「一覧の作り直しの手間から」).

A census site the AST proves to be observational data needs no hand review and
the runtime index has no digests, so a body edit changes no generated file. An
unmapped site that can emit a town key still fails the manifest check.
"""
import tests  # noqa: F401 -- isolate runtime files
import ast
import json
from pathlib import Path
import sys
import textwrap
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import town_structure_lint as lint  # noqa: E402
import town_work_data_proof as data_proof  # noqa: E402
import town_work_manifest as generator  # noqa: E402

PROVED = {
    'compare': 'def f(snapshot):\n return snapshot.level > 3\n',
    'containers': 'def f(snapshot):\n return frozenset(x.slot for x in snapshot.items)\n',
    'local_list': 'def f(snapshot):\n found = []\n found.append(1)\n return len(found)\n',
    'arithmetic': 'def f(snapshot):\n count = snapshot.gold - 5\n return count // 2\n',
    'self_call': ('class P:\n def g(self):\n  return 1\n'
                  ' def f(self):\n  return self.g() + 1\n'),
}
UNPROVED = {
    'literal_key': 'def f(snapshot):\n return "5"\n',
    'fstring_key': 'def f(snapshot):\n return f"p{snapshot.slot}"\n',
    'stored_key': 'class P:\n def f(self):\n  return self.pending_key\n',
    'lambda_key': 'def f(snapshot):\n return lambda: "5"\n',
    'foreign_call': 'def f(table, key):\n return table.get(key)\n',
    'str_operator': 'def f(snapshot):\n return snapshot.prefix % 3\n',
    'send_seam': 'class P:\n def f(self):\n  self.send("5")\n  return True\n',
    'send_through_helper': ('def g(port):\n port.post_keys("5")\n'
                            'def f(port):\n g(port)\n return True\n'),
    'self_mutation': 'class P:\n def f(self):\n  self.cache = 1\n  return True\n',
    'owned_mutator': 'class P:\n def f(self, x):\n  self.items.append(x)\n  return True\n',
    'mutating_self_call': ('class P:\n def g(self):\n  self.cache = 1\n'
                           ' def f(self):\n  self.g()\n  return True\n'),
    'callback': 'def f(callback):\n callback()\n return True\n',
    'decorated': '@claims("x")\ndef f(snapshot):\n return True\n',
    # Step 10 (2026-11-11): what the module-level rules must still refuse.
    'or_key': 'def f(snapshot):\n return snapshot.ready or "5"\n',
    'and_key_last': 'def f(snapshot):\n return snapshot.ready and "5"\n',
    'max_of_keys': 'def f(snapshot):\n return max("5", snapshot.key)\n',
    'next_item': 'def f(snapshot):\n return next((i.slot for i in snapshot.items), None)\n',
    'str_constant': 'WAIT = "5"\ndef f(snapshot):\n return WAIT\n',
    'rebound_constant': 'WAIT = 1\ndef g():\n global WAIT\n WAIT = "5"\ndef f(snapshot):\n return WAIT\n',
    'str_class': 'class K(str):\n pass\ndef f(snapshot):\n return K("5")\n',
    'new_class': 'class K:\n def __new__(cls):\n  return "5"\ndef f(snapshot):\n return K()\n',
    'unknown_base': 'from enum import StrEnum\nclass K(StrEnum):\n A = "5"\ndef f(snapshot):\n return K("5")\n',
    'sending_init': ('class K:\n def __init__(self, port):\n  port.post_keys("5")\n'
                     'def f(port):\n K(port)\n return True\n'),
    'mutating_init': ('class K:\n def __init__(self, policy):\n  policy.cache = 1\n'
                      'def f(policy):\n return K(policy)\n'),
    'closure_free_name': 'WAIT = 1\ndef outer():\n WAIT = "5"\n def f():\n  return WAIT\n return f\n',
}
# Proved only with the module-level resolution (the sources) or the step 10 expression rules.
PROVED_WITH_SOURCES = {
    'empty_str': 'def f(snapshot):\n return ""\n',
    'and_chain': 'def f(snapshot):\n return snapshot.item and snapshot.level > 3\n',
    'max_constant': 'def f(snapshot):\n return max(1, snapshot.hp * snapshot.level)\n',
    'max_comprehension': 'def f(snapshot):\n return max((m.hp // 2 for m in snapshot.monsters), default=0)\n',
    'module_constant': 'LIMIT = 3\ndef f(snapshot):\n return LIMIT\n',
    'dataclass': ('from dataclasses import dataclass\n@dataclass\nclass Plan:\n step: int\n'
                  'def f(snapshot):\n return Plan(snapshot.level)\n'),
    'named_tuple': ('from typing import NamedTuple\nclass Plan(NamedTuple):\n step: int\n'
                    'class Wider(Plan):\n pass\ndef f(snapshot):\n return Wider(1)\n'),
}
# Conservative reviews: proved data (step 10, 2026-11-11) but hand-reviewed as action/producer. The hand
# review keeps their index rows; reclassifying them is an open question of the step 10 report.
CONSERVATIVE_REVIEWS = {'dungeon_shop.py:entrance', 'quest_find_exit.py:_exit_cell'}


def proved(source, origin='census', modules=True, extra=None):
    sources = {'m.py': textwrap.dedent(source), **(extra or {})}
    functions = lint.collect(sources)
    names = {}
    for site, function in functions.items():
        names.setdefault(function.name, []).append(site)
    selected = {site for site in functions if site.startswith('m.py:') and site.endswith(('.f', ':f'))}
    origins = {site: [origin] for site in functions}
    return data_proof.proved_data(functions, names, origins, selected, generator.SEAM_NAMES,
                                  sources if modules else None)


class DataProofRulesTest(unittest.TestCase):
    def test_observational_helpers_are_proved(self):
        for label, source in PROVED.items():
            with self.subTest(label):
                self.assertTrue(proved(source), source)

    def test_anything_that_can_emit_or_mutate_is_not_proved(self):
        for label, source in UNPROVED.items():
            with self.subTest(label):
                self.assertFalse(proved(source), source)

    def test_only_census_origin_is_proved(self):
        self.assertFalse(proved(PROVED['compare'], origin='emit/driver'))

    def test_module_level_rules_prove_pure_helpers(self):
        for label, source in PROVED_WITH_SOURCES.items():
            with self.subTest(label):
                self.assertTrue(proved(source), source)

    def test_without_sources_only_the_body_rules_apply(self):
        for label in ('module_constant', 'dataclass', 'named_tuple'):
            with self.subTest(label):
                self.assertFalse(proved(PROVED_WITH_SOURCES[label], modules=False))

    def test_imported_module_function_and_constant_are_resolved(self):
        helper = {'ranged.py': 'SCALE = 2\ndef damage(hp):\n return hp // SCALE\n'
                               'def key(hp):\n return "5"\n'}
        for import_line in ('from hengbot import ranged', 'from . import ranged',
                            'import hengbot.ranged as ranged'):
            with self.subTest(import_line):
                self.assertTrue(proved(import_line + '\ndef f(s):\n return ranged.damage(s.hp)\n',
                                       extra=helper))
                self.assertTrue(proved(import_line + '\ndef f(s):\n return ranged.SCALE\n', extra=helper))
                self.assertFalse(proved(import_line + '\ndef f(s):\n return ranged.key(s.hp)\n',
                                        extra=helper))
        self.assertTrue(proved('from hengbot.ranged import SCALE\ndef f(s):\n return SCALE\n', extra=helper))
        self.assertFalse(proved('def f(s):\n import json as ranged\n return ranged.dumps(s)\n',
                                extra=helper))


def _policy_sources(body, helpers='', extra=None):
    sources = {'policy.py': 'class HengbotPolicy:\n' + body + helpers, 'town_terminal.py': ''}
    sources.update(extra or {})
    return sources


class ProducerCensusTest(unittest.TestCase):
    """The census selects every key-returning function choose_key can reach, so a new one needs a review.

    Moved from the retired tests.test_town_structure_lint (2026-11-01); it now asserts the census the
    manifest reads instead of the retired producer baseline's findings.
    """
    def assertCensus(self, sources, site):
        self.assertIn(site, lint.producer_census(sources))

    def test_undecorated_town_wait_producer_is_selected(self):
        self.assertEqual(lint.producer_census(_policy_sources(' def choose_key(self, snapshot):\n  return None\n')),
                         {})
        self.assertCensus(_policy_sources(
            ' def choose_key(self, snapshot):\n  key = self._new_town_work(snapshot)\n  return key\n',
            ' def _new_town_work(self, snapshot):\n  return "5"\n'), 'policy.py:HengbotPolicy._new_town_work')

    def test_alias_callback_and_opaque_return_paths_are_selected(self):
        for expression in ('self._new_town_work(snapshot)',
                           'self._adapter(lambda: self._new_town_work(snapshot))',
                           'getattr(self, "_new_town_work")(snapshot)',
                           'call(snapshot)'):
            sources = _policy_sources(
                ' def choose_key(self, snapshot):\n  call = self._new_town_work\n  key = ' + expression
                + '\n  return key\n',
                ' def _new_town_work(self, snapshot):\n  return "5"\n'
                ' def _adapter(self, call):\n  return call()\n')
            with self.subTest(expression=expression):
                self.assertCensus(sources, 'policy.py:HengbotPolicy._new_town_work')

    def test_module_and_method_aliases_are_selected(self):
        for expression in ('work(snapshot)', 'self.adapt(work, snapshot)'):
            sources = _policy_sources(' def choose_key(self, snapshot):\n  return ' + expression + '\n',
                                      ' def adapt(self, call, snapshot):\n  return call(snapshot)\n')
            sources['policy.py'] += '\ndef new_producer(snapshot):\n return "5"\nwork = new_producer\n'
            with self.subTest(expression=expression):
                self.assertCensus(sources, 'policy.py:new_producer')
        self.assertCensus(_policy_sources(' def choose_key(self, snapshot):\n  return self.work(snapshot)\n',
                                          ' def new_producer(self, snapshot):\n  return "5"\n'
                                          ' work = new_producer\n'),
                          'policy.py:HengbotPolicy.new_producer')

    def test_imported_mixins_subpackages_and_callbacks_are_selected(self):
        sources = _policy_sources(' def choose_key(self, snapshot):\n  return self.new_work(snapshot)\n',
                                  extra={'new_mixin.py': 'class NewMixin:\n def new_work(self, snapshot):\n'
                                                         '  return "5"\n'})
        sources['policy.py'] = 'from .new_mixin import NewMixin\n' + sources['policy.py']
        self.assertCensus(sources, 'new_mixin.py:NewMixin.new_work')
        sources = _policy_sources(' def choose_key(self, snapshot):\n  return work(snapshot)\n',
                                  extra={'town/work.py': 'WAIT = "5"\ndef produce(snapshot):\n return WAIT\n'})
        sources['policy.py'] = 'from hengbot.town.work import produce as work\n' + sources['policy.py']
        self.assertCensus(sources, 'town/work.py:produce')
        for import_line, expression in (
            ('from . import work', 'work.produce(snapshot)'),
            ('from hengbot import work', 'work.produce(snapshot)'),
            ('from hengbot.work import produce as callback', 'self.adapt(callback, snapshot)'),
        ):
            sources = _policy_sources(' def choose_key(self, snapshot):\n  return ' + expression + '\n',
                                      ' def adapt(self, call, snapshot):\n  return call(snapshot)\n',
                                      {'work.py': 'def produce(snapshot):\n return "5"\n'})
            sources['policy.py'] = import_line + '\n' + sources['policy.py']
            with self.subTest(import_line=import_line):
                self.assertCensus(sources, 'work.py:produce')

    def test_reverse_import_driver_is_not_a_policy_descendant(self):
        sources = _policy_sources(' def choose_key(self, snapshot):\n  return None\n', extra={
            'driver.py': 'from hengbot.policy import HengbotPolicy\ndef new_work():\n return "5"\n'})
        self.assertNotIn('driver.py:new_work', lint.producer_census(sources))


def _mutant(sources):
    """The repository plus a new key producer, its int helper and a body edit of a reviewed producer."""
    mutant = dict(sources)
    tree = ast.parse(mutant['policy.py'])
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'HengbotPolicy')
    choose = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_choose_key')
    choose.body.insert(0, ast.parse('return self.new_town_work(snapshot)').body[0])
    cls.body.append(ast.parse('def new_town_work(self, snapshot):\n'
                              ' return "5" * self.new_town_count(snapshot)').body[0])
    cls.body.append(ast.parse('def new_town_count(self, snapshot) -> int:\n'
                              ' return len(snapshot.inventory) + 1').body[0])
    mutant['policy.py'] = ast.unparse(ast.fix_missing_locations(tree))
    # A behaviour-neutral body edit of a reviewed producer (old rules: a new digest to commit).
    old = 'def _town_destroy_key(self'
    assert mutant['policy_town.py'].count(old) == 1
    head, tail = mutant['policy_town.py'].split(old)
    signature, body = tail.split(':\n', 1)
    indent = body[:len(body) - len(body.lstrip())]
    mutant['policy_town.py'] = f'{head}{old}{signature}:\n{indent}_neutral_edit = None\n{body}'
    return mutant


def _cached_inventory():
    """generator.inventory, run once per distinct source set (it takes ~20 s on the repository)."""
    original, cache = generator.inventory, {}

    def inventory(sources):
        key = tuple(sorted(sources.items()))
        if key not in cache:
            cache[key] = original(sources)
        return cache[key]
    return inventory


class RepositoryManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patcher = patch.object(generator, 'inventory', _cached_inventory())
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.sources = generator.sources()
        cls.reviewed = json.loads(generator.REVIEW.read_text(encoding='utf8'))
        cls.index = json.loads(generator.INDEX.read_text(encoding='utf8'))

    def test_repository_index_is_current_and_digest_free(self):
        self.assertEqual(generator.check_repository(), [])
        self.assertFalse([site for site, row in self.index.items() if set(row) != set(generator.RUNTIME_FIELDS)])

    def test_proof_never_overrides_a_hand_review(self):
        functions, selected, origins, names = generator.inventory(self.sources)
        found = generator.proved_data(functions, names, origins, selected, self.sources)
        self.assertTrue(found)
        # Any proved site with a non-data hand review other than the known conservative ones is a proof bug.
        self.assertEqual({site for site in found if site in self.reviewed
                          and self.reviewed[site]['classification'] != 'data'}, CONSERVATIVE_REVIEWS)
        self.assertTrue(all(self.index[site]['classification'] == self.reviewed[site]['classification']
                            for site in CONSERVATIVE_REVIEWS))
        # The index rows of proved sites without a hand review are the mechanical data row.
        self.assertTrue(all(self.index[site] == data_proof.DATA_REVIEW
                            for site in found - self.reviewed.keys()))

    def test_unmapped_key_producer_fails_and_its_int_helper_needs_no_review(self):
        mutant = _mutant(self.sources)
        with self.assertRaisesRegex(ValueError, r'unmapped candidates=\[[^]]*new_town_work') as raised:
            generator.generate(mutant, self.reviewed)
        self.assertNotIn('new_town_count', str(raised.exception))
        # A minimal review entry (classification, rows, evidence) maps it; nothing else changes.
        reviewed = dict(self.reviewed, **{'policy.py:HengbotPolicy.new_town_work': dict(
            classification='producer', rows=['survival'], evidence='test producer')})
        index = generator.runtime_index(generator.generate(mutant, reviewed))
        self.assertEqual(index.pop('policy.py:HengbotPolicy.new_town_count'), data_proof.DATA_REVIEW)
        self.assertEqual(index.pop('policy.py:HengbotPolicy.new_town_work'), dict(
            classification='producer', rows=['survival'],
            delegation=generator.REVIEW_DEFAULTS['delegation']))
        self.assertEqual(index, self.index)


if __name__ == '__main__':
    unittest.main()
