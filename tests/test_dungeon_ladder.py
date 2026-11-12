"""The dungeon ladder's table against the order of the source, and the owner rules' places."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dungeon_ladder_lint as lint  # noqa: E402
from hengbot import dungeon_ladder as ladder, survival_preemption, town_terminal  # noqa: E402


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

    def test_two_rungs_swapped_in_a_layer_module_fail(self):
        findings = analyze_with(plan=lambda source: swapped(
            source, '"_darkness_recovery_key", lambda', '"_dark_locomotion_key", lambda'))
        self.assertTrue(any('ladder row' in finding and 'ladder_light.key line' in finding
                            for finding in findings), findings)
        self.assertTrue(any(finding.startswith('layer light: the table says')
                            for finding in findings), findings)

    def test_a_rung_of_another_layer_in_a_layer_module_fails(self):
        anchor = '    # Class 16 lights the dark'
        rung = ('    opening = policy._town_producer_entry("_opening_q34_town_key", lambda: None)\n'
                '    if opening is not None:\n        return opening\n')
        findings = analyze_with(plan=lambda source: source.replace(anchor, rung + anchor))
        self.assertTrue(any(finding.startswith('layer light: the table says')
                            and '_opening_q34_town_key' in finding for finding in findings), findings)

    def test_a_layer_module_not_called_from_decide_fails(self):
        findings = analyze_with(policy=lambda source: source.replace(
            'light = ladder_light.key(self, snapshot)', 'light = None'))
        self.assertIn('layer light: _decide calls ladder_light.key 0 time(s), not once', findings)

    def test_a_layer_module_falling_off_its_end_fails(self):
        # Falling off would return None, which _decide returns as its answer: the next layer
        # is asked only on PASS (dungeon_ladder.PASS).
        findings = analyze_with(plan=lambda source: source.replace(
            '    return PASS\n', '    pass\n'))
        self.assertIn('layer light: ladder_light.key does not end with return PASS', findings)

    def test_pass_is_no_row(self):
        rows = lint.ladder_rows(*lint.repository_sources())
        self.assertNotIn(lint.PASS_ROW, {row.name for row in rows})
        self.assertIsNot(ladder.PASS, None)
        self.assertFalse(isinstance(ladder.PASS, str))

    def test_each_layer_module_is_a_layer_of_the_table(self):
        self.assertLessEqual(ladder.LAYER_MODULES.keys(), {layer.name for layer in ladder.LADDER})
        rows = lint.ladder_rows(*lint.repository_sources())
        for name, module in ladder.LAYER_MODULES.items():
            with self.subTest(layer=name):
                self.assertIn(f'{module}.key', {row.where for row in rows})
                self.assertNotIn(f'{module}.key', {row.name for row in rows})

    def test_a_new_rung_without_a_row_fails(self):
        anchor = 'emergency = self._town_producer_entry("_emergency_item"'
        rung = ('new = self._town_producer_entry("_new_key", lambda: None)\n'
                '        if new is not None:\n            return new\n        ')
        findings = analyze_with(policy=lambda source: source.replace(anchor, rung + anchor))
        self.assertTrue(any('_new_key' in finding for finding in findings), findings)

    def test_a_direct_rung_moved_behind_the_entry_fails(self):
        # The floor-avoidance layer is asked in ladder_floor_avoidance (LAYER_MODULES).
        findings = analyze_with(plan=lambda source: source.replace(
            'summons = summon_response.key(policy, snapshot)',
            'summons = policy._town_producer_entry("summon_response.key", '
            'lambda: summon_response.key(policy, snapshot))'))
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
        self.assertEqual(inside, {'quest_find_exit.key', 'quest25_battle.key', 'quest_room_sweep.key'})
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

    def test_the_instant_death_rung_heads_every_enemy_board(self):
        # Owner 2026-11-07 「作戦が先・即死だけ例外」 (threat tiers answer 11, plan step 4).
        boards = [(plan, branch) for plan in ladder.FLOOR_PLANS for branch in plan.branches
                  if branch.enemy and ladder.OWN in [role for _, role in branch.rungs]]
        self.assertEqual(len(boards), 4)
        for plan, branch in boards:
            with self.subTest(plan=plan.rung, board=branch.board):
                self.assertEqual(branch.rungs[0], (ladder.INSTANT_DEATH, ladder.SURVIVAL))
                self.assertEqual(lint._branch_findings(plan, branch), [])

    def test_the_instant_death_rung_missing_or_moved_fails(self):
        for rungs in (
            (('_heal', ladder.SURVIVAL), ('summon_response.key', ladder.SUMMONS), ('_fight', ladder.OWN)),
            (('_heal', ladder.SURVIVAL), (ladder.INSTANT_DEATH, ladder.SURVIVAL),
             ('summon_response.key', ladder.SUMMONS), ('_fight', ladder.OWN)),
        ):
            with self.subTest(rungs=rungs):
                findings = lint._branch_findings(ladder.FLOOR_PLANS[0], ladder.Branch('board', rungs))
                self.assertTrue(any('instant-death rung' in finding for finding in findings), findings)

    def test_the_instant_death_rung_dropped_from_a_plan_module_fails(self):
        findings = analyze_with(plan=lambda source: source.replace(
            '        threat_tiers.instant_death_key(\n            policy, snapshot, lambda: '
            '_below_line_recall(policy, snapshot, profile, line=False))\n        or ', '        ', 1))
        self.assertTrue(any('quest_find_exit.key: the table says' in finding for finding in findings),
                        findings)

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


class PreemptionCompletenessTest(unittest.TestCase):
    def test_the_gate_refuses_what_the_table_says(self):
        self.assertEqual(survival_preemption.PREEMPTED_RUNGS, ladder.preempted_names())
        self.assertLessEqual(survival_preemption.PREEMPTED_RUNGS,
                             {rung.name for rung in ladder.rows()})

    def test_a_rung_above_combat_with_no_answer_fails(self):
        layer = ladder.Layer("pre-combat", "", (ladder.Rung("_new_key", "entry"),))
        self.assertEqual(lint._preemption_findings([layer]), [
            '_new_key: above the combat rungs, neither preempted nor exempt with a reason'])

    def test_a_direct_rung_cannot_be_preempted(self):
        layer = ladder.Layer("idle", "", (ladder.Rung("mod.key", "direct", True),))
        self.assertEqual(lint._preemption_findings([layer]), [
            'mod.key: preempted but direct: the gate is in the entry'])

    def test_preempted_and_exempt_fails(self):
        layer = ladder.Layer("idle", "", (ladder.Rung("_x", "entry", True, "why"),))
        self.assertEqual(lint._preemption_findings([layer]), ['_x: both preempted and exempt'])


class DungeonBoardRungTest(unittest.TestCase):
    """An entry row moved from a direct call adds no town hold: it declares itself off the town."""

    def test_it_does_not_apply_on_a_town_or_store_board(self):
        for name in ('junk_destroy_now.destroy_now_key', 'consumable_policy.use_now_key'):
            decl = town_terminal.TERMINALS[name]
            self.assertIs(decl.intended_terminal, town_terminal.dungeon_board_intended_terminal)
        terminal = town_terminal.dungeon_board_intended_terminal
        self.assertEqual(terminal(None, SimpleNamespace(in_town=True, store=None)),
                         town_terminal.NOT_APPLICABLE)
        self.assertEqual(terminal(None, SimpleNamespace(in_town=False, store=object())),
                         town_terminal.NOT_APPLICABLE)
        self.assertIsNone(terminal(None, SimpleNamespace(in_town=False, store=None)))


class ReturnsOverTest(unittest.TestCase):
    def test_a_rung_returns_over_every_row_below_it(self):
        over = {rung.name for rung in ladder.returns_over('quest_find_exit.key')}
        self.assertLessEqual({'_emergency_item', 'summon_response.key', 'navigator.decide'}, over)
        self.assertNotIn('summon_response.key', {
            rung.name for rung in ladder.returns_over('navigator.decide')})


if __name__ == '__main__':
    unittest.main()
