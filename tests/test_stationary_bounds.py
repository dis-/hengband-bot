"""The stationary waits taken out of the loop guard with a bound and a named stop.

Whole-bot maintainability review 2026-11-23, K3, owner (b)-1 「上限を付けて見張りから外す」
(hengbot.stationary_bounds).  CONSTRUCTED: the boards below are built by hand (a player on one
cell of a dungeon floor, the producer's own reason and key on every decision, the game clock
advanced 10 game turns a decision -- a player turn at normal speed); no recorded run held these
waits long enough to reach a bound.  For every bounded wait they show

* the driver's cell guard never counts the hold (no loop-detected however long it lasts);
* within the bound the key and the reason are the ones decided;
* past the bound the reason is ``stationary:exhausted:<reason>``, a named final stop of the
  driver (its own incident kind and banner), never loop-detected.

The unprofitable-unique disengage's spent budget is shown on the real policy
(UniqueCombatConsumableTest's board): ``combat:avoid-unprofitable-unique-fruitless`` in place of
``combat:fruitless`` (which the driver reports as loop-detected).
"""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from dataclasses import replace
from types import SimpleNamespace
import unittest

from hengbot import (amberite_curse, angband_finale_battle, cli, policy_constants, policy_fundraising,
                     policy_town, quest25_battle, reasons, stationary_bounds, status_cure)
from hengbot.model import Position
from hengbot.policy_constants import FRUITLESS_DISENGAGE_LIMIT, REST_MACRO, WAIT_KEY

FLOOR = (1, 40, 0)
CELL = Position(5, 5)
TURNS_PER_DECISION = 10

# The producers' own names for the bounded waits (a renamed producer fails here).
PRODUCER_REASONS = {
    amberite_curse.HOLD_REASON: "amberite:hold",
    angband_finale_battle.HOLD_REASON: "angband-finale:hold",
    status_cure.DUNGEON_WAIT_SIGHT_REASON: "blind:wait-sight",
    policy_fundraising.FUNDRAISING_WAIT_SIGHT_REASON: "fundraise:wait-sight",
    policy_town.RETURN_WAIT_SIGHT_REASON: "return:wait-sight",
    quest25_battle.FIRE_HOLD_REASON: "quest25:hold-out-of-fire",
}
REST_REASONS = {"blind:wait-sight", "fundraise:wait-sight", "return:wait-sight"}


def board(turn, *, position=CELL, hp=100, mp=50, floor=FLOOR, in_town=False):
    return SimpleNamespace(
        in_town=in_town, store=None, inside_arena=False, floor_key=floor, turn=turn, messages=(),
        player=SimpleNamespace(position=position, hp=hp, mp=mp, blind=0, confused=0, afraid=0,
                               poisoned=0, stunned=0, cut=0, paralyzed=0, hallucinated=0,
                               cut_rank=None, stun_rank=None))


def key_of(reason):
    return REST_MACRO if reason in REST_REASONS else WAIT_KEY


class Run:
    """Decisions of one producer on one cell; ``step`` returns (key, reason, guard counted)."""

    def __init__(self, sequence=0, turn=1000):
        self.policy = SimpleNamespace(last_reason=None, _decision_sequence=sequence)
        self.turn = turn
        self.previous = None

    def step(self, reason, *, key=None, position=CELL, hp=100, mp=50, advance=TURNS_PER_DECISION):
        self.turn += advance
        self.policy._decision_sequence += 1
        self.policy.last_reason = reason
        snapshot = board(self.turn, position=position, hp=hp, mp=mp)
        key = key_of(reason) if key is None else key
        sent = stationary_bounds.bound(self.policy, snapshot, key)
        previous = self.previous
        counted = cli._cell_loop_guard_applies(
            snapshot, self.policy.last_reason,
            previous.player.position if previous is not None else position,
            previous.player if previous is not None else None, sent)
        self.previous = snapshot
        return sent, self.policy.last_reason, counted


def decisions_within(row) -> int:
    """The decisions a hold may take and stay within its bound."""
    if row.unit == stationary_bounds.DECISIONS:
        return row.limit
    return row.limit // TURNS_PER_DECISION + 1  # the first board starts the clock


