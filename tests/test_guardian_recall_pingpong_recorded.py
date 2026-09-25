"""Pins: a guardian bounce is counted, and no switch lands on a blocked guardian floor.

Live incident 2026-09-25 01:54-02:01 (first run on the new exe, one bot
process, 635 decisions): seven town<->Orc-cave round trips in seven minutes,
no stop, no loop detection.  Each trip: shop -> ``town:recall-to-alt-dungeon``
('rfc') -> land on Orc cave 23F -> ``return:recall`` ('rf') with
``last_return_trigger = "guardian-kit-insufficient"`` -> town.  Every trip
burned recall scrolls and gold (9204 -> 5391 gold) for zero floor progress.

How it began (decision 8, recorded ``town-progress-invariant:defect:town:
unsafe-recall-fallback``): the objective was Angband, whose recall landing 50
needs a *Destruction* method the character lacks, so
``_activate_safe_recall_fallback`` picked the shallowest entered alternate.
That was the Orc cave, whose recall landing 23 IS its guardian floor
(DungeonDefinitions: max depth 23, guardian 373), and the character cannot beat
that guardian (``_guardian_fight_viable`` false).  ``_pick_alternate_dungeon``
never asked; it checked only the landing's required abilities.

Why the existing valve never fired: the over-extension judgement at a town
arrival counts only dives of the recall target (``_dive_dungeon ==
_target_dungeon_id``), but the same observation first resets
``_target_dungeon_id`` to Angband whenever Angband's recall is unlocked and only
re-applies the alternate AFTER the judgement.  On all three recorded arrivals
the dive dungeon was 3 and the target read there was 1, so every bounce was
skipped: the recorded ``over_extended_dive_streak`` and
``last_overextended_depth`` stay 0 for the whole run.  The guardian-bounce
count now reads the target the bot pursued up to the arriving board (the
depth-progress and over-extension judgements are unchanged).

Round 2, user decision 2026-09-25 (「倒せない階でなければ深くても可」): once the
bounces are counted, the valve found nothing shallower than the bounced
landing 23 and kept the Orc cave.  A valve fired by guardian bounces only is
now bounded by "the landing is not a guardian floor the kit cannot pass"
instead of "shallower than the bounced landing", so it picks Forest (24).

Round 3, user decision 2026-09-25 (「見える形で停止する」): when that guardian
valve finds no alternate at all, the run ends with the policy-declared final
stop ``town:blocked:guardian-bounce-no-alternate`` (pinned on the recorded
valve board with one named change: every other landing moved onto its own
blocked guardian floor).  A bounce now counts only when THIS dive's return
started on the guardian floor, not when a stale trigger is left over.

Substrate: tests/fixtures/guardian-recall-pingpong-20260925.jsonl.gz, frozen by
tests/extract_guardian_recall_pingpong_fixture.py at the recorded decision
boundaries (see its .provenance.txt): decisions 0..262 by log index, from the
state log's first row (the game was launched for this run, so the window starts
at the episode's first board) up to the first decision a restarted policy does
not reproduce (263, an unrelated town fight).  Log indices are used because
the first town decision after every landing reuses the countdown's last
``decision_sequence``.

Walls, each declared:
- Home history/disposal files and the calibration file live in a temporary
  directory; the calibration file is the run's own (written before the run).
- DECLARED WALL (live replay only): the live picker had no guardian-floor
  check, so a fixed policy would never go to the Orc cave and every later
  recorded board would be counterfactual.  To reproduce the live state, the
  replay answers ``_pick_alternate_dungeon`` with the recorded
  ``alternate_dungeon_id`` of the deciding row while the policy holds no
  alternate (decision 8 only).  The arrival judgement and the valve are not
  walled; the valve's own picker call at the third arrival is the real one.
- DECLARED WALL (live replay only, added with orc-cave-residual-path
  2026-09-25): the live town router had no guardian-landing gate, so the
  replay answers ``_recall_landing_guardian_blocked`` with False; otherwise
  the recalls to the Orc cave's blocked landing (13, 92, 185) would be
  refused and every later recorded board would be counterfactual.  G1's
  fixed replay and the r3 board run without it.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import copy
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import EMPTY_DIVE_LIMIT, POLICY_FINAL_STOP_REASONS

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "guardian-recall-pingpong-20260925.jsonl.gz"
CALIBRATION = FIXTURES / (
    "guardian-recall-pingpong-20260925.character-calibration.json"
)
FIXTURE_SHA256 = "7c7c9d481d4965020a38291fbc6e4aea4d5416c0617ce32d7cf7fbb36941f3bf"
BOUNDARIES_SHA256 = (
    "53c87c9b4a8b94d859c77a6d1de9cb56634b00de67045b1f9846aeda2c63e00a"
)
CALIBRATION_SHA256 = (
    "a90e4700854b1b3cf839a278a846078c7f9d768c82c058551c6f52173660016b"
)
ORC_CAVE = 3
FOREST = 7
ORC_CAVE_LANDING = 23  # recorded dungeon_recall_depths[3]; its guardian floor
FOREST_LANDING = 24  # recorded dungeon_recall_depths[7]; Forest max depth 32
FALLBACK = 8  # unsafe-recall fallback that chose the Orc cave
FIRST_RECALL = 13  # first town:recall-to-alt-dungeon ('rfc')
BOUNCES = (37, 138, 211)  # return:recall 'rf' on (3, 23), guardian-kit-insufficient
ARRIVALS = (84, 177, 257)  # the first town decision after each bounce
LAST = 262
VALVE = 258  # the decision whose observation lands the third bounce in town


def _bar_record(policy):
    """S2b.2: the bar table's record on the decision row (record-only)."""
    claim = policy.decision_claim or {}
    return {
        name: claim.get(name)
        for name in ("would_bar", "bars_set", "bars_lifted", "bar_skipped")
    }
