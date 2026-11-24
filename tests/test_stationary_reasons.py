"""The loop guard's stationary reasons, moved from cli.py's hand lists to the registry.

Maintainability review 2026-11-18, (a)-5 (S5): cli.STATIONARY_REASONS, STATIONARY_EXEMPT_REASONS,
QUEST_COMBAT_REASON_PREFIXES and the literal prefixes item: / ranged: / chest: of
cli._cell_loop_guard_applies became views of hengbot.reasons.STATIONARY_ROWS.  The lists are
frozen here as they stood at ae4da7673c, and the answer "is this reason exempt from the loop
guard?" is pinned for every reason the code knows: the registry's rows, the old lists and
prefixes, every reason shape the source sends (scripts/reason_registry_lint.py) and their
neighbours (a ``:suffix``, a glued suffix, one character less)."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from functools import lru_cache
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reason_registry_lint as lint  # noqa: E402
from hengbot import anaguma, cli, policy, policy_constants, quest25_battle, quest_target_search, reasons  # noqa: E402
from hengbot import stationary_bounds, status_cure  # noqa: E402
from hengbot.model import Position  # noqa: E402

# cli.STATIONARY_REASONS at ae4da7673c.
OLD_STATIONARY_REASONS = frozenset({
    'breeder-breakthrough:wait-recall', 'combat:disengage-search-upstairs',
    'combat:disengage-wait-recall', 'confused:wait', 'esp-threat:leave-dig-to-frontier',
    'esp-threat:leave-dig-to-upstairs', 'esp-threat:leave-search-upstairs',
    'esp-threat:leave-wait-recall', 'fundraise:abort-unbeatable-unique:wait-recall',
    'fundraise:clear-escape-path', 'fundraise:wait-recall', 'melee', 'return:dig-to-frontier',
    'return:dig-to-upstairs', 'return:search-upstairs', 'return:wait-recall', 'search',
    'summoner:wait-recall', 'town:wait-recall', 'wilderness:wait-recall',
})
# cli.STATIONARY_EXEMPT_REASONS at ae4da7673c.
OLD_STATIONARY_EXEMPT_REASONS = frozenset({
    'anaguma:close-haste', 'anaguma:detect', 'anaguma:dig', 'anaguma:dig:absorbed-power',
    'anaguma:hold', 'breakout:dig-to-stairs', 'combat:disengage-wait', 'detected:hold-choke',
    'emergency:wait', 'flee:wait', 'fundraise:dig-mark-bump', 'fundraise:dig-to-treasure',
    'fundraise:mine-treasure', 'fundraise:open-upstairs-door', 'fundraise:seek-treasure:open-door',
    'fundraise:tunnel-out', 'once-quest:recover', 'quest-search:wait-redetect',
    'quest-strategy:exit-dig', 'quest-strategy:hold', 'quest-strategy:open-final-door',
    'quest-strategy:open-opening-door', 'quest-strategy:open-sequence-door', 'quest25:rest-recharge',
    'quest25:trap-search', 'return:wait', 'status-threat:wait', 'summoner:hold-choke',
    'town:blocked:repetition', 'unseen:choke-wait', 'warning:trap-search',
})
# Exact (EXEMPT) rows added since ae4da7673c, each with its own bound: the short blindness wait
# (status_cure.SHORT_BLIND_MAX_GAME_TURNS) and the (b)-1 waits of stationary_bounds (owner
# 2026-11-23 「上限を付けて見張りから外す」).
ADDED_EXEMPT_REASONS = frozenset({'blind:short-wait'}) | frozenset(
    row.reason for row in stationary_bounds.BOUNDS)
# HOLD rows added since: deep_fall_guard's recall wait, the income run's bounded wall search
# (n1-a life-537, policy_fundraising ``_secret_wall_exit``).
ADDED_STATIONARY_REASONS = frozenset({'deep-fall-guard:wait-recall', 'fundraise:search'})
# cli.QUEST_COMBAT_REASON_PREFIXES and the literal prefixes of _cell_loop_guard_applies.
OLD_QUEST_COMBAT_REASON_PREFIXES = ('quest-strategy:melee', 'quest-strategy:ranged-fire',
                                    'quest-strategy:q2-fire')
OLD_ACTION_PREFIXES = ('item:', 'ranged:', 'chest:')


def old_stationary(reason: str) -> bool:
    """cli._cell_loop_guard_applies's test at ae4da7673c, verbatim, with the rows added since."""
    return (
        any(
            reason == stationary
            or reason.startswith(f"{stationary}:")
            for stationary in OLD_STATIONARY_REASONS | ADDED_STATIONARY_REASONS
        )
        or reason in OLD_STATIONARY_EXEMPT_REASONS | ADDED_EXEMPT_REASONS
        or reason.startswith(OLD_QUEST_COMBAT_REASON_PREFIXES)
        or reason.startswith("item:")
        or reason.startswith("ranged:")
        or reason.startswith("chest:")
    )


@lru_cache(maxsize=1)
def known_reasons() -> frozenset:
    """Every reason string the code knows, and its neighbours."""
    base = set(OLD_STATIONARY_REASONS | OLD_STATIONARY_EXEMPT_REASONS)
    base |= set(OLD_QUEST_COMBAT_REASON_PREFIXES + OLD_ACTION_PREFIXES)
    base |= {row.pattern for row in reasons.ROWS}
    base |= {row.reason for row in reasons.STATIONARY_ROWS}
    base |= set(lint.shapes())
    out = set()
    for reason in base:
        out |= {reason, reason + ":x", reason + ":absorbed-power", reason + "x", reason + "-x",
                reason[:-1], reason.replace("*", "x")}
    out |= {"rest", "item", "ranged", "chest", "items:x", "quest-strategy:meleex",
            "quest-strategy:q2-fire-offset", "quest-strategy:ranged-fire:magic-eater"}
    return frozenset(reason for reason in out if reason)


