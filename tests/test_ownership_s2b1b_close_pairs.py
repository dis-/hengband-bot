"""Stage S2b.1b: close the in-scope violation pairs of the live run -- record-only.

``SOL-DESIGN-ownership-contract.md`` rev 10.2 (the S2b.2 gate: in-scope
violations <= 1 per runtime hour and every remaining pair explained).  The
measurement: bot session 36788, 2026-09-25 19:39-20:41, 16,750 claim rows;
``ladder_numbers`` read 33 in-scope violations and 13 in-scope retargets.
The rows behind all 46 events are frozen in
``tests/fixtures/ownership-claims-20260925-2041-in-scope-violations.jsonl.gz``
(provenance beside it).

One cause per pair, one test class per cause
--------------------------------------------
(b) typing   ``breakout:seek-frontier`` (16) and ``livelock:seek-window-edge``
             (1), ``detectors>explore``: one-shot rewrites that hand the walk
             to explore on the next board, typed Reach -> typed Terminal.
(c) rank     ``esp-threat:hunt-weak`` (4, ``esp-threat>combat``): produced at
             the rest slot's rung, ranked at the committed hunt's rung.  Once
             it ranks below combat the swing preempts it, and the rest slot's
             walk then needs its own ending (a): the rest gate closing, or the
             slot choosing no hunt.
(a) writer   a suspended chase whose monster is gone was never released
             (``hunt>explore`` 9); a named release found another owner's claim
             standing and closed nothing, so a suspended claim was displaced
             (``floor-loot>explore`` 2 -- and the emergency-return gate that
             shuts loot out had no release at all); ``_release_choke_plan``
             had no release (``positioning>combat`` 1); the town kill-mob
             chase and its last-known walk replaced each other (retarget
             ``survival`` 6); fundraising's own order (multiplier, loot,
             vein) replaced its walks (retarget ``fundraising`` 5); the
             oscillation branch searched away from the explore walk
             (retarget ``explore`` 2).

The reader-visible corrections (typing, rank) are re-derived on the frozen
rows through ``ownership_metrics.rejudge_recorded_violations``; the writer's
missing releases are pinned on boards that reproduce the recorded sequence,
each with a revert that brings the recorded violation back.  Record-only: the
last class replays every ``choose_key`` pin with the register off and compares
keys and reasons.

No pre-existing test is changed.  No policy attribute is added (the new code
reads ``_explore_goal_identity``, ``_esp_threat_assessment``,
``_town_hunt_target``, ``_loot_target``, ``_treasure_target`` and the choke
plan, all existing, and keeps the rest in locals).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare runs

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.claim_goal_typing import (
    GoalTypingRow,
    WALK_TARGET,
    goal_typing,
)
from hengbot.claim_ladder import rung_named, rung_of
from hengbot.claim_register import ClaimOwner, reach, reach_monster
from hengbot.model import (
    DUNGEON_YEEK_CAVE,
    MonsterState,
    PLAYER_CLASS_WARRIOR,
    Position,
    Snapshot,
    SV_DIGGING_SHOVEL,
    TVAL_DIGGING,
)
from hengbot.ownership_metrics import (
    ladder_numbers,
    rejudge_recorded_violations,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import ChokeEngagementPlan

import policy_shop_fixture as shop_fixture
from policy_fixtures import grid, hostile, item, player
from test_ownership_claims import _Replay
from test_ownership_s2a1_closure import (
    _dungeon_board,
    _exit,
    _fresh_policy,
    _town_board,
)
from test_ownership_s2b1_ladder import _Decisions


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "tests" / "fixtures"
    / "ownership-claims-20260925-2041-in-scope-violations.jsonl.gz"
)
FIXTURE_SHA256 = "a4bd0fbf3db48672168a61db3b003e9eeff4196d8b82342f241203b400e2422b"

# ``ladder_numbers`` on session 36788 (all 16,750 rows); the frozen rows
# reproduce the in-scope lines exactly.
RECORDED_IN_SCOPE = {
    "detectors>explore": 17,
    "hunt>explore": 9,
    "esp-threat>combat": 4,
    "floor-loot>explore": 2,
    "positioning>combat": 1,
}
RECORDED_RETARGETS = {"survival": 6, "fundraising": 5, "explore": 2}
# What the reader alone can say today: typing and rank.
READER_TERMINAL_NOW = {"in-scope:detectors>explore": 17}
READER_PREEMPTION = {"in-scope:esp-threat>combat": 4}
READER_STILL_VIOLATION = {
    "hunt>explore": 9,
    "retarget:survival": 6,
    "retarget:fundraising": 5,
    "retarget:explore": 2,
    "floor-loot>explore": 2,
    "positioning>combat": 1,
}

PRE_FIX_REACH = frozenset({"breakout:seek-frontier", "livelock:seek-window-edge"})


def _pre_fix_typing(family, reason):
    """The typing table before S2b.1b: the two rewrites typed Reach."""
    if family == "detectors" and (reason or "") in PRE_FIX_REACH:
        return GoalTypingRow(family, reason, "Reach", WALK_TARGET)
    return goal_typing(family, reason)


def _pre_fix_rung_of(family, reason, **kwargs):
    """The ladder before S2b.1b: the rest slot's hunt at the hunt rung."""
    name = str(getattr(family, "value", family))
    if name == "esp-threat" and (reason or "").startswith(
        ("esp-threat:hunt-weak", "esp-threat:hunt-medium")
    ):
        return rung_named("_esp_threat_hunt_key")
    return rung_of(family, reason, **kwargs)


