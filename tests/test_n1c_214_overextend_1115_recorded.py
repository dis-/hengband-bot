"""n1-c life-214 2026-11-15: a dive's haul is what it keeps, and an Angband alternate is no switch.

Owner (verbatim): 「持ち帰るべき有効な品を5つ以上拾う、に条件を引き上げる。壊す、捨てる品をカウント
しない。」 -- asked why n1-c (Lv38 Magic-Eater, Angband 49F, about fifty dives in two hours,
mostly 20-60 s) never fell back to a shallower depth (「こういうときはフォールバックして少し
浅い階層で探索させることになっていなかったか？」).  ``over_extension.judge_dive`` reset the
over-extended streak on more than ``OVEREXTEND_LOOT_MAX`` pickup decisions; 16:06:44 (turn
4833524): two over-extended dives (16:04:32 four escapes, 16:05:16 three) and then a dive of
six pickups reset the streak at 2, though it kept four items: four armours and a crown were
destroyed by the game's auto-destroy when identified (「ザック中: 金の冠 [0,+5](j)。」
「金の冠 [0,+5]を自動破壊します。」; src/spell-kind/spells-perception.cpp identify_item ->
autopick_alter_item with destroy_identify), a Rod of Fire Bolts was absorbed.  Now the haul is
the acquisitions still carried and not junk at the town arrival (``dive_haul``).

Second (the alternate): the alternate-dungeon record of turn 5249782 (17:03) held Angband as
the alternate (``guardian_valve``) and 91 dives without depth progress -- Angband, the target
itself once its recall is open, so the no-depth-progress valve that waits for no alternate never
ran.  ``alternate_lease.diverts``: an unleased Angband alternate while its recall is open leads
nowhere else.

Recorded (tests/extract_n1c_214_overextend_1115_fixture.py): the town-arrival checkpoint of 17:07
(turn 5269763, after an Angband 49F dive) restores the character -- its dungeon knowledge,
landings (Angband 49, Chameleon cave 30, the Mountain 25, the Orc cave 23, the Castle 20,
dungeon 4 18, the Forest 15, the Yeek cave 13), equipment state and the junk predicate's gates
-- and its journal row 0 is the town board; the packs of seven Angband 49F dives of 16:00-16:18
(every board on which the carried units changed or that followed a pickup decision) are carried
on that town board and on the first raw board of the checkpoint's own 49F dive.  DECLARED: the
boards are observed through ``_observe`` (the judgement's producer), the turns shifted to follow
the checkpoint's, a decided reason other than a pickup observed as ``explore``; each dive's
counted escapes (the live ``over_extension.dive_emergencies`` increments) are counted with
``escape_count.count`` on its first board; the five Yeek cave fundraising dives of 16:07-16:11
between d67 and d73 are left out (fundraising dives are not judged); the streak starts at the
live value 0 (16:04:07).

On this board the fallback floor is 29 (the deepest reached 49 less 20, owner 2026-11-13) and
the only entered landing in 29-48 is the Chameleon cave 30, never a fallback, so the valve that
now fires on d73 (16:12:38) finds no landing; since owner 2026-11-15 (「想定は城か山。城29F、山29F
をターゲットにして、浅いところから潜って辿り着く。」, dive_floor) it then dives the Mountain 25F to 29F
(tests/test_n1c_214_dive_floor_1115_recorded.py).  With the floor lifted (DECLARED WALL) it takes
the Mountain 25, the deepest that fits (owner 2026-11-10 「収まる中で一番深い所へ」).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import alternate_lease, dive_floor, escape_count, fallback_depth_floor
from hengbot.model import DUNGEON_ANGBAND, parse_snapshot
from hengbot.policy_constants import (
    EMPTY_DIVE_LIMIT, NO_DEPTH_PROGRESS_DIVE_LIMIT, OVEREXTEND_LOOT_MAX, PICKUP_REASONS,
)
from support.town_arrival_fixture import load
from tests.support.fallback_floor import floor_lifted

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-214-overextend-1115"
MOUNTAIN, CHAMELEON_CAVE = 14, 18
FIRST_TURN = 4813671  # d64's first board
# The alternate-dungeon record of turn 5249782 (2026-11-15 17:03, n1-c life-214).
RECORD_17_03 = {"_alternate_dungeon": 1, "_alternate_dungeon_reason": "guardian_valve",
                "_last_overextended_depth": 49, "_no_depth_progress_dives": 91}


class N1c214Dives(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, journal, rows = load(FIXTURE, Path(scratch.name))
        self.addCleanup(lambda: self.policy._home_disposal.history_path.unlink(missing_ok=True))
        entry = journal[0]
        self.town_raw = json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])
        self.dives = json.loads(lzma.decompress((FIXTURE / "dives.json.xz").read_bytes()))
        # Row 0: the checkpoint's own dive ends on its arrival board.
        self.policy.last_reason = "return:wait-recall"
        self.policy._observe(rows[0][1]())
        self.shift = self.town_raw["turn"] + 1000 - FIRST_TURN
        self.policy._target_empty_dives = 0  # DECLARED: the live streak at 16:04:07
        # DECLARED: no dive without depth progress yet, so that valve (AngbandAlternateTest's
        # subject) stays out of the over-extension replay; the checkpoint's count is 2.
        self.policy._no_depth_progress_dives = 0

    def board(self, raw, state):
        raw = copy.deepcopy(raw)
        raw["inventory"], raw["equipment"] = state["inventory"], state["equipment"]
        raw["turn"] = state["turn"] + self.shift
        return parse_snapshot(raw, self.policy._monrace_knowledge)

    def dive(self, name):
        """One recorded dive, from its first 49F board to its town arrival board."""
        policy, dive = self.policy, self.dives[name]
        states = dive["states"]
        for index, state in enumerate(states[:-1]):
            policy.last_reason = (
                "town:wait-recall" if index == 0
                else state["reason"] if state["reason"] in PICKUP_REASONS else "explore")
            policy._observe(self.board(self.dives["template"], state))
            if index == 0:
                for _ in range(dive["escapes"]):
                    escape_count.count(policy)
        policy.last_reason = "return:wait-recall"
        arrival = self.board(self.town_raw, states[-1])
        policy._observe(arrival)
        return arrival

    def dives_through(self, last):
        order = ["d64", "d65", "d66", "d67", "d73", "d74", "d75"]
        streaks = []
        for name in order[:order.index(last) + 1]:
            arrival = self.dive(name)
            streaks.append((name, self.policy._target_empty_dives))
        return arrival, streaks


class KeptHaulTest(N1c214Dives):
    """「壊す、捨てる品をカウントしない」: only what the dive keeps clears the streak."""

    def test_six_pickups_keeping_four_hold_the_streak(self):
        arrival, streaks = self.dives_through("d67")
        dive = self.dives["d67"]
        self.assertEqual((dive["time"], dive["pickup_decisions"], dive["escapes"]),
                         ("2026-11-15T16:06:44+0900", 6, 1))
        self.assertGreater(dive["pickup_decisions"], OVEREXTEND_LOOT_MAX)
        # Unfixed (live): the six pickups reset the streak, 2 -> 0.
        self.assertEqual(streaks, [("d64", 0), ("d65", 1), ("d66", 2), ("d67", 2)])
        # Ten kinds entered the pack on d67; four of them are still carried at the arrival.
        self.assertEqual((self.policy._dive_loot, self.policy._dive_kept_loot), (10, 4))
        self.assertEqual(arrival.dungeon_recall_depths[DUNGEON_ANGBAND], 49)

    def test_the_third_over_extended_dive_asks_the_valve(self):
        policy = self.policy
        self.dives_through("d67")
        asked = []
        real = policy._pick_alternate_dungeon

        def recorded(snapshot, **kwargs):
            asked.append((kwargs, real(snapshot, **kwargs)))
            return asked[-1][1]

        # The real pick answers; its questions and answers are only recorded.
        with mock.patch.object(policy, "_pick_alternate_dungeon", side_effect=recorded):
            arrival = self.dive("d73")
        self.assertEqual((self.dives["d73"]["pickup_decisions"], policy._dive_kept_loot), (7, 1))
        # Unfixed: the seven pickups reset the streak and the valve was never asked.
        over_extension_asks = [answer for kwargs, answer in asked
                               if kwargs.get("prefer_deepest") and "max_entry_depth" not in kwargs]
        # No landing fits (the floor 29, the Chameleon cave 30 is never a fallback): the dive to
        # the floor answers, the Mountain (dive_floor).
        self.assertEqual(over_extension_asks, [MOUNTAIN])
        self.assertEqual(policy._target_empty_dives, 0)
        self.assertEqual(policy._last_overextended_depth, 49)
        self.assertEqual(fallback_depth_floor.floor(policy, arrival), 29)
        self.assertEqual(arrival.dungeon_recall_depths[CHAMELEON_CAVE], 30)
        self.assertFalse(policy._fallback_destination_allowed(CHAMELEON_CAVE))
        self.assertEqual((policy._alternate_dungeon, dive_floor.target(policy)), (MOUNTAIN, 29))

    @floor_lifted()  # DECLARED WALL (tests/support/fallback_floor.py): the floor refuses every landing
    def test_with_the_floor_lifted_the_switch_lands_on_the_mountain(self):
        policy = self.policy
        _arrival, streaks = self.dives_through("d73")
        self.assertEqual(streaks[-2:], [("d67", 2), ("d73", 0)])
        self.assertEqual(EMPTY_DIVE_LIMIT, 3)
        # Unfixed: no switch (the streak reset on d67 and d73).
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason),
                         (MOUNTAIN, "over_extended_dives"))
        self.assertEqual(policy._target_dungeon_id, MOUNTAIN)

    def test_a_dive_keeping_five_or_more_still_resets(self):
        # Control, on the fixed and the unfixed code alike: d75 (16:18:02, 23 pickups) keeps
        # eleven items.  DECLARED: the streak d74 leaves on the fixed code (1) raised to 2.
        self.policy._target_empty_dives = EMPTY_DIVE_LIMIT - 1
        self.dive("d75")
        dive = self.dives["d75"]
        self.assertEqual((dive["time"], dive["pickup_decisions"]), ("2026-11-15T16:18:02+0900", 23))
        self.assertEqual(self.policy._target_empty_dives, 0)
        self.assertEqual(self.policy._dive_kept_loot, 11)
        self.assertGreater(self.policy._dive_kept_loot, OVEREXTEND_LOOT_MAX)

    def test_d74_after_the_valve_starts_the_next_streak(self):
        _arrival, streaks = self.dives_through("d74")
        self.assertEqual(self.dives["d74"]["pickup_decisions"], 7)
        self.assertEqual(self.policy._dive_kept_loot, 2)
        # Unfixed: the seven pickups reset it (0).
        self.assertEqual(streaks[-2:], [("d73", 0), ("d74", 1)])


class AngbandAlternateTest(N1c214Dives):
    """An unleased Angband alternate with Angband's recall open is the target itself."""

    def held(self, **state):
        # DECLARED: the 17:03 alternate-dungeon record's switch state (RECORD_17_03); its
        # restore refuses this later board (the Orc cave fell at 17:06).
        for name, value in {**RECORD_17_03, **state}.items():
            setattr(self.policy, name, value)

    def test_the_no_depth_progress_valve_runs_under_the_angband_alternate(self):
        self.held()
        arrival = self.dive("d65")
        self.assertTrue(arrival.angband_recall_unlocked)
        self.assertGreaterEqual(RECORD_17_03["_no_depth_progress_dives"], NO_DEPTH_PROGRESS_DIVE_LIMIT)
        # Unfixed: the valve waited for no alternate and the count went on (92).
        self.assertEqual(self.policy._no_depth_progress_dives, 0)
        # On this board no landing fits (floor 29): the dive to the floor (dive_floor, 11-15).
        self.assertEqual((self.policy._alternate_dungeon, self.policy._alternate_dungeon_reason,
                          dive_floor.target(self.policy)), (MOUNTAIN, "no_depth_progress", 29))
        self.assertTrue(arrival.angband_recall_unlocked)

    @floor_lifted()  # DECLARED WALL (tests/support/fallback_floor.py): the floor refuses every landing
    def test_with_the_floor_lifted_it_switches_to_the_mountain(self):
        self.held()
        self.dive("d65")
        self.assertEqual((self.policy._alternate_dungeon, self.policy._alternate_dungeon_reason),
                         (MOUNTAIN, "no_depth_progress"))
        self.assertEqual(self.policy._alternate_lease, alternate_lease.FIRST_LEASE)

    def test_control_a_leased_angband_switch_still_blocks_it(self):
        # A switch made to Angband because a deeper conquest was too hard (n1-b life-365) is a
        # lease still running: its dives are the lease's, not a lack of depth progress.
        self.held(_alternate_dungeon_reason="over_extended_dives",
                  _alternate_lease=alternate_lease.FIRST_LEASE, _alternate_dives=0)
        arrival = self.dive("d65")
        self.assertTrue(alternate_lease.diverts(self.policy, arrival))
        self.assertEqual(self.policy._no_depth_progress_dives, 92)
        self.assertEqual((self.policy._alternate_dungeon, self.policy._alternate_dives),
                         (DUNGEON_ANGBAND, 1))


if __name__ == "__main__":
    unittest.main()