def board(position=Position(5, 5), *, in_town=False, inside_arena=False):
    return SimpleNamespace(player=SimpleNamespace(position=position), in_town=in_town,
                           inside_arena=inside_arena)


class EquivalenceTest(unittest.TestCase):
    def test_the_views_hold_the_old_lists(self):
        self.assertEqual(cli.STATIONARY_REASONS, OLD_STATIONARY_REASONS | ADDED_STATIONARY_REASONS)
        self.assertEqual(cli.STATIONARY_EXEMPT_REASONS,
                         OLD_STATIONARY_EXEMPT_REASONS | ADDED_EXEMPT_REASONS)
        self.assertEqual(cli.QUEST_COMBAT_REASON_PREFIXES, OLD_QUEST_COMBAT_REASON_PREFIXES)
        self.assertEqual(cli.STATIONARY_ACTION_PREFIXES, OLD_ACTION_PREFIXES)

    def test_every_known_reason_answers_as_before(self):
        snapshot = board()
        candidates = known_reasons()
        self.assertGreater(len(candidates), 2000)
        differ = sorted(
            reason for reason in candidates
            if cli._cell_loop_guard_applies(snapshot, reason, Position(5, 5)) == old_stationary(reason))
        self.assertEqual(differ, [])
        differ = sorted(reason for reason in candidates
                        if reasons.stationary(reason) != old_stationary(reason))
        self.assertEqual(differ, [])

    def test_a_move_or_the_town_still_decide_alone(self):
        for reason in ("melee", "quest25:trap-search", "item:quaff", "walk"):
            self.assertTrue(cli._cell_loop_guard_applies(board(), reason, Position(4, 5)), reason)
            self.assertFalse(cli._cell_loop_guard_applies(board(in_town=True), reason), reason)
            self.assertFalse(cli._cell_loop_guard_applies(board(inside_arena=True), reason), reason)


class ProducersTest(unittest.TestCase):
    """The producers' own constants are rows of the table (a new one fails here)."""

    def test_holds(self):
        holds = reasons.stationary_set(reasons.HOLD)
        self.assertLessEqual(policy_constants.RETURN_STATIONARY_REASONS, holds)
        relabelled = {policy_constants.ESP_THREAT_LEAVE_PREFIX + reason[len("return:"):]
                      for reason in policy_constants.RETURN_STATIONARY_REASONS}
        self.assertLessEqual(relabelled, holds)
        self.assertIn(f"{policy_constants.MINING_ABORT_REASON_PREFIX}:wait-recall", holds)

    def test_exempt(self):
        exempt = reasons.stationary_set(reasons.EXEMPT)
        self.assertLessEqual(anaguma.STATIONARY, exempt)
        self.assertLessEqual(set(policy.ESCAPE_BUDGETED_WAIT_LIMITS), exempt)
        self.assertIn(quest25_battle.SEARCH_REASON, exempt)
        self.assertIn(quest25_battle.RECHARGE_REASON, exempt)
        self.assertIn(policy_constants.ONCE_QUEST_TICK_REST_REASON, exempt)
        self.assertIn(quest_target_search.REDETECT_WAIT_REASON, exempt)
        self.assertIn(status_cure.SHORT_BLIND_WAIT_REASON, exempt)

    def test_rows_are_unique_and_well_formed(self):
        names = [row.reason for row in reasons.STATIONARY_ROWS]
        self.assertEqual(len(names), len(set(names)))
        for row in reasons.STATIONARY_ROWS:
            self.assertIn(row.match, reasons.STATIONARY_MATCHES, row)
            self.assertTrue(row.rule, row)


NL = "\n"


class LintTest(unittest.TestCase):
    def test_the_repository_has_no_hand_list(self):
        self.assertEqual(lint.stationary_findings(), [])

    def test_a_hand_list_in_cli_fails(self):
        sources = lint.repository_sources()
        old = "STATIONARY_ACTION_PREFIXES = reasons.stationary_prefixes(reasons.ACTION)" + NL
        self.assertIn(old, sources["cli"])
        sources["cli"] = sources["cli"].replace(
            old, old + 'STATIONARY_EXTRA_REASONS = frozenset({"quest99:wait"})' + NL, 1)
        findings = lint.analyze(sources)
        self.assertTrue(any("STATIONARY_EXTRA_REASONS" in finding for finding in findings), findings)

    def test_a_literal_prefix_in_the_guard_fails(self):
        sources = lint.repository_sources()
        old = "                QUEST_COMBAT_REASON_PREFIXES + STATIONARY_ACTION_PREFIXES," + NL
        self.assertIn(old, sources["cli"])
        sources["cli"] = sources["cli"].replace(
            old, old + "            ) or reason.startswith(\"wand:\") or (" + NL + "                False" + NL, 1)
        findings = lint.stationary_findings(sources)
        self.assertTrue(any("_cell_loop_guard_applies (startswith)" in finding for finding in findings),
                        findings)

    def test_the_unregistered_count_is_a_report(self):
        """(a)-10: the shapes no row knows are counted, never a finding."""
        unregistered = lint.unregistered_shapes()
        self.assertTrue(unregistered)
        self.assertEqual(lint.analyze(), [])
        for shape in unregistered:
            self.assertIsNone(reasons.lookup(shape))
            self.assertFalse(reasons.stationary(shape))


if __name__ == "__main__":
    unittest.main()