def _frozen_rows():
    with gzip.open(FIXTURE, "rb") as stream:
        data = stream.read()
    return data, [json.loads(line) for line in data.decode("utf-8").splitlines()]


def _dungeon_policy(board):
    policy = _fresh_policy(board)
    skill, _boards = _Replay.dungeon_boards()
    policy.consume_skill_knowledge(skill)
    return policy


def _quiet_dungeon_board(**player_fields):
    """Recorded dungeon board 0 with nothing perceived: its decision passes
    the rest block and lands on exploration."""
    board = replace(_dungeon_board(0), detected_monsters=[])
    if player_fields:
        board = replace(board, player=replace(board.player, **player_fields))
    return board


def _standing(policy, family, reason, goal, board):
    """The claim the previous row left, opened at its own rung."""
    rung = rung_of(family, reason)
    register = policy._claim_register
    register.declare(
        family, goal, floor=board.floor_key,
        opened_sequence=policy._decision_sequence, opened_turn=board.turn,
        rank=rung.rank, rung=rung.name,
    )
    register.take_closing()
    return register.current


def _suspend_standing(policy, board, label="preempted-by:combat"):
    register = policy._claim_register
    register.suspend(label, sequence=policy._decision_sequence, turn=board.turn)
    register.take_closing()


def _no_release(*_args, **_kwargs):
    return None


# -- the recorded rows, re-derived by the reader -------------------------------


class RecordedRowsTest(unittest.TestCase):
    """Typing and rank are reader-visible: re-derived on the frozen rows."""

    @classmethod
    def setUpClass(cls):
        cls.data, cls.rows = _frozen_rows()

    def test_the_rows_are_the_frozen_ones_and_read_as_measured(self):
        self.assertEqual(hashlib.sha256(self.data).hexdigest(), FIXTURE_SHA256)
        self.assertEqual(len(self.rows), 200)
        numbers = ladder_numbers(self.rows)
        self.assertEqual(numbers["violations"]["in-scope"]["pairs"], RECORDED_IN_SCOPE)
        self.assertEqual(numbers["retargets"]["in-scope"]["by_owner"], RECORDED_RETARGETS)

    def test_the_reader_rejudges_typing_and_rank(self):
        judged = rejudge_recorded_violations(self.rows)
        self.assertEqual(judged["before"]["in-scope"]["count"], 46)
        self.assertEqual(
            judged["verdicts"]["terminal-now"]["pairs"], READER_TERMINAL_NOW
        )
        self.assertEqual(judged["verdicts"]["preemption"]["pairs"], READER_PREEMPTION)
        self.assertEqual(
            judged["after"]["in-scope"]["pairs"], READER_STILL_VIOLATION
        )
        self.assertNotIn("holder-unknown", judged["verdicts"])

    def test_revert_proof_the_pre_fix_table_and_ladder_keep_them(self):
        with patch("hengbot.ownership_metrics.goal_typing", _pre_fix_typing), patch(
            "hengbot.ownership_metrics.rung_of", _pre_fix_rung_of
        ):
            judged = rejudge_recorded_violations(self.rows)
        self.assertNotIn("terminal-now", judged["verdicts"])
        self.assertNotIn("preemption", judged["verdicts"])
        self.assertEqual(judged["after"]["in-scope"]["count"], 46)


