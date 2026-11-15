"""The cross-layer rules' observer (hengbot.cross_rules): it records, it decides nothing.

Maintainability review of the dungeon decisions 2026-11-15, stage 1."""
import tests  # noqa: F401  -- runtime-file isolation before policy imports

import unittest
from types import SimpleNamespace

from hengbot import cross_rules


class _Policy:
    last_reason = ""


def _board(*, level=10, in_town=False):
    return SimpleNamespace(in_town=in_town, store=None, dungeon_level=level)


class CrossRuleObserverTest(unittest.TestCase):
    def test_step_after_the_registry_read_is_consulted(self):
        policy = _Policy()
        cross_rules.begin(policy)
        cross_rules.consult(policy, cross_rules.LEFT_CELLS, "explore")
        cross_rules.produce(policy, cross_rules.LEFT_CELLS, "walker")
        cross_rules.end(policy, _board(), "4")
        self.assertEqual(cross_rules.report(policy),
                         ["cross-rule:left-cells:consulted:walker"])

    def test_step_before_any_registry_read_is_not_consulted(self):
        policy = _Policy()
        cross_rules.begin(policy)
        cross_rules.produce(policy, cross_rules.LEFT_CELLS, "walker")
        cross_rules.consult(policy, cross_rules.LEFT_CELLS, "later")
        cross_rules.end(policy, _board(), "4")
        self.assertEqual(cross_rules.report(policy),
                         ["cross-rule:left-cells:not-consulted:walker"])

    def test_dungeon_rest_and_wait_read_the_uncurse_point(self):
        policy = _Policy()
        policy.last_reason = "rest:hp"
        cross_rules.begin(policy)
        cross_rules.end(policy, _board(), "R&\r")
        self.assertEqual(cross_rules.report(policy),
                         ["cross-rule:uncurse-before-rest:not-consulted:rest:hp"])
        cross_rules.begin(policy)
        cross_rules.consult(policy, cross_rules.UNCURSE_BEFORE_REST, "key")
        cross_rules.end(policy, _board(), "5")
        self.assertEqual(cross_rules.report(policy),
                         ["cross-rule:uncurse-before-rest:consulted:rest:hp"])

    def test_town_rest_is_not_a_dungeon_rule(self):
        policy = _Policy()
        cross_rules.begin(policy)
        cross_rules.end(policy, _board(level=0, in_town=True), "R&\r")
        self.assertIsNone(cross_rules.report(policy))

    def test_escape_noted_by_its_producer(self):
        from hengbot.policy_constants import EMERGENCY_ESCAPE_REASONS

        reason = sorted(EMERGENCY_ESCAPE_REASONS)[0]
        policy = _Policy()
        policy.last_reason = reason
        cross_rules.begin(policy)
        cross_rules.end(policy, _board(), "r")
        state = cross_rules.report(policy)[0].split(":")[2]
        self.assertIn(state, (cross_rules.NOT_CONSULTED, cross_rules.CONSULTED))
        cross_rules.begin(policy)
        cross_rules.consult(policy, cross_rules.ESCAPE_LINE_OF_FIRE, "x")
        cross_rules.end(policy, _board(), "r")
        self.assertEqual(cross_rules.report(policy),
                         [f"cross-rule:escape-line-of-fire:consulted:{reason}"])

    def test_destruction_flash_lists_the_memories_left(self):
        policy = _Policy()
        policy._retreat_veto_life = object()
        cross_rules.begin(policy)
        cross_rules.destruction_flash(policy, ("monster_memory.KINDS",))
        cross_rules.end(policy, _board(level=0, in_town=True), "")
        self.assertEqual(cross_rules.report(policy), [
            "cross-rule:destruction-forget:consulted:monster_memory.KINDS",
            "cross-rule:destruction-forget:not-consulted:_retreat_veto_life"])

    def test_nothing_is_stored_on_the_policy(self):
        policy = _Policy()
        cross_rules.begin(policy)
        cross_rules.produce(policy, cross_rules.LEFT_CELLS, "walker")
        cross_rules.end(policy, _board(), "4")
        self.assertEqual(vars(policy), {})

    def test_real_hooks_name_the_caller(self):
        from hengbot import left_cells

        policy = SimpleNamespace(_engagement_owned_avoid_cells=frozenset())

        def some_walker():
            return left_cells.refused(policy, SimpleNamespace(floor_key=(1, 1, 0)))

        cross_rules.begin(policy)
        some_walker()
        sites = [site for _clock, site in cross_rules._ledger(policy).consults[cross_rules.LEFT_CELLS]]
        self.assertEqual(sites, ["some_walker"])


if __name__ == "__main__":
    unittest.main()
