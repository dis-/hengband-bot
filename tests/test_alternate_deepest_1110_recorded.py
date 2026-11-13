"""n1-b life-362 2026-11-10 08:01: the over-extension switch takes the deepest fit.

Owner request 2026-11-10: 「n1-bの帰還先選定ロジックを確認。61Fが厳しいとき、
50Fとか40Fくらいで探索してほしいのだが23Fで長時間過ごしているようだ。」
Asked how to choose, the owner answered 「収まる中で一番深い所へ」: 「切り替え先を
一番浅いダンジョンではなく、行き過ぎた深さより浅い中で一番深いダンジョンにする
（今なら城の32階）。鉄獄の階は下げない。」

Recorded (tests/extract_n1b_362_alternate_1110_fixture.py): the town arrival
after the third over-extended Angband dive in a row (Angband 70F, two
emergency escapes each, Lv40 warrior).  The arrival policy is restored and
every decision is the public ``choose_key``; the observation of the arrival
board is the real producer of the switch (``over_extension.judge_dive`` then
the valve in ``policy_observation._observe``).  Entered dungeons and recall
landings on the board: Angband 70, Yeek cave 13 (reserved), Orc cave 23
(conquered), the conquered forgetting maze (4) 18, Forest 15 (excluded),
Castle 32, Mountain 50, Anti-melee cave 40, Chameleon cave 30.  The live bot
(shallowest rule) recalled to the Orc cave 23F (row 11 ``rgc``) and stayed
there; the same Mountain/Angband -> Orc cave cycle had repeated since
2026-11-09 22:04 (each restart forgets the alternate).  The deepest landing
that fits: the Mountain's 50 needs *Destruction* the kit lacks, the
Anti-melee cave refuses melee, the Chameleon cave is never a fallback, so
the Castle 32.

The arrival checkpoint (20261110-080128.560636743) holds the policy pickled
before the arrival board was observed; row 0 observes it and runs the switch,
row 11 is the recall read.  DECLARED: a row whose decision differs from the
recorded one is posted with the recorded key (``RecordedVisit.decide``).
Row 0 is the one such row before the read, on the unfixed code as on the
fixed one (periodic:character-dump replayed, town:recover recorded); rows
1-10 replay as recorded on both.  The step-down case asks the valve's
question again on the restored policy with the depth and the alternate the
next streak would leave (DECLARED CONSTRUCTED, no further dive is recorded).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path

from hengbot.cli import _consume_response_sequence

from hengbot import fallback_depth_floor
from hengbot.model import DUNGEON_ANGBAND
from tests.support.fallback_floor import floor_lifted
from tests.support.recorded import _policy
from tests.test_stops_1109_town_recorded import RecordedVisit

FIXTURES = Path(__file__).with_name("fixtures") / "alternate-deepest-1110"
ORC_CAVE, CASTLE, MOUNTAIN, ANTI_MELEE, CHAMELEON_CAVE = 3, 12, 14, 17, 18
LANDINGS = {1: 70, 2: 13, 3: 23, 4: 18, 7: 15, 12: 32, 14: 50, 17: 40, 18: 30}
RECALL_ROW = 11
ORC_LETTER, CASTLE_LETTER = "c", "f"


class AlternateDeepestVisit(RecordedVisit):
    fixtures = FIXTURES
    fixture = "visit"

    def replay(self, last):
        """Rows 0..``last`` decided on the restored arrival policy."""
        return [(row, *self.decide(row)) for row in range(last + 1)]


# DECLARED WALL (tests/support/fallback_floor.py): Angband 70 reached, the floor 50 refuses the
# Castle 32 and the Orc cave 23 (FallbackDepthFloorTest); the deepest-fit order predates the floor.
@floor_lifted()
class OverExtensionDeepestTest(AlternateDeepestVisit):
    """Answer 「収まる中で一番深い所へ」: the deepest landing that still fits."""

    def test_arrival_policy_is_the_third_over_extended_dive(self):
        # The streak and the dive the arrival judges, as the live process
        # pickled them (two over-extended dives; the third ends on row 0).
        policy = self.policy
        self.assertEqual(policy._target_empty_dives, 2)
        self.assertEqual(policy._dive_dungeon, DUNGEON_ANGBAND)
        self.assertGreaterEqual(policy._dive_emergencies, 2)
        self.assertEqual(self.journal[RECALL_ROW]["key"], "rg" + ORC_LETTER)
        self.assertEqual(self.journal[RECALL_ROW]["reason"], "town:recall-to-alt-dungeon")

    def test_switch_takes_the_castle_not_the_orc_cave(self):
        (_row, board, _key, _reason), = self.replay(0)
        policy = self.policy
        self.assertEqual(policy._alternate_dungeon_reason, "over_extended_dives")
        self.assertEqual(policy._last_overextended_depth, 70)
        self.assertEqual(dict(board.dungeon_recall_depths), LANDINGS)
        # Unfixed (live): the Orc cave, the shallowest landing below 70.
        self.assertEqual(policy._alternate_dungeon, CASTLE)
        self.assertEqual(policy._target_dungeon_id, CASTLE)

    def test_recall_read_lands_in_the_castle(self):
        rows = self.replay(RECALL_ROW)
        _row, board, key, reason = rows[-1]
        self.assertEqual(board.entered_dungeon_ids.index(CASTLE), ord(CASTLE_LETTER) - ord("a"))
        self.assertEqual(board.entered_dungeon_ids.index(ORC_CAVE), ord(ORC_LETTER) - ord("a"))
        # Unfixed (live, and replayed on the unfixed code): 'rgc', the Orc cave.
        self.assertEqual((key, reason), ("rg" + CASTLE_LETTER, "town:recall-to-alt-dungeon"))

    def test_deeper_landings_that_do_not_fit_are_passed_over(self):
        (_row, board, _key, _reason), = self.replay(0)
        policy = self.policy
        # The Mountain's landing 50 needs *Destruction*, which this kit lacks;
        # the Anti-melee cave (40) refuses a melee character and the Chameleon
        # cave (30) is never a fallback.
        self.assertEqual(policy._missing_required_abilities(board, LANDINGS[MOUNTAIN]),
                         frozenset({"destruction"}))
        self.assertFalse(policy._fallback_destination_allowed(ANTI_MELEE))
        self.assertFalse(policy._can_fight_in_dungeon(ANTI_MELEE))
        self.assertFalse(policy._fallback_destination_allowed(CHAMELEON_CAVE))
        self.assertEqual(policy._missing_required_abilities(board, LANDINGS[CASTLE]), frozenset())
        # Angband's recall depth is never lowered (「鉄獄の階は下げない」).
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 70)

    def test_another_streak_steps_down_from_the_castle(self):
        # The re-run after another empty streak on the Castle, as the valve
        # asks it (``_last_overextended_depth`` the Castle's landing, the
        # Castle itself the alternate being left): the next deepest fit, the
        # Orc cave 23; below it nothing fits (the Yeek cave is reserved, the
        # conquered forgetting maze and the Forest are never fallbacks).
        (_row, board, _key, _reason), = self.replay(0)
        policy = self.policy
        policy._last_overextended_depth = LANDINGS[CASTLE]
        self.assertEqual(policy._pick_alternate_dungeon(board, prefer_deepest=True), ORC_CAVE)
        policy._alternate_dungeon = ORC_CAVE
        policy._last_overextended_depth = LANDINGS[ORC_CAVE]
        self.assertIsNone(policy._pick_alternate_dungeon(board, prefer_deepest=True))

# DECLARED WALL (tests/support/fallback_floor.py): Angband 70 reached, the floor 50 refuses the
# Castle 32 and the Orc cave 23 (FallbackDepthFloorTest); the deepest-fit order predates the floor.
@floor_lifted()
class RestartKeepsTheSwitchTest(AlternateDeepestVisit):
    """The switch survives a process restart (alternate_dungeon_record).

    Live: every deploy restarted the bot and the fresh process forgot the
    switch; the Mountain 50F conquest and Angband 61-70F came back and
    three more dives with emergency escapes were redone before the valve
    switched again (restarts 2026-11-10 00:59-07:51, keep-running-events).

    The previous process is the restored arrival policy; its row 0 makes the
    switch through the real observation, which writes the record.  DECLARED:
    the checkpoint predates the record, so its path is set the way
    ``cli._configure_policy_output_paths`` sets it.  The restarted process is
    a fresh policy (tests.support.recorded._policy) whose first board is the
    recorded row 1 board.  DECLARED WALL: its ~f skill values are the
    previous process's (the first decision of a fresh process asks them).
    """

    def restart(self, *, carry=True):
        record = self.scratch / "alternate-dungeon.json"
        self.policy._alternate_dungeon_record_path = record
        self.replay(0)
        self.assertEqual(self.policy._alternate_dungeon, CASTLE)
        if not carry:
            record.unlink(missing_ok=True)
        fresh_dir = self.scratch / "fresh"
        fresh_dir.mkdir()
        fresh = _policy(fresh_dir, self.policy._monrace_knowledge)
        fresh._alternate_dungeon_record_path = record
        entry = self.journal[1]
        line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
        _decoded, snapshots = _consume_response_sequence(
            [line + chr(10)], fresh, lambda _key: True, fresh._monrace_knowledge,
            knowledge_ledger_path=fresh_dir / "knowledge.jsonl")
        board = snapshots[-1]
        two_weapon, shield = self.policy._skill_exp_cache[:2]
        fresh._skill_exp_cache = (two_weapon, shield, board.player.level,
                                  fresh._town_visit_epoch)
        key = fresh.choose_key(board)
        return fresh, board, key

    def test_restarted_process_keeps_the_castle(self):
        fresh, board, _key = self.restart()
        self.assertTrue(board.in_town)
        # Unfixed: the fresh process went back to Angband 70F (the control).
        self.assertEqual(fresh._alternate_dungeon, CASTLE)
        self.assertEqual(fresh._target_dungeon_id, CASTLE)
        self.assertEqual(fresh._alternate_dungeon_reason, "over_extended_dives")
        self.assertEqual(fresh._last_overextended_depth, 70)
        self.assertIsNone(fresh._conquest_committed)

    def test_control_without_the_record_the_too_deep_target_comes_back(self):
        fresh, _board, _key = self.restart(carry=False)
        self.assertIsNone(fresh._alternate_dungeon)
        # On this board the fresh process goes back to Angband 70F, the
        # depth the three over-extended dives just came from.
        self.assertEqual(fresh._target_dungeon_id, DUNGEON_ANGBAND)


class FallbackDepthFloorTest(AlternateDeepestVisit):
    """Owner 2026-11-13 「フォールバックは最新到達-20Fまでにする。」 on the recorded arrival."""

    def test_no_switch_under_the_floor_and_the_next_rules_decide(self):
        (_row, board, _key, _reason), = self.replay(0)
        policy = self.policy
        # Angband 70 is the deepest reached: the floor is 50.  Below the over-extended 70 only
        # the Mountain 50 is at the floor, and it needs *Destruction* the kit lacks.
        self.assertEqual(fallback_depth_floor.floor(policy, board), 50)
        self.assertIsNone(policy._pick_alternate_dungeon(board, prefer_deepest=True))
        # No over-extension switch (live: the Orc cave 23; until 11-13: the Castle 32).  The
        # next rule is the guardian valve of the Mountain 50 target, which takes Angband 70
        # first (owner 2026-11-07), a landing at the floor or deeper.
        self.assertNotEqual(policy._alternate_dungeon_reason, "over_extended_dives")
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason,
                          policy._target_dungeon_id),
                         (DUNGEON_ANGBAND, "guardian_valve", DUNGEON_ANGBAND))


if __name__ == "__main__":
    unittest.main()
