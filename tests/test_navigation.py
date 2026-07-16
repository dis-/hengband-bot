"""Tests for the R1 navigation redesign: the shared progress ledger, the
mode-independent no-progress invariant, and the survival gate.

The regression scenarios mirror the 2026-07-17 Yeek Cave 6F incident: a
remembered-but-unreachable downstairs kept three navigation modes
(seek-downstairs / approach-descent / breakout:descent) handing the same
doomed goal to each other for 1600+ decisions while the character ate its
last ration and reached food_state "weak" with an empty pack.
"""

import unittest

from hengbot.model import Position, Snapshot
from hengbot.cli import LOOP_WINDOW
from hengbot.navigation import NAV_TARGET_STALL_LIMIT, NavigationLedger
from hengbot.policy import (
    NAV_NO_PROGRESS_LIMIT,
    RESUME_DESCENT_BLOCK_DECISIONS,
    WAIT_KEY,
    HengbotPolicy,
)
from test_policy import FOOD, SCROLL, grid, hostile, item, player

from hengbot.model import SV_SCROLL_WORD_OF_RECALL

DUNGEON_FLOOR = (2, 6, 0)

DESCENT_TRIAD_REASONS = {"seek-downstairs", "approach-descent", "breakout:descent"}


class NavigationLedgerTest(unittest.TestCase):
    def test_target_expiry_precedes_process_loop_detector(self):
        # The ledger is the recovery mechanism; the outer detector is only a
        # fail-safe.  If this ordering reverses, a two-cell descent oscillation
        # stops the bot before the policy can abandon its stale stair target.
        self.assertLess(NAV_TARGET_STALL_LIMIT, LOOP_WINDOW)

    def test_resume_descent_guard_precedes_process_loop_detector(self):
        self.assertLess(RESUME_DESCENT_BLOCK_DECISIONS, LOOP_WINDOW)

    def test_first_observation_counts_as_improvement(self):
        ledger = NavigationLedger()
        self.assertTrue(ledger.observe("descend", Position(1, 1), 10))
        self.assertTrue(ledger.improved_this_decision)

    def test_improvement_resets_stall(self):
        ledger = NavigationLedger(stall_limit=3)
        target = Position(1, 1)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        self.assertFalse(ledger.is_expired("descend", target))
        self.assertTrue(ledger.observe("descend", target, 9))
        ledger.observe("descend", target, 9)
        ledger.observe("descend", target, 9)
        self.assertFalse(ledger.is_expired("descend", target))

    def test_stalled_target_expires_for_its_kind_only(self):
        ledger = NavigationLedger(stall_limit=2)
        target = Position(1, 1)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 12)
        self.assertTrue(ledger.is_expired("descend", target))
        self.assertEqual(ledger.expired_targets("descend"), {target})
        self.assertFalse(ledger.is_expired("explore", target))

    def test_begin_decision_clears_the_improvement_flag(self):
        ledger = NavigationLedger()
        ledger.observe("descend", Position(1, 1), 10)
        ledger.begin_decision()
        self.assertFalse(ledger.improved_this_decision)

    def test_reset_forgets_expiries(self):
        ledger = NavigationLedger(stall_limit=1)
        target = Position(1, 1)
        ledger.observe("descend", target, 10)
        ledger.observe("descend", target, 10)
        self.assertTrue(ledger.is_expired("descend", target))
        ledger.reset()
        self.assertFalse(ledger.is_expired("descend", target))


