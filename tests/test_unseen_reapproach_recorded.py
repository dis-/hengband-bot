"""Recorded pins: walking back into a continuing unseen attack (Angband 30F, 2026-10-20).

User 2026-10-06 「後ずさりは今のまま・拾いを諦める」 and 2026-10-19 (one
question, one predicate): while an unseen attack continues, nothing in the
direction retreated from is approached again -- by exploration or by loot --
and a restarted bot still knows the attack.

Source: Linux soak c4-a life-014, captures 20261020-040109-loop-detected,
-040122-no-key-exhausted and -040134-no-key-exhausted.  The fixture holds the
state row of each decision from the floor arrival (9604, recall landing at
(22, 64)) to the loop stop (9714), then the first board of the restarted
process ("1:1"); ``.recorded.json`` holds the live (tag, turn, key, reason,
position, hp, messages).  Declared: the knowledge row is the restarted
process's (turn 2564990, same character); the calibration file is the shared
recorded one of ``test_esp_threat_rest_recorded`` (no calibration was
captured; nothing here reads it on a dungeon floor).

Replay on e8ae2b19, fresh process warmed on 9604's board: every key of
9605-9714 equals live except 9629 (probe vs seek-loot, a pre-floor history
difference); from 9630 to the loop stop it is the live sequence, including
the explore '4' steps back onto the hit cells.  After the fix the first
divergence is 9647 (explore leaves the attack's area); later boards are the
live ones the fixed bot would not have seen, so they are declared boards.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import hengbot.cli as cli
from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "unseen-reapproach-dl30-20261020.jsonl.gz"
RECORDED = FIXTURES / "unseen-reapproach-dl30-20261020.recorded.json"
SHA256 = {
    FIXTURE: "52caf86c5ae00828551f47bfda508e1bf647c518256b802373eb2c7cf8aa4de1",
    RECORDED: "eb07809b7239635c87be42b0110e6e59863e2b5dd82fcb8adaaafa3e8ba9cfdb",
}
FLOOR = (1, 30, 0)
ARRIVAL = 9604
LOOP_STOP = 9714
FIRST_FIX_DIVERGENCE = 9647
LAST_LOOP_EXPLORE = 9712  # explore '4' from (22, 62) onto the hit cell (22, 61)
RESTART_BOARD = "1:1"  # restarted process: seek-loot '4' toward (23, 61)
ITEM_IN_ATTACK = Position(23, 61)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class UnseenReapproachRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        cls.knowledge = json.loads(records[0]["line"])
        cls.boards = {record["sequence"]: record["line"] for record in records[1:]}
        rows = json.loads(RECORDED.read_text(encoding="utf-8"))["recorded"]
        cls.recorded = {row[0]: row for row in rows}
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _process(self, directory: Path):
        """A bot process as the CLI starts it, decision log in ``directory``."""
        policy = _policy(directory, self.monrace)
        policy.consume_skill_knowledge(self.knowledge)
        # Looked up so the controls also run on e8ae2b19, which has no record.
        configure = getattr(cli, "_configure_unseen_attack_memory", None)
        if configure is not None:
            configure(policy, type(
                "Args", (), {"decision_log": directory / "bot-decisions.jsonl"}
            ))
        return policy

    def _decide(self, policy, directory: Path, tag: str):
        _decoded, snapshots = _consume_response_sequence(
            [self.boards[tag]], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        board = snapshots[-1]
        key = policy.choose_key(board)
        policy.confirm_key_posted(key)
        return str(key), policy.last_reason, board

    def _replay_floor(self, policy, directory: Path, last: int):
        rows = {}
        for sequence in range(ARRIVAL, last + 1):
            tag = f"0:{sequence}"
            rows[sequence] = self._decide(policy, directory, tag)
        return rows

    def _live(self, tag):
        row = self.recorded[tag]
        return row[2], row[3]

    def test_recorded_rows_are_the_incident(self):
        loop = [self._live(f"0:{n}") for n in range(9710, 9713)]
        self.assertEqual(loop, [("4", "explore")] * 3)
        self.assertEqual(self.recorded["0:9713"][4], [22, 61])
        self.assertTrue(any(m.startswith("何か") for m in self.recorded["0:9713"][6]))
        self.assertEqual(self._live(RESTART_BOARD), ("4", "seek-loot"))
        self.assertEqual(self._live("1:7"), (None, "warning:blocked-step"))

    def test_explore_does_not_walk_back_into_the_attack(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            policy = self._process(directory)
            rows = self._replay_floor(policy, directory, LOOP_STOP)
        for sequence in range(9630, FIRST_FIX_DIVERGENCE):
            with self.subTest(sequence=sequence):
                self.assertEqual(rows[sequence][:2], self._live(f"0:{sequence}"))
        # Live (and e8ae2b19): explore '4' toward the frontier (24, 59)
        # behind the hit cells of 9645 (22, 62), retreat heading east.
        self.assertEqual(self._live(f"0:{FIRST_FIX_DIVERGENCE}"), ("4", "explore"))
        self.assertEqual(rows[FIRST_FIX_DIVERGENCE][:2], ("8", "explore"))
        # Declared board (the fixed bot was elsewhere): the last explore
        # before the loop stop no longer steps onto the hit cell (22, 61).
        self.assertEqual(self._live(f"0:{LAST_LOOP_EXPLORE}"), ("4", "explore"))
        self.assertEqual(rows[LAST_LOOP_EXPLORE][:2], ("6", "explore"))
        # The retreat itself is unchanged on the hit boards.
        for sequence in (9645, 9646, 9713, 9714):
            with self.subTest(retreat=sequence):
                self.assertEqual(rows[sequence][:2], self._live(f"0:{sequence}"))

    def test_restarted_process_still_knows_the_attack(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = self._process(directory)
            self._replay_floor(first, directory, LOOP_STOP)
            record = json.loads(
                (directory / "unseen-attack.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                (record["floor"], record["turn"], record["position"], record["direction"]),
                (list(FLOOR), self.recorded["0:9713"][1], [22, 61], [0, 1]),
            )
            restarted = self._process(directory)
            key, reason, _board = self._decide(restarted, directory, RESTART_BOARD)
        # Live (and e8ae2b19): seek-loot '4' back to (23, 61), the fire bolt,
        # the retreat onto a warning-refused cell and no key, three times.
        self.assertEqual((key, reason), ("9", "explore"))
        self.assertNotEqual(restarted._loot_target, ITEM_IN_ATTACK)

    def test_control_no_attack_record_still_loots_the_item(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            restarted = self._process(directory)
            key, reason, _board = self._decide(restarted, directory, RESTART_BOARD)
        self.assertEqual((key, reason), self._live(RESTART_BOARD))
        self.assertEqual(restarted._loot_target, ITEM_IN_ATTACK)

    def test_control_attack_past_the_quiet_window_still_loots_the_item(self):
        from hengbot.policy_identification import UNSEEN_LOOT_QUIET_TURNS

        turn = self.recorded[RESTART_BOARD][1]
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "unseen-attack.json").write_text(json.dumps({
                "floor": list(FLOOR),
                "turn": turn - UNSEEN_LOOT_QUIET_TURNS,
                "position": [22, 61],
                "direction": [0, 1],
            }) + "\n", encoding="utf-8")
            restarted = self._process(directory)
            key, reason, _board = self._decide(restarted, directory, RESTART_BOARD)
        self.assertEqual((key, reason), self._live(RESTART_BOARD))
        self.assertEqual(restarted._loot_target, ITEM_IN_ATTACK)


if __name__ == "__main__":
    unittest.main()
