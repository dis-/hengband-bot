"""Re-keying town work reviews of moved or renamed functions (#47, owner 2026-11-01 「作る」, item 15).

A review keyed by module:qualname goes stale when its function moves or is
renamed; scripts/town_work_rekey.py moves the review to the new key only when
a function with the identical body (normalized AST, docstring-insensitive)
appeared. A changed body is never re-keyed.
"""
import tests  # noqa: F401 -- isolate runtime files
import ast
import json
from pathlib import Path
import re
import sys
import textwrap
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import town_structure_lint as lint  # noqa: E402
import town_work_manifest as generator  # noqa: E402
import town_work_rekey as rekey  # noqa: E402

REVIEW = dict(classification='producer', rows=['survival'], evidence='reviewed by hand')
HELPER = '''
def helper(snapshot):
    """Old documentation."""
    return "k" + snapshot.slot
'''


def plan(old, new, reviewed):
    old_functions = lint.collect({name: textwrap.dedent(source) for name, source in old.items()})
    new_functions = lint.collect({name: textwrap.dedent(source) for name, source in new.items()})
    return rekey.rekey_plan(old_functions, new_functions, reviewed, set(new_functions))


class RekeyPlanTest(unittest.TestCase):
    def test_moved_function_is_rekeyed(self):
        moved = HELPER.replace('    """Old documentation."""\n', '')
        moves, ambiguous, unmatched = plan({'a.py': HELPER}, {'a.py': '', 'b.py': moved},
                                           {'a.py:helper': REVIEW})
        self.assertEqual((moves, ambiguous, unmatched), ({'a.py:helper': 'b.py:helper'}, {}, []))

    def test_renamed_method_is_rekeyed(self):
        old = 'class P:\n    def old_name(self, snapshot):\n        """Old."""\n        return self.key(snapshot)\n'
        new = 'class P:\n    def new_name(self, snapshot):\n        """New."""\n        return self.key(snapshot)\n'
        moves, _ambiguous, unmatched = plan({'m.py': old}, {'m.py': new}, {'m.py:P.old_name': REVIEW})
        self.assertEqual((moves, unmatched), ({'m.py:P.old_name': 'm.py:P.new_name'}, []))

    def test_changed_body_is_not_rekeyed(self):
        changed = HELPER.replace('"k"', '"j"')
        moves, ambiguous, unmatched = plan({'a.py': HELPER}, {'b.py': changed}, {'a.py:helper': REVIEW})
        self.assertEqual((moves, ambiguous, unmatched), ({}, {}, ['a.py:helper']))

    def test_two_identical_new_bodies_are_left_for_a_hand_review(self):
        moves, ambiguous, unmatched = plan({'a.py': HELPER}, {'b.py': HELPER, 'c.py': HELPER},
                                           {'a.py:helper': REVIEW})
        self.assertEqual((moves, ambiguous, unmatched), ({}, {'a.py:helper': ['b.py:helper', 'c.py:helper']}, []))

    def test_apply_moves_keeps_order_and_entries(self):
        reviewed = {'a.py:first': {'x': 1}, 'a.py:helper': REVIEW, 'z.py:last': {'y': 2}}
        result = rekey.apply_moves(reviewed, {'a.py:helper': 'b.py:helper'})
        self.assertEqual(list(result), ['a.py:first', 'b.py:helper', 'z.py:last'])
        self.assertIs(result['b.py:helper'], REVIEW)


def _cached_inventory():
    """generator.inventory, run once per distinct source set (it takes ~20 s on the repository)."""
    original, cache = generator.inventory, {}

    def inventory(sources):
        key = tuple(sorted(sources.items()))
        if key not in cache:
            cache[key] = original(sources)
        return cache[key]
    return inventory


def _rename(sources, old, new):
    pattern = re.compile(rf'\b{re.escape(old)}\b')
    return {name: pattern.sub(new, source) for name, source in sources.items()}


def _move_method(sources, name, source_file, target_file, target_class, edit=''):
    """Move a method between mixin classes of two modules (a policy split), with a new docstring.

    edit: statements put at the start of the moved body (a changed body).
    """
    result = dict(sources)
    tree = ast.parse(result[source_file])
    owner = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
                 and any(isinstance(child, ast.FunctionDef) and child.name == name for child in node.body))
    method = next(child for child in owner.body if isinstance(child, ast.FunctionDef) and child.name == name)
    owner.body.remove(method)
    if ast.get_docstring(method, clean=False) is not None:
        method.body = method.body[1:]
    method.body[:0] = [ast.Expr(ast.Constant('Moved here by a split.'))] + ast.parse(edit).body
    result[source_file] = ast.unparse(ast.fix_missing_locations(tree))
    target = ast.parse(result[target_file])
    cls = next(node for node in target.body if isinstance(node, ast.ClassDef) and node.name == target_class)
    cls.body.append(method)
    result[target_file] = ast.unparse(ast.fix_missing_locations(target))
    return result


class RepositoryRekeyTest(unittest.TestCase):
    """On the repository: the manifest refuses a move/rename and names the tool; the re-keyed review passes."""
    SITE = 'policy_town.py:TownMixin._town_destroy_key'

    @classmethod
    def setUpClass(cls):
        patcher = patch.object(generator, 'inventory', _cached_inventory())
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.sources = generator.sources()
        cls.reviewed = json.loads(generator.REVIEW.read_text(encoding='utf8'))
        cls.index = json.loads(generator.INDEX.read_text(encoding='utf8'))

    def check(self, mutant, new_site):
        self.assertIn(self.SITE, self.reviewed)
        with self.assertRaisesRegex(ValueError, r'stale reviews=.*_town_destroy_key.*town_work_rekey\.py'):
            generator.generate(mutant, self.reviewed)
        moves, ambiguous, unmatched = rekey.plan_for_sources(self.sources, mutant, self.reviewed)
        self.assertEqual((moves, ambiguous, unmatched), ({self.SITE: new_site}, {}, []))
        index = generator.runtime_index(generator.generate(mutant, rekey.apply_moves(self.reviewed, moves)))
        expected = dict(self.index)
        expected[new_site] = expected.pop(self.SITE)
        self.assertEqual(index, expected)

    def test_renamed_method_is_rekeyed(self):
        mutant = _rename(self.sources, '_town_destroy_key', '_town_destroy_item_key')
        self.check(mutant, 'policy_town.py:TownMixin._town_destroy_item_key')

    def test_method_moved_to_another_module_is_rekeyed(self):
        mutant = _move_method(self.sources, '_town_destroy_key', 'policy_town.py', 'policy_home.py', 'HomeMixin')
        self.check(mutant, 'policy_home.py:HomeMixin._town_destroy_key')

    def test_moved_method_with_a_changed_body_is_not_rekeyed(self):
        mutant = _move_method(self.sources, '_town_destroy_key', 'policy_town.py', 'policy_home.py', 'HomeMixin',
                              edit='changed = None')
        moves, ambiguous, unmatched = rekey.plan_for_sources(self.sources, mutant, self.reviewed)
        self.assertEqual((moves, ambiguous, unmatched), ({}, {}, [self.SITE]))


if __name__ == '__main__':
    unittest.main()