# -- (b) typing: detectors>explore ---------------------------------------------


class OneShotRewriteTypingTest(unittest.TestCase):
    """``breakout:seek-frontier`` (16) and ``livelock:seek-window-edge`` (1):
    the rewrite owns one decision; explore owns the walk that follows."""

    REASONS = ("breakout:seek-frontier", "livelock:seek-window-edge")

    def test_typed_terminal(self):
        for reason in self.REASONS:
            with self.subTest(reason=reason):
                self.assertEqual(goal_typing("detectors", reason).kind, "Terminal")
        # the other livelock walk keeps its Reach
        self.assertEqual(
            goal_typing("detectors", "livelock:seek-upstairs").kind, "Reach"
        )

    def _sequence(self, reason):
        run = _Decisions()
        rewrite = run.decide(reason, cell=run.cell(5))
        walk = run.decide("explore", cell=run.cell(5))
        return rewrite, walk

    def test_explore_takes_the_same_goal_without_a_violation(self):
        for reason in self.REASONS:
            with self.subTest(reason=reason):
                rewrite, walk = self._sequence(reason)
                self.assertEqual(rewrite["goal"]["kind"], "Terminal")
                self.assertIsNone(walk["violation"])
                self.assertEqual(walk["goal"]["kind"], "Reach")

    def test_revert_proof_typed_reach_the_walk_is_a_violation(self):
        for reason in self.REASONS:
            with self.subTest(reason=reason), patch(
                "hengbot.policy.claim_goal_typing", _pre_fix_typing
            ):
                _rewrite, walk = self._sequence(reason)
                self.assertEqual(
                    (walk["violation"]["from"], walk["violation"]["to"]),
                    ("detectors", "explore"),
                )


# -- (c) rank + (a) the rest slot's ending: esp-threat>combat ------------------


class EspThreatRestHuntTest(unittest.TestCase):
    """``esp-threat:hunt-weak`` (4): the swing preempts it; the rest slot's
    walk ends where the slot is passed without a hunt."""

    def test_the_rest_slot_ranks_below_the_combat_rungs(self):
        weak = rung_of("esp-threat", "esp-threat:hunt-weak")
        self.assertEqual(weak.name, "_esp_threat_rest_key")
        self.assertEqual(
            rung_of("esp-threat", "esp-threat:hunt-medium").name,
            "_esp_threat_rest_key",
        )
        self.assertEqual(
            rung_of("esp-threat", "esp-threat:hunt-strong").name,
            "_esp_threat_hunt_key",
        )
        for reason in ("melee", "ranged:fire"):
            with self.subTest(reason=reason):
                self.assertLess(rung_of("combat", reason).rank, weak.rank)

    def test_the_swing_preempts_the_walk(self):
        run = _Decisions()
        walk = run.decide("esp-threat:hunt-weak", cell=run.cell(6))
        swing = run.decide("melee")
        self.assertIsNone(swing["violation"])
        self.assertEqual(
            (swing["closed_claim"]["claim_id"], swing["closed_claim"]["closed_reason"]),
            (walk["claim_id"], "preempted-by:combat"),
        )
        back = run.decide("esp-threat:hunt-weak", cell=run.cell(6))
        self.assertEqual(back["claim_id"], walk["claim_id"])

    def test_revert_proof_at_the_hunt_rung_the_swing_is_a_violation(self):
        with patch("hengbot.policy.claim_rung_of", _pre_fix_rung_of):
            run = _Decisions()
            run.decide("esp-threat:hunt-weak", cell=run.cell(6))
            swing = run.decide("melee")
        self.assertEqual(
            (swing["violation"]["from"], swing["violation"]["to"]),
            ("esp-threat", "combat"),
        )

    def _suspended_walk_then_decide(self, board, *, release=True):
        policy = _dungeon_policy(board)
        cell = (board.player.position.y + 5, board.player.position.x)
        _standing(policy, "esp-threat", "esp-threat:hunt-weak", reach(cell), board)
        _suspend_standing(policy, board)
        if release:
            key = policy.choose_key(board)
        else:
            with patch.object(policy, "_release_esp_threat_rest_hunt", _no_release):
                key = policy.choose_key(board)
        return str(key), policy.last_reason, dict(policy.decision_claim)

    def test_the_rest_gate_closed_ends_the_suspended_walk(self):
        # The recorded 11421 / 11458: HP back at 90 %, the slot is not asked.
        board = _quiet_dungeon_board()
        self.assertGreaterEqual(board.player.hp_ratio, 0.9)
        _key, reason, row = self._suspended_walk_then_decide(board)
        self.assertEqual(reason, "explore")
        self.assertIsNone(row["violation"])
        (closing,) = row["suspended_closed"]
        self.assertEqual(
            (closing["owner"], closing["closed"], closing["closed_reason"]),
            ("esp-threat", "release", "esp-threat:rest-gate-closed"),
        )

    def test_the_slot_choosing_no_hunt_ends_it(self):
        board = _quiet_dungeon_board(hp=100)
        _key, reason, row = self._suspended_walk_then_decide(board)
        self.assertEqual(reason, "rest")
        (closing,) = row["suspended_closed"]
        self.assertEqual(closing["closed_reason"], "esp-threat:rest-no-assessment")

    def test_revert_proof_without_the_ending_explore_displaces_it(self):
        board = _quiet_dungeon_board()
        _key, _reason, row = self._suspended_walk_then_decide(board, release=False)
        (closing,) = row["suspended_closed"]
        self.assertEqual(closing["closed_reason"], "resume-displaced")
        self.assertEqual(
            (closing["violation"]["from"], closing["violation"]["to"]),
            ("esp-threat", "explore"),
        )

    def test_the_committed_strong_hunt_is_not_touched(self):
        board = _quiet_dungeon_board()
        policy = _dungeon_policy(board)
        cell = (board.player.position.y + 5, board.player.position.x)
        _standing(policy, "esp-threat", "esp-threat:hunt-strong", reach(cell), board)
        _suspend_standing(policy, board)
        policy._release_esp_threat_rest_hunt("esp-threat:rest-gate-closed")
        self.assertEqual(len(policy._claim_register.suspended), 1)


