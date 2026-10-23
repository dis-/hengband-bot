"""A detected pack with no covered cell reachable is not retreated from (n1-a life-001).

Live incident: Linux soak n1-a, life-001 (Lv28 Zombie Warrior), Angband 20F
(floor (1, 20, 0)), 2026-10-23 14:26:43 / 14:26:50 / 14:26:57: the loop
detector stopped the bot three times within 12 s and the runner retired the
character.  An ESP-perceived, awake Large kobold pack stood west of the wall at
x=14 and never moved; a Fauchard lay at (18,14) and bolts at (19,13).  At
(17,15) two kobolds were within SWARM_LOOKAHEAD, so `detected:prepare-choke`
retreated; no covered cell was reachable, so it took the flee step '3' to
(18,16) and committed to nothing.  There only one kobold was inside the window,
the owner fell silent and `seek-loot` walked '7' back to (17,15).

Fix (owner decision 2026-10-23, "隘路が無ければ後退しない"): when no covered
cell is reachable the preparation does not retreat at all - no flee step and no
wait in the open; the ordinary producers act.  The 2026-09-20 hold stays for an
actual choke only.

Fixture tests/fixtures/detected-pack-flee-loop-20261023-state.jsonl.gz: the
121 `player_turn` state rows (turns 1680749..1681926) of the captures
20261023-142650-loop-detected and 20261023-142657-loop-detected, copied as-is,
one row per turn (the restart re-reads of the same turn and the `knowledge`
rows are dropped).  Recorded decisions of those turns (bot-decisions.jsonl.gz):
1680784 (17,15) '3' detected:prepare-choke, 1680794 (18,16) '7' seek-loot, and
the same pair on every following pair of boards up to the stop.

DECLARED CONSTRUCTED: the closed-loop walk places the player of each recorded
board at the cell the replayed policy stepped to (the pack, the walls and the
loot do not change across the recorded boards, and the frozen boards neither
remove picked-up items nor reveal new ground); the control removes the
detected pack from a recorded board.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest

from hengbot.cli import LOOP_WINDOW, _cell_loop_guard_applies, _is_looping
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SWARM_LOOKAHEAD
from test_esp_threat_rest_recorded import EDIT
from test_floor_dwell_seen_floor_recorded import FIXTURES, _Replay


STATE = FIXTURES / "detected-pack-flee-loop-20261023-state.jsonl.gz"
STATE_SHA256 = "5e206fd5f306839b96331b73bcfd6965b217bffd9d44862eb2ec66dc5408dc01"
ONSET = 4  # turn 1680784, recorded '3' detected:prepare-choke at (17,15)
WINDOW_CELL = Position(17, 15)
FLEE_CELL = Position(18, 16)
MOVES = {
    "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
    "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
}


def _states() -> list[str]:
    data = STATE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == STATE_SHA256
    return gzip.decompress(data).decode("utf-8").splitlines()


class DetectedPackNoChokeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.states = _states()
        assert len(cls.states) == 121
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _replay(self, upto: int) -> _Replay:
        replay = _Replay(self, self.monrace)
        for line in self.states[:upto]:
            replay.board(line)
        return replay

    def _converging(self, policy, board):
        return [
            monster for monster in policy._perceived_hostiles(board)
            if monster.perception == "detected" and not monster.asleep
            and monster.distance <= SWARM_LOOKAHEAD
        ]

    def test_recorded_onset_without_a_covered_cell_does_not_retreat(self):
        replay = self._replay(ONSET)
        board, key, reason = replay.decide(self.states[ONSET])
        policy = replay.policy
        self.assertEqual(board.turn, 1680784)
        self.assertEqual(board.player.position, WINDOW_CELL)
        converging = self._converging(policy, board)
        self.assertEqual(
            sorted((m.index, m.distance) for m in converging), [(7, 2), (10, 3)]
        )
        destination, step = policy._summoner_retreat_route(
            board, converging, converging
        )
        self.assertIsNone(destination)
        self.assertEqual(step, FLEE_CELL)
        # Recorded: '3' detected:prepare-choke (the flee step to (18,16)).
        # Now the loot owner keeps walking to the Fauchard at (18,14).
        self.assertEqual((key, reason), ("1", "seek-loot"))
        self.assertIsNone(policy._detected_threat_route)
        self.assertIsNone(policy._detected_threat_hold)

    def test_recorded_window_boards_never_retreat_or_wait(self):
        # Open loop over the recorded alternation (boards 4..41): the recorded
        # decisions at (17,15) were 'detected:prepare-choke' flee steps.
        replay = self._replay(ONSET)
        rows = []
        for line in self.states[ONSET:42]:
            board, key, reason = replay.decide(line)
            rows.append((board.player.position, key, reason))
        window_rows = [row for row in rows if row[0] == WINDOW_CELL]
        self.assertGreaterEqual(len(window_rows), 15)
        for position, key, reason in rows:
            with self.subTest(position=position, key=key):
                self.assertNotIn(
                    reason, {"detected:prepare-choke", "summoner:hold-choke"}
                )

    def _closed_loop(self):
        replay = self._replay(ONSET)
        policy = replay.policy
        position = None
        walk = []
        for line in self.states[ONSET:]:
            row = json.loads(line)
            if position is not None:
                row["player"]["y"], row["player"]["x"] = position.y, position.x
            board, key, reason = replay.decide(json.dumps(row, ensure_ascii=False))
            hold = policy._detected_threat_hold
            walk.append((board, key, reason, hold))
            here = board.player.position
            dy, dx = MOVES.get(key, (0, 0))
            position = Position(here.y + dy, here.x + dx)
        return walk

    def test_closed_loop_collects_loot_without_tripping_the_loop_detector(self):
        walk = self._closed_loop()
        recent_cells = []
        previous = None
        fired = []
        for board, key, reason, _hold in walk:
            if not _cell_loop_guard_applies(board, reason, previous):
                recent_cells.clear()
            else:
                position = board.player.position
                recent_cells.append((board.floor_key, position.y, position.x))
                if _is_looping(recent_cells, window=LOOP_WINDOW):
                    fired.append(board.turn)
            previous = board.player.position
        self.assertEqual(fired, [])

        reasons = [reason for _board, _key, reason, _hold in walk]
        self.assertNotIn("detected:prepare-choke", reasons)
        self.assertNotIn("summoner:hold-choke", reasons)
        # Instead: the Fauchard (18,14) and the bolts (19,13) are picked up,
        # then exploration continues.
        pickups = [
            board.player.position
            for board, key, reason, _hold in walk if reason == "pickup"
        ]
        self.assertEqual(pickups, [Position(18, 14), Position(19, 13)])
        self.assertEqual(reasons[0], "seek-loot")
        self.assertIn("explore", reasons)

    def test_control_recorded_board_without_the_pack_is_loot(self):
        replay = self._replay(ONSET)
        row = json.loads(self.states[ONSET])
        row["detected_monsters"] = []  # DECLARED CONSTRUCTED: no perceived pack
        board, key, reason = replay.decide(json.dumps(row, ensure_ascii=False))
        self.assertEqual(board.player.position, WINDOW_CELL)
        self.assertEqual(reason, "seek-loot")
        self.assertIsNone(replay.policy._detected_threat_route)


if __name__ == "__main__":
    unittest.main()