class TableTest(unittest.TestCase):
    def test_the_producers_send_the_bounded_names(self):
        for produced, expected in PRODUCER_REASONS.items():
            self.assertEqual(produced, expected)
            self.assertIn(produced, stationary_bounds.BY_REASON)

    def test_every_bound_is_an_exempt_row(self):
        exempt = reasons.stationary_set(reasons.EXEMPT)
        for row in stationary_bounds.BOUNDS:
            self.assertIn(row.reason, exempt, row)
            self.assertTrue(reasons.stationary(row.reason), row)
            rule = next(r.rule for r in reasons.STATIONARY_ROWS if r.reason == row.reason)
            self.assertIn(f"stationary_bounds.{row.name}", rule)
            self.assertEqual(getattr(stationary_bounds, row.name), row.limit)

    def test_the_values(self):
        self.assertEqual(stationary_bounds.BLIND_MAX_GAME_TURNS, 3990)
        self.assertEqual(stationary_bounds.RECALL_MAX_GAME_TURNS, 350)
        self.assertEqual(stationary_bounds.UNPROFITABLE_UNIQUE_WAIT_MAX_DECISIONS, 100)
        self.assertEqual(stationary_bounds.FINALE_HOLD_MAX_DECISIONS,
                         angband_finale_battle.STAND_ROUTE_TRIES * angband_finale_battle.OPEN_STAND_WAIT)
        self.assertEqual(stationary_bounds.NO_END_HOLD_MAX_GAME_TURNS,
                         policy_constants.DETECTED_THREAT_HOLD_MAX_GAME_TURNS)
        # Never earlier than the loop guard stopped these waits before (40 normal-speed turns).
        self.assertGreaterEqual(stationary_bounds.NO_END_HOLD_MAX_GAME_TURNS,
                                cli.LOOP_WINDOW * TURNS_PER_DECISION)

    def test_the_stop_is_named_and_final(self):
        for row in stationary_bounds.BOUNDS:
            reason = stationary_bounds.stop_reason(row.reason)
            policy = SimpleNamespace(last_reason=reason, _decision_sequence=1)
            self.assertTrue(cli._policy_final_stop_required(policy), reason)
            self.assertEqual(cli._policy_final_stop_kind(reason), reason)
            self.assertNotEqual(cli._policy_final_stop_kind(reason), "loop-detected")
            banner = cli._policy_final_stop_banner(reason)
            self.assertIn(row.reason, banner)
            self.assertIn(row.name, banner)