class DescentTargetExpiryTest(unittest.TestCase):
    """The incident regression: an unreachable remembered stair must expire."""

    def _incident_snapshot(self):
        # A tiny mapped pocket with an open (unknown) edge to the east — a
        # permanent frontier the pathfinder can approach but never reveal
        # (dark-floor flicker) — and a remembered downstairs far outside it.
        origin = Position(10, 10)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(9, 10): grid(9, 10),
        }
        return Snapshot(
            player(origin.y, origin.x, food=12000),
            grids,
            [],
            floor_key=DUNGEON_FLOOR,
            width=40,
            height=40,
        )

    def test_unreachable_remembered_stair_expires_and_frees_navigation(self):
        snapshot = self._incident_snapshot()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        target = Position(12, 30)
        policy._remembered_downstairs.add(target)

        reasons = []
        expired_at = None
        for step in range(NAV_TARGET_STALL_LIMIT * 3):
            policy.choose_key(snapshot)
            reasons.append(policy.last_reason)
            if policy._nav_ledger.is_expired("descend", target):
                expired_at = step
                break
        self.assertIsNotNone(
            expired_at,
            f"target never expired; last reasons: {reasons[-6:]}",
        )
        self.assertLessEqual(expired_at, NAV_TARGET_STALL_LIMIT * 2)

        # From now on the doomed stair must be dead to EVERY mode: no
        # seek/approach/breakout decision may target it again this visit.
        for _ in range(20):
            policy.choose_key(snapshot)
            self.assertNotIn(policy.last_reason, DESCENT_TRIAD_REASONS)

    def test_reachable_visible_stair_is_still_walked_to(self):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        snapshot = Snapshot(
            player(10, 10, food=12000),
            grids,
            [],
            floor_key=DUNGEON_FLOOR,
            width=40,
            height=40,
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        self.assertEqual(policy.choose_key(snapshot), "6")
        self.assertEqual(policy.last_reason, "seek-downstairs")

    def test_floor_change_resets_expiries(self):
        snapshot = self._incident_snapshot()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        target = Position(12, 30)
        policy._nav_ledger.observe("descend", target, 10)
        for _ in range(NAV_TARGET_STALL_LIMIT + 1):
            policy._nav_ledger.observe("descend", target, 10)
        self.assertTrue(policy._nav_ledger.is_expired("descend", target))
        next_floor = Snapshot(
            player(10, 10, food=12000),
            dict(snapshot.grids),
            [],
            floor_key=(2, 7, 0),
            width=40,
            height=40,
        )
        policy.choose_key(next_floor)
        self.assertFalse(policy._nav_ledger.is_expired("descend", target))


class NavigationInvariantTest(unittest.TestCase):
    def _quiet_room(self, *, upstairs=False, inventory=()):
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
        }
        if upstairs:
            grids[Position(10, 12)] = grid(10, 12, upstairs=True)
        return Snapshot(
            player(10, 10, food=12000),
            grids,
            [],
            floor_key=DUNGEON_FLOOR,
            width=40,
            height=40,
            inventory=list(inventory),
        )

    def test_no_progress_counter_trips_the_invariant(self):
        snapshot = self._quiet_room()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        # The first couple of calls legitimately count as progress (initial
        # coverage and economy-marker baselines); the invariant needs the
        # budget's worth of genuinely flat decisions after those.
        for _ in range(NAV_NO_PROGRESS_LIMIT + 2):
            policy._update_navigation_progress(snapshot)
        self.assertTrue(policy._nav_exhausted)

    def test_new_coverage_resets_the_counter(self):
        snapshot = self._quiet_room()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        for _ in range(NAV_NO_PROGRESS_LIMIT - 1):
            policy._update_navigation_progress(snapshot)
        policy._remembered_known_t.add((20, 20))
        policy._update_navigation_progress(snapshot)
        self.assertEqual(policy._nav_stall_count, 0)
        self.assertFalse(policy._nav_exhausted)

    def test_combat_resets_the_counter(self):
        snapshot = self._quiet_room()
        fighting = Snapshot(
            snapshot.player,
            dict(snapshot.grids),
            [hostile(1, 10, 11)],
            floor_key=DUNGEON_FLOOR,
            width=40,
            height=40,
        )
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._build_grid_index(snapshot)
        policy._nav_stall_count = NAV_NO_PROGRESS_LIMIT - 1
        policy._update_navigation_progress(fighting)
        self.assertEqual(policy._nav_stall_count, 0)

    def test_exhausted_floor_reads_a_recall_scroll(self):
        recall = item("w", SCROLL, SV_SCROLL_WORD_OF_RECALL)
        snapshot = self._quiet_room(inventory=[recall])
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_exhausted = True
        self.assertEqual(policy.choose_key(snapshot), "rw")
        self.assertEqual(policy.last_reason, "livelock:recall-escape")

    def test_exhausted_floor_seeks_upstairs_without_a_scroll(self):
        snapshot = self._quiet_room(upstairs=True)
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_exhausted = True
        policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "livelock:seek-upstairs")

    def test_exhausted_floor_with_no_escape_stops_visibly(self):
        snapshot = self._quiet_room()
        policy = HengbotPolicy()
        policy._floor_key = snapshot.floor_key
        policy._nav_exhausted = True
        key = policy.choose_key(snapshot)
        # The pocket has a frontier, but exhaustion means those modes already
        # failed for the whole budget — the policy must surface the livelock
        # (the CLI stops on this reason) instead of resuming the cycle.
        if policy.last_reason == "livelock:exhausted":
            self.assertEqual(key, WAIT_KEY)
        else:
            # An up-stairs-free pocket without a scroll may legitimately still
            # explore its frontier once; the invariant then re-trips. Drive a
            # few more decisions and require the visible stop to appear.
            for _ in range(5):
                policy._nav_exhausted = True
                key = policy.choose_key(snapshot)
                if policy.last_reason == "livelock:exhausted":
                    break
            self.assertEqual(policy.last_reason, "livelock:exhausted")
            self.assertEqual(key, WAIT_KEY)