# -- (a) hunt>explore -----------------------------------------------------------


class SuspendedChaseTargetLostTest(unittest.TestCase):
    """``hunt>explore`` (9): hunt, a shot preempts it, the target dies, the
    next decision explores.  The suspended chase is released as an active
    one would be."""

    def _sequence(self):
        board = _dungeon_board(5)
        far = next(
            (monster.index, monster.race_id)
            for monster in board.detected_monsters
            if board.player.position.distance_to(monster.position) > 1
        )
        policy = _fresh_policy(board)
        policy.last_reason = "hunt"
        policy._declare_monster(far)
        chase = _exit(policy, board, "hunt", "1")
        policy._decision_goal = None
        shot = _exit(policy, board, "ranged:fire", "f1")
        return policy, chase, shot

    def test_the_gone_target_releases_the_suspended_chase(self):
        policy, chase, shot = self._sequence()
        self.assertEqual(shot["closed_claim"]["closed_reason"], "preempted-by:combat")
        policy._decision_goal = None
        after = _exit(policy, _quiet_dungeon_board(), "explore", "4")
        self.assertIsNone(after["violation"])
        (closing,) = after["suspended_closed"]
        self.assertEqual(
            (closing["claim_id"], closing["closed"], closing["closed_reason"]),
            (chase["claim_id"], "release", "target-lost"),
        )
        self.assertNotIn("violation", closing)

    def test_revert_proof_a_perceived_target_is_displaced(self):
        policy, _chase, _shot = self._sequence()
        policy._decision_goal = None
        board = _dungeon_board(5)
        standing_in = next(
            monster for monster in board.detected_monsters
            if board.player.position.distance_to(monster.position) > 1
        )
        with patch.object(
            policy, "_claim_perceived_monster", return_value=standing_in
        ):
            after = _exit(policy, _quiet_dungeon_board(), "explore", "4")
        (closing,) = after["suspended_closed"]
        self.assertEqual(closing["closed_reason"], "resume-displaced")
        self.assertEqual(
            (closing["violation"]["from"], closing["violation"]["to"]),
            ("hunt", "explore"),
        )


# -- (a) floor-loot>explore -----------------------------------------------------


