"""Revert-proof pins using base methods in memory; no checkout or bot actions."""
import tests  # noqa: F401
import ast
import io
import subprocess
import unittest

import hengbot.policy_home as home
import hengbot.policy_quest as quest
from test_mana_home_recorded import ManaHomeRecordedTest


def main():
    pins = (
        (home, home.HomeMixin, '_ensure_home_visit_request',
         'test_recorded_after_public_decision_withdraws_under_survival'),
        (quest, quest.QuestMixin, '_derived_home_visit_request',
         'test_recorded_after_public_decision_withdraws_under_survival'),
        (home, home.HomeMixin, '_atomic_home_withdraw_dispatch_key',
         'test_suspended_errand_item_and_quantity_survive_absorption'),
    )
    for module, klass, name, test in pins:
        relative = 'src/hengbot/' + module.__name__.split('.')[-1] + '.py'
        source = subprocess.check_output(['git', 'show', '82fcaeb9:' + relative]).decode('utf8')
        tree = ast.parse(source)
        parent = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == klass.__name__)
        function = next(node for node in parent.body if isinstance(node, ast.FunctionDef) and node.name == name)
        namespace = dict(vars(module))
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-base-method>', 'exec'), namespace)
        original = getattr(klass, name)
        try:
            setattr(klass, name, namespace[name])
            output = io.StringIO()
            result = unittest.TextTestRunner(stream=output).run(unittest.TestSuite([ManaHomeRecordedTest(test)]))
            assert result.failures and not result.errors, output.getvalue()
            print('REVERT-PROOF:', name, '->', test, 'fails with the actual base method')
        finally:
            setattr(klass, name, original)


if __name__ == '__main__':
    main()