class SurvivalGateTest(unittest.TestCase):
    def _dungeon(self, *, food, inventory=(), grids=None, monsters=()):
        cells = grids or {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 8): grid(10, 8, upstairs=True),
            Position(10, 9): grid(10, 9),
        }
        return Snapshot(
            player(10, 10, food=food),
            cells,
            list(monsters),
            floor_key=(2, 3, 0),
            width=40,
            height=40,
            inventory=list(inventory),
        )

    def test_hungry_with_food_eats_even_with_a_descent_target_known(self):
        # Pre-R1, a known downstairs made step 6 return before the eat step —
        # the "eat is dead while descending" hole behind the starvation death.
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        snap = self._dungeon(
            food=1500, inventory=[item("b", FOOD, 35)], grids=grids
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "Eb")
        self.assertEqual(policy.last_reason, "survival:eat")

    def test_starving_with_no_food_overrides_mining_mode(self):
        snap = self._dungeon(food=800)  # "weak", empty pack
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy.choose_key(snap)
        self.assertEqual(policy._last_return_trigger, "food-hungry")
        self.assertTrue(policy.last_reason.startswith("return:"))
        self.assertTrue(policy._returning_to_town)

    def test_well_fed_mining_run_never_triggers_the_survival_path(self):
        # A kitless miner may still be sent home by fundraising's OWN return
        # policy — that is pre-existing behaviour. What the gate must never do
        # is claim a well-fed character is starving.
        snap = self._dungeon(food=12000)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy.choose_key(snap)
        self.assertFalse(policy.last_reason.startswith("survival:"))
        self.assertNotEqual(policy._last_return_trigger, "food-hungry")

    def test_gate_defers_to_combat_unless_fainting(self):
        snap = self._dungeon(
            food=1500,
            inventory=[item("b", FOOD, 35)],
            monsters=[hostile(1, 10, 11)],
        )
        policy = HengbotPolicy()
        policy.choose_key(snap)
        self.assertEqual(policy.last_reason, "melee")

    def test_gate_eats_mid_combat_when_fainting(self):
        snap = self._dungeon(
            food=100,  # fainting
            inventory=[item("b", FOOD, 35)],
            monsters=[hostile(1, 10, 11)],
        )
        policy = HengbotPolicy()
        key = policy.choose_key(snap)
        # The emergency-item step (step 0) may claim the fainting case first;
        # either path must put food in the character's mouth this turn.
        self.assertIn("E", key)

    def test_gate_ignores_a_distant_spectator_monster(self):
        # A hostile merely visible across the floor must not indefinitely
        # defer eating — only a NEARBY threat does.
        snap = self._dungeon(
            food=1500,
            inventory=[item("b", FOOD, 35)],
            monsters=[hostile(1, 10, 20, distance=10)],
        )
        policy = HengbotPolicy()
        self.assertEqual(policy.choose_key(snap), "Eb")
        self.assertEqual(policy.last_reason, "survival:eat")

    def test_weak_with_no_food_leaves_a_kill_quest_floor(self):
        # Starvation kills through paralysis with HP untouched, so the
        # kill-quest exit lock's HP panic release never fires. Weak-or-worse
        # with nothing edible must release the lock and walk out via the
        # exit stairs, visibly accepting the quest loss.
        from hengbot.quest_knowledge import QuestInfo
        from hengbot.model import QuestState

        info = QuestInfo(14, "Warg problem", 5, 5, 0, num_mon=16)
        quest = QuestState(id=14, status=1, type=5, cur_num=2, max_num=16)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 8): grid(10, 8, upstairs=True),
        }
        snap = Snapshot(
            player(10, 10, food=800),  # weak, empty pack
            grids,
            [],
            floor_key=(0, 5, 14),
            width=40,
            height=40,
            quests={14: quest},
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        policy.choose_key(snap)
        self.assertIn(
            policy.last_reason,
            {"survival:seek-exit", "survival:stairs-quest-fail",
             "survival:ascend", "return:ascend", "return:seek-upstairs"},
        )

    def test_merely_hungry_keeps_working_a_locked_quest_floor(self):
        from hengbot.quest_knowledge import QuestInfo
        from hengbot.model import QuestState

        info = QuestInfo(14, "Warg problem", 5, 5, 0, num_mon=16)
        quest = QuestState(id=14, status=1, type=5, cur_num=2, max_num=16)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 8): grid(10, 8, upstairs=True),
        }
        snap = Snapshot(
            player(10, 10, food=1500),  # hungry but not yet weak
            grids,
            [],
            floor_key=(0, 5, 14),
            width=40,
            height=40,
            quests={14: quest},
        )
        policy = HengbotPolicy(quest_knowledge={14: info})
        policy.choose_key(snap)
        self.assertFalse(policy.last_reason.startswith("survival:"))
        self.assertFalse(policy.last_reason.startswith("return:"))


if __name__ == "__main__":
    unittest.main()