class SuspendedNamedReleaseTest(unittest.TestCase):
    """``floor-loot>explore`` (2): seek-loot, an escape preempts it, the
    emergency teleport sets ``_emergency_return_active`` and ordinary loot is
    shut out for the floor; the next decision probes / explores."""

    def _loot_walk(self, board):
        policy = _dungeon_policy(board)
        loot = Position(board.player.position.y, board.player.position.x - 3)
        claim = _standing(policy, "floor-loot", "seek-loot", reach((loot.y, loot.x)), board)
        _suspend_standing(policy, board, "preempted-by:escape")
        policy._loot_target = loot
        return policy, claim, loot

    def test_the_emergency_return_gate_releases_the_suspended_walk(self):
        board = _quiet_dungeon_board()
        policy, claim, _loot = self._loot_walk(board)
        policy._emergency_return_active = True
        policy.choose_key(board)
        row = policy.decision_claim
        self.assertEqual(policy.last_reason, "explore")
        self.assertIsNone(row["violation"])
        (closing,) = row["suspended_closed"]
        self.assertEqual(
            (closing["claim_id"], closing["closed"], closing["closed_reason"]),
            (claim.claim_id, "release", "loot-suppressed:emergency-return"),
        )

    def test_revert_proof_without_the_release_explore_displaces_it(self):
        board = _quiet_dungeon_board()
        policy, _claim, _loot = self._loot_walk(board)
        policy._emergency_return_active = True
        with patch.object(policy, "_release_claim_goal", _no_release):
            policy.choose_key(board)
        (closing,) = policy.decision_claim["suspended_closed"]
        self.assertEqual(
            (closing["violation"]["from"], closing["violation"]["to"]),
            ("floor-loot", "explore"),
        )

    def test_a_named_release_closes_its_goal_while_suspended(self):
        board = _quiet_dungeon_board()
        policy, claim, loot = self._loot_walk(board)
        other = Position(loot.y, loot.x - 1)
        policy._release_claim_goal("loot-retarget", other, owners=("floor-loot",))
        self.assertEqual(len(policy._claim_register.suspended), 1)
        policy._release_claim_goal("loot-retarget", loot, owners=("floor-loot",))
        self.assertEqual(policy._claim_register.suspended, ())
        (closing,) = policy._claim_register.take_suspended_closings()
        self.assertEqual(
            (closing["claim_id"], closing["closed_reason"]),
            (claim.claim_id, "loot-retarget"),
        )

    def test_an_unnamed_release_does_not_reach_the_stack(self):
        board = _quiet_dungeon_board()
        policy, _claim, _loot = self._loot_walk(board)
        policy._release_claim_goal("anything", owners=("floor-loot",))
        self.assertEqual(len(policy._claim_register.suspended), 1)


# -- (a) positioning>combat -----------------------------------------------------