# Named change for the r3 terminal pin: every other candidate's recall
# landing moved onto its own guardian floor (Forest max 32, Mountain max 50,
# Castle max 65), none of whose guardians the recorded kit can beat.
ALL_BLOCKED_LANDINGS = {FOREST: 31, 14: 49, 12: 64}


class GuardianRecallPingPongRecordedTest(unittest.TestCase):
    live = None
    live_base = None
    # S2b.2: the bar table's record of every live-replay decision.
    live_bars = None

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == (
            CALIBRATION_SHA256
        )
        boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(boundaries["input_rows"])
        assert len(cls.recorded) == LAST + 1
        cls.starts = [0]
        for count in boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    @classmethod
    def _new_policy(cls, directory: Path):
        policy = _policy(directory, cls.monrace)
        policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        return policy

    @classmethod
    def _consume(cls, policy, index, directory):
        segment = cls.lines[cls.starts[index] : cls.starts[index + 1]]
        _decoded, snapshots = _consume_response_sequence(
            segment, policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        return snapshots[-1]

    @classmethod
    def _live(cls):
        """Replay the whole window with the recorded alternate choice (wall)."""
        if cls.live is not None:
            return cls.live
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = cls._new_policy(directory)
            decided = []
            arrivals = []
            valve_calls = []
            bars = []
            for index in range(LAST + 1):
                snapshot = cls._consume(policy, index, directory)
                if index == VALVE:
                    # Deep copy of the live state as the valve's board arrives.
                    cls.live_base = (copy.deepcopy(policy), snapshot)
                observed_floor = policy._floor_key
                recorded_alternate = cls.recorded[index]["alternate_dungeon_id"]
                real_pick = policy._pick_alternate_dungeon

                def pick(board, **kwargs):
                    if policy._alternate_dungeon is None:
                        return recorded_alternate  # DECLARED WALL
                    result = real_pick(board, **kwargs)
                    valve_calls.append(
                        (index, kwargs, policy._last_overextended_depth, result)
                    )
                    return result

                # DECLARED WALL (orc-cave-residual-path, 2026-09-25): the live
                # town router had no guardian-landing gate either; it read
                # every recall to the Orc cave's blocked landing 23.
                with patch.object(
                    policy, "_pick_alternate_dungeon", pick
                ), patch.object(
                    policy, "_recall_landing_guardian_blocked",
                    return_value=False, create=True,
                ):
                    key = policy.choose_key(snapshot)
                decided.append((str(key), policy.last_reason))
                bars.append(_bar_record(policy))
                if (
                    observed_floor is not None
                    and observed_floor[0] != 0
                    and policy._floor_key[0] == 0
                ):
                    # This decision observed the landing in town.  (The first
                    # town decision, the ~f skill request, answers before the
                    # observation; the arrival is observed on the next one.)
                    arrivals.append(
                        (
                            index,
                            policy._target_empty_dives,
                            policy._last_overextended_depth,
                            # getattr: pre-fix code has no share and must
                            # fail these pins by assertion, not AttributeError.
                            getattr(policy, "_guardian_bounce_dives", None),
                            policy._alternate_dungeon,
                            policy._target_dungeon_id,
                        )
                    )
                policy.confirm_key_posted(key)
            cls.live = (decided, arrivals, valve_calls)
            cls.live_bars = bars
        return cls.live

    def _fixed_until_first_recall(self):
        """A restarted fixed policy (no wall) decides decisions 0..13."""
        policy = self._new_policy(self.directory)
        decided = []
        for index in range(FIRST_RECALL + 1):
            snapshot = self._consume(policy, index, self.directory)
            if index == FIRST_RECALL:
                return policy, decided, snapshot
            key = policy.choose_key(snapshot)
            decided.append((str(key), policy.last_reason))
            policy.confirm_key_posted(key)
        raise AssertionError("unreachable")

    # ------------------------------------------------------------ recorded
    def test_recorded_run_is_the_uncounted_guardian_bounce(self):
        recorded = self.recorded
        self.assertEqual(
            recorded[FALLBACK]["reason"],
            "town-progress-invariant:defect:town:unsafe-recall-fallback"
            "=>town-progress-invariant:approach",
        )
        self.assertEqual(recorded[FALLBACK]["alternate_dungeon_id"], ORC_CAVE)
        self.assertEqual(
            [
                (recorded[i]["key"], recorded[i]["reason"])
                for i in (FIRST_RECALL, 92, 185)
            ],
            [("rfc", "town:recall-to-alt-dungeon")] * 3,
        )
        for index in BOUNCES:
            row = recorded[index]
            self.assertEqual(
                (row["key"], row["reason"], row["dungeon_id"], row["level"]),
                ("rf", "return:recall", ORC_CAVE, ORC_CAVE_LANDING),
            )
            self.assertEqual(row["last_return_trigger"], "guardian-kit-insufficient")
        # The live valve never counted a bounce and never fired.
        self.assertEqual(
            {row["over_extended_dive_streak"] for row in recorded}, {0}
        )
        self.assertEqual({row["last_overextended_depth"] for row in recorded}, {0})
        for index in ARRIVALS:
            self.assertEqual(recorded[index]["dungeon_id"], 0)
            self.assertEqual(recorded[index]["alternate_dungeon_id"], ORC_CAVE)

    def test_live_replay_reproduces_every_recorded_decision(self):
        decided, _arrivals, _valve = self._live()
        self.assertEqual(
            [
                index
                for index, pair in enumerate(decided)
                if pair != (self.recorded[index]["key"], self.recorded[index]["reason"])
            ],
            [],
        )

    def test_s2b2_the_bar_table_records_nothing_here_with_the_switch_off(self):
        # S2b.2 (record-only): the switch is off, every recorded decision is
        # reproduced (above), and no claim of this window ends barred -- the
        # ping-pong is a departure/recall latch, which no bar catches.
        decided, _arrivals, _valve = self._live()
        bars = type(self).live_bars
        self.assertEqual(len(bars), len(decided))
        self.assertEqual(
            [
                index for index, row in enumerate(bars)
                if any(value is not None for value in row.values())
            ],
            [],
        )

    # ------------------------------------------------------------ G2
    def test_g2_every_guardian_bounce_is_counted_and_the_valve_fires(self):
        _decided, arrivals, valve_calls = self._live()
        # The landing in town is observed on the decision after each recorded
        # first town decision (84, 177, 257).
        observed = [arrival[0] for arrival in arrivals]
        self.assertEqual(observed, [index + 1 for index in ARRIVALS])
        self.assertEqual(EMPTY_DIVE_LIMIT, 3)
        # The first two bounces advance the streak (and its guardian-bounce
        # share); the third reaches the limit, so the valve fires on that very
        # observation: it records the bounced landing as the over-extended
        # depth, consults the picker and restarts the streak.
        self.assertEqual(
            [arrival[1:4] for arrival in arrivals],
            [(1, 0, 1), (2, 0, 2), (0, ORC_CAVE_LANDING, 0)],
        )
        self.assertEqual(
            [(index, kwargs, depth) for index, kwargs, depth, _r in valve_calls],
            [
                (
                    observed[2],
                    {"guardian_bounced_dungeon": ORC_CAVE},
                    ORC_CAVE_LANDING,
                )
            ],
        )

    # ------------------------------------------------------------ G1 (r2)
    def test_g1_guardian_valve_leaves_the_orc_cave_for_a_deeper_landing(self):
        """User decision 2026-09-25 「倒せない階でなければ深くても可」.

        After the three recorded bounces nothing below the bounced landing 23
        qualifies (Labyrinth 18 is a conquered forgetting maze, Yeek cave and
        Angband are never fallbacks).  The valve fired by guardian bounces may
        land deeper: the shallowest landing that is not a blocked guardian
        floor is Forest's 24.  The live state stayed on the Orc cave.
        """
        decided, arrivals, valve_calls = self._live()
        index, _streak, _depth, _bounces, alternate, target = arrivals[2]
        self.assertEqual([call[3] for call in valve_calls], [FOREST])
        self.assertEqual((alternate, target), (FOREST, FOREST))
        self.assertEqual(self.recorded[index]["alternate_dungeon_id"], ORC_CAVE)
        # The switch itself posts nothing different inside the window: every
        # recorded decision up to 262 is still reproduced (see the fidelity
        # test); the next recall to the alternate lies beyond the window.
        self.assertEqual(
            decided[index:],
            [
                (self.recorded[i]["key"], self.recorded[i]["reason"])
                for i in range(index, LAST + 1)
            ],
        )

    # ------------------------------------------------------------ r3
    def test_r3_no_qualifying_alternate_stops_the_run_visibly(self):
        """User decision 2026-09-25 「見える形で停止する」.

        The recorded valve board with one named change: every candidate but
        the Orc cave lands on its own guardian floor the kit cannot pass.  The
        guardian valve finds no alternate, and the same decision already
        answers with the policy-declared final stop, on which the driver
        writes the row and ends the run instead of recalling back.
        """
        self._live()
        base, board = self.live_base
        policy = copy.deepcopy(base)
        board = replace(
            board,
            dungeon_recall_depths={
                **board.dungeon_recall_depths, **ALL_BLOCKED_LANDINGS
            },
        )
        for dungeon, depth in ALL_BLOCKED_LANDINGS.items():
            self.assertTrue(policy._guardian_floor_blocked(board, dungeon, depth))
        key = policy.choose_key(board)
        self.assertEqual(
            policy.last_reason, "town:blocked:guardian-bounce-no-alternate"
        )
        self.assertIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)
        self.assertEqual(key, "5")
        self.assertEqual(policy._alternate_dungeon, ORC_CAVE)
        # Unchanged, the same board switches to Forest instead (G1-r2).
        policy = copy.deepcopy(base)
        policy.choose_key(self.live_base[1])
        self.assertEqual(policy._alternate_dungeon, FOREST)
        self.assertEqual(policy.last_reason, self.recorded[VALVE]["reason"])

    # ------------------------------------------------------------ G1
    def test_g1_fallback_does_not_choose_a_blocked_guardian_landing(self):
        policy, decided, board = self._fixed_until_first_recall()
        # Everything before the first recall is the recorded run ...
        self.assertEqual(
            decided,
            [
                (self.recorded[index]["key"], self.recorded[index]["reason"])
                for index in range(FIRST_RECALL)
            ],
        )
        # ... but the fallback at decision 8 skipped the Orc cave.
        self.assertEqual(policy._alternate_dungeon, FOREST)
        self.assertEqual(board.dungeon_recall_depths[ORC_CAVE], ORC_CAVE_LANDING)
        self.assertEqual(board.dungeon_recall_depths[FOREST], FOREST_LANDING)
        self.assertTrue(
            policy._guardian_floor_blocked(board, ORC_CAVE, ORC_CAVE_LANDING)
        )
        self.assertFalse(
            policy._guardian_floor_blocked(board, FOREST, FOREST_LANDING)
        )
        key = policy.choose_key(board)
        recorded = self.recorded[FIRST_RECALL]
        self.assertEqual((recorded["key"], recorded["reason"]), (
            "rfc", "town:recall-to-alt-dungeon",
        ))
        self.assertEqual(policy.last_reason, "town:recall-to-alt-dungeon")
        self.assertEqual(key, "rf" + policy._recall_selection_key(board, FOREST))
        self.assertEqual(key, "rfe")


if __name__ == "__main__":
    unittest.main()
