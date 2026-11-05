"""The dungeon ladder's table against the order of the source, and the owner rules' places."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dungeon_ladder_lint as lint  # noqa: E402
from hengbot import dungeon_ladder as ladder  # noqa: E402


def analyze_with(policy=None, plan=None):
    """The check on the repository's sources, one of them edited."""
    policy_source, plan_sources = lint.repository_sources()
    if policy is not None:
        policy_source = policy(policy_source)
    if plan is not None:
        plan_sources = {module: plan(source) for module, source in plan_sources.items()}
    return lint.analyze(policy_source, plan_sources)


def swapped(source, first, second):
    return source.replace(first, '\0').replace(second, first).replace('\0', second)


class TableAgainstSourceTest(unittest.TestCase):
    def test_the_table_is_the_order_of_the_source(self):
        self.assertEqual(lint.analyze_repository(), [])

    def test_two_rungs_swapped_in_decide_fail(self):
        findings = analyze_with(policy=lambda source: swapped(
            source, '"_emergency_item", lambda', '"_esp_threat_hunt_key", lambda'))
        self.assertTrue(any('ladder row' in finding for finding in findings), findings)

    def test_a_new_rung_without_a_row_fails(self):
        anchor = 'emergency = self._town_producer_entry("_emergency_item"'
        rung = ('new = self._town_producer_entry("_new_key", lambda: None)\n'
                '        if new is not None:\n            return new\n        ')
        findings = analyze_with(policy=lambda source: source.replace(anchor, rung + anchor))
        self.assertTrue(any('_new_key' in finding for finding in findings), findings)

    def test_a_direct_rung_moved_behind_the_entry_fails(self):
        findings = analyze_with(policy=lambda source: source.replace(
            'summons = summon_response.key(self, snapshot)',
            'summons = self._town_producer_entry("summon_response.key", '
            'lambda: summon_response.key(self, snapshot))'))
        self.assertTrue(any('summon_response.key (direct)' in finding for finding in findings), findings)

    def test_a_filter_added_after_decide_fails(self):
        anchor = 'key = self._flee_sustain_key(snapshot, key)'
        findings = analyze_with(policy=lambda source: source.replace(
            anchor, 'key = self._new_filter(snapshot, key)\n        ' + anchor))
        self.assertTrue(any('after _decide' in finding for finding in findings), findings)

    def test_a_plan_rung_order_changed_in_its_module_fails(self):
        findings = analyze_with(plan=lambda source: source.replace(
            '            or summon_response.key(policy, snapshot)\n', '', 1))
        self.assertTrue(any('quest_find_exit.key: the table says' in finding for finding in findings),
                        findings)


class OwnerRulePlacesTest(unittest.TestCase):
    """Where each rule that must run before a plan's own order sits."""

    def test_each_rule_sits_above_or_inside_every_plan(self):
        names = [rung.name for rung in ladder.rows()]
        inside = {plan.rung for plan in ladder.FLOOR_PLANS}
        self.assertEqual(inside, {'quest_find_exit.key', 'quest_room_sweep.key'})
        for rule in ladder.OWNER_RULES:
            with self.subTest(rule=rule.name):
                self.assertEqual(rule.below_rule, ('navigator.decide',))
                self.assertLess(names.index(rule.rung), names.index('navigator.decide'))
                for plan in ladder.FLOOR_PLANS:
                    self.assertIn(plan.rung, rule.ahead)
                    for branch in plan.branches:
                        roles = [role for _, role in branch.rungs]
                        if ladder.OWN not in roles:
                            continue
                        if rule.role == ladder.SURVIVAL and not branch.enemy:
                            continue
                        self.assertIn(rule.role, roles, (plan.rung, branch.board))
                        self.assertLess(roles.index(rule.role), roles.index(ladder.OWN),
                                        (plan.rung, branch.board))

    def test_the_summons_dropped_from_a_plan_branch_fail(self):
        # The regression of 4b04bafa56: the plan's own order with no summon rule above it.
        branch = ladder.Branch('board', (('_heal', ladder.SURVIVAL), ('_fight', ladder.OWN)))
        findings = lint._branch_findings(ladder.FLOOR_PLANS[0], branch)
        self.assertTrue(any('without the summon rules' in finding for finding in findings), findings)

    def test_the_plan_order_above_the_summons_fails(self):
        branch = ladder.Branch('board', (
            ('_heal', ladder.SURVIVAL), ('_fight', ladder.OWN), ('summon_response.key', ladder.SUMMONS)))
        findings = lint._branch_findings(ladder.FLOOR_PLANS[0], branch)
        self.assertTrue(any('returns over the summon rules' in finding for finding in findings), findings)

    def test_survival_below_the_summons_or_missing_fails(self):
        for rungs in (
            (('summon_response.key', ladder.SUMMONS), ('_heal', ladder.SURVIVAL), ('_fight', ladder.OWN)),
            (('summon_response.key', ladder.SUMMONS), ('_fight', ladder.OWN)),
        ):
            with self.subTest(rungs=rungs):
                self.assertTrue(lint._branch_findings(ladder.FLOOR_PLANS[0], ladder.Branch('board', rungs)))

    def test_a_new_rung_above_a_rule_needs_a_reason(self):
        names = [rung.name for rung in ladder.rows()]
        at = names.index('summon_response.key')
        findings = lint._rule_findings(names[:at] + ['_new_owner_key'] + names[at:])
        self.assertEqual(findings, [
            '_new_owner_key returns over the summons rule (summon_response.key) '
            'and OWNER_RULES gives no reason'])

    def test_the_navigator_above_a_rule_fails(self):
        names = [rung.name for rung in ladder.rows()]
        names.remove('navigator.decide')
        findings = lint._rule_findings(['navigator.decide', *names])
        self.assertTrue(any('navigator.decide returns over the survival rule' in finding
                            for finding in findings), findings)


class ReturnsOverTest(unittest.TestCase):
    def test_a_rung_returns_over_every_row_below_it(self):
        over = {rung.name for rung in ladder.returns_over('quest_find_exit.key')}
        self.assertLessEqual({'_emergency_item', 'summon_response.key', 'navigator.decide'}, over)
        self.assertNotIn('summon_response.key', {
            rung.name for rung in ladder.returns_over('navigator.decide')})


if __name__ == '__main__':
    unittest.main()