class EachWaitTest(unittest.TestCase):
    def test_no_loop_detected_within_the_bound_and_a_named_stop_beyond(self):
        for row in stationary_bounds.BOUNDS:
            with self.subTest(reason=row.reason):
                run = Run()
                within = decisions_within(row)
                for decision in range(within):
                    sent, reason, counted = run.step(row.reason)
                    self.assertEqual(sent, key_of(row.reason), decision)
                    self.assertEqual(reason, row.reason, decision)
                    self.assertFalse(counted, decision)  # the cell guard never counts it
                sent, reason, _ = run.step(row.reason)
                self.assertEqual(sent, key_of(row.reason))
                self.assertEqual(reason, stationary_bounds.stop_reason(row.reason))
                self.assertTrue(cli._policy_final_stop_required(run.policy))

    def test_at_high_speed_the_game_turn_bounds_keep_their_game_time(self):
        row = stationary_bounds.BY_REASON["threat:wait"]
        run = Run()
        for _ in range(row.limit // 3 + 1):  # +30 speed: about 3 game turns a player turn
            _, reason, _ = run.step(row.reason, advance=3)
        self.assertEqual(reason, row.reason)


class EpisodeTest(unittest.TestCase):
    def hold(self, run, reason, count):
        for _ in range(count):
            _, last, _ = run.step(reason)
        return last

    def test_a_step_to_another_cell_starts_again(self):
        run = Run()
        self.hold(run, "threat:wait", 50)
        run.step("threat:wait", position=Position(5, 6))
        self.assertEqual(self.hold(run, "threat:wait", 50), "threat:wait")

    def test_another_decision_between_starts_again(self):
        run = Run()
        self.hold(run, "threat:wait", 50)
        run.step("melee", key="4")
        self.assertEqual(self.hold(run, "threat:wait", 50), "threat:wait")

    def test_a_decision_the_hook_did_not_see_starts_again(self):
        run = Run()
        self.hold(run, "threat:wait", 50)
        run.policy._decision_sequence += 1
        self.assertEqual(self.hold(run, "threat:wait", 50), "threat:wait")

    def test_a_recovering_board_starts_again(self):
        run = Run()
        self.hold(run, "amberite:hold", 50)
        run.step("amberite:hold", hp=101)
        for _ in range(50):
            _, last, _ = run.step("amberite:hold", hp=101)
        self.assertEqual(last, "amberite:hold")

    def test_the_fire_rest_is_the_fire_hold_companion(self):
        run = Run()
        last = None
        for _ in range(60):  # 120 decisions, 1200 game turns: past the 500 bound
            run.step("quest25:rest-out-of-fire", key=REST_MACRO)
            _, last, _ = run.step("quest25:hold-out-of-fire")
            if stationary_bounds.is_stop(last):
                break
        self.assertEqual(last, stationary_bounds.stop_reason("quest25:hold-out-of-fire"))

    def test_the_companion_alone_never_stops(self):
        run = Run()
        for _ in range(200):
            _, last, _ = run.step("quest25:rest-out-of-fire", key=REST_MACRO)
        self.assertEqual(last, "quest25:rest-out-of-fire")

    def test_town_and_unbounded_reasons_are_untouched(self):
        policy = SimpleNamespace(last_reason="threat:wait", _decision_sequence=1)
        town = board(10_000, in_town=True)
        self.assertEqual(stationary_bounds.bound(policy, town, WAIT_KEY), WAIT_KEY)
        self.assertEqual(policy.last_reason, "threat:wait")
        self.assertIsNone(getattr(policy, stationary_bounds.STATE))
        policy.last_reason = "walk"
        self.assertEqual(stationary_bounds.bound(policy, board(1), "6"), "6")
        self.assertEqual(policy.last_reason, "walk")


class UniqueFruitlessTest(unittest.TestCase):
    """The real policy on UniqueCombatConsumableTest's harmless-unique board."""

    def test_a_fresh_unique_disengage_is_unchanged(self):
        policy, snapshot = self.board()
        policy.choose_key(snapshot)
        self.assertTrue(policy.last_reason.startswith("combat:avoid-unprofitable-unique-"))

    def board(self):
        from tests.test_policy_combat import UniqueCombatConsumableTest
        from hengbot.policy import HengbotPolicy
        from hengbot.model import DUNGEON_YEEK_CAVE

        snapshot, _, knowledge = UniqueCombatConsumableTest()._snapshot(
            hp=200, max_hp=200, monster_hp=1500, monster_speed=115, blow_sides=0)
        snapshot = replace(snapshot, floor_key=(DUNGEON_YEEK_CAVE, 1, 0))
        return HengbotPolicy(monrace_knowledge={9001: knowledge}), snapshot

    def test_the_spent_unique_disengage_is_a_named_stop(self):
        # The floor's disengage budget was spent by an earlier latch (the arming reads it back
        # from the escape state); the unique arms the disengage again.
        policy, snapshot = self.board()
        policy._escape_state.floor = snapshot.floor_key
        policy._escape_state.budgets["fruitless-disengage"] = FRUITLESS_DISENGAGE_LIMIT
        policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, policy_constants.UNPROFITABLE_UNIQUE_FRUITLESS_REASON)
        self.assertTrue(cli._policy_final_stop_required(policy))
        self.assertNotEqual(cli._policy_final_stop_kind(policy.last_reason), "loop-detected")
        self.assertIn("FRUITLESS_DISENGAGE_LIMIT", cli._policy_final_stop_banner(policy.last_reason))


if __name__ == "__main__":
    unittest.main()
