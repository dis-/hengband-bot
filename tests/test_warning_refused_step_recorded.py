"""Recorded pins: a step producer re-selects a grid the weapon warning refused (Angband 30F, 2026-10-20).

Owner direction 2026-10-19 (one question, one predicate): "may the bot step
onto cell C now?" answers False for a warning-refused grid for every step
producer (``_warning_step_refused``), and the decision falls through to
another candidate or the next producer instead of the gate's WAIT, which the
prompt-bearing board turned into no key (the CLI's no-key-exhausted stop).
The forced walk (物資が全て尽きている場合のみ徒歩強行を許す) is unchanged.

Source: Linux soak c4-a life-014, captures 20261020-104109-no-key-exhausted
(breeder-breakthrough:seek-frontier), -120202-no-key-exhausted (melee:choke)
and -120239-no-key-exhausted (probe).  The fixture holds every state row of
each capture (row index per capture); ``.recorded.json`` holds the live
(sequence, turn, key, reason, position, messages) of the decisions in that
window.

Declared:
* No skill knowledge row was captured; the ``~f`` row is the same
  character's from ``unseen-reapproach-dl30-20261020`` with ``player.level``
  set to each board's level (only the dual-wield / shield skills read it).
* 104109: the process is fresh, so the breakthrough latch armed before the
  window and the live claim state (emergency return active, not returning
  to town; claim row 3439 rung _breeder_breakthrough_escape_key) are set
  after the first board.  The fresh frontier goal differs from live, so the
  prompt of the last board is attributed to the live step (19, 38) -> (20, 37)
  (decision 3439 '1').
* 120202: the fresh process does not re-arm the choke plan of 3513 (it
  answers melee '2' there), so the last board's prompt is attributed to the
  live step (39, 14) -> (38, 15) of 3513 and the choke route is asked on that
  board directly with its visible monsters.
* 120239: the fresh process replays the window; 276-278 equal live (probe
  '2', '4', '1', each refused by the warning).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    _build_argument_parser,
    _configure_policy_output_paths,
    _consume_response_sequence,
)
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge

from recorded_floor_knowledge import pre_seen_floor_replay
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "warning-refused-step-dl30-20261020.jsonl.gz"
RECORDED = FIXTURES / "warning-refused-step-dl30-20261020.recorded.json"
KNOWLEDGE = FIXTURES / "unseen-reapproach-dl30-20261020.jsonl.gz"
SHA256 = {
    FIXTURE: "7c93f8cd0b386dc6c8808e5acf498a20d8ec0b957ec9619c178503aad23de4dd",
    RECORDED: "637382cf4338a6694e60a50605538e252dfece2dc5e1e1e70c9b4e053f48652c",
}
BREEDER = "20261020-104109-no-key-exhausted"
CHOKE = "20261020-120202-no-key-exhausted"
PROBE = "20261020-120239-no-key-exhausted"
DIRECTION = {(-1, -1): "7", (-1, 0): "8", (-1, 1): "9", (0, -1): "4",
             (0, 1): "6", (1, -1): "1", (1, 0): "2", (1, 1): "3"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _key_to(origin: Position, cell: Position) -> str:
    return DIRECTION[(cell.y - origin.y, cell.x - origin.x)]


class WarningRefusedStepRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        cls.boards: dict[str, list[str]] = {}
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                cls.boards.setdefault(record["capture"], []).append(record["line"])
        cls.recorded = json.loads(RECORDED.read_text(encoding="utf-8"))["recorded"]
        with gzip.open(KNOWLEDGE, "rt", encoding="utf-8") as stream:
            cls.knowledge = json.loads(json.loads(stream.readline())["line"])
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _process(self, directory: Path):
        policy = _policy(directory, self.monrace)
        _configure_policy_output_paths(policy, _build_argument_parser().parse_args([
            "--state-file", str(directory / "state.jsonl"),
            "--decision-log", str(directory / "bot-decisions.jsonl"),
        ]))
        return policy

    def _board(self, policy, directory: Path, line: str):
        level = json.loads(line)["player"]["level"]
        cache = getattr(policy, "_skill_exp_cache", None)
        if cache is None or cache[2] != level:
            knowledge = json.loads(json.dumps(self.knowledge))
            knowledge["player"]["level"] = level
            policy.consume_skill_knowledge(knowledge)
        _decoded, snapshots = _consume_response_sequence(
            [line], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        return snapshots[-1]

    def _decide(self, policy, board):
        key = policy.choose_key(board)
        if key is not None:
            policy.confirm_key_posted(key)
        return key, policy.last_reason

    def _warm(self, policy, directory: Path, capture: str, last: int, setup=None):
        """Decide rows 0..last-1 of ``capture``; return the board of ``last``."""
        lines = self.boards[capture]
        for row in range(last):
            board = self._board(policy, directory, lines[row])
            if row == 0 and setup is not None:
                setup(policy, board)
            self._decide(policy, board)
        return self._board(policy, directory, lines[last])

    def _live(self, capture: str, sequence: int):
        row = next(r for r in self.recorded[capture] if r[0] == sequence)
        return row[2], row[3]

    def _attribute_prompt(self, policy, board, origin, target):
        """The live step the last board's prompt answers (declared)."""
        policy._warning_step_pending = (
            policy._decision_sequence, board.floor_key, origin, target, False,
        )

    def test_recorded_rows_are_the_incident(self):
        for capture, last in ((BREEDER, 3440), (CHOKE, 3514), (PROBE, 279)):
            with self.subTest(capture=capture):
                self.assertEqual(self._live(capture, last), (None, "warning:blocked-step"))
        self.assertEqual(self._live(BREEDER, 3439), ("1", "breeder-breakthrough:seek-frontier"))
        self.assertEqual(self._live(CHOKE, 3513), ("9", "melee:choke"))
        self.assertEqual(
            [self._live(PROBE, n) for n in (276, 277, 278)],
            [("2", "probe"), ("4", "probe"), ("1", "probe")],
        )

    @pre_seen_floor_replay  # declared wall: board recorded 2026-10-20, before the 2026-10-23 seen-floor rule (tests/recorded_floor_knowledge.py)
    def test_probe_does_not_reselect_a_refused_cell(self):
        lines = self.boards[PROBE]
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            policy = self._process(directory)
            board = self._warm(policy, directory, PROBE, len(lines) - 4)
            for sequence in (276, 277, 278):
                with self.subTest(sequence=sequence):
                    self.assertEqual(self._decide(policy, board), self._live(PROBE, sequence))
                    board = self._board(policy, directory, lines[len(lines) - 279 + sequence])
            key, reason = self._decide(policy, board)
            refused = set(policy._warning_refused_cells)
        here = Position(23, 47)
        self.assertEqual(board.player.position, here)
        self.assertTrue({Position(24, 47), Position(23, 46), Position(24, 46)} <= refused)
        # Live (and d2b0553b): the oscillation probe re-selects (24, 47) ->
        # warning:blocked-step -> no key.  Now the probe has no unrefused
        # unknown grid and the same rung searches this spot.
        self.assertEqual((key, reason), ("s", "search"))
        self.assertNotIn(key, {_key_to(here, cell) for cell in refused
                               if max(abs(cell.y - here.y), abs(cell.x - here.x)) == 1})

    def _breeder_setup(self, policy, board):
        policy._floor_key = board.floor_key
        policy._breeder_breakthrough_floor = board.floor_key
        policy._emergency_return_active = True
        policy._returning_to_town = False

    def test_breakthrough_routes_around_a_refused_cell(self):
        lines = self.boards[BREEDER]
        here, refused, other = Position(19, 38), Position(18, 38), Position(20, 37)
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            policy = self._process(directory)
            board = self._warm(policy, directory, BREEDER, len(lines) - 1, self._breeder_setup)
            self.assertEqual(board.player.position, here)
            # The fresh process's own last step was seek-frontier '8' onto
            # (18, 38); the recorded prompt board answers it (declared).
            self.assertEqual(policy._warning_step_pending[2:4], (here, refused))
            # Control: the same board without the refusal keeps that step.
            self.assertEqual(policy._breeder_breakthrough_frontier_step(board), refused)
            key, reason = self._decide(policy, board)
            self.assertIn(refused, policy._warning_refused_cells)
        # d2b0553b: seek-frontier re-selects (18, 38) -> warning:blocked-step
        # -> no key (live: the same shape on (20, 37)).  Now the route goes
        # around the refused grid.
        self.assertEqual((key, reason), (_key_to(here, other), "breeder-breakthrough:seek-frontier"))
        self.assertNotEqual(key[:1], _key_to(here, refused))

    def test_choke_route_skips_a_refused_cell(self):
        lines = self.boards[CHOKE]
        here, refused = Position(39, 14), Position(38, 15)
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            policy = self._process(directory)
            board = self._warm(policy, directory, CHOKE, len(lines) - 1)
            self.assertEqual(board.player.position, here)
            hostiles = list(board.visible_monsters)
            # The fresh process latched (38, 15) at 3506 from its own step;
            # drop it so this board's prompt latches it as live did.
            policy._warning_refused_cells.discard(refused)
            policy._engagement_avoid_cells.discard(refused)
            # Control: without the refusal the route's first step is the
            # live '9' of 3513.
            self.assertEqual(policy._validated_choke_route(board, hostiles)[1], refused)
            self._attribute_prompt(policy, board, here, refused)
            key, reason = self._decide(policy, board)
            self.assertIn(refused, policy._warning_refused_cells)
            route = policy._validated_choke_route(board, hostiles)
        # The whole decision is a control: the fresh process holds no choke
        # plan, so it answers melee '2' at d2b0553b too, never stepping in.
        self.assertEqual((key, reason), ("2", "melee"))
        # The pin: at d2b0553b the choke route's first step is (38, 15)
        # again (live 3514: melee:choke onto it -> no key); now the route
        # never starts through the refused grid.
        self.assertTrue(route is None or route[1] != refused)
        self.assertNotEqual(key[:1], _key_to(here, refused))

    @pre_seen_floor_replay  # declared wall: board recorded 2026-10-20, before the 2026-10-23 seen-floor rule (tests/recorded_floor_knowledge.py)
    def test_control_forced_walk_still_walks_with_y(self):
        lines = self.boards[PROBE]
        here, refused = Position(23, 47), Position(24, 47)
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            policy = self._process(directory)
            board = self._warm(policy, directory, PROBE, len(lines) - 1)
            self.assertIn(refused, policy._warning_refused_cells)
            self.assertTrue(policy._warning_step_refused(board, refused))
            exhausted = replace(board, inventory=[
                item for item in board.inventory
                if item is not policy._find_teleport_scroll(board)
                and item is not policy._find_phase_scroll(board)
                and item is not policy._find_recall_scroll(board)
            ])
            self.assertTrue(policy._warning_supplies_exhausted(exhausted))
            self.assertFalse(policy._warning_step_refused(exhausted, refused))
            self.assertEqual(
                policy._step_toward(exhausted, refused), _key_to(here, refused) + "y"
            )


if __name__ == "__main__":
    unittest.main()