class ChokePlanReleaseTest(unittest.TestCase):
    """``positioning>combat`` (1): ``melee:choke-reposition`` walked 22 rows
    toward its choke cell, then the plan was released and a swing followed."""

    def _reposition(self):
        board = _quiet_dungeon_board()
        board = replace(board, player=replace(board.player, hp=board.player.max_hp // 5))
        policy = _fresh_policy(board)
        destination = Position(board.player.position.y, board.player.position.x - 4)
        _standing(
            policy, "positioning", "melee:choke-reposition",
            reach((destination.y, destination.x)), board,
        )
        policy._choke_engagement_plan = ChokeEngagementPlan(
            floor=board.floor_key, phase="reposition", destination=destination,
            covered_retreat_direction=(0, 1), trigger_last_seen={},
            start_exp=board.player.exp, start_gold=board.player.gold,
            start_breeder_count=0, last_player_hp=board.player.hp,
        )
        return policy, board

    def test_the_released_plan_releases_its_walk(self):
        policy, board = self._reposition()
        self.assertIsNone(policy._choke_engagement_key(board, [], []))
        self.assertEqual(policy._choke_engagement_plan.release_cause, "hp-authority")
        row = _exit(policy, board, "melee", "1")
        self.assertIsNone(row["violation"])
        self.assertEqual(
            (row["closed_claim"]["closed"], row["closed_claim"]["closed_reason"]),
            ("release", "choke-plan-released:hp-authority"),
        )

    def test_revert_proof_without_the_release_the_swing_is_a_violation(self):
        policy, board = self._reposition()
        with patch.object(policy, "_release_claim_goal", _no_release):
            policy._choke_engagement_key(board, [], [])
        row = _exit(policy, board, "melee", "1")
        self.assertEqual(
            (row["violation"]["from"], row["violation"]["to"]),
            ("positioning", "combat"),
        )


# -- (a) retarget: survival (town kill-mob) -------------------------------------


class TownKillMobChaseTest(unittest.TestCase):
    """Retarget ``survival`` (6): the chase of a monster and the walk to where
    it was last seen replace each other (the recorded 3219-3227, 8009, where
    the monster was detected but not in sight)."""

    def _board(self, **monsters):
        board = _town_board()
        return replace(board, **monsters)

    @staticmethod
    def _far_cell(board):
        here = board.player.position
        return next(
            grid.position for grid in sorted(
                board.grids.values(),
                key=lambda grid: (
                    here.distance_to(grid.position), grid.position.y, grid.position.x
                ),
            )
            if grid.passable and not grid.is_store
            and here.distance_to(grid.position) >= 4
        )

    def _out_of_sight(self, release=True):
        base = _town_board()
        here = base.player.position
        detected = MonsterState(
            index=7, position=Position(here.y, here.x + 6), hp=5, max_hp=5,
            distance=6, friendly=False, pet=False, race_id=33,
            perception="detected",
        )
        board = self._board(detected_monsters=[detected])
        policy = _fresh_policy(board)
        _standing(policy, "survival", "town:kill-mob-approach", reach_monster(7, 33), board)
        policy._town_hunt_target = self._far_cell(board)
        if release:
            key = policy._town_kill_mob_key(board)
        else:
            with patch.object(policy, "_release_claim_goal", _no_release):
                key = policy._town_kill_mob_key(board)
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")
        return _exit(policy, board, "town:kill-mob-approach", key)

    def test_a_detected_only_target_ends_the_chase_before_the_last_known_walk(self):
        row = self._out_of_sight()
        self.assertIsNone(row["violation"])
        self.assertEqual(row["closed_claim"]["closed_reason"], "target-out-of-sight")
        self.assertEqual(row["goal_note"], "last-known")

    def test_revert_proof_out_of_sight(self):
        row = self._out_of_sight(release=False)
        self.assertEqual(
            (row["violation"]["kind"], row["violation"]["from"]),
            ("retarget", "survival"),
        )

    def _reacquired(self, release=True):
        base = _town_board()
        target = self._far_cell(base)
        here = base.player.position
        seen = MonsterState(
            index=8, position=target, hp=5, max_hp=5,
            distance=here.distance_to(target), friendly=False, pet=False,
            race_id=34,
        )
        board = self._board(visible_monsters=[seen])
        policy = _fresh_policy(board)
        last_known = Position(here.y + 1, here.x + 1)
        _standing(
            policy, "survival", "town:kill-mob-approach",
            reach((last_known.y, last_known.x)), board,
        )
        policy._town_hunt_target = last_known
        if release:
            key = policy._town_kill_mob_key(board)
        else:
            with patch.object(policy, "_release_claim_goal", _no_release):
                key = policy._town_kill_mob_key(board)
        return _exit(policy, board, "town:kill-mob-approach", key)

    def test_a_monster_in_sight_again_ends_the_last_known_walk(self):
        row = self._reacquired()
        self.assertIsNone(row["violation"])
        self.assertEqual(row["closed_claim"]["closed_reason"], "last-known-reacquired")
        self.assertEqual(row["goal"], {"kind": "Reach", "monster": [8, 34]})

    def test_revert_proof_reacquired(self):
        row = self._reacquired(release=False)
        self.assertEqual(
            (row["violation"]["kind"], row["violation"]["from"]),
            ("retarget", "survival"),
        )

    # Round 2 (gpt-6-sol P2): the monster reappears ADJACENT, at the
    # last-known cell itself; the attack branch acts on it before any route.

    def _reacquired_adjacent(self, *, friendly, release=True):
        base = _town_board()
        here = base.player.position
        cell = next(
            grid.position for grid in sorted(
                base.grids.values(),
                key=lambda grid: (grid.position.y, grid.position.x),
            )
            if grid.passable and not grid.is_store
            and here.distance_to(grid.position) == 1
        )
        seen = MonsterState(
            index=9, position=cell, hp=5, max_hp=5, distance=1,
            friendly=friendly, pet=False, race_id=35,
        )
        board = self._board(visible_monsters=[seen])
        policy = _fresh_policy(board)
        _standing(
            policy, "survival", "town:kill-mob-approach", reach((cell.y, cell.x)),
            board,
        )
        policy._town_hunt_target = cell
        if release:
            key = policy._town_kill_mob_key(board)
        else:
            with patch.object(policy, "_release_claim_goal", _no_release):
                key = policy._town_kill_mob_key(board)
        if friendly:
            self.assertEqual(policy.last_reason, "town:kill-mob-friendly")
            return _exit(policy, board, "town:kill-mob-friendly", key)
        self.assertIsNone(key)  # the ordinary adjacent melee acts
        return _exit(policy, board, "melee", "1")

    def test_an_adjacent_reacquired_monster_ends_the_last_known_walk(self):
        for friendly in (True, False):
            with self.subTest(friendly=friendly):
                row = self._reacquired_adjacent(friendly=friendly)
                self.assertIsNone(row["violation"])
                self.assertEqual(
                    (row["closed_claim"]["closed"],
                     row["closed_claim"]["closed_reason"]),
                    ("release", "last-known-reacquired"),
                )

    def test_revert_proof_reacquired_adjacent(self):
        friendly = self._reacquired_adjacent(friendly=True, release=False)
        self.assertEqual(
            (friendly["violation"]["kind"], friendly["violation"]["from"]),
            ("retarget", "survival"),
        )
        hostile_row = self._reacquired_adjacent(friendly=False, release=False)
        self.assertEqual(
            (hostile_row["violation"]["from"], hostile_row["violation"]["to"]),
            ("survival", "combat"),
        )


# -- (a) retarget: fundraising ---------------------------------------------------


class _MiningBoards(shop_fixture._TownShopFixtureBase):
    """The Yeek-cave level-1 mining boards of ``test_policy_town``."""

    def _board(self, grids, monsters=()):
        tool = item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)
        return Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
            grids,
            list(monsters),
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=1),
            equipment=[tool, self._lantern()],
        )

    @staticmethod
    def _policy(board):
        policy = HengbotPolicy()
        policy.prime(board)
        policy._fundraising_mode = "mine"
        policy._mining_scroll_used_floor = board.floor_key
        return policy


