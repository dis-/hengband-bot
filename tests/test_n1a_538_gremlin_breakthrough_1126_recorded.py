"""n1-a life-538 (2026-11-26 07:18:37, loop-detected): the latched グレムリン floor never read Recall.

The chain (Zombie warrior Lv30, HP 728/728, dungeon 12 29F, no quest, six Word of Recall
scrolls carried, one process):

 * turn 1334738: ``emergency:teleport`` on this floor sets ``_emergency_return_active`` (a
   floor-scoped flag: the routine return looting stays off for the visit).  The player rested to
   full and explored for some 4,500 game turns.
 * 1338145-1339309: the 100-attack window on the グレムリン (race 153, MULTIPLY) did not bring the
   count down; the breeder latch (``_breeder_breakthrough_floor``) named the floor
   (jsonlog/breeder-floor.json: ``breakthrough`` true, 100 actions).
 * 1339312-1339651: ``_breeder_breakthrough_key`` skipped its Recall because the flag stood and no
   town return was active, so the up-stairs walk went through the swarm: from (23,60) '1' into a
   グレムリン every action, killed one each time, the cell refilled, until the loop detector stopped
   the character.

The rule (owner 2026-11-02 「20ターンで数が減らせないなら逃走を選択する」, the window 100 since
2026-11-09): the latch is the decided give-up, and a floor without a quest leaves by Recall.  The
emergency flag says nothing about that exit.

Recorded: tests/fixtures/n1a-538-gremlin-breakthrough-1126.json.gz
(tests/extract_n1a_538_gremlin_breakthrough_1126_fixture.py): the boards of the breakthrough's
first and last decisions as the snapshot ring kept them, their recorded rows, the floor's emergency
row and the capture's policy-state flags.

DECLARED CONSTRUCTED: policy checkpoints are not boards, so the fresh policy gets the capture's
policy-state values (policy-state.json ``_breeder_breakthrough_floor`` [12,29,0],
``_emergency_return_active`` true, ``_returning_to_town`` false, ``_fundraising_mode`` null) and
the startup skill exchange constant of tests/test_breeder_refill_escape_recorded.py.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-538-gremlin-breakthrough-1126.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
RECALL = "breeder-breakthrough:recall"


class GremlinBreakthroughRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _decide(self, index: int, *, emergency: bool = True):
        with TemporaryDirectory() as directory:
            policy = _policy(Path(directory), self.monrace)
            policy._crossarea_fundraising_enforced = True
            policy._skill_exp_cache = (0, 0, 19, None)  # DECLARED CONSTRUCTED (module note)
            _decoded, boards = _consume_response_sequence(
                [CASE["boards"][index]], policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=Path(directory) / "knowledge.jsonl",
            )
            board = boards[-1]
            flags = CASE["policy_state_flags"]
            policy._breeder_breakthrough_floor = tuple(flags["_breeder_breakthrough_floor"])
            policy._emergency_return_active = emergency and flags["_emergency_return_active"]
            policy._returning_to_town = flags["_returning_to_town"]
            policy._fundraising_mode = flags["_fundraising_mode"]
            key = policy._breeder_breakthrough_key(board, policy._strategic_hostiles(board))
            return board, policy, key, policy.last_reason

    def test_recorded_rows_are_the_incident(self):
        first, last = CASE["recorded"]
        self.assertEqual((first["turn"], first["key"], first["reason"]),
                         (1339312, "1", "breeder-breakthrough:seek-upstairs"))
        self.assertEqual((last["turn"], last["key"], last["reason"], last["position"]),
                         (1339651, "1", "breeder-breakthrough:clear-escape-path", {"y": 23, "x": 60}))
        emergency = CASE["emergency_row"]
        self.assertEqual((emergency["reason"], emergency["floor"]["dungeon_id"], emergency["floor"]["level"]),
                         ("emergency:teleport", 12, 29))
        self.assertTrue(CASE["breeder_floor"]["state"]["breakthrough"])
        self.assertEqual(CASE["breeder_floor"]["state"]["engagement"][2], 100)
        self.assertTrue(CASE["policy_state_flags"]["_emergency_return_active"])
        self.assertFalse(CASE["policy_state_flags"]["_returning_to_town"])

    def test_latched_floor_reads_recall_after_an_earlier_emergency_escape(self):
        for index, recorded in enumerate(CASE["recorded"]):
            with self.subTest(turn=recorded["turn"]):
                board, policy, key, reason = self._decide(index)
                self.assertEqual(board.turn, recorded["turn"])
                self.assertEqual(board.floor_key, (12, 29, 0))
                self.assertIsNone(policy._active_quest_id(board))
                self.assertFalse(board.player.blind or board.player.confused)
                self.assertIsNotNone(policy._find_recall_scroll(board))
                self.assertTrue(policy._can_read_scrolls(board))
                self.assertEqual(reason, RECALL)
                self.assertTrue(key.startswith("r"), key)
                self.assertNotEqual(reason, recorded["reason"])

    def test_without_the_flag_the_board_already_read_recall(self):
        # The flag was the only gate: the same board with it down read Recall before the fix too.
        _board, _policy_, key, reason = self._decide(1, emergency=False)
        self.assertEqual(reason, RECALL)
        self.assertTrue(key.startswith("r"), key)


if __name__ == "__main__":
    unittest.main()