class FundraisingOrderTest(_MiningBoards):
    """Retarget ``fundraising`` (5): the vein walk yields to realised loot
    (6817, 6860, 7544) and the loot walk to a multiplier (7166, 7481)."""

    def _loot_over_vein(self, release=True):
        board = self._board({
            Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, objects=1),
            Position(11, 10): grid(11, 10), Position(12, 10): grid(12, 10),
        })
        policy = self._policy(board)
        vein = Position(12, 10)
        policy._treasure_target = vein
        _standing(policy, "fundraising", "fundraise:seek-treasure", reach((12, 10)), board)
        if release:
            key = policy.choose_key(board)
        else:
            with patch.object(policy, "_release_claim_goal", _no_release):
                key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("6", "fundraise:seek-loot"))
        return policy.decision_claim

    def _multiplier_over_loot(self, release=True):
        breeder = hostile(5, 10, 13, distance=3, can_multiply=True, hp=3,
                          max_hp=3, race_id=40)
        grids = {Position(10, x): grid(10, x) for x in range(8, 15)}
        grids[Position(11, 10)] = grid(11, 10, objects=1)
        board = self._board(grids, [breeder])
        policy = self._policy(board)
        policy._loot_target = Position(11, 10)
        _standing(policy, "fundraising", "fundraise:seek-loot", reach((11, 10)), board)
        threat = {"operational_total": 1.0, "total": 1.0,
                  "expected_total": 1.0, "monsters": []}
        with patch.object(policy, "threat_prediction", return_value=threat):
            if release:
                key = policy.choose_key(board)
            else:
                with patch.object(policy, "_release_claim_goal", _no_release):
                    key = policy.choose_key(board)
        self.assertEqual(
            (str(key), policy.last_reason), ("6", "fundraise:eliminate-multiplier")
        )
        return policy.decision_claim

    def test_loot_before_the_vein_releases_the_vein_walk(self):
        row = self._loot_over_vein()
        self.assertIsNone(row["violation"])
        self.assertEqual(row["closed_claim"]["closed_reason"], "treasure-yield:seek-loot")

    def test_revert_proof_loot_before_the_vein(self):
        row = self._loot_over_vein(release=False)
        self.assertEqual(
            (row["violation"]["kind"], row["violation"]["from"]),
            ("retarget", "fundraising"),
        )

    def test_the_multiplier_before_loot_releases_the_loot_walk(self):
        row = self._multiplier_over_loot()
        self.assertIsNone(row["violation"])
        self.assertEqual(
            row["closed_claim"]["closed_reason"], "loot-yield:eliminate-multiplier"
        )

    def test_revert_proof_the_multiplier_before_loot(self):
        row = self._multiplier_over_loot(release=False)
        self.assertEqual(
            (row["violation"]["kind"], row["violation"]["from"]),
            ("retarget", "fundraising"),
        )


# -- (a) retarget: explore ------------------------------------------------------


class OscillationSearchTest(unittest.TestCase):
    """Retarget ``explore`` (2): explore walks to its goal, the walk circles,
    the oscillation branch searches in place (3466, 14228)."""

    def _walk_then_search(self, release=True):
        board = _quiet_dungeon_board()
        policy = _dungeon_policy(board)
        walk_key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "explore")
        walk = dict(policy.decision_claim)
        policy.confirm_key_posted(walk_key)
        with patch.object(policy, "_is_oscillating", return_value=True), patch.object(
            policy, "_probe_unknown_step", return_value=None
        ):
            if release:
                key = policy.choose_key(board)
            else:
                with patch.object(policy, "_release_explore_walk", _no_release):
                    key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("s", "search"))
        return walk, policy.decision_claim

    def test_the_oscillation_search_releases_the_walk(self):
        walk, row = self._walk_then_search()
        self.assertIsNone(row["violation"])
        self.assertEqual(
            (row["closed_claim"]["claim_id"], row["closed_claim"]["closed_reason"]),
            (walk["claim_id"], "explore-oscillating:search"),
        )

    def test_revert_proof_the_search_is_a_retarget(self):
        _walk, row = self._walk_then_search(release=False)
        self.assertEqual(
            (row["violation"]["kind"], row["violation"]["from"]),
            ("retarget", "explore"),
        )


# -- record-only -----------------------------------------------------------------


class RecordOnlyTest(unittest.TestCase):
    """The same boards decide the same keys and reasons with the register off."""

    def _decide_both(self, build):
        results = []
        for register_on in (True, False):
            policy, board, patches = build()
            if not register_on:
                policy._claim_register = None
            for patcher in patches:
                patcher.start()
            try:
                key = policy.choose_key(board)
            finally:
                for patcher in patches:
                    patcher.stop()
            results.append((str(key), policy.last_reason))
        return results

    def test_keys_and_reasons_are_unchanged(self):
        def rest_gate(hp=None):
            def build():
                board = _quiet_dungeon_board(**({} if hp is None else {"hp": hp}))
                policy = _dungeon_policy(board)
                cell = (board.player.position.y + 5, board.player.position.x)
                _standing(policy, "esp-threat", "esp-threat:hunt-weak", reach(cell), board)
                _suspend_standing(policy, board)
                return policy, board, []
            return build

        def loot_gate():
            board = _quiet_dungeon_board()
            policy = _dungeon_policy(board)
            loot = Position(board.player.position.y, board.player.position.x - 3)
            _standing(policy, "floor-loot", "seek-loot", reach((loot.y, loot.x)), board)
            _suspend_standing(policy, board, "preempted-by:escape")
            policy._loot_target = loot
            policy._emergency_return_active = True
            return policy, board, []

        def oscillation():
            board = _quiet_dungeon_board()
            policy = _dungeon_policy(board)
            policy.confirm_key_posted(policy.choose_key(board))
            return policy, board, [
                patch.object(policy, "_is_oscillating", return_value=True),
                patch.object(policy, "_probe_unknown_step", return_value=None),
            ]

        mining = _MiningBoards()

        def vein():
            board = mining._board({
                Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11),
                Position(10, 12): grid(10, 12, objects=1),
                Position(11, 10): grid(11, 10), Position(12, 10): grid(12, 10),
            })
            policy = mining._policy(board)
            policy._treasure_target = Position(12, 10)
            _standing(policy, "fundraising", "fundraise:seek-treasure", reach((12, 10)), board)
            return policy, board, []

        for name, build in (
            ("rest-gate-closed", rest_gate()),
            ("rest-no-hunt", rest_gate(hp=100)),
            ("loot-gate", loot_gate),
            ("oscillation", oscillation),
            ("vein-yield", vein),
        ):
            with self.subTest(board=name):
                on, off = self._decide_both(build)
                self.assertEqual(on, off)


if __name__ == "__main__":
    unittest.main()
